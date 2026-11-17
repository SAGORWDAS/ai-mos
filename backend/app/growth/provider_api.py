from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, model_validator
from sqlalchemy import select

from app.contracts import Input
from app.growth.billing import lifecycle, ref
from app.growth.connections import active, unseal
from app.growth.contracts import InboxSync
from app.growth.effects import settle_payment
from app.growth.inbox import import_page
from app.growth.models import Checkout, Integration
from app.growth.providers import GoogleProvider, ProviderError, StripeProvider
from app.growth.runtime import record
from app.tenancy import tenant_scope


class AvailabilityInput(Input):
    starts_at: float
    ends_at: float
    execution_mode: str = Field(default="sandbox", pattern="^(sandbox|live)$")

    @model_validator(mode="after")
    def bounded_window(self):
        if not 900 <= self.ends_at - self.starts_at <= 86400:
            raise ValueError("Availability window must be 15 minutes to one day")
        return self


def install_provider_routes(app, runtime, settings, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.post("/calendar/availability")
    async def availability(
        data: AvailabilityInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        from app.growth.models import Meeting

        org_id = who["organization"].id
        conflict = await session.scalar(
            select(Meeting.id).where(
                Meeting.organization_id == org_id,
                Meeting.status.in_(["booked", "queued"]),
                Meeting.starts_at < data.ends_at,
                Meeting.ends_at > data.starts_at,
            )
        )
        available = not bool(conflict)
        if data.execution_mode == "live":
            connection = await active(session, settings, org_id, "calendar")
            if not connection:
                raise HTTPException(409, "enabled_calendar_required")
            credentials = connection["credentials"]
            provider = GoogleProvider(
                credentials.get("access_token", ""),
                calendar_id=credentials.get("calendar_id") or "primary",
                transport=runtime.delivery.transport,
            )
            try:
                if credentials.get("refresh_token"):
                    await provider.refresh(
                        credentials.get("client_id", ""),
                        credentials.get("client_secret", ""),
                        credentials["refresh_token"],
                    )
                available = (
                    await provider.availability(data.starts_at, data.ends_at, use_cache=True)
                    and available
                )
            except ProviderError as error:
                raise HTTPException(502, error.code) from None
        return {
            "available": available,
            "simulated": data.execution_mode == "sandbox",
            "cache_max_age_seconds": 45,
            "note": "Booking rechecks availability; external calendar races remain possible.",
        }

    @router.post("/inbox/sync")
    async def sync_inbox(
        data: InboxSync, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner", "admin", "member"})
        org_id = who["organization"].id
        connection = await active(session, settings, org_id, "gmail")
        if not connection:
            raise HTTPException(409, "enabled_gmail_required")
        credentials = connection["credentials"]
        provider = GoogleProvider(
            credentials.get("access_token", ""), transport=runtime.delivery.transport
        )
        await session.commit()
        try:
            if credentials.get("refresh_token"):
                await provider.refresh(
                    credentials.get("client_id", ""),
                    credentials.get("client_secret", ""),
                    credentials["refresh_token"],
                )
            page = await provider.inbox_page(data.cursor)
        except ProviderError as error:
            raise HTTPException(502, error.code) from None
        await require(session, request, who, {"owner", "admin", "member"})
        current = await active(session, settings, org_id, "gmail")
        if not current or (current["id"], current["version"]) != (
            connection["id"],
            connection["version"],
        ):
            raise HTTPException(409, "connection_changed_or_disconnected")
        counts = await import_page(
            session,
            org_id,
            connection["account_ref"],
            page["messages"],
            auto_draft=current["auto_draft_replies"],
            actor_id=who["user"].id,
        )
        await record(
            session,
            org_id,
            who["user"].id,
            "inbox.synced",
            connection["id"],
            trace=request.state.trace_id,
        )
        await session.commit()
        return {**counts, "next_cursor": page["next_cursor"]}

    @router.post("/effects/{effect_id}/reconcile")
    async def reconcile(
        effect_id: str, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner"}, writes=False)
        await session.commit()
        try:
            return await runtime.delivery.reconcile(
                who["organization"].id, effect_id, who["user"].id
            )
        except ProviderError as error:
            raise HTTPException(502, error.code) from None

    @router.post("/webhooks/stripe/{org_id}")
    async def stripe_webhook(org_id: str, request: Request, session=Depends(db)):
        await tenant_scope(session, organization_id=org_id)
        integration = await session.scalar(
            select(Integration).where(
                Integration.organization_id == org_id,
                Integration.provider == "stripe",
                Integration.status == "verified",
            )
        )
        if not integration:
            raise HTTPException(401, "webhook_provider_not_verified")
        credentials = unseal(settings, integration)
        provider = StripeProvider(
            credentials.get("secret_key", ""), credentials.get("webhook_secret", "")
        )
        try:
            event = provider.verify_event(
                await request.body(), request.headers.get("stripe-signature")
            )
        except ProviderError:
            raise HTTPException(401, "invalid_webhook_signature") from None
        if event.get("type") not in {
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
        }:
            return await lifecycle(session, org_id, event)
        try:
            receipt = event["data"]["object"]
            if receipt.get("payment_status") != "paid":
                return {"status": "ignored"}
            reference = receipt["id"]
            amount, currency = receipt["amount_total"], receipt["currency"].upper()
        except (KeyError, TypeError, AttributeError):
            raise HTTPException(422, "invalid_payment_event") from None
        checkout = await session.scalar(
            select(Checkout).where(
                Checkout.organization_id == org_id, Checkout.provider_ref == reference
            )
        )
        if not checkout:
            metadata = receipt.get("metadata", {})
            if metadata.get("ai_mos_organization_id") != org_id:
                raise HTTPException(404, "unknown_checkout")
            checkout = await session.scalar(
                select(Checkout).where(
                    Checkout.organization_id == org_id,
                    Checkout.id == metadata.get("ai_mos_checkout_id"),
                )
            )
            if not checkout or not checkout.provider_ref.startswith("pending:"):
                raise HTTPException(404, "unknown_checkout")
            if checkout.amount_minor != amount or checkout.currency != currency:
                raise HTTPException(422, "payment_amount_mismatch")
            checkout.provider_ref = reference
            await session.flush()
        checkout.payment_ref = ref(receipt.get("payment_intent"))
        checkout.subscription_ref = ref(receipt.get("subscription"))
        await session.flush()
        return await settle_payment(
            session,
            {
                "event_id": event["id"],
                "checkout_ref": reference,
                "type": "payment.succeeded",
                "amount_minor": amount,
                "currency": currency,
            },
            simulated=not bool(event.get("livemode")),
            provider_verified=True,
        )

    app.include_router(router)
    return {"inbox_sync": sync_inbox, "availability": availability}
