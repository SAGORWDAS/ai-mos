import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from app.contracts import Input
from app.growth.ingestion import fetch_text, isolated_pdf_text
from app.growth.knowledge import index_document
from app.growth.runtime import find, public, record
from app.models import Brand


class Website(Input):
    url: str = Field(min_length=10, max_length=2000)
    title: str = Field(min_length=1, max_length=200)


def install_knowledge(app, db, identity, require):
    router = APIRouter(prefix="/v1/brands")

    async def allowed(session, request, who, brand_id):
        await require(session, request, who, {"owner", "admin", "member"})
        return await find(session, Brand, who["organization"].id, brand_id)

    async def save(session, who, brand, title, content, source):
        item = await index_document(
            session, who["organization"].id, brand.id, title, content, source
        )
        await record(session, who["organization"].id, who["user"].id, "document.ingested", item.id)
        await session.commit()
        return public(item)

    @router.post("/{brand_id}/ingest-pdf", status_code=201)
    async def pdf(
        brand_id: str,
        request: Request,
        title: str = "Uploaded PDF",
        who=Depends(identity),
        session=Depends(db),
    ):
        brand = await allowed(session, request, who, brand_id)
        if not 1 <= len(title) <= 200:
            raise HTTPException(422, "document_title_limit")
        content = await request.body()
        if len(content) > 5_000_000:
            raise HTTPException(413, "pdf_limit_5mb")
        extracted = await asyncio.to_thread(isolated_pdf_text, content)
        return await save(session, who, brand, title, extracted, "uploaded-pdf")

    @router.post("/{brand_id}/ingest-website", status_code=201)
    async def website(
        brand_id: str, data: Website, request: Request, who=Depends(identity), session=Depends(db)
    ):
        brand = await allowed(session, request, who, brand_id)
        await session.commit()
        content, source = await fetch_text(data.url)
        await allowed(session, request, who, brand_id)
        return await save(session, who, brand, data.title, content, source)

    app.include_router(router)
