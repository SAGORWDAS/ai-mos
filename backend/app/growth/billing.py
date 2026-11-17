"""Signed lifecycle receipts. No refund or subscription change is initiated here."""

import hashlib
import time

from fastapi import HTTPException
from sqlalchemy import select, update

from app.growth.models import Checkout, Customer, Notification, Payment, ProviderEvent, Subscription
from app.models import Organization
from app.tenancy import tenant_scope


def ref(value):
    return value.get("id", "") if isinstance(value, dict) else value or ""


async def lifecycle(session, org_id, event, provider="stripe"):
    await tenant_scope(session, organization_id=org_id)
    await session.execute(
        update(Organization)
        .where(Organization.id == org_id)
        .values(emergency_stop=Organization.emergency_stop)
    )
    prior = await session.scalar(
        select(ProviderEvent).where(
            ProviderEvent.organization_id == org_id,
            ProviderEvent.provider == provider,
            ProviderEvent.event_id == event["id"],
        )
    )
    if prior:
        return {"status": "duplicate"}
    kind = event.get("type", "")
    if kind not in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.paid",
        "invoice.payment_failed",
        "charge.refunded",
        "charge.dispute.created",
        "charge.dispute.closed",
    }:
        return {"status": "ignored"}
    data = event.get("data", {}).get("object", {})
    if not isinstance(data, dict) or not isinstance(data.get("id"), str):
        raise HTTPException(422, "invalid_provider_event")
    occurred = event.get("created", time.time())
    if not isinstance(occurred, (int, float)) or occurred < 0:
        raise HTTPException(422, "invalid_event_timestamp")
    receipt = ProviderEvent(
        organization_id=org_id,
        provider=provider,
        event_id=event["id"],
        kind=kind,
        object_ref=data["id"],
        occurred_at=occurred,
        simulated=not bool(event.get("livemode")),
        evidence={},
    )
    subscription = None
    if kind.startswith("customer.subscription."):
        subscription = await session.scalar(
            select(Subscription).where(
                Subscription.organization_id == org_id, Subscription.provider_ref == data["id"]
            )
        )
        if not subscription:
            raise HTTPException(409, "subscription_checkout_not_received_retry_later")
        if occurred >= subscription.last_event_at:
            status = "canceled" if kind.endswith(".deleted") else data.get("status")
            if status not in {
                "active",
                "trialing",
                "past_due",
                "unpaid",
                "canceled",
                "incomplete",
                "incomplete_expired",
                "paused",
            }:
                raise HTTPException(422, "unknown_subscription_status")
            if subscription.status != "canceled" or status == "canceled":
                subscription.status = status
            items = data.get("items", {}).get("data", [])
            period = data.get("current_period_end") or max(
                [item.get("current_period_end", 0) for item in items] + [0]
            )
            if isinstance(period, (int, float)) and period > 0:
                subscription.current_period_end = period
            subscription.last_event_at = occurred
            receipt.evidence = {
                "status": status,
                "cancel_at_period_end": bool(data.get("cancel_at_period_end")),
            }
    elif kind in {"invoice.paid", "invoice.payment_failed"}:
        subscription_id = ref(data.get("subscription")) or ref(
            (data.get("parent") or {}).get("subscription_details", {}).get("subscription")
        )
        subscription = (
            await session.scalar(
                select(Subscription).where(
                    Subscription.organization_id == org_id,
                    Subscription.provider_ref == subscription_id,
                )
            )
            if subscription_id
            else None
        )
        if not subscription:
            raise HTTPException(409, "subscription_checkout_not_received_retry_later")
        if kind == "invoice.paid":
            amount = data.get("amount_paid")
            currency = str(data.get("currency", "")).upper()
            if type(amount) is not int or amount < 0 or currency != subscription.currency:
                raise HTTPException(422, "invalid_invoice_amount_or_currency")
            invoice_key = (
                "invoice:" + hashlib.sha256((provider + org_id + data["id"]).encode()).hexdigest()
            )
            checkout = await session.get(Checkout, subscription.checkout_id)
            receipt.evidence = {
                "checkout_id": checkout.id,
                "payment_ref": ref(data.get("payment_intent")),
                "paid_total_minor": amount,
            }
            duplicate = await session.scalar(
                select(Payment.id).where(
                    Payment.organization_id == org_id,
                    Payment.provider_event_id == invoice_key,
                )
            )
            # Initial invoice is already represented by the paid Checkout receipt.
            if amount > 0 and data.get("billing_reason") != "subscription_create" and not duplicate:
                session.add(
                    Payment(
                        organization_id=org_id,
                        provider_event_id=invoice_key,
                        checkout_id=checkout.id,
                        lead_id=checkout.lead_id,
                        amount_minor=amount,
                        currency=currency,
                        status="succeeded",
                        simulated=receipt.simulated,
                    )
                )
                receipt.amount_minor = amount
                receipt.currency = currency
            period = data.get("period_end", 0)
            if isinstance(period, (int, float)):
                subscription.current_period_end = max(subscription.current_period_end, period)
            if occurred >= subscription.last_event_at and subscription.status != "canceled":
                subscription.status = "active"
        elif occurred >= subscription.last_event_at and subscription.status != "canceled":
            subscription.status = "past_due"
            session.add(
                Notification(
                    organization_id=org_id,
                    title="Subscription payment failed. Review the provider receipt.",
                    subject_id=subscription.id,
                )
            )
        subscription.last_event_at = max(occurred, subscription.last_event_at)
    elif kind in {"charge.refunded", "charge.dispute.created", "charge.dispute.closed"}:
        payment_ref = ref(data.get("payment_intent"))
        checkout = (
            await session.scalar(
                select(Checkout).where(
                    Checkout.organization_id == org_id, Checkout.payment_ref == payment_ref
                )
            )
            if payment_ref
            else None
        )
        paid_total = None
        invoice_receipt = None
        if not checkout and payment_ref:
            invoice_receipt = await session.scalar(
                select(ProviderEvent).where(
                    ProviderEvent.organization_id == org_id,
                    ProviderEvent.kind == "invoice.paid",
                    ProviderEvent.evidence["payment_ref"].as_string() == payment_ref,
                )
            )
            if invoice_receipt:
                checkout = await session.get(Checkout, invoice_receipt.evidence.get("checkout_id"))
                paid_total = invoice_receipt.evidence.get("paid_total_minor")
        if not checkout:
            raise HTTPException(409, "payment_checkout_not_received_retry_later")
        if kind == "charge.refunded":
            amount = data.get("amount_refunded")
            if (
                type(amount) is not int
                or not 0
                <= amount
                <= (paid_total if paid_total is not None else checkout.amount_minor)
                or str(data.get("currency", "")).upper() != checkout.currency
            ):
                raise HTTPException(422, "invalid_refund_receipt")
            prior_refunds = (
                await session.scalars(
                    select(ProviderEvent).where(
                        ProviderEvent.organization_id == org_id,
                        ProviderEvent.provider == provider,
                        ProviderEvent.kind == kind,
                        ProviderEvent.object_ref == data["id"],
                    )
                )
            ).all()
            previous = -sum(row.amount_minor for row in prior_refunds)
            receipt.amount_minor = -max(0, amount - previous)
            receipt.currency = checkout.currency
            receipt.evidence = {
                "checkout_id": checkout.id,
                "cumulative_refund_minor": amount,
                "payment_ref": payment_ref,
                "invoice_object_ref": invoice_receipt.object_ref if invoice_receipt else None,
            }
        else:
            receipt.evidence = {
                "checkout_id": checkout.id,
                "status": str(data.get("status", "unknown"))[:40],
            }
        session.add(
            Notification(
                organization_id=org_id,
                title="Payment provider event: " + kind + " — human review required.",
                subject_id=checkout.id,
            )
        )
    else:
        return {"status": "ignored"}
    if subscription:
        customer = await session.get(Customer, subscription.customer_id)
        states = (
            await session.scalars(
                select(Subscription.status).where(
                    Subscription.organization_id == org_id, Subscription.customer_id == customer.id
                )
            )
        ).all()
        customer.status = (
            "active"
            if any(state in {"active", "trialing"} for state in states)
            else "churned"
            if all(state in {"canceled", "incomplete_expired"} for state in states)
            else "at_risk"
        )
    session.add(receipt)
    await session.commit()
    return {"status": "processed", "event_id": receipt.id}
