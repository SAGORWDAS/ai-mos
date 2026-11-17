"""Evidence-backed campaign attribution; currencies and test/live outcomes never mix."""

import time
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import select, update

from app.growth.contracts import Keyed
from app.growth.models import AttributionTouch, Campaign, Draft, Expense, Lead, Payment, Task
from app.growth.runtime import find, public, record
from app.models import Organization


class TouchInput(Keyed):
    lead_id: str
    campaign_id: str
    channel: Literal["email", "website", "social", "paid_ad", "referral", "other"]
    evidence: str = Field(min_length=10, max_length=1000)
    occurred_at: float = Field(gt=0)
    simulated: bool = True


async def record_message_touch(session, message, campaign_id=None):
    if message.status not in {"sent", "delivered"} or message.direction != "outbound":
        return
    org_id = message.organization_id
    if not campaign_id and message.draft_id:
        draft = await find(session, Draft, org_id, message.draft_id)
        if draft.task_id:
            task = await find(session, Task, org_id, draft.task_id)
            campaign_id = task.input.get("campaign_id")
    if not campaign_id:
        return
    campaign = await find(session, Campaign, org_id, campaign_id)
    lead = await find(session, Lead, org_id, message.lead_id)
    if campaign.brand_id != lead.brand_id:
        raise HTTPException(422, "campaign_brand_mismatch")
    identity = "message:" + message.id
    if not await session.scalar(
        select(AttributionTouch.id).where(
            AttributionTouch.organization_id == org_id, AttributionTouch.idempotency_key == identity
        )
    ):
        session.add(
            AttributionTouch(
                organization_id=org_id,
                lead_id=lead.id,
                campaign_id=campaign.id,
                channel="email",
                evidence="Outbound provider receipt: " + message.id,
                occurred_at=time.time(),
                simulated=message.simulated,
                idempotency_key=identity,
            )
        )


def allocate(payments, touches, model, window_days):
    """Allocate each payment in integer minor units. Return unassigned value explicitly."""
    buckets = defaultdict(lambda: {"payments": 0, "amount_minor": 0})
    for payment in payments:
        eligible = sorted(
            (
                t
                for t in touches
                if t.lead_id == payment.lead_id
                and t.simulated == payment.simulated
                and payment.created_at - window_days * 86400 <= t.occurred_at <= payment.created_at
            ),
            key=lambda t: (t.occurred_at, t.id),
        )
        if model == "first_touch":
            campaigns = [eligible[0].campaign_id] if eligible else [None]
        elif model == "last_touch":
            campaigns = [eligible[-1].campaign_id] if eligible else [None]
        else:
            campaigns = sorted({t.campaign_id for t in eligible}) or [None]
        sign = -1 if payment.amount_minor < 0 else 1
        share, remainder = divmod(abs(payment.amount_minor), len(campaigns))
        for index, campaign_id in enumerate(campaigns):
            bucket = buckets[(campaign_id, payment.currency, payment.simulated)]
            bucket["payments"] += 1
            bucket["amount_minor"] += sign * (share + (1 if index < remainder else 0))
    return [
        {"campaign_id": campaign, "currency": currency, "simulated": simulated, **values}
        for (campaign, currency, simulated), values in buckets.items()
    ]


def install_attribution(app, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.post("/attribution/touches", status_code=201)
    async def touch(data: TouchInput, request: Request, who=Depends(identity), session=Depends(db)):
        await require(session, request, who, {"owner", "admin", "member"})
        org_id = who["organization"].id
        # Serialize duplicate imports without losing the original evidence on replay.
        await session.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(emergency_stop=Organization.emergency_stop)
        )
        lead = await find(session, Lead, org_id, data.lead_id)
        campaign = await find(session, Campaign, org_id, data.campaign_id)
        if campaign.brand_id != lead.brand_id:
            raise HTTPException(422, "campaign_brand_mismatch")
        if data.occurred_at > time.time() + 60:
            raise HTTPException(422, "touch_cannot_be_in_future")
        prior = await session.scalar(
            select(AttributionTouch).where(
                AttributionTouch.organization_id == org_id,
                AttributionTouch.idempotency_key == data.idempotency_key,
            )
        )
        if prior:
            if any(getattr(prior, key) != value for key, value in data.model_dump().items()):
                raise HTTPException(409, "idempotency_key_payload_conflict")
            return public(prior)
        item = AttributionTouch(organization_id=org_id, **data.model_dump())
        session.add(item)
        await session.flush()
        await record(session, org_id, who["user"].id, "attribution.recorded", item.id)
        await session.commit()
        return public(item)

    @router.get("/attribution/report")
    async def report(
        model: Literal["first_touch", "last_touch", "linear"] = "last_touch",
        window_days: int = Query(default=90, ge=1, le=365),
        who=Depends(identity),
        session=Depends(db),
    ):
        org_id = who["organization"].id
        payments = (
            await session.scalars(
                select(Payment).where(
                    Payment.organization_id == org_id, Payment.status == "succeeded"
                )
            )
        ).all()
        touches = (
            await session.scalars(
                select(AttributionTouch).where(AttributionTouch.organization_id == org_id)
            )
        ).all()
        expenses = (
            await session.scalars(select(Expense).where(Expense.organization_id == org_id))
        ).all()
        from app.growth.measurement import complete_report

        measured = await complete_report(
            session, org_id, payments, touches, expenses, model, window_days
        )
        return {
            "model": model,
            "window_days": window_days,
            "revenue": allocate(payments, touches, model, window_days),
            **measured,
            "touches": len(touches),
            "note": "Recorded evidence, known model charges and recorded USD expenses only. "
            "Unknown charges remain held; missing costs are not estimated. Linear credit is equal "
            "per distinct campaign. Unassigned value stays visible. Currencies and test/live "
            "outcomes never mix. Ambiguous refunds stay unassigned. Attribution is not causation.",
        }

    app.include_router(router)
