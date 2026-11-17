import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select

from app.growth.billing import lifecycle
from app.growth.contracts import Keyed
from app.growth.models import Checkout, Subscription
from app.growth.runtime import find


class Simulate(Keyed):
    kind: Literal["renewal", "payment_failed", "cancel", "refund"]
    amount_minor: int | None = Field(default=None, ge=1, le=100000000)


def install_billing(app, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.post("/checkouts/{checkout_id}/simulate-lifecycle")
    async def simulate(
        checkout_id: str,
        data: Simulate,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await require(session, request, who, {"owner"})
        org_id = who["organization"].id
        checkout = await find(session, Checkout, org_id, checkout_id)
        if not checkout.provider_ref.startswith("sandbox:"):
            raise HTTPException(403, "cannot_simulate_real_checkout")
        if checkout.status != "paid":
            raise HTTPException(409, "paid_checkout_required")
        subscription = await session.scalar(
            select(Subscription).where(
                Subscription.organization_id == org_id, Subscription.checkout_id == checkout.id
            )
        )
        checkout.payment_ref = "sandbox-payment:" + checkout.id
        if subscription and not subscription.provider_ref:
            subscription.provider_ref = "sandbox-subscription:" + checkout.id
        if data.kind == "refund":
            kind = "charge.refunded"
            body = {
                "id": "sandbox-charge:" + checkout.id,
                "payment_intent": checkout.payment_ref,
                "amount_refunded": data.amount_minor or checkout.amount_minor,
                "currency": checkout.currency,
            }
        else:
            if not subscription:
                raise HTTPException(409, "recurring_subscription_required")
            if data.kind == "cancel":
                kind = "customer.subscription.deleted"
                body = {
                    "id": subscription.provider_ref,
                    "status": "canceled",
                    "current_period_end": subscription.current_period_end,
                }
            else:
                kind = "invoice.paid" if data.kind == "renewal" else "invoice.payment_failed"
                body = {
                    "id": "sandbox-invoice:" + data.idempotency_key,
                    "subscription": subscription.provider_ref,
                    "amount_paid": data.amount_minor or subscription.amount_minor,
                    "currency": subscription.currency,
                    "billing_reason": "subscription_cycle",
                    "period_end": max(subscription.current_period_end, time.time()) + 30 * 86400,
                }
        await session.flush()
        return await lifecycle(
            session,
            org_id,
            {
                "id": "sandbox:" + data.idempotency_key,
                "created": time.time(),
                "type": kind,
                "livemode": False,
                "data": {"object": body},
            },
            provider="sandbox",
        )

    app.include_router(router)
