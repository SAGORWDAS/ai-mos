"""Import plain text from known contacts; messages never become tool instructions."""

import base64
import hashlib
from email.utils import parseaddr

from sqlalchemy import select, update

from app.growth.automation import dispatch
from app.growth.effects import suppress
from app.growth.knowledge import classify
from app.growth.models import Enrollment, Lead, Message


def plain_text(part, depth=0):
    if depth > 10 or part.get("filename"):
        return ""
    if part.get("mimeType") in {"text/plain", "text/html"}:
        encoded = part.get("body", {}).get("data", "")
        try:
            decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode(
                "utf-8", "replace"
            )
            if part.get("mimeType") == "text/html":
                from app.growth.ingestion import html_text

                return html_text(decoded)
            return decoded
        except (ValueError, TypeError):
            return ""
    children = part.get("parts", [])[:20]
    if part.get("mimeType") == "multipart/alternative":
        plain = next((child for child in children if child.get("mimeType") == "text/plain"), None)
        if plain:
            return plain_text(plain, depth + 1)
    return "\n".join(plain_text(child, depth + 1) for child in children)


async def import_page(session, org_id, account, messages):
    counts = {"imported": 0, "duplicates": 0, "unknown_contacts": 0, "unsupported": 0}
    for raw in messages:
        payload = raw.get("payload", {})
        headers = {
            item.get("name", "").lower(): item.get("value", "")
            for item in payload.get("headers", [])
        }
        address = parseaddr(headers.get("from", ""))[1].strip().lower()
        body = plain_text(payload).strip()
        if not raw.get("id") or not address or not body or len(body) > 20000:
            counts["unsupported"] += 1
            continue
        key = "gmail:" + hashlib.sha256((account.lower() + ":" + raw["id"]).encode()).hexdigest()
        if await session.scalar(
            select(Message.id).where(
                Message.organization_id == org_id, Message.idempotency_key == key
            )
        ):
            counts["duplicates"] += 1
            continue
        lead = await session.scalar(
            select(Lead).where(Lead.organization_id == org_id, Lead.email == address)
        )
        if not lead:
            counts["unknown_contacts"] += 1
            continue
        classification = classify(body)
        if classification["label"] in {"unsubscribe", "complaint"}:
            await suppress(
                session,
                org_id,
                lead.email,
                "opt_out" if classification["label"] == "unsubscribe" else "complaint",
            )
        elif classification["label"] not in {"auto_reply", "bounce_notice"} and lead.status not in {
            "suppressed",
            "converted",
        }:
            lead.status = "replied"
        item = Message(
            organization_id=org_id,
            lead_id=lead.id,
            direction="inbound",
            subject=headers.get("subject", "")[:200],
            body=body,
            status="received",
            provider_id=raw["id"],
            classification=classification,
            idempotency_key=key,
            simulated=False,
        )
        session.add(item)
        await session.flush()
        if classification["label"] not in {"auto_reply", "bounce_notice"}:
            await session.execute(
                update(Enrollment)
                .where(Enrollment.organization_id == org_id, Enrollment.lead_id == lead.id)
                .values(status="stopped")
            )
        await dispatch(session, org_id, "message.received", item, item.id)
        counts["imported"] += 1
    return counts
