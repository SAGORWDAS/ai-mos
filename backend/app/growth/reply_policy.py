"""Explicit, expiring standing authority for one exact templated inbound response."""

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import case, or_, select, update

from app.contracts import Input
from app.growth.connections import active
from app.growth.knowledge import claim_sources, draft_text
from app.growth.models import (
    Agent,
    Approval,
    Effect,
    Integration,
    Lead,
    Message,
    ReplyPolicy,
)
from app.growth.runtime import find, public, record
from app.models import Brand, Membership


def brand_hash(brand):
    data = {
        key: getattr(brand, key)
        for key in [
            "id",
            "name",
            "positioning",
            "icp",
            "voice",
            "pricing",
            "approved_claims",
            "prohibited_claims",
        ]
    }
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def preview(brand):
    if not brand.approved_claims:
        return ""
    sample = SimpleNamespace(name="Recipient", personalisation="", personalisation_evidence="")
    return "Thanks for your reply.\n\n" + draft_text(
        brand, sample, [{"text": brand.approved_claims[0]}]
    )


def template_hash(brand):
    return hashlib.sha256(preview(brand).encode()).hexdigest()


class PolicyInput(Input):
    enabled: bool
    execution_mode: Literal["sandbox", "live"] = "sandbox"
    daily_cap: int = Field(default=5, ge=1, le=20)
    expires_days: int = Field(default=7, ge=1, le=30)
    reviewed_template_hash: str = Field(default="", max_length=64)


async def authority(session, settings, org_id, approval, execution_mode):
    if not approval.decision_basis.startswith("standing_policy:"):
        return
    policy_id = approval.decision_basis.split(":", 1)[1]
    policy = await find(session, ReplyPolicy, org_id, policy_id)
    role = await session.scalar(
        select(Membership.role).where(
            Membership.organization_id == org_id, Membership.user_id == policy.owner_id
        )
    )
    brand = await find(session, Brand, org_id, policy.brand_id)
    agent = await session.scalar(
        select(Agent).where(Agent.organization_id == org_id, Agent.role_id == "AGT-08")
    )
    if (
        not policy.enabled
        or policy.expires_at <= time.time()
        or policy.execution_mode != execution_mode
        or role != "owner"
        or policy.owner_id != approval.decided_by
        or policy.brand_hash != brand_hash(brand)
        or (agent and not agent.enabled)
    ):
        raise HTTPException(409, "standing_reply_authority_revoked")
    if execution_mode == "live":
        connection = await active(session, settings, org_id, "gmail")
        if not connection or (connection["id"], connection["version"]) != (
            policy.connection_id,
            policy.connection_version,
        ):
            raise HTTPException(409, "standing_reply_connection_changed")


def clear_automatic_intent(body):
    """A classifier score alone cannot authorize a send; require an unambiguous whole reply."""
    normalized = " ".join(body.lower().split())
    return bool(
        re.fullmatch(
            r"(?:please )?(?:tell me more|send (?:me )?more (?:details|information)|"
            r"can you send (?:me )?more (?:details|information)|"
            r"can we schedule a call|let's schedule a call|book a demo)[.!?]*",
            normalized,
        )
    )


async def maybe_send(runtime, session, task, draft):
    if task.type != "reply" or not task.input.get("auto_review"):
        return False
    org_id = task.organization_id
    lead = await find(session, Lead, org_id, draft.lead_id)
    policy = await session.scalar(
        select(ReplyPolicy).where(
            ReplyPolicy.organization_id == org_id,
            ReplyPolicy.brand_id == lead.brand_id,
            ReplyPolicy.enabled.is_(True),
        )
    )
    if not policy or policy.expires_at <= time.time():
        return False
    brand = await find(session, Brand, org_id, lead.brand_id)
    incoming = await find(session, Message, org_id, task.input["message_id"])
    agent = await session.scalar(
        select(Agent).where(Agent.organization_id == org_id, Agent.role_id == "AGT-08")
    )
    if (
        policy.brand_hash != brand_hash(brand)
        or policy.template_hash != template_hash(brand)
        or incoming.direction != "inbound"
        or incoming.classification.get("label") not in {"interested", "meeting_request"}
        or incoming.classification.get("escalate")
        or incoming.classification.get("confidence", 0) < 0.85
        or not clear_automatic_intent(incoming.body)
        or (
            policy.execution_mode == "live"
            and (incoming.simulated or brand.voice.get("sandbox_only"))
        )
        or (agent and not agent.enabled)
        or lead.personalisation
    ):
        return False
    sources = (await claim_sources(session, brand))[:1]
    expected = "Thanks for your reply.\n\n" + draft_text(brand, lead, sources)
    if draft.body != expected or draft.subject != f"A question from {brand.name}"[:90]:
        return False
    from app.growth.effects import draft_payload, execute, freeze

    approval = await session.scalar(
        select(Approval)
        .where(
            Approval.organization_id == org_id,
            Approval.subject_type == "draft",
            Approval.subject_id == draft.id,
        )
        .order_by(Approval.created_at.desc())
        .limit(1)
    )
    if approval and approval.status not in {"pending", "approved"}:
        return False
    identity = "automatic-reply:" + incoming.id
    if await session.scalar(
        select(Effect.id).where(
            Effect.organization_id == org_id, Effect.idempotency_key == identity
        )
    ):
        return True
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    reserved = await session.execute(
        update(ReplyPolicy)
        .where(
            ReplyPolicy.id == policy.id,
            ReplyPolicy.enabled.is_(True),
            ReplyPolicy.expires_at > time.time(),
            or_(ReplyPolicy.counter_day != today, ReplyPolicy.counter_used < ReplyPolicy.daily_cap),
        )
        .values(
            counter_day=today,
            counter_used=case(
                (ReplyPolicy.counter_day == today, ReplyPolicy.counter_used + 1), else_=1
            ),
        )
    )
    if not reserved.rowcount:
        return False
    approval = approval or await freeze(
        session, org_id, policy.owner_id, "draft", draft.id, "send_email", draft_payload(draft)
    )
    approval.status = "approved"
    approval.decided_by = policy.owner_id
    approval.decided_at = time.time()
    approval.decision_basis = "standing_policy:" + policy.id
    await record(
        session, org_id, policy.owner_id, "reply_policy.approved_exact_template", approval.id
    )
    await (
        session.commit()
    )  # Reserve an attempt even if a later contactability/budget guard refuses it.
    owner_id, approval_id, draft_id, mode = (
        policy.owner_id,
        approval.id,
        draft.id,
        policy.execution_mode,
    )
    try:
        await authority(session, runtime.settings, org_id, approval, mode)
        await execute(session, runtime.settings, org_id, owner_id, approval_id, identity, mode)
        return True
    except HTTPException as error:
        await session.rollback()
        approval = await find(session, Approval, org_id, approval_id)
        if approval.status == "approved":
            approval.status = "pending"
            approval.decision_basis = "standing_policy_blocked"
            approval.decided_by = None
            approval.decided_at = None
        await record(
            session,
            org_id,
            owner_id,
            "reply_policy.held_for_review",
            draft_id,
            decision=str(error.detail)[:120],
        )
        await session.commit()
        return False


def install_reply_policy(app, settings, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.get("/brands/{brand_id}/reply-digest")
    async def digest(
        brand_id: str,
        request: Request,
        offset: int = Query(default=0, ge=0, le=1_000_000),
        who=Depends(identity),
        session=Depends(db),
    ):
        await require(session, request, who, {"owner", "admin"}, writes=False)
        org_id = who["organization"].id
        await find(session, Brand, org_id, brand_id)
        policy_id = await session.scalar(
            select(ReplyPolicy.id).where(
                ReplyPolicy.organization_id == org_id, ReplyPolicy.brand_id == brand_id
            )
        )
        since = time.time() - 7 * 86400
        if not policy_id:
            return {"since": since, "items": [], "next_offset": None}
        records = (
            (
                await session.execute(
                    select(
                        Effect.id,
                        Effect.created_at,
                        Effect.status,
                        Effect.result,
                        Approval.subject_id.label("draft_id"),
                    )
                    .join(Approval, Approval.id == Effect.approval_id)
                    .where(
                        Effect.organization_id == org_id,
                        Approval.organization_id == org_id,
                        Approval.decision_basis == "standing_policy:" + policy_id,
                        Effect.created_at >= since,
                    )
                    .order_by(Effect.created_at, Effect.id)
                    .offset(offset)
                    .limit(101)
                )
            )
            .mappings()
            .all()
        )
        return {
            "since": since,
            "items": [dict(r) for r in records[:100]],
            "next_offset": offset + 100 if len(records) > 100 else None,
        }

    @router.get("/brands/{brand_id}/reply-policy")
    async def read(brand_id: str, who=Depends(identity), session=Depends(db)):
        brand = await find(session, Brand, who["organization"].id, brand_id)
        policy = await session.scalar(
            select(ReplyPolicy).where(
                ReplyPolicy.organization_id == who["organization"].id,
                ReplyPolicy.brand_id == brand.id,
            )
        )
        return {
            "policy": public(policy) if policy else None,
            "template_preview": preview(brand),
            "template_hash": template_hash(brand),
            "requires_reapproval": bool(policy and policy.brand_hash != brand_hash(brand)),
        }

    @router.put("/brands/{brand_id}/reply-policy")
    async def save(
        brand_id: str,
        data: PolicyInput,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await require(session, request, who, {"owner"}, writes=data.enabled)
        org_id = who["organization"].id
        brand = await find(session, Brand, org_id, brand_id)
        if data.enabled and (
            not preview(brand) or data.reviewed_template_hash != template_hash(brand)
        ):
            raise HTTPException(409, "review_current_reply_template_first")
        connection = None
        if data.enabled and data.execution_mode == "live":
            if brand.voice.get("sandbox_only"):
                raise HTTPException(409, "sample_business_is_sandbox_only")
            connection = await active(session, settings, org_id, "gmail")
            if not connection:
                raise HTTPException(409, "enabled_gmail_required")
            integration = await find(session, Integration, org_id, connection["id"])
            integration.auto_draft_replies = True
            integration.sync_enabled = True
            integration.sync_next_at = 0
        policy = await session.scalar(
            select(ReplyPolicy).where(
                ReplyPolicy.organization_id == org_id, ReplyPolicy.brand_id == brand.id
            )
        )
        if not policy:
            policy = ReplyPolicy(organization_id=org_id, brand_id=brand.id, owner_id=who["user"].id)
            session.add(policy)
        policy.owner_id = who["user"].id
        policy.enabled = data.enabled
        policy.execution_mode = data.execution_mode
        policy.daily_cap = data.daily_cap
        policy.expires_at = time.time() + data.expires_days * 86400
        policy.brand_hash = brand_hash(brand)
        policy.template_hash = template_hash(brand)
        policy.connection_id = connection["id"] if connection else None
        policy.connection_version = connection["version"] if connection else 0
        await session.flush()
        await record(session, org_id, who["user"].id, "reply_policy.updated", policy.id)
        await session.commit()
        return public(policy)

    app.include_router(router)
