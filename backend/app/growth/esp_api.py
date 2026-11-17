from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update

from app.growth.connections import unseal
from app.growth.effects import suppress
from app.growth.esp import verify_svix
from app.growth.models import Integration, Lead, Message, ProviderEvent
from app.growth.providers import ProviderError
from app.models import Organization
from app.tenancy import tenant_scope


def install_esp(app, settings, db):
    router = APIRouter(prefix="/v1")

    @router.post("/webhooks/resend/{org_id}")
    async def event(org_id: str, request: Request, session=Depends(db)):
        await tenant_scope(session, organization_id=org_id)
        integration = await session.scalar(
            select(Integration).where(
                Integration.organization_id == org_id,
                Integration.provider == "resend",
                Integration.status == "verified",
            )
        )
        if not integration:
            raise HTTPException(401, "verified_provider_required")
        credentials = unseal(settings, integration)
        try:
            event_id, data = verify_svix(
                credentials.get("webhook_secret", ""), await request.body(), request.headers
            )
        except ProviderError:
            raise HTTPException(401, "invalid_webhook_signature") from None
        kind = data.get("type")
        if kind not in {"email.sent", "email.delivered", "email.bounced", "email.complained"}:
            return {"status": "ignored"}
        await session.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(emergency_stop=Organization.emergency_stop)
        )
        if await session.scalar(
            select(ProviderEvent.id).where(
                ProviderEvent.organization_id == org_id,
                ProviderEvent.provider == "resend",
                ProviderEvent.event_id == event_id,
            )
        ):
            return {"status": "duplicate"}
        provider_id = data.get("data", {}).get("email_id")
        message = (
            await session.scalar(
                select(Message).where(
                    Message.organization_id == org_id,
                    Message.provider_id == provider_id,
                    Message.direction == "outbound",
                    Message.simulated.is_(False),
                )
            )
            if isinstance(provider_id, str)
            else None
        )
        if not message:
            raise HTTPException(409, "message_receipt_not_received_retry_later")
        lead = await session.get(Lead, message.lead_id)
        if kind in {"email.bounced", "email.complained"}:
            await suppress(
                session, org_id, lead.email, "bounce" if kind == "email.bounced" else "complaint"
            )
            message.status = "bounced" if kind == "email.bounced" else "complained"
        elif kind == "email.delivered" and message.status not in {"bounced", "complained"}:
            message.status = "delivered"
        # An acceptance event never proves inbox delivery or overrides a terminal receipt.
        session.add(
            ProviderEvent(
                organization_id=org_id,
                provider="resend",
                event_id=event_id,
                kind=kind,
                object_ref=provider_id,
                occurred_at=float(request.headers["svix-timestamp"]),
                simulated=False,
                evidence={"message_id": message.id, "status": message.status},
            )
        )
        await session.commit()
        return {"status": "processed"}

    app.include_router(router)
