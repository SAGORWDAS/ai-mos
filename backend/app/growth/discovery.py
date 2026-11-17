import asyncio
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import func, select

from app.growth.connections import active
from app.growth.contracts import Keyed
from app.growth.ingestion import fetch_text
from app.growth.models import Command, Expense, Lead, Plan, ProviderEvent, Suppression, Task
from app.growth.providers import ProviderError
from app.growth.runtime import find
from app.models import Brand


class Search(Keyed):
    brand_id: str
    query: str = Field(min_length=3, max_length=300)
    connected_provider: bool = False


class Enrich(Keyed):
    brand_id: str
    url: str = Field(min_length=10, max_length=2000)
    company: str = Field(default="", max_length=200)
    refresh: bool = False


async def enrich(session, task):
    from app.growth.runtime import Runtime

    await find(session, Brand, task.organization_id, task.input["brand_id"])
    prior = (
        await session.scalars(
            select(Task)
            .where(
                Task.organization_id == task.organization_id,
                Task.type == "prospect_enrich",
                Task.status == "succeeded",
                Task.input["url"].as_string() == task.input["url"],
                Task.input["brand_id"].as_string() == task.input["brand_id"],
                func.coalesce(Task.output["observed_at"].as_float(), Task.created_at)
                >= time.time() - 90 * 86400,
            )
            .order_by(Task.created_at.desc())
            .limit(1)
        )
    ).all()
    if not task.input.get("refresh"):
        for row in prior:
            if (
                row.input.get("url") == task.input["url"]
                and row.input.get("brand_id") == task.input["brand_id"]
            ):
                current_ids = []
                for lead_id in row.output.get("created_lead_ids", []):
                    contact = await session.scalar(
                        select(Lead).where(
                            Lead.organization_id == task.organization_id,
                            Lead.id == lead_id,
                            Lead.brand_id == task.input["brand_id"],
                            Lead.status != "suppressed",
                        )
                    )
                    if contact:
                        current_ids.append(contact.id)
                return {
                    **row.output,
                    "created_lead_ids": current_ids,
                    "cached": True,
                    "cached_task_id": row.id,
                    "observed_at": row.output.get("observed_at", row.created_at),
                }
    await session.commit()
    content, url = await fetch_text(task.input["url"])
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    emails = sorted(
        {
            value.lower().rstrip(".,;")
            for value in re.findall(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", content, re.I)
            if value.lower().rsplit("@", 1)[-1].rstrip(".,;") == host
        }
    )[:5]
    await Runtime.checkpoint(session, task.organization_id, task.id, task.created_by, task.attempt)
    created = []
    for address in emails:
        if await session.scalar(
            select(Suppression.id).where(
                Suppression.organization_id == task.organization_id, Suppression.address == address
            )
        ):
            continue
        lead = await session.scalar(
            select(Lead).where(Lead.organization_id == task.organization_id, Lead.email == address)
        )
        if not lead:
            lead = Lead(
                organization_id=task.organization_id,
                brand_id=task.input["brand_id"],
                name=(task.input["company"] or host)[:120],
                company=task.input["company"] or host,
                domain=host,
                email=address,
                source=("Observed public business contact: " + url)[:500],
                source_confidence=75,
                source_ref=url,
                source_observed_at=time.time(),
                lawful_basis="not_established",
                basis_evidence="Observed on "
                + url[:1800]
                + ". Publication does not establish marketing permission.",
            )
            session.add(lead)
            await session.flush()
            created.append(lead.id)
    await session.commit()
    return {
        "observed_at": time.time(),
        "cached": False,
        "source_url": url,
        "observed_addresses": emails,
        "created_lead_ids": created,
        "contactability": "not_established",
        "note": "Only addresses supplied by this business domain are imported. "
        "No address is guessed.",
    }


async def discover(session, settings, task, transport=None):
    from app.growth.runtime import Runtime

    await Runtime.checkpoint(session, task.organization_id, task.id, task.created_by, task.attempt)
    await find(session, Brand, task.organization_id, task.input["brand_id"])
    if not task.input["connected_provider"]:
        return {
            "simulated": True,
            "results": [],
            "note": "Sandbox performs no external lookup. "
            "Import supplied contacts or enable a verified search connection.",
        }
    connection = await active(session, settings, task.organization_id, "brave")
    if not connection:
        raise HTTPException(409, "enabled_search_provider_required")
    cache_key = hashlib.sha256(
        json.dumps(
            [connection["id"], connection["version"], " ".join(task.input["query"].split())]
        ).encode()
    ).hexdigest()
    cached = await session.scalar(
        select(ProviderEvent)
        .where(
            ProviderEvent.organization_id == task.organization_id,
            ProviderEvent.provider == "brave",
            ProviderEvent.kind == "search.completed",
            ProviderEvent.object_ref == cache_key,
            ProviderEvent.created_at >= time.time() - 86400,
        )
        .order_by(ProviderEvent.created_at.desc())
        .limit(1)
    )
    if cached:
        return {
            **cached.evidence["output"],
            "cached": True,
            "cache_receipt_id": cached.id,
            "source_search_cost_micros": cached.evidence["output"].get("search_cost_micros"),
            "search_cost_micros": 0,
            "cost_basis": "cache_hit_zero_new_provider_cost",
        }
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    attempts = await session.scalar(
        select(func.count())
        .select_from(ProviderEvent)
        .where(
            ProviderEvent.organization_id == task.organization_id,
            ProviderEvent.provider == "brave",
            ProviderEvent.kind == "search.attempt",
            ProviderEvent.created_at >= start,
        )
    )
    if attempts >= 100:
        raise HTTPException(429, "daily_search_limit_100")
    session.add(
        ProviderEvent(
            organization_id=task.organization_id,
            provider="brave",
            event_id=task.id + ":" + str(task.attempt),
            kind="search.attempt",
            object_ref=task.id,
            occurred_at=time.time(),
            simulated=False,
            evidence={"query": task.input["query"], "cost": "provider_billed_outside_model_ledger"},
        )
    )
    await session.commit()
    try:
        async with (
            asyncio.timeout(25),
            httpx.AsyncClient(
                timeout=20, transport=transport, follow_redirects=False, trust_env=False
            ) as client,
        ):
            async with client.stream(
                "GET",
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": task.input["query"], "count": 20},
                headers={"X-Subscription-Token": connection["credentials"]["api_key"]},
            ) as response:
                response.raise_for_status()
                body = bytearray()
                async for block in response.aiter_bytes():
                    body.extend(block)
                    if len(body) > 2_000_000:
                        raise ValueError("search_response_too_large")
                results = json.loads(body).get("web", {}).get("results", [])
        observed_at = time.time()
        quoted_price = connection["credentials"].get("search_price_micros", "")
        price = int(quoted_price) if quoted_price else None
        safe = []
        for result in results[:20]:
            url = str(result.get("url", ""))[:2000]
            if urlsplit(url).scheme != "https":
                continue
            safe.append(
                {
                    "title": str(result.get("title", ""))[:300],
                    "url": url,
                    "description": str(result.get("description", ""))[:1000],
                    "source": "Brave web search",
                    "retrieved_at": observed_at,
                    "contactability": "not_established",
                }
            )
        if price is not None and safe:
            for index, row in enumerate(safe):
                row["allocated_search_cost_micros"] = price // len(safe) + (
                    index < price % len(safe)
                )
        output = {
            "simulated": False,
            "cached": False,
            "retrieved_at": observed_at,
            "search_cost_micros": price,
            "cost_basis": "owner_configured_USD_contract_accrual"
            if price is not None
            else "unknown_provider_cost",
            "results": safe,
            "note": "Research suggestions only; contactability is not established. "
            "No email address is inferred.",
        }
        receipt = ProviderEvent(
            organization_id=task.organization_id,
            provider="brave",
            event_id=task.id + ":" + str(task.attempt) + ":completed",
            kind="search.completed",
            object_ref=cache_key,
            occurred_at=observed_at,
            simulated=False,
            evidence={"output": output, "price_version": connection["version"]},
        )
        session.add(receipt)
        if price:
            campaign_id = None
            if task.plan_id:
                campaign_id = await session.scalar(
                    select(Command.parsed)
                    .join(Plan, Plan.command_id == Command.id)
                    .where(
                        Plan.organization_id == task.organization_id,
                        Plan.id == task.plan_id,
                        Command.organization_id == task.organization_id,
                    )
                )
                campaign_id = (campaign_id or {}).get("campaign_id")
            session.add(
                Expense(
                    organization_id=task.organization_id,
                    campaign_id=campaign_id,
                    category="prospect_data",
                    amount_micros=price,
                    simulated=False,
                    evidence="Configured Brave search price accrual; receipt " + receipt.event_id,
                )
            )
        await session.commit()
        await Runtime.checkpoint(
            session, task.organization_id, task.id, task.created_by, task.attempt
        )
        return output
    except (httpx.HTTPError, TimeoutError, ValueError, TypeError, AttributeError):
        raise ProviderError("search_provider_failed") from None


def install_discovery(app, runtime, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.post("/prospects/enrich", status_code=202)
    async def enrichment(
        data: Enrich, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner", "admin", "member"})
        await find(session, Brand, who["organization"].id, data.brand_id)
        task = await runtime.enqueue(
            session,
            who["organization"].id,
            who["user"].id,
            "prospect_enrich",
            "AGT-04",
            data.idempotency_key,
            data.model_dump(exclude={"idempotency_key"}),
        )
        return {"id": task.id, "status": task.status}

    @router.post("/prospects/search", status_code=202)
    async def search(data: Search, request: Request, who=Depends(identity), session=Depends(db)):
        await require(session, request, who, {"owner", "admin", "member"})
        await find(session, Brand, who["organization"].id, data.brand_id)
        task = await runtime.enqueue(
            session,
            who["organization"].id,
            who["user"].id,
            "prospect_search",
            "AGT-04",
            data.idempotency_key,
            data.model_dump(exclude={"idempotency_key"}),
        )
        return {"id": task.id, "status": task.status}

    app.include_router(router)
    return {"search": search, "enrich": enrichment}
