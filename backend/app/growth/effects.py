import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.growth.automation import dispatch
from app.growth.connections import active
from app.growth.contracts import PaymentEvent
from app.growth.gateway import ensure_budget
from app.growth.knowledge import guard_content, guard_draft
from app.growth.models import (
    Activity,
    Approval,
    Campaign,
    Checkout,
    Content,
    Customer,
    DailySend,
    Draft,
    Effect,
    Enrollment,
    Lead,
    Meeting,
    Message,
    Payment,
    Subscription,
    Suppression,
)
from app.growth.runtime import find, public, record
from app.models import Brand, Membership, Organization
from app.tenancy import tenant_scope


def payload_hash(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


async def freeze(session, org_id, actor_id, kind, subject_id, action, payload):
    existing = await session.scalar(
        select(Approval).where(
            Approval.organization_id == org_id,
            Approval.subject_type == kind,
            Approval.subject_id == subject_id,
            Approval.status.in_(["pending", "approved"]),
            Approval.expires_at > time.time(),
            Approval.payload_hash == payload_hash(payload),
        )
    )
    if existing:
        return existing
    item = Approval(
        organization_id=org_id,
        subject_type=kind,
        subject_id=subject_id,
        action_class=action,
        payload=payload,
        payload_hash=payload_hash(payload),
        expires_at=time.time() + 86400,
    )
    session.add(item)
    await session.flush()
    await record(session, org_id, actor_id, "approval.requested", item.id)
    return item


async def suppress(session, org_id, address, reason):
    insert = sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert
    await session.execute(
        insert(Suppression)
        .values(
            id=str(uuid4()),
            created_at=time.time(),
            organization_id=org_id,
            address=address.lower(),
            reason=reason,
        )
        .on_conflict_do_nothing(index_elements=["organization_id", "address"])
    )
    await session.execute(
        update(Lead)
        .where(Lead.organization_id == org_id, Lead.email == address.lower())
        .values(status="suppressed")
    )
    await session.execute(
        update(Enrollment)
        .where(
            Enrollment.organization_id == org_id,
            Enrollment.lead_id.in_(
                select(Lead.id).where(Lead.organization_id == org_id, Lead.email == address.lower())
            ),
        )
        .values(status="stopped")
    )


def draft_payload(draft):
    return {
        "draft_id": draft.id,
        "lead_id": draft.lead_id,
        "version": draft.version,
        "subject": draft.subject,
        "body": draft.body,
        "claims": draft.claims,
    }


async def send_one(session, org_id, actor_id, draft, approval, key, daily_cap, simulated=True):
    lead = await find(session, Lead, org_id, draft.lead_id)
    blocked = await session.scalar(
        select(Suppression.id).where(
            Suppression.organization_id == org_id, Suppression.address == lead.email
        )
    )
    if blocked:
        raise HTTPException(403, "suppressed_recipient")
    if lead.lawful_basis == "not_established" or not lead.basis_evidence.strip():
        raise HTTPException(403, "contactability_not_established")
    brand = await find(session, Brand, org_id, lead.brand_id)
    if not simulated and brand.voice.get("sandbox_only"):
        raise HTTPException(409, "sample_business_is_sandbox_only")
    await guard_draft(session, brand, lead, draft.subject, draft.body, draft.claims)
    if "unsubscribe" not in draft.body.lower():
        raise HTTPException(422, "opt_out_required")
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    insert = sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert
    await session.execute(
        insert(DailySend)
        .values(organization_id=org_id, day=day, count=0)
        .on_conflict_do_nothing(index_elements=["organization_id", "day"])
    )
    counter = await session.execute(
        update(DailySend)
        .where(
            DailySend.organization_id == org_id, DailySend.day == day, DailySend.count < daily_cap
        )
        .values(count=DailySend.count + 1)
    )
    if not counter.rowcount:
        raise HTTPException(429, "daily_send_cap")
    message = Message(
        organization_id=org_id,
        lead_id=lead.id,
        draft_id=draft.id,
        approval_id=approval.id,
        direction="outbound",
        subject=draft.subject,
        body=draft.body,
        status="delivered" if simulated else "queued",
        provider_id="sandbox:" + str(uuid4()) if simulated else "",
        idempotency_key=key,
        simulated=simulated,
    )
    session.add(message)
    draft.status = "sent" if simulated else "queued"
    if simulated:
        lead.status = "contacted"
    session.add(
        Activity(
            organization_id=org_id,
            lead_id=lead.id,
            actor_id=actor_id,
            action="message.delivered" if simulated else "message.queued",
            detail="Sandbox delivery; no email was transmitted"
            if simulated
            else "Awaiting provider receipt",
        )
    )
    await session.flush()
    await record(
        session,
        org_id,
        actor_id,
        "message.simulated" if simulated else "message.queued",
        message.id,
    )
    if simulated:
        from app.growth.attribution import record_message_touch

        await record_message_touch(
            session, message, approval.subject_id if approval.subject_type == "campaign" else None
        )
    return public(message)


async def execute(session, settings, org_id, actor_id, approval_id, key, execution_mode="sandbox"):
    budget = await ensure_budget(session, org_id)
    # Serialize all effects with stop/suppression/booking decisions at the tenant boundary.
    await session.execute(
        update(Organization)
        .where(Organization.id == org_id)
        .values(emergency_stop=Organization.emergency_stop)
    )
    await session.refresh(budget)
    stopped = await session.scalar(
        select(Organization.emergency_stop).where(Organization.id == org_id)
    )
    if stopped:
        raise HTTPException(423, "emergency_stop")
    existing = await session.scalar(
        select(Effect).where(Effect.organization_id == org_id, Effect.idempotency_key == key)
    )
    if existing:
        if existing.approval_id != approval_id:
            raise HTTPException(409, "idempotency_key_payload_conflict")
        if existing.result.get("simulated", True) != (execution_mode == "sandbox"):
            raise HTTPException(409, "idempotency_key_payload_conflict")
        return existing.result
    approval = await find(session, Approval, org_id, approval_id)
    if approval.decision_basis.startswith("standing_policy:"):
        from app.growth.reply_policy import authority

        await authority(session, settings, org_id, approval, execution_mode)
    if approval.action_class == "launch_paid_ads":
        role = await session.scalar(
            select(Membership.role).where(
                Membership.organization_id == org_id, Membership.user_id == actor_id
            )
        )
        if role != "owner":
            raise HTTPException(403, "owner_required")
    if execution_mode == "local" and approval.action_class != "publish_content":
        raise HTTPException(422, "local_execution_only_for_publication")
    provider_name = {
        "send_email": "gmail",
        "send_bulk_campaign": "resend",
        "book_meeting": "calendar",
        "launch_paid_ads": "meta_ads",
    }.get(approval.action_class)
    if approval.action_class == "publish_channel":
        provider_name = approval.payload.get("channel")
        if provider_name not in {"wordpress", "linkedin"}:
            raise HTTPException(422, "unknown_publishing_channel")
    connection = (
        await active(session, settings, org_id, provider_name)
        if provider_name and execution_mode == "live"
        else None
    )
    if execution_mode == "live" and not connection:
        raise HTTPException(409, "verified_active_provider_required")
    simulated = connection is None
    if approval.status != "approved" or approval.expires_at <= time.time():
        raise HTTPException(409, "approval_not_valid")
    claimed = await session.execute(
        update(Approval)
        .where(
            Approval.id == approval.id,
            Approval.status == "approved",
            Approval.expires_at > time.time(),
        )
        .values(status="executed")
    )
    if not claimed.rowcount:
        raise HTTPException(409, "approval_already_consumed")

    if approval.action_class == "send_email":
        draft = await find(session, Draft, org_id, approval.subject_id)
        if payload_hash(draft_payload(draft)) != approval.payload_hash:
            raise HTTPException(409, "approval_payload_changed")
        result = await send_one(
            session, org_id, actor_id, draft, approval, key, budget.daily_send_cap, simulated
        )
    elif approval.action_class == "send_bulk_campaign":
        campaign = await find(session, Campaign, org_id, approval.subject_id)
        if campaign.status == "paused":
            raise HTTPException(409, "campaign_paused")
        items = []
        for lead_id in campaign.lead_ids:
            draft = await session.scalar(
                select(Draft)
                .where(
                    Draft.organization_id == org_id,
                    Draft.lead_id == lead_id,
                    Draft.status.in_(["draft", "pending_approval"]),
                )
                .order_by(Draft.created_at.desc())
            )
            if not draft:
                raise HTTPException(409, "campaign_draft_missing")
            if connection:
                recipient = await find(session, Lead, org_id, draft.lead_id)
                if recipient.lawful_basis != "consent":
                    raise HTTPException(403, "bulk_requires_recorded_opt_in")
            items.append(draft)
        payload = {
            "campaign_id": campaign.id,
            "name": campaign.name,
            "drafts": [draft_payload(draft) for draft in items],
            "budget_micros": campaign.budget_micros,
        }
        if payload_hash(payload) != approval.payload_hash:
            raise HTTPException(409, "approval_payload_changed")
        # One transaction: a failed contact/cap rolls back every local message and the approval.
        result = {
            "messages": [
                await send_one(
                    session,
                    org_id,
                    actor_id,
                    draft,
                    approval,
                    "bulk:" + hashlib.sha256(f"{key}:{draft.id}".encode()).hexdigest(),
                    budget.daily_send_cap,
                    simulated,
                )
                for draft in items
            ],
            "simulated": simulated,
        }
        campaign.status = "completed" if simulated else "active"
    elif approval.action_class == "book_meeting":
        item = await find(session, Meeting, org_id, approval.subject_id)
        meeting_lead = await find(session, Lead, org_id, item.lead_id)
        meeting_brand = await find(session, Brand, org_id, meeting_lead.brand_id)
        if not simulated and meeting_brand.voice.get("sandbox_only"):
            raise HTTPException(409, "sample_business_is_sandbox_only")
        payload = {
            "meeting_id": item.id,
            "lead_id": item.lead_id,
            "title": item.title,
            "starts_at": item.starts_at,
            "ends_at": item.ends_at,
            "timezone": item.timezone,
        }
        if payload_hash(payload) != approval.payload_hash:
            raise HTTPException(409, "approval_payload_changed")
        if item.starts_at <= time.time():
            raise HTTPException(409, "meeting_in_past")
        overlap = await session.scalar(
            select(Meeting.id).where(
                Meeting.organization_id == org_id,
                Meeting.status.in_(["booked", "queued"]),
                Meeting.starts_at < item.ends_at,
                Meeting.ends_at > item.starts_at,
            )
        )
        if overlap:
            raise HTTPException(409, "meeting_slot_unavailable")
        item.status = "booked" if simulated else "queued"
        item.provider_id = "sandbox:" + str(uuid4()) if simulated else ""
        lead = await find(session, Lead, org_id, item.lead_id)
        if simulated:
            lead.status = "meeting_set"
        result = {**public(item), "simulated": simulated}
    elif approval.action_class == "publish_content":
        item = await find(session, Content, org_id, approval.subject_id)
        payload = {"content_id": item.id, "title": item.title, "body": item.body}
        if payload_hash(payload) != approval.payload_hash:
            raise HTTPException(409, "approval_payload_changed")
        brand = await find(session, Brand, org_id, item.brand_id)
        await guard_content(session, brand, item.title, item.title, item.body, item.citations)
        item.status = "published_local" if execution_mode == "local" else "published_sandbox"
        simulated = execution_mode != "local"
        result = {**public(item), "simulated": simulated}
        if not simulated:
            result["url"] = f"/api/v1/public/{org_id}/{item.id}"
    elif approval.action_class == "launch_paid_ads":
        from app.growth.advertising import check_ad

        brand, image = await check_ad(session, org_id, approval.payload)
        if connection:
            if brand.voice.get("sandbox_only") or image.output.get("simulated", True):
                raise HTTPException(409, "sample_assets_cannot_run_paid_ads")
            if (connection["id"], connection["version"]) != (
                approval.payload.get("connection_id"),
                approval.payload.get("connection_version"),
            ):
                raise HTTPException(409, "ads_connection_changed_request_new_approval")
            if connection["credentials"].get("currency") != approval.payload["currency"]:
                raise HTTPException(409, "ad_account_currency_mismatch")
        result = {
            "simulated": simulated,
            "status": "simulated" if simulated else "queued",
            "budget_minor": approval.payload["lifetime_budget_minor"],
            "currency": approval.payload["currency"],
        }
    elif approval.action_class == "publish_channel":
        from app.growth.publishing import check_publication

        item, brand = await check_publication(session, org_id, approval.payload)
        if connection:
            if brand.voice.get("sandbox_only"):
                raise HTTPException(409, "sample_business_is_sandbox_only")
            if (connection["id"], connection["version"]) != (
                approval.payload.get("connection_id"),
                approval.payload.get("connection_version"),
            ):
                raise HTTPException(409, "publication_connection_changed_request_new_approval")
        result = {
            "content_id": item.id,
            "channel": provider_name,
            "simulated": simulated,
            "status": "simulated" if simulated else "queued",
        }
    else:
        raise HTTPException(403, "unregistered_external_action")
    if connection:
        result = {
            **result,
            "_connection_id": connection["id"],
            "_connection_version": connection["version"],
            "_account_ref": connection["account_ref"],
        }
    effect = Effect(
        organization_id=org_id,
        action=approval.action_class,
        idempotency_key=key,
        approval_id=approval.id,
        payload=approval.payload,
        status="simulated" if simulated else "queued" if connection else "succeeded",
        result=result,
    )
    session.add(effect)
    await session.flush()
    result = {**result, "effect_id": effect.id}
    effect.result = result
    await record(session, org_id, actor_id, "approval.executed", approval.id)
    await session.commit()
    return result


def signature(secret, timestamp, body):
    return hmac.new(
        secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256
    ).hexdigest()


async def payment_event(session, settings, body, timestamp, supplied_signature):
    try:
        stamp = int(timestamp)
    except (ValueError, TypeError):
        raise HTTPException(401, "invalid_webhook_timestamp") from None
    expected = signature(settings.payment_webhook_secret, stamp, body)
    if abs(time.time() - stamp) > 300 or not hmac.compare_digest(
        expected, supplied_signature or ""
    ):
        raise HTTPException(401, "invalid_webhook_signature")
    try:
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("object_required")
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, "invalid_webhook_payload") from None
    return await settle_payment(session, data, simulated=True)


async def settle_payment(session, data, simulated, provider_verified=False):
    if data.get("type") != "payment.succeeded":
        return {"status": "ignored"}
    try:
        data = PaymentEvent.model_validate(data).model_dump()
    except ValidationError:
        raise HTTPException(422, "invalid_webhook_payload") from None
    event_id, ref = data["event_id"], data["checkout_ref"]
    prior = await session.scalar(select(Payment).where(Payment.provider_event_id == event_id))
    if prior:
        return {"status": "duplicate", "payment_id": prior.id}
    if data.get("type") != "payment.succeeded":
        return {"status": "ignored"}
    if session.bind.dialect.name == "postgresql":
        org_id = await session.scalar(
            text("SELECT resolve_checkout_org(:reference)"), {"reference": ref}
        )
        if org_id:
            await tenant_scope(session, organization_id=org_id)
    checkout = await session.scalar(select(Checkout).where(Checkout.provider_ref == ref))
    if not checkout:
        raise HTTPException(404, "unknown_checkout")
    if not provider_verified and not checkout.provider_ref.startswith("sandbox:"):
        raise HTTPException(403, "sandbox_event_cannot_pay_real_checkout")
    if (
        data.get("amount_minor") != checkout.amount_minor
        or data.get("currency") != checkout.currency
    ):
        raise HTTPException(422, "payment_amount_mismatch")
    await session.execute(
        update(Organization)
        .where(Organization.id == checkout.organization_id)
        .values(emergency_stop=Organization.emergency_stop)
    )
    # Recheck replay under the write lock for concurrent callbacks.
    prior = await session.scalar(select(Payment).where(Payment.provider_event_id == event_id))
    if prior:
        return {"status": "duplicate", "payment_id": prior.id}
    await session.refresh(checkout)
    if checkout.status == "paid":
        return {"status": "already_paid"}
    payment = Payment(
        organization_id=checkout.organization_id,
        provider_event_id=event_id,
        checkout_id=checkout.id,
        lead_id=checkout.lead_id,
        amount_minor=checkout.amount_minor,
        currency=checkout.currency,
        status="succeeded",
        simulated=simulated,
    )
    session.add(payment)
    if checkout.provider_ref.startswith("sandbox:"):
        checkout.payment_ref = "sandbox-payment:" + checkout.id
        if checkout.recurring:
            checkout.subscription_ref = "sandbox-subscription:" + checkout.id
    checkout.status = "paid"
    lead = await find(session, Lead, checkout.organization_id, checkout.lead_id)
    lead.status = "converted"
    customer = await session.scalar(
        select(Customer).where(
            Customer.organization_id == checkout.organization_id, Customer.lead_id == lead.id
        )
    )
    if not customer:
        customer = Customer(
            organization_id=checkout.organization_id,
            lead_id=lead.id,
            onboarding=[
                {"step": name, "done": False}
                for name in [
                    "Welcome",
                    "Collect requirements",
                    "Schedule kickoff",
                    "Deliver first value",
                ]
            ],
        )
        session.add(customer)
    customer.simulated = (
        customer.simulated and simulated if customer.simulated is not None else simulated
    )
    await session.flush()
    if checkout.recurring:
        existing_subscription = await session.scalar(
            select(Subscription).where(
                Subscription.organization_id == checkout.organization_id,
                Subscription.checkout_id == checkout.id,
            )
        )
        if not existing_subscription:
            session.add(
                Subscription(
                    organization_id=checkout.organization_id,
                    customer_id=customer.id,
                    checkout_id=checkout.id,
                    amount_minor=checkout.amount_minor,
                    currency=checkout.currency,
                    provider_ref=checkout.subscription_ref,
                    current_period_end=time.time() + 30 * 86400 if simulated else 0,
                )
            )
    await dispatch(session, checkout.organization_id, "payment.succeeded", payment, payment.id)
    await session.commit()
    return {
        "status": "processed",
        "payment_id": payment.id,
        "customer_id": customer.id,
        "simulated": simulated,
    }
