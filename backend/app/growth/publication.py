"""Opt-in owned publishing. Private drafts never appear on unauthenticated routes."""

import hashlib
import html
import ipaddress
import secrets
import textwrap
import time
from pathlib import Path
from string import Template
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import Field
from sqlalchemy import func, select, update

from app.contracts import EmailInput
from app.growth.knowledge import guard_content
from app.growth.models import BrandChunk, Content, Lead, Message, Notification
from app.growth.runtime import find, record
from app.models import Brand, Organization
from app.tenancy import tenant_scope


class Enquiry(EmailInput):
    name: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=10, max_length=2000)
    request_reply: bool
    website: str = Field(default="", max_length=200)


def public_base(settings):
    """Canonical URLs come from trusted deployment config, never the request Host header."""
    value = settings.public_api_url.rstrip("/")
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        _ = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or host == "localhost"
        or host.endswith((".localhost", ".test", ".example", ".invalid", ".local"))
    ):
        return ""
    try:
        ipaddress.ip_address(host)
        return ""  # A production site's hostname belongs in deployment configuration.
    except ValueError:
        return value


def page(brand, item, settings):
    template = Template(
        (Path(__file__).parent / "templates/published.html").read_text(encoding="utf-8")
    )
    base = public_base(settings)
    canonical = f"{base}/v1/public/{item.organization_id}/{item.id}" if base else ""
    description = " ".join(item.body.split())[:160]
    return template.substitute(
        name=html.escape(brand.name),
        title=html.escape(item.title),
        page_title=html.escape(
            item.title
            if item.title.casefold() == brand.name.casefold()
            else f"{item.title} | {brand.name}"
        ),
        body=html.escape(item.body),
        id=item.id,
        description=html.escape(description),
        canonical=(
            f'<link rel="canonical" href="{html.escape(canonical)}">'
            f'<meta property="og:url" content="{html.escape(canonical)}">'
        )
        if canonical
        else "",
        robots="index, follow"
        if base and settings.public_indexing_enabled
        else "noindex, nofollow",
    )


def install_publication(app, db, identity, require, limiter, settings):
    router = APIRouter(prefix="/v1")

    async def published(session, org_id, content_id):
        await tenant_scope(session, organization_id=org_id)
        item = await session.scalar(
            select(Content).where(
                Content.organization_id == org_id,
                Content.id == content_id,
                Content.status == "published_local",
            )
        )
        if not item:
            raise HTTPException(404, "not_found")
        brand = await find(session, Brand, org_id, item.brand_id)
        try:
            await guard_content(session, brand, item.title, item.title, item.body, item.citations)
        except HTTPException:
            raise HTTPException(404, "publication_requires_review") from None
        return brand, item

    @router.get("/public/{org_id}/sitemap.xml")
    async def sitemap(
        org_id: str, page: int = Query(default=-1, ge=-1, le=49999), session=Depends(db)
    ):
        from xml.etree.ElementTree import Element, SubElement, tostring

        base = public_base(settings)
        if not base or not settings.public_indexing_enabled:
            raise HTTPException(404, "public_indexing_not_enabled")
        await tenant_scope(session, organization_id=org_id)
        count = await session.scalar(
            select(func.count())
            .select_from(Content)
            .where(Content.organization_id == org_id, Content.status == "published_local")
        )
        if page == -1 and count > 1000:
            root = Element("sitemapindex", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
            for number in range(min(50000, (count + 999) // 1000)):
                entry = SubElement(root, "sitemap")
                SubElement(
                    entry, "loc"
                ).text = f"{base}/v1/public/{org_id}/sitemap.xml?page={number}"
            return Response(
                tostring(root, encoding="utf-8", xml_declaration=True),
                media_type="application/xml",
                headers={"X-Robots-Tag": "noindex"},
            )
        items = (
            await session.scalars(
                select(Content)
                .where(Content.organization_id == org_id, Content.status == "published_local")
                .order_by(Content.id)
                .offset(max(0, page) * 1000)
                .limit(1000)
            )
        ).all()
        brands = {
            brand.id: brand
            for brand in (
                await session.scalars(
                    select(Brand).where(
                        Brand.organization_id == org_id,
                        Brand.id.in_({item.brand_id for item in items}),
                    )
                )
            ).all()
        }
        identifiers = list(
            {claim.get("brand_chunk_id") for item in items for claim in item.citations}
        )
        chunks = {}
        for offset in range(0, len(identifiers), 500):
            rows = (
                await session.scalars(
                    select(BrandChunk).where(
                        BrandChunk.organization_id == org_id,
                        BrandChunk.id.in_(identifiers[offset : offset + 500]),
                    )
                )
            ).all()
            chunks.update({chunk.id: chunk for chunk in rows})
        root = Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
        for item in items:
            try:
                brand = brands.get(item.brand_id)
                if not brand:
                    continue
                await guard_content(
                    session, brand, item.title, item.title, item.body, item.citations, chunks=chunks
                )
            except HTTPException:
                continue
            entry = SubElement(root, "url")
            SubElement(entry, "loc").text = f"{base}/v1/public/{org_id}/{item.id}"
        return Response(
            tostring(root, encoding="utf-8", xml_declaration=True),
            media_type="application/xml",
            headers={"X-Robots-Tag": "noindex"},
        )

    @router.get("/public/{org_id}/{content_id}", response_class=HTMLResponse)
    async def view(org_id: str, content_id: str, session=Depends(db)):
        brand, item = await published(session, org_id, content_id)
        return HTMLResponse(
            page(brand, item, settings),
            headers={
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
                "form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
                "Referrer-Policy": "same-origin",
                "X-Robots-Tag": "index, follow"
                if public_base(settings) and settings.public_indexing_enabled
                else "noindex, nofollow",
            },
        )

    @router.post("/public/{org_id}/{content_id}/enquire")
    async def enquire(org_id: str, content_id: str, request: Request, session=Depends(db)):
        brand, item = await published(session, org_id, content_id)
        address = request.client.host if request.client else "unknown"
        if not await limiter.allow(address + ":public:" + org_id):
            raise HTTPException(429, "enquiry_rate_limited")
        from urllib.parse import parse_qs

        from pydantic import ValidationError

        try:
            raw = (
                await request.json()
                if "application/json" in request.headers.get("content-type", "")
                else {
                    key: values[0]
                    for key, values in parse_qs((await request.body()).decode()).items()
                }
            )
            data = Enquiry.model_validate(raw)
        except (ValueError, UnicodeError, ValidationError):
            raise HTTPException(422, "invalid_enquiry") from None
        if not data.request_reply:
            raise HTTPException(422, "reply_request_required")
        if not data.website:
            await session.execute(
                update(Organization)
                .where(Organization.id == org_id)
                .values(emergency_stop=Organization.emergency_stop)
            )
            if await session.scalar(
                select(Organization.emergency_stop).where(Organization.id == org_id)
            ):
                raise HTTPException(423, "workspace_paused")
            lead = await session.scalar(
                select(Lead).where(Lead.organization_id == org_id, Lead.email == data.email)
            )
            if not lead:
                lead = Lead(
                    organization_id=org_id,
                    brand_id=brand.id,
                    name=data.name,
                    email=data.email,
                    source="Owned website enquiry: " + item.id,
                    lawful_basis="not_established",
                    basis_evidence="Requested an enquiry reply; "
                    "marketing permission not established. See private inbox message.",
                )
                session.add(lead)
                await session.flush()
            enquiry_key = (
                "website:"
                + hashlib.sha256(
                    (
                        content_id + data.email + data.message + str(int(time.time() // 86400))
                    ).encode()
                ).hexdigest()
            )
            previous = await session.scalar(
                select(Message.id).where(
                    Message.organization_id == org_id, Message.idempotency_key == enquiry_key
                )
            )
            if not previous:
                session.add(
                    Message(
                        organization_id=org_id,
                        lead_id=lead.id,
                        direction="inbound",
                        subject="Website enquiry: " + item.title[:170],
                        body=data.message,
                        status="received",
                        provider_id="website:" + secrets.token_hex(12),
                        classification={
                            "label": "needs_human",
                            "confidence": 0,
                            "escalate": True,
                            "source": "owned_website",
                        },
                        idempotency_key=enquiry_key,
                        simulated=False,
                    )
                )
                session.add(
                    Notification(
                        organization_id=org_id,
                        title=("Website enquiry: " + data.message)[:200],
                        subject_id=lead.id,
                    )
                )
            await session.commit()
        if "application/json" in request.headers.get("content-type", ""):
            return {"status": "received"}
        return HTMLResponse(
            '<!doctype html><html lang="en"><title>Enquiry received</title>'
            "<main><h1>Enquiry received</h1><p>The business can review your request "
            "in its workspace.</p></main></html>"
        )

    @router.post("/content/{content_id}/unpublish")
    async def unpublish(
        content_id: str, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner", "admin"})
        item = await find(session, Content, who["organization"].id, content_id)
        item.status = "draft"
        await record(
            session, who["organization"].id, who["user"].id, "content.unpublished", item.id
        )
        await session.commit()
        return {"status": "unpublished"}

    @router.get("/brands/{brand_id}/creative.svg")
    async def creative(brand_id: str, who=Depends(identity), session=Depends(db)):
        brand = await find(session, Brand, who["organization"].id, brand_id)
        name = html.escape(brand.name)
        claim = brand.approved_claims[0] if brand.approved_claims else brand.positioning
        # Code-native brand card, never represented as a generated photograph.
        lines = textwrap.wrap(claim, width=65)[:3]
        text = "".join(f'<tspan x="70" dy="48">{html.escape(line)}</tspan>' for line in lines)
        title = "".join(
            f'<tspan x="70" dy="58">{html.escape(line)}</tspan>'
            for line in textwrap.wrap(brand.name, width=32)[:3]
        )
        svg = Template((Path(__file__).parent / "templates/card.svg").read_text()).substitute(
            name=name, title=title, text=text
        )
        return Response(
            svg,
            media_type="image/svg+xml",
            headers={
                "Content-Disposition": 'attachment; filename="brand-card.svg"',
                "Content-Security-Policy": "default-src 'none'; sandbox",
            },
        )

    app.include_router(router)
