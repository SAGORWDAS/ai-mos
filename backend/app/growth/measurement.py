"""Campaign cost lineage, outcome credit and refund-aware revenue without inferred FX."""

import hashlib
import time
from collections import defaultdict
from types import SimpleNamespace

from sqlalchemy import and_, select

from app.growth.models import (
    Campaign,
    Checkout,
    Command,
    Customer,
    Effect,
    Lead,
    Meeting,
    ModelUsage,
    Plan,
    ProviderEvent,
    Task,
)


def refund_events(receipts, payments, checkouts, org_id):
    """Use the original payment's touch window, never a later campaign's refund date."""
    result, unresolved = [], 0
    for receipt in receipts:
        if receipt.kind != "charge.refunded" or not receipt.amount_minor:
            continue
        evidence = receipt.evidence
        candidates = [
            p
            for p in payments
            if p.checkout_id == evidence.get("checkout_id")
            and p.simulated == receipt.simulated
            and p.currency == receipt.currency
        ]
        matched = None
        if evidence.get("invoice_object_ref"):
            identity = (
                "invoice:"
                + hashlib.sha256(
                    (receipt.provider + org_id + evidence["invoice_object_ref"]).encode()
                ).hexdigest()
            )
            matched = next((p for p in candidates if p.provider_event_id == identity), None)
        checkout = checkouts.get(evidence.get("checkout_id"))
        if not matched and checkout and evidence.get("payment_ref") == checkout.payment_ref:
            base = [p for p in candidates if not p.provider_event_id.startswith("invoice:")]
            matched = base[0] if len(base) == 1 else None
        if not matched and len(candidates) == 1:
            matched = candidates[0]
        if not matched:
            unresolved += 1
        result.append(
            SimpleNamespace(
                lead_id=matched.lead_id if matched else "unassigned-refund",
                created_at=matched.created_at if matched else receipt.created_at,
                amount_minor=receipt.amount_minor,
                currency=receipt.currency,
                simulated=receipt.simulated,
            )
        )
    return result, unresolved


def combine_revenue(gross, refunds):
    buckets = defaultdict(int)
    for row in gross + refunds:
        buckets[(row["campaign_id"], row["currency"], row["simulated"])] += row["amount_minor"]
    return [
        {"campaign_id": key[0], "currency": key[1], "simulated": key[2], "amount_minor": value}
        for key, value in buckets.items()
    ]


async def complete_report(session, org_id, payments, touches, expenses, model, window_days):
    from app.growth.attribution import allocate

    async def rows(cls):
        return (await session.scalars(select(cls).where(cls.organization_id == org_id))).all()

    campaigns = {row.id: row for row in await rows(Campaign)}
    costs = defaultdict(
        lambda: {"amount_micros": 0, "model_micros": 0, "expense_micros": 0, "held_micros": 0}
    )
    for expense in expenses:
        bucket = costs[(expense.campaign_id, expense.simulated)]
        bucket["amount_micros"] += expense.amount_micros
        bucket["expense_micros"] += expense.amount_micros
    lineage = (
        await session.execute(
            select(ModelUsage, Task.input, Command.parsed)
            .join(Task, and_(Task.id == ModelUsage.task_id, Task.organization_id == org_id))
            .outerjoin(Plan, and_(Plan.id == Task.plan_id, Plan.organization_id == org_id))
            .outerjoin(
                Command, and_(Command.id == Plan.command_id, Command.organization_id == org_id)
            )
            .where(ModelUsage.organization_id == org_id)
        )
    ).all()
    for usage, payload, command in lineage:
        campaign_id = payload.get("campaign_id") or (command or {}).get("campaign_id")
        campaign_id = campaign_id if campaign_id in campaigns else None
        bucket = costs[(campaign_id, usage.simulated)]
        bucket["amount_micros"] += usage.cost_micros
        bucket["model_micros"] += usage.cost_micros
        if not usage.settled:
            bucket["held_micros"] += usage.reserved_micros

    checkouts = {row.id: row for row in await rows(Checkout)}
    receipts = await rows(ProviderEvent)
    ad_spend = {}
    for receipt in sorted(receipts, key=lambda row: (row.created_at, row.id)):
        if receipt.provider == "meta_ads" and receipt.kind == "ads.insights":
            ad_spend[receipt.object_ref] = receipt.evidence
    refunds, unresolved = refund_events(receipts, payments, checkouts, org_id)
    refund_credit = allocate(refunds, touches, model, window_days)
    gross = allocate(payments, touches, model, window_days)

    # Micro-credits preserve an exact total of one outcome across linear campaign weights.
    funnel = defaultdict(
        lambda: {
            "contact_credit": 0,
            "qualified_credit": 0,
            "meeting_credit": 0,
            "customer_credit": 0,
        }
    )

    def credit(event, metric):
        for row in allocate([event], touches, model, window_days):
            funnel[(row["campaign_id"], row["simulated"])][metric] += row["amount_minor"]

    now = time.time()
    leads = await rows(Lead)
    modes = defaultdict(set)
    for touch in touches:
        if now - window_days * 86400 <= touch.occurred_at <= now:
            modes[touch.lead_id].add(touch.simulated)
    for lead in leads:
        for mode in modes[lead.id]:
            event = SimpleNamespace(
                lead_id=lead.id,
                created_at=now,
                amount_minor=1_000_000,
                currency="OUTCOME",
                simulated=mode,
            )
            credit(event, "contact_credit")
            if lead.score >= 65:
                credit(event, "qualified_credit")
    meetings = {row.id: row for row in await rows(Meeting)}
    for effect in await rows(Effect):
        meeting = meetings.get(effect.payload.get("meeting_id"))
        if (
            effect.action == "book_meeting"
            and effect.status in {"simulated", "succeeded"}
            and meeting
            and meeting.status == "booked"
        ):
            credit(
                SimpleNamespace(
                    lead_id=meeting.lead_id,
                    created_at=effect.created_at,
                    amount_minor=1_000_000,
                    currency="OUTCOME",
                    simulated=effect.result.get("simulated", True),
                ),
                "meeting_credit",
            )
    for customer in await rows(Customer):
        paid = [
            p.created_at
            for p in payments
            if p.lead_id == customer.lead_id and p.simulated == customer.simulated
        ]
        if paid:
            credit(
                SimpleNamespace(
                    lead_id=customer.lead_id,
                    created_at=min(paid),
                    amount_minor=1_000_000,
                    currency="OUTCOME",
                    simulated=customer.simulated,
                ),
                "customer_credit",
            )
    outcomes = []
    for key in set(funnel) | set(costs):
        values = {name: value / 1_000_000 for name, value in funnel[key].items()}
        cost = costs[key]["amount_micros"]
        outcomes.append(
            {
                "campaign_id": key[0],
                "simulated": key[1],
                **values,
                "recorded_cpl_micros": cost / values["qualified_credit"]
                if values["qualified_credit"]
                else None,
                "recorded_cac_micros": cost / values["customer_credit"]
                if values["customer_credit"]
                else None,
            }
        )
    return {
        "refunds": refund_credit,
        "ad_spend": list(ad_spend.values()),
        "net_revenue": combine_revenue(gross, refund_credit),
        "unresolved_refunds": unresolved,
        "outcomes": outcomes,
        "untouched_contacts": sum(not modes[lead.id] for lead in leads),
        "costs": [
            {"campaign_id": key[0], "simulated": key[1], **value} for key, value in costs.items()
        ],
    }
