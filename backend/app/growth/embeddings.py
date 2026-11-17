import hashlib
import json
import math
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select, text

from app.growth.connections import active
from app.growth.contracts import Keyed
from app.growth.models import BrandChunk, BrandDocument
from app.growth.runtime import find
from app.models import Brand


class Embed(Keyed):
    connected_provider: bool = False


class Semantic(Embed):
    query: str = Field(min_length=3, max_length=500)


def unit_vector(values):
    if (
        not isinstance(values, list)
        or not 1 <= len(values) <= 8192
        or any(
            type(value) not in {int, float} or abs(value) > 1e10 or not math.isfinite(value)
            for value in values
        )
    ):
        raise ValueError("invalid_embedding_vector")
    length = math.sqrt(sum(value * value for value in values))
    if not math.isfinite(length) or length == 0:
        raise ValueError("invalid_embedding_norm")
    return [value / length for value in values]


def sandbox_vector(content):
    vector = [0.0] * 32
    for token in re.findall(r"\w+", content.lower()):
        digest = hashlib.sha256(token.encode()).digest()
        vector[digest[0] % 32] += 1 if digest[1] % 2 else -1
    return unit_vector(vector)


async def selected_model(session, settings, org_id, connected):
    if not connected:
        return "sandbox/hash-embedding-v1"
    connection = await active(session, settings, org_id, "openrouter")
    model = (
        connection["credentials"].get("embedding_model_id", "")
        if connection
        else settings.embedding_model_id
        if settings.provider_mode == "openrouter"
        else ""
    )
    if not model:
        raise HTTPException(409, "embedding_model_not_configured")
    return model


async def vector_column(session):
    return session.bind.dialect.name == "postgresql" and await session.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='brand_chunks' "
            "AND column_name='embedding_vector')"
        )
    )


async def execute_embedding(runtime, session, task):
    mode = task.input["connected_provider"]
    model = await selected_model(session, runtime.settings, task.organization_id, mode)
    if model != task.input["embedding_model"]:
        raise ValueError("embedding_model_changed_reindex_required")
    if task.type == "embed_document":
        document = await find(
            session, BrandDocument, task.organization_id, task.input["document_id"]
        )
        chunks = (
            await session.scalars(
                select(BrandChunk)
                .where(
                    BrandChunk.organization_id == task.organization_id,
                    BrandChunk.brand_id == document.brand_id,
                    BrandChunk.document_id == document.id,
                    BrandChunk.id.in_(task.input["chunk_ids"]),
                )
                .order_by(BrandChunk.ordinal)
            )
        ).all()
        pending = [
            chunk for chunk in chunks if chunk.embedding_model != model or not chunk.embedding
        ]
        if pending:
            inputs = [chunk.content for chunk in pending]
            await session.commit()
            result = await runtime.gateway.generate(
                task,
                inputs,
                {"vectors": [sandbox_vector(value) for value in inputs]} if not mode else {},
                operation="embedding",
                sandbox_only=not mode,
            )
            await runtime.checkpoint(
                session, task.organization_id, task.id, task.created_by, task.attempt
            )
            if result["model_id"] != model or len(result.get("vectors", [])) != len(pending):
                raise ValueError("embedding_response_mismatch")
            vectors = [unit_vector(vector) for vector in result["vectors"]]
            if len({len(vector) for vector in vectors}) != 1:
                raise ValueError("embedding_dimensions_mismatch")
            await runtime.gateway.remember(session, task, result)
            native = await vector_column(session)
            for chunk, vector in zip(pending, vectors, strict=True):
                chunk.embedding, chunk.embedding_model = vector, model
                if native:
                    await session.execute(
                        text(
                            "UPDATE brand_chunks SET embedding_vector=CAST(:vector AS vector) "
                            "WHERE organization_id=:org AND id=:id"
                        ),
                        {"vector": json.dumps(vector), "org": task.organization_id, "id": chunk.id},
                    )
        all_chunks = (
            await session.scalars(
                select(BrandChunk).where(
                    BrandChunk.organization_id == task.organization_id,
                    BrandChunk.document_id == document.id,
                )
            )
        ).all()
        document.status = (
            "embedded"
            if all(chunk.embedding_model == model and chunk.embedding for chunk in all_chunks)
            else "partially_embedded"
        )
        await session.commit()
        return {
            "document_id": document.id,
            "indexed_chunks": len(pending),
            "model_id": model,
            "simulated": not mode,
            "document_status": document.status,
        }
    chunks = (
        await session.scalars(
            select(BrandChunk).where(
                BrandChunk.organization_id == task.organization_id,
                BrandChunk.brand_id == task.input["brand_id"],
                BrandChunk.embedding_model == model,
            )
        )
    ).all()
    if not chunks:
        return {
            "passages": [],
            "note": "Index documents with this embedding model first.",
            "simulated": not mode,
        }
    await session.commit()
    result = await runtime.gateway.generate(
        task,
        [task.input["query"]],
        {"vectors": [sandbox_vector(task.input["query"])]} if not mode else {},
        operation="embedding",
        sandbox_only=not mode,
    )
    await runtime.checkpoint(session, task.organization_id, task.id, task.created_by, task.attempt)
    if result["model_id"] != model or len(result.get("vectors", [])) != 1:
        raise ValueError("embedding_response_mismatch")
    query = unit_vector(result["vectors"][0])
    await runtime.gateway.remember(session, task, result)
    if await vector_column(session):
        passages = [
            dict(row)
            for row in (
                await session.execute(
                    text(
                        "SELECT id AS chunk_id,document_id,content,"
                        "1-(embedding_vector <=> CAST(:vector AS vector)) AS score "
                        "FROM brand_chunks WHERE organization_id=:org AND brand_id=:brand "
                        "AND embedding_model=:model AND embedding_vector IS NOT NULL "
                        "AND vector_dims(embedding_vector)=:dimensions "
                        "ORDER BY embedding_vector <=> CAST(:vector AS vector) LIMIT 5"
                    ),
                    {
                        "vector": json.dumps(query),
                        "org": task.organization_id,
                        "brand": task.input["brand_id"],
                        "model": model,
                        "dimensions": len(query),
                    },
                )
            )
            .mappings()
            .all()
        ]
        method = "pgvector_cosine"
    else:
        passages = sorted(
            [
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "content": chunk.content,
                    "score": sum(a * b for a, b in zip(query, chunk.embedding, strict=True)),
                }
                for chunk in chunks
                if len(chunk.embedding) == len(query)
            ],
            key=lambda row: row["score"],
            reverse=True,
        )[:5]
        method = "exact_cosine"
    await session.commit()
    return {
        "passages": passages,
        "method": method,
        "model_id": model,
        "simulated": not mode,
        "note": "Hash-vector simulation is not semantic AI."
        if not mode
        else "Embedding similarity with sources; supplied facts still require approval.",
    }


def install_embeddings(app, runtime, settings, db, identity, require):
    router = APIRouter(prefix="/v1/brands")

    @router.post("/{brand_id}/documents/{document_id}/embed", status_code=202)
    async def embed(
        brand_id: str,
        document_id: str,
        data: Embed,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await require(session, request, who, {"owner", "admin", "member"})
        await find(session, Brand, who["organization"].id, brand_id)
        document = await find(session, BrandDocument, who["organization"].id, document_id)
        if document.brand_id != brand_id:
            raise HTTPException(404, "not_found")
        model = await selected_model(
            session, settings, who["organization"].id, data.connected_provider
        )
        chunks = (
            await session.scalars(
                select(BrandChunk)
                .where(
                    BrandChunk.organization_id == who["organization"].id,
                    BrandChunk.document_id == document_id,
                )
                .order_by(BrandChunk.ordinal)
            )
        ).all()
        tasks = []
        for offset in range(0, len(chunks), 32):
            payload = {
                "brand_id": brand_id,
                "document_id": document_id,
                "chunk_ids": [chunk.id for chunk in chunks[offset : offset + 32]],
                "embedding_model": model,
                "connected_provider": data.connected_provider,
            }
            key = (
                "embed:"
                + hashlib.sha256((data.idempotency_key + ":" + str(offset)).encode()).hexdigest()
            )
            task = await runtime.enqueue(
                session,
                who["organization"].id,
                who["user"].id,
                "embed_document",
                "AGT-02",
                key,
                payload,
            )
            tasks.append(task.id)
        return {"task_ids": tasks, "chunks": len(chunks), "model_id": model}

    @router.post("/{brand_id}/semantic-search", status_code=202)
    async def search(
        brand_id: str, data: Semantic, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner", "admin", "member"})
        await find(session, Brand, who["organization"].id, brand_id)
        model = await selected_model(
            session, settings, who["organization"].id, data.connected_provider
        )
        task = await runtime.enqueue(
            session,
            who["organization"].id,
            who["user"].id,
            "semantic_search",
            "AGT-02",
            data.idempotency_key,
            {
                "brand_id": brand_id,
                "query": data.query,
                "connected_provider": data.connected_provider,
                "embedding_model": model,
            },
        )
        return {"id": task.id, "status": task.status}

    app.include_router(router)
