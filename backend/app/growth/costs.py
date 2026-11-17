import time
from decimal import ROUND_CEILING, Decimal, InvalidOperation

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import delete, func, select, update

from app.contracts import Input
from app.growth.connections import active
from app.growth.models import Budget, ModelCache, ModelUsage
from app.growth.runtime import find, public, record


class Reconcile(Input):
    cost_micros: int | None = Field(default=None, ge=0, le=1000000000)
    evidence: str = Field(default="", max_length=1000)


def install_costs(app, runtime, settings, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.get("/model-cache")
    async def cache_status(who=Depends(identity), session=Depends(db)):
        org_id = who["organization"].id
        hits = await session.scalar(
            select(func.count())
            .select_from(ModelUsage)
            .where(ModelUsage.organization_id == org_id, ModelUsage.status == "cache_hit")
        )
        avoided = await session.scalar(
            select(func.count())
            .select_from(ModelUsage)
            .where(
                ModelUsage.organization_id == org_id,
                ModelUsage.status == "cache_hit",
                ModelUsage.simulated.is_(False),
            )
        )
        responses = await session.scalar(
            select(func.count())
            .select_from(ModelCache)
            .where(ModelCache.organization_id == org_id, ModelCache.expires_at > time.time())
        )
        return {
            "validated_responses": responses,
            "cache_hits": hits,
            "provider_calls_avoided": avoided,
            "expiry_hours": settings.model_cache_seconds / 3600,
        }

    @router.post("/model-cache/clear")
    async def clear_cache(request: Request, who=Depends(identity), session=Depends(db)):
        await require(session, request, who, {"owner"})
        result = await session.execute(
            delete(ModelCache).where(ModelCache.organization_id == who["organization"].id)
        )
        await record(session, who["organization"].id, who["user"].id, "model.cache_cleared")
        await session.commit()
        return {"deleted": result.rowcount}

    @router.post("/model-usage/{usage_id}/reconcile")
    async def reconcile(
        usage_id: str, data: Reconcile, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner"})
        org_id = who["organization"].id
        usage = await find(session, ModelUsage, org_id, usage_id)
        if usage.settled:
            return {"status": "already_settled", "usage": public(usage)}
        if usage.status == "reserved" or not usage.reservation_period:
            raise HTTPException(409, "attempt_still_running_or_legacy_record")
        cost = data.cost_micros
        evidence = data.evidence
        if cost is None:
            connection = await active(session, settings, org_id, "openrouter")
            if not connection or not usage.provider_ref:
                raise HTTPException(409, "provider_reference_required_or_supply_receipt_cost")
            await session.commit()
            try:
                async with httpx.AsyncClient(
                    timeout=20, transport=runtime.gateway.transport
                ) as client:
                    response = await client.get(
                        "https://openrouter.ai/api/v1/generation",
                        params={"id": usage.provider_ref},
                        headers={"Authorization": "Bearer " + connection["credentials"]["api_key"]},
                    )
                    response.raise_for_status()
                    result = response.json()["data"]
                    price = Decimal(str(result["total_cost"]))
                    if result.get("id") != usage.provider_ref or not price.is_finite() or price < 0:
                        raise ValueError()
                    cost = int((price * 1000000).to_integral_value(rounding=ROUND_CEILING))
                    evidence = "OpenRouter generation receipt: " + usage.provider_ref
            except (httpx.HTTPError, ValueError, KeyError, TypeError, InvalidOperation):
                raise HTTPException(502, "cost_receipt_not_available") from None
            await require(session, request, who, {"owner"})
            await session.refresh(usage)
            if usage.settled:
                return {"status": "already_settled", "usage": public(usage)}
        elif len(evidence.strip()) < 10:
            raise HTTPException(422, "receipt_evidence_required")
        budget = await session.scalar(
            select(Budget).where(
                Budget.organization_id == org_id, Budget.period == usage.reservation_period
            )
        )
        if not budget or budget.reserved_micros < usage.reserved_micros:
            raise HTTPException(409, "reservation_requires_operator_review")
        await session.execute(
            update(Budget)
            .where(Budget.id == budget.id)
            .values(
                reserved_micros=Budget.reserved_micros - usage.reserved_micros,
                spent_micros=Budget.spent_micros + cost,
            )
        )
        usage.cost_micros, usage.settled, usage.reconciliation_evidence = cost, True, evidence
        await record(session, org_id, who["user"].id, "model.cost_reconciled", usage.id)
        await session.commit()
        return {"status": "settled", "usage": public(usage)}

    app.include_router(router)
