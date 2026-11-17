import base64
import hashlib
import hmac
import json
import time

import httpx
from sqlalchemy import select

from app.growth.connections import active
from app.growth.effects import draft_payload, payload_hash
from app.growth.knowledge import guard_draft
from app.growth.models import Campaign, Draft, Lead, Message, Suppression
from app.growth.providers import ProviderError, require_secret
from app.growth.runtime import find
from app.models import Brand


class ResendProvider:
    def __init__(self, key, sender, transport=None):
        self.key, self.sender, self.transport = key, sender, transport

    async def send_batch(self, emails, idempotency_key):
        require_secret(self.key)
        if not 1 <= len(emails) <= 20:
            raise ProviderError("batch_size_limit")
        try:
            async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
                response = await client.post(
                    "https://api.resend.com/emails/batch",
                    headers={
                        "Authorization": "Bearer " + self.key,
                        "Idempotency-Key": idempotency_key,
                    },
                    json=[
                        {
                            "from": self.sender,
                            "to": [email["recipient"]],
                            "subject": email["subject"],
                            "text": email["body"],
                        }
                        for email in emails
                    ],
                )
        except httpx.TransportError:
            raise ProviderError("bulk_receipt_unknown", uncertain=True) from None
        if response.status_code >= 400:
            raise ProviderError("bulk_provider_rejected", uncertain=response.status_code >= 500)
        try:
            receipts = response.json()["data"]
            ids = [row["id"] for row in receipts]
            if (
                len(ids) != len(emails)
                or len(set(ids)) != len(ids)
                or any(not isinstance(value, str) or not 1 <= len(value) <= 200 for value in ids)
            ):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise ProviderError("bulk_receipt_incomplete", uncertain=True) from None
        return {"provider_ids": ids, "status": "sent"}


def verify_svix(secret, body, headers):
    try:
        require_secret(secret)
        key = base64.b64decode(secret.removeprefix("whsec_"), validate=True)
        timestamp = headers.get("svix-timestamp", "")
        message_id = headers.get("svix-id", "")
        if not key or not 1 <= len(message_id) <= 200 or abs(time.time() - int(timestamp)) > 300:
            raise ValueError()
        expected = base64.b64encode(
            hmac.new(
                key, (message_id + "." + timestamp + ".").encode() + body, hashlib.sha256
            ).digest()
        ).decode()
        signatures = [
            entry.split(",", 1)
            for entry in headers.get("svix-signature", "").split()
            if "," in entry
        ]
        if not any(
            version == "v1" and hmac.compare_digest(expected, value)
            for version, value in signatures
        ):
            raise ValueError()
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError()
        return message_id, data
    except (ValueError, TypeError, ProviderError):
        raise ProviderError("invalid_webhook_signature") from None


async def prepare_bulk(session, settings, effect, approval, transport):
    org_id = effect.organization_id
    connection = await active(session, settings, org_id, "resend")
    if (
        not connection
        or connection["id"] != effect.result.get("_connection_id")
        or connection["version"] != effect.result.get("_connection_version")
    ):
        raise ProviderError("connection_changed_or_disconnected")
    campaign = await find(session, Campaign, org_id, approval.subject_id)
    if campaign.status == "paused":
        raise ProviderError("campaign_paused")
    emails = []
    for frozen in effect.payload["drafts"]:
        draft = await find(session, Draft, org_id, frozen["draft_id"])
        if payload_hash(draft_payload(draft)) != payload_hash(frozen):
            raise ProviderError("approval_payload_changed")
        lead = await find(session, Lead, org_id, draft.lead_id)
        blocked = await session.scalar(
            select(Suppression.id).where(
                Suppression.organization_id == org_id, Suppression.address == lead.email
            )
        )
        if blocked or lead.status == "suppressed":
            raise ProviderError("suppressed_recipient")
        if lead.lawful_basis != "consent":
            raise ProviderError("bulk_requires_recorded_opt_in")
        brand = await find(session, Brand, org_id, lead.brand_id)
        await guard_draft(session, brand, lead, draft.subject, draft.body, draft.claims)
        emails.append({"recipient": lead.email, "subject": draft.subject, "body": draft.body})
    credentials = connection["credentials"]
    return (
        connection,
        ResendProvider(credentials["api_key"], credentials["sender"], transport),
        {"emails": emails, "idempotency_key": org_id + ":" + effect.id},
    )


async def finish_bulk(session, effect, state, receipt):
    org_id = effect.organization_id
    ids = receipt.get("provider_ids", [])
    for index, frozen in enumerate(effect.payload["drafts"]):
        message = await session.scalar(
            select(Message).where(
                Message.organization_id == org_id,
                Message.approval_id == effect.approval_id,
                Message.draft_id == frozen["draft_id"],
            )
        )
        if message:
            message.status = "sent" if state == "succeeded" else state
            if state == "succeeded":
                message.provider_id = ids[index]
                from app.growth.attribution import record_message_touch

                await record_message_touch(session, message, effect.payload["campaign_id"])
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
    campaign = await find(session, Campaign, org_id, effect.payload["campaign_id"])
    campaign.status = "completed" if state == "succeeded" else state
