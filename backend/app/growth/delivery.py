"""Durable provider dispatch; ambiguous effects are reconciled, never blindly retried."""

import asyncio
import time

from fastapi import HTTPException
from sqlalchemy import select, text, update

from app.growth.connections import active, unseal
from app.growth.effects import draft_payload, payload_hash
from app.growth.knowledge import guard_draft
from app.growth.models import (
    Approval,
    Draft,
    Effect,
    Integration,
    Lead,
    Meeting,
    Message,
    Suppression,
)
from app.growth.providers import GoogleProvider, ProviderError
from app.growth.runtime import find, record
from app.models import Brand, Membership, Organization
from app.tenancy import tenant_scope


class Dispatcher:
    def __init__(self, factory, settings):
        self.factory, self.settings = factory, settings
        self.transport = (
            None  # Dependency injection for contract tests; never supplied by API input.
        )

    async def tick(self):
        async with self.factory() as session:
            if session.bind.dialect.name == "postgresql":
                picked = (
                    (await session.execute(text("SELECT * FROM claim_next_effect()")))
                    .mappings()
                    .first()
                )
                await session.commit()
                if not picked:
                    return False
                await tenant_scope(session, picked["org_id"], picked["actor_id"])
                item = await session.get(Effect, picked["effect_id"])
            else:
                expired = await session.scalar(
                    select(Effect)
                    .where(
                        Effect.status == "dispatching",
                        Effect.dispatch_started_at < time.time() - 90,
                    )
                    .limit(1)
                )
                if expired:
                    approval = await find(
                        session, Approval, expired.organization_id, expired.approval_id
                    )
                    expired_id, expired_org, expired_actor = (
                        expired.id,
                        expired.organization_id,
                        approval.decided_by,
                    )
                    await session.commit()
                    await self.finish(
                        expired_org,
                        expired_id,
                        expired_actor,
                        "uncertain",
                        {"error": "worker_receipt_missing"},
                    )
                    return True
                item = await session.scalar(
                    select(Effect)
                    .join(Organization, Organization.id == Effect.organization_id)
                    .where(Effect.status == "queued", Organization.emergency_stop.is_(False))
                    .order_by(Effect.created_at)
                    .limit(1)
                )
                if not item:
                    return False
                claimed = await session.execute(
                    update(Effect)
                    .where(Effect.id == item.id, Effect.status == "queued")
                    .values(status="dispatching", dispatch_started_at=time.time())
                )
                await session.commit()
                if not claimed.rowcount:
                    return True
                await session.refresh(item)
            item_id, org_id = item.id, item.organization_id
            approval = await find(session, Approval, org_id, item.approval_id)
            actor_id = approval.decided_by
            if item.status == "uncertain":
                await session.commit()
                await self.finish(
                    org_id, item_id, actor_id, "uncertain", {"error": "worker_receipt_missing"}
                )
                return True
            try:
                connection, provider, arguments = await self.prepare(session, item, approval)
                await session.commit()
            except (HTTPException, ProviderError) as error:
                code = str(error.detail) if isinstance(error, HTTPException) else error.code
                await session.rollback()
                await self.finish(org_id, item_id, actor_id, "failed", {"error": code})
                return True
        try:
            if item.action == "send_email":
                receipt = await provider.send_email(**arguments)
            elif item.action == "book_meeting":
                receipt = await provider.book(**arguments)
            elif item.action == "send_bulk_campaign":
                receipt = await provider.send_batch(**arguments)
            else:
                raise ProviderError("unregistered_live_action")
            await self.finish(org_id, item_id, actor_id, "succeeded", receipt)
        except ProviderError as error:
            await self.finish(
                org_id,
                item_id,
                actor_id,
                "uncertain" if error.uncertain else "failed",
                {"error": error.code},
            )
        except asyncio.CancelledError:
            await asyncio.shield(
                self.finish(org_id, item_id, actor_id, "uncertain", {"error": "worker_interrupted"})
            )
            raise
        except Exception:
            await self.finish(
                org_id, item_id, actor_id, "uncertain", {"error": "provider_outcome_unknown"}
            )
        return True

    async def prepare(self, session, effect, approval):
        org_id = effect.organization_id
        await session.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(emergency_stop=Organization.emergency_stop)
        )
        stopped = await session.scalar(
            select(Organization.emergency_stop).where(Organization.id == org_id)
        )
        if stopped:
            raise ProviderError("emergency_stop")
        approver_role = await session.scalar(
            select(Membership.role).where(
                Membership.organization_id == org_id, Membership.user_id == approval.decided_by
            )
        )
        allowed = {"owner"} if effect.action == "send_bulk_campaign" else {"owner", "admin"}
        if approver_role not in allowed:
            raise ProviderError("approver_access_revoked")
        if (
            approval.expires_at <= time.time()
            or payload_hash(effect.payload) != approval.payload_hash
        ):
            raise ProviderError("approval_expired_or_changed")
        if effect.action == "send_bulk_campaign":
            from app.growth.esp import prepare_bulk

            return await prepare_bulk(session, self.settings, effect, approval, self.transport)
        provider_name = "gmail" if effect.action == "send_email" else "calendar"
        connection = await active(session, self.settings, org_id, provider_name)
        if (
            not connection
            or connection["id"] != effect.result.get("_connection_id")
            or connection["version"] != effect.result.get("_connection_version")
        ):
            raise ProviderError("connection_changed_or_disconnected")
        credentials = connection["credentials"]
        provider = GoogleProvider(
            credentials.get("access_token", ""),
            credentials.get("sender", ""),
            credentials.get("calendar_id") or "primary",
            self.transport,
        )
        if credentials.get("refresh_token"):
            await provider.refresh(
                credentials.get("client_id", ""),
                credentials.get("client_secret", ""),
                credentials["refresh_token"],
            )
        lead = await find(session, Lead, org_id, effect.payload["lead_id"])
        blocked = await session.scalar(
            select(Suppression.id).where(
                Suppression.organization_id == org_id, Suppression.address == lead.email
            )
        )
        if blocked or lead.status == "suppressed":
            raise ProviderError("suppressed_recipient")
        if effect.action == "send_email":
            if lead.lawful_basis == "not_established":
                raise ProviderError("contactability_not_established")
            draft = await find(session, Draft, org_id, effect.payload["draft_id"])
            if payload_hash(draft_payload(draft)) != approval.payload_hash:
                raise ProviderError("approval_payload_changed")
            brand = await find(session, Brand, org_id, lead.brand_id)
            await guard_draft(session, brand, lead, draft.subject, draft.body, draft.claims)
            arguments = {
                "recipient": lead.email,
                "subject": draft.subject,
                "body": draft.body,
                "idempotency_key": effect.organization_id + ":" + effect.id,
            }
        elif effect.action == "book_meeting":
            meeting = await find(session, Meeting, org_id, effect.payload["meeting_id"])
            if meeting.starts_at <= time.time():
                raise ProviderError("meeting_in_past")
            arguments = {
                "title": meeting.title,
                "starts_at": meeting.starts_at,
                "ends_at": meeting.ends_at,
                "attendee": lead.email,
                "idempotency_key": effect.organization_id + ":" + effect.id,
            }
        else:
            raise ProviderError("unregistered_live_action")
        return connection, provider, arguments

    async def finish(self, org_id, effect_id, actor_id, state, receipt):
        async with self.factory() as session:
            item = await find(session, Effect, org_id, effect_id)
            item.status = state
            item.result = {
                **item.result,
                "status": state,
                "dispatch_status": state,
                "receipt": receipt,
            }
            if item.action == "send_email":
                message = await session.scalar(
                    select(Message).where(
                        Message.organization_id == org_id, Message.approval_id == item.approval_id
                    )
                )
                if message:
                    message.status = "sent" if state == "succeeded" else state
                    message.provider_id = receipt.get("provider_id", "")
                    draft = await find(session, Draft, org_id, message.draft_id)
                    draft.status = message.status
                    lead = await find(session, Lead, org_id, message.lead_id)
                    if state == "succeeded" and lead.status not in {
                        "suppressed",
                        "replied",
                        "meeting_set",
                        "converted",
                    }:
                        lead.status = "contacted"
            elif item.action == "book_meeting":
                meeting = await find(session, Meeting, org_id, item.payload["meeting_id"])
                meeting.status = "booked" if state == "succeeded" else state
                meeting.provider_id = receipt.get("provider_id", "")
                lead = await find(session, Lead, org_id, meeting.lead_id)
                if state == "succeeded" and lead.status not in {"suppressed", "converted"}:
                    lead.status = "meeting_set"
            elif item.action == "send_bulk_campaign":
                from app.growth.esp import finish_bulk

                await finish_bulk(session, item, state, receipt)
            await record(
                session, org_id, actor_id, "provider.effect_result", item.id, decision=state
            )
            await session.commit()

    async def reconcile(self, org_id, effect_id, actor_id):
        async with self.factory() as session:
            effect = await find(session, Effect, org_id, effect_id)
            if effect.status != "uncertain":
                raise HTTPException(409, "effect_not_uncertain")
            integration = await find(session, Integration, org_id, effect.result["_connection_id"])
            if integration.status != "verified":
                raise HTTPException(409, "verified_provider_required")
            if integration.account_ref != effect.result.get("_account_ref"):
                raise HTTPException(409, "provider_account_changed")
            credentials = unseal(self.settings, integration)
            if effect.action == "send_bulk_campaign":
                return {"status": "provider_console_review_required", "retry_send_allowed": False}
            provider = GoogleProvider(
                credentials.get("access_token", ""),
                credentials.get("sender", ""),
                credentials.get("calendar_id") or "primary",
                self.transport,
            )
            if credentials.get("refresh_token"):
                await provider.refresh(
                    credentials.get("client_id", ""),
                    credentials.get("client_secret", ""),
                    credentials["refresh_token"],
                )
            if effect.action == "send_email":
                receipt = await provider.reconcile_email(effect.organization_id + ":" + effect.id)
                if receipt["status"] == "found":
                    await session.commit()
                    await self.finish(org_id, effect_id, actor_id, "succeeded", receipt)
                    return {"status": "reconciled", "retry_send_allowed": False}
                return receipt
            if effect.action == "book_meeting":
                receipt = await provider.reconcile_booking(effect.organization_id + ":" + effect.id)
                if receipt["status"] == "found":
                    await session.commit()
                    await self.finish(org_id, effect_id, actor_id, "succeeded", receipt)
                    return {"status": "reconciled", "retry_send_allowed": False}
                return receipt
            raise HTTPException(409, "reconciliation_not_supported")
