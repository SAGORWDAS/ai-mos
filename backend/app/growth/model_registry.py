"""Tenant model selections, provider catalog evidence and immutable per-attempt snapshots."""

import asyncio
import hashlib
import json
import re
import time
from decimal import Decimal, InvalidOperation
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.growth.models import Integration, ModelRegistry
from app.tenancy import tenant_scope

FIELDS = {"chat": "model_id", "embedding": "embedding_model_id", "image": "image_model_id"}
PATHS = {
    "chat": "/api/v1/chat/completions",
    "embedding": "/api/v1/embeddings",
    "image": "/api/v1/images",
}
CATALOG_URL = "https://openrouter.ai/api/v1/models"
MAX_AGE = 7 * 86400


def configured(settings, org_id, operation, connection):
    credentials = (
        connection["credentials"]
        if connection
        else {
            "model_id": settings.model_id,
            "embedding_model_id": settings.embedding_model_id,
            "image_model_id": settings.image_model_id,
            "api_key": settings.openrouter_api_key,
        }
    )
    model_id = credentials.get(FIELDS[operation], "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}", model_id):
        return None
    if "/" not in model_id and model_id.startswith(("sk-", "ghp_", "github_pat_")):
        return None
    source_id = connection["id"] if connection else None
    version = connection["version"] if connection else 0
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                org_id,
                operation,
                model_id,
                source_id,
                version,
                hashlib.sha256(credentials.get("api_key", "").encode()).hexdigest(),
            ]
        ).encode()
    ).hexdigest()
    return {
        "operation": operation,
        "model_id": model_id,
        "source_connection_id": source_id,
        "source_connection_version": version,
        "source_fingerprint": fingerprint,
    }


def eligible(entry):
    return bool(
        entry
        and entry.status == "verified"
        and entry.verified_at
        and 0 <= time.time() - entry.verified_at <= MAX_AGE
        and entry.price_snapshot
    )


async def resolve_entry(session, settings, org_id, operation, connection):
    await tenant_scope(session, org_id)
    source = configured(settings, org_id, operation, connection)
    if not source:
        return None
    insert = sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert
    await session.execute(
        insert(ModelRegistry)
        .values(
            id=str(uuid4()),
            created_at=time.time(),
            organization_id=org_id,
            status="unverified",
            price_snapshot={},
            verified_at=None,
            verification_error="catalog_verification_required",
            **source,
        )
        .on_conflict_do_nothing(index_elements=["organization_id", "operation", "model_id"])
    )
    entry = await session.scalar(
        select(ModelRegistry).where(
            ModelRegistry.organization_id == org_id,
            ModelRegistry.operation == operation,
            ModelRegistry.model_id == source["model_id"],
        )
    )
    if entry.source_fingerprint != source["source_fingerprint"]:
        for name, value in source.items():
            setattr(entry, name, value)
        entry.status, entry.price_snapshot, entry.verified_at = "unverified", {}, None
        entry.last_checked_at = 0
        entry.verification_error = "model_connection_changed"
    await session.flush()
    return entry


async def catalog_candidates(client, credentials):
    """Metadata reads only. A valid account key is not itself proof of model pricing."""

    async def fetch(operation, model_id):
        result = {
            "operation": operation,
            "model_id": model_id,
            "status": "unverified",
            "price_snapshot": {},
            "verified_at": None,
            "verification_error": "",
        }
        try:
            async with (
                asyncio.timeout(20),
                client.stream(
                    "GET",
                    CATALOG_URL,
                    params={
                        "q": model_id,
                        "endpoints": PATHS[operation],
                        "output_modalities": "all",
                    },
                    headers={"Authorization": "Bearer " + credentials["api_key"]},
                ) as response,
            ):
                response.raise_for_status()
                raw = bytearray()
                async for block in response.aiter_bytes():
                    raw.extend(block)
                    if len(raw) > 2_000_000:
                        raise ValueError()
                data = json.loads(raw)
            models = data.get("data") if isinstance(data, dict) else None
            if not isinstance(models, list):
                result["verification_error"] = "catalog_unavailable"
                return result
            model = next(
                (row for row in models if isinstance(row, dict) and row.get("id") == model_id), None
            )
            if not model:
                result["verification_error"] = "catalog_model_missing"
                return result
            price = model.get("pricing")
            required = {"prompt", "completion"} if operation == "chat" else {"prompt"}
            if operation == "image":
                required = (
                    {"image"} if isinstance(price, dict) and "image" in price else {"request"}
                )
            if not isinstance(price, dict) or not required.issubset(price):
                result["verification_error"] = "catalog_pricing_missing"
                return result
            if len(json.dumps(price, allow_nan=False)) > 20000:
                raise ValueError()
            for name in required | ({"request", "image", "prompt", "completion"} & price.keys()):
                value = Decimal(str(price[name]))
                if not value.is_finite() or value < 0 or value > 1_000_000:
                    raise ValueError()
            now = time.time()
            result.update(
                status="verified",
                verified_at=now,
                price_snapshot={
                    "provider": "openrouter",
                    "currency": "USD",
                    "rates": price,
                    "catalog_url": CATALOG_URL,
                    "endpoint": PATHS[operation],
                    "fetched_at": now,
                },
            )
        except (httpx.HTTPError, TimeoutError):
            result["verification_error"] = "catalog_unavailable"
        except (ValueError, TypeError, KeyError, InvalidOperation):
            result["verification_error"] = "catalog_pricing_invalid"
        return result

    selected = [(operation, credentials.get(field, "")) for operation, field in FIELDS.items()]
    return await asyncio.gather(
        *(
            fetch(operation, model_id)
            for operation, model_id in selected
            if model_id and len(model_id) <= 200
        )
    )


async def record_catalog(session, settings, org_id, connection, candidates):
    for candidate in candidates:
        operation = candidate["operation"]
        source = configured(settings, org_id, operation, connection)
        if not source or candidate["model_id"] != source["model_id"]:
            continue
        entry = await resolve_entry(session, settings, org_id, operation, connection)
        error = candidate["verification_error"]
        entry.last_checked_at = time.time()
        entry.verification_error = error
        if error != "catalog_unavailable" or not eligible(entry):
            entry.status = candidate["status"]
            entry.price_snapshot = candidate["price_snapshot"]
            entry.verified_at = candidate["verified_at"]
    await session.flush()


def snapshot(entry):
    if not entry:
        return {}
    return {
        "pricing": entry.price_snapshot,
        "verified_at": entry.verified_at,
        "source_connection_id": entry.source_connection_id,
        "source_connection_version": entry.source_connection_version,
    }


def install_model_registry(app, runtime, settings, db, identity, require):
    from app.growth.connections import unseal
    from app.growth.runtime import public, record

    router = APIRouter(prefix="/v1/model-registry")

    async def lookup(session, org_id):
        return await session.scalar(
            select(Integration).where(
                Integration.organization_id == org_id, Integration.provider == "openrouter"
            )
        )

    @router.get("")
    async def listing(who=Depends(identity), session=Depends(db)):
        org_id = who["organization"].id
        integration = await lookup(session, org_id)
        saved_credentials = unseal(settings, integration) if integration else {}
        connection = None
        if integration and integration.status == "verified":
            connection = {
                "id": integration.id,
                "version": integration.version,
                "credentials": saved_credentials,
            }
        rows = (
            await session.scalars(
                select(ModelRegistry)
                .where(ModelRegistry.organization_id == org_id)
                .order_by(ModelRegistry.created_at.desc(), ModelRegistry.id)
                .limit(101)
            )
        ).all()
        models = []
        for row in rows[:100]:
            source = configured(settings, org_id, row.operation, connection)
            current = bool(source and row.source_fingerprint == source["source_fingerprint"])
            models.append(
                {**public(row), "current": current, "eligible": current and eligible(row)}
            )
        return {
            "models": models,
            "truncated": len(rows) > 100,
            "freshness_days": 7,
            "request_allowance_micros": int(
                saved_credentials.get("max_cost_micros") or settings.model_max_cost_micros
            ),
            "verification_required": settings.app_env == "production"
            or not settings.allow_unverified_models,
            "note": "Catalog identity/pricing verification is separate from model quality. "
            "Advertised rates are snapshots, not guaranteed final charges. "
            "Actual usage costs and unknown-charge holds remain in the ledger.",
        }

    @router.post("/refresh")
    async def refresh(request: Request, who=Depends(identity), session=Depends(db)):
        await require(session, request, who, {"owner"})
        org_id = who["organization"].id
        item = await lookup(session, org_id)
        if not item or item.status != "verified":
            raise HTTPException(409, "verify_openrouter_account_first")
        connection = {"id": item.id, "version": item.version, "credentials": unseal(settings, item)}
        await session.commit()
        async with httpx.AsyncClient(
            timeout=20, transport=runtime.gateway.transport, follow_redirects=False, trust_env=False
        ) as client:
            candidates = await catalog_candidates(client, connection["credentials"])
        await require(session, request, who, {"owner"})
        await session.refresh(item)
        if item.version != connection["version"] or item.status != "verified":
            raise HTTPException(409, "connection_changed_during_catalog_verification")
        await record_catalog(session, settings, org_id, connection, candidates)
        await record(
            session,
            org_id,
            who["user"].id,
            "model.catalog_refreshed",
            item.id,
            trace=request.state.trace_id,
        )
        await session.commit()
        return await listing(who, session)

    app.include_router(router)
