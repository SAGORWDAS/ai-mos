import csv
import io
import json
import time
from collections import Counter
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, update

from app.growth import contracts as c
from app.growth.automation import dispatch
from app.growth.connections import active
from app.growth.effects import (
    draft_payload,
    execute,
    freeze,
    payment_event,
    signature,
    suppress,
)
from app.growth.gateway import ensure_budget
from app.growth.knowledge import classify, guard_draft, index_document, retrieve
from app.growth.models import (
    RESOURCES,
    Activity,
    Agent,
    Approval,
    Campaign,
    Checkout,
    Command,
    Content,
    Customer,
    Draft,
    Enrollment,
    Expense,
    Lead,
    Learning,
    Meeting,
    Message,
    ModelUsage,
    Notification,
    Payment,
    Plan,
    ProviderEvent,
    Sequence,
    SupportThread,
    Task,
    Workflow,
    WorkflowRun,
)
from app.growth.runtime import AGENTS, find, public, record
from app.models import Brand


def install(app, runtime, settings, db, identity, require):
    router = APIRouter(prefix="/v1")

    async def write(request, who, session, owner=False):
        await require(session, request, who, {"owner"} if owner else {"owner", "admin", "member"})

    async def audited(session, who, request, action, subject=""):
        await record(
            session,
            who["organization"].id,
            who["user"].id,
            action,
            subject,
            trace=request.state.trace_id,
        )

    @router.get("/data/{resource}")
    async def listing(
        resource: str, before: float | None = None, who=Depends(identity), session=Depends(db)
    ):
        model = RESOURCES.get(resource)
        if not model:
            raise HTTPException(404, "unknown_resource")
        query = select(model).where(model.organization_id == who["organization"].id)
        if before is not None:
            query = query.where(model.created_at < before)
        rows = (
            await session.scalars(query.order_by(model.created_at.desc(), model.id).limit(201))
        ).all()
        return {
            "items": [public(row) for row in rows[:200]],
            "next_cursor": rows[199].created_at if len(rows) > 200 else None,
        }

    @router.get("/data/{resource}/{record_id}")
    async def detail(resource: str, record_id: str, who=Depends(identity), session=Depends(db)):
        if resource not in RESOURCES:
            raise HTTPException(404, "unknown_resource")
        return public(await find(session, RESOURCES[resource], who["organization"].id, record_id))

    @router.get("/agents")
    async def agents(who=Depends(identity), session=Depends(db)):
        configured = (
            await session.scalars(
                select(Agent).where(Agent.organization_id == who["organization"].id)
            )
        ).all()
        overrides = {row.role_id: row for row in configured}
        return [
            {
                **item,
                "enabled": overrides[key].enabled if key in overrides else True,
                "mode": settings.provider_mode,
                "implementation": "shared_workflow_engine",
            }
            for key, item in AGENTS.items()
        ]

    @router.put("/agents/{role_id}")
    async def agent_update(
        role_id: str,
        data: c.AgentInput,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await write(request, who, session, owner=True)
        if role_id not in AGENTS:
            raise HTTPException(404, "unknown_agent")
        item = await session.scalar(
            select(Agent).where(
                Agent.organization_id == who["organization"].id, Agent.role_id == role_id
            )
        )
        if not item:
            item = Agent(
                organization_id=who["organization"].id,
                role_id=role_id,
                name=AGENTS[role_id]["name"],
                enabled=data.enabled,
            )
            session.add(item)
        item.enabled = data.enabled
        await audited(session, who, request, "agent.updated", role_id)
        await session.commit()
        return {"role_id": role_id, "enabled": data.enabled}

    @router.post("/commands", status_code=202)
    async def command(
        data: c.CommandInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        org_id, actor_id = who["organization"].id, who["user"].id
        brand = await find(session, Brand, org_id, data.brand_id)
        parsed = data.model_dump(exclude={"idempotency_key"})
        parsed["audience"] = data.audience or ", ".join(brand.icp.get("segments", []))
        missing = []
        if not parsed["audience"]:
            missing.append("audience")
        if not brand.positioning:
            missing.append("brand.positioning")
        if not brand.approved_claims:
            missing.append("brand.approved_claims")
        if missing:
            return {"status": "needs_information", "missing_fields": missing}
        previous = await session.scalar(
            select(Task).where(
                Task.organization_id == org_id, Task.idempotency_key == data.idempotency_key
            )
        )
        if previous:
            if previous.type != "plan" or previous.input.get("request") != parsed:
                raise HTTPException(409, "idempotency_key_payload_conflict")
            return {"status": "queued", "task": public(previous)}
        item = Command(
            organization_id=org_id,
            created_by=actor_id,
            brand_id=brand.id,
            raw=data.objective,
            parsed=parsed,
        )
        session.add(item)
        await session.flush()
        task = await runtime.enqueue(
            session,
            org_id,
            actor_id,
            "plan",
            "AGT-01",
            data.idempotency_key,
            {"command_id": item.id, "request": parsed},
        )
        return {"status": "queued", "task": public(task)}

    @router.post("/plans/{plan_id}/approve")
    async def approve_plan(
        plan_id: str, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        item = await find(session, Plan, who["organization"].id, plan_id)
        if item.status != "draft":
            raise HTTPException(409, "plan_not_draft")
        item.status = "approved"
        await audited(session, who, request, "plan.approved", item.id)
        await session.commit()
        await runtime.schedule(session, who["organization"].id, item.id)
        return public(item)

    @router.post("/tasks/{task_id}/retry")
    async def retry_task(
        task_id: str, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        item = await find(session, Task, who["organization"].id, task_id)
        if item.status not in {"failed", "blocked"} or item.attempt >= 3:
            raise HTTPException(409, "task_not_retryable")
        if item.error_code == "dependency_failed":
            raise HTTPException(409, "retry_failed_dependency_first")
        item.status, item.error_code = "ready", ""
        if item.plan_id:
            plan = await find(session, Plan, who["organization"].id, item.plan_id)
            plan.status = "running"
            await session.execute(
                update(Task)
                .where(
                    Task.organization_id == who["organization"].id,
                    Task.plan_id == item.plan_id,
                    Task.error_code == "dependency_failed",
                )
                .values(status="created", error_code="")
            )
        await audited(session, who, request, "task.retried", item.id)
        await session.commit()
        return public(item)

    @router.post("/tasks/{task_id}/cancel")
    async def cancel_task(
        task_id: str, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        item = await find(session, Task, who["organization"].id, task_id)
        if item.status not in {"created", "ready", "blocked", "running"} or (
            item.status == "running" and item.type == "checkout"
        ):
            raise HTTPException(409, "task_not_cancellable")
        item.status = "cancelled"
        await audited(session, who, request, "task.cancelled", item.id)
        await session.commit()
        if item.plan_id:
            await runtime.schedule(session, who["organization"].id, item.plan_id)
        return public(item)

    @router.post("/brands/{brand_id}/documents", status_code=201)
    async def document(
        brand_id: str,
        data: c.DocumentInput,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await write(request, who, session)
        await find(session, Brand, who["organization"].id, brand_id)
        item = await index_document(
            session, who["organization"].id, brand_id, data.title, data.content, data.source_uri
        )
        await audited(session, who, request, "document.indexed", item.id)
        await session.commit()
        return public(item)

    @router.post("/brands/{brand_id}/search")
    async def search(
        brand_id: str, data: c.SearchInput, who=Depends(identity), session=Depends(db)
    ):
        await find(session, Brand, who["organization"].id, brand_id)
        return {
            "method": "lexical_overlap",
            "passages": await retrieve(
                session, who["organization"].id, brand_id, data.query, data.limit
            ),
        }

    @router.get("/budgets/current")
    async def current_budget(who=Depends(identity), session=Depends(db)):
        return public(await ensure_budget(session, who["organization"].id))

    @router.put("/budgets/current")
    async def update_budget(
        data: c.BudgetInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session, owner=True)
        item = await ensure_budget(session, who["organization"].id)
        if data.limit_micros < item.spent_micros + item.reserved_micros:
            raise HTTPException(409, "limit_below_committed_spend")
        item.limit_micros, item.daily_send_cap = data.limit_micros, data.daily_send_cap
        await audited(session, who, request, "budget.updated", item.id)
        await session.commit()
        return public(item)

    @router.post("/leads/import")
    async def import_leads(
        data: c.LeadImport, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        created, duplicates = [], []
        for entry in data.leads:
            await find(session, Brand, who["organization"].id, entry.brand_id)
            prior = await session.scalar(
                select(Lead).where(
                    Lead.organization_id == who["organization"].id, Lead.email == entry.email
                )
            )
            if prior:
                duplicates.append(entry.email)
                continue
            item = Lead(organization_id=who["organization"].id, **entry.model_dump())
            session.add(item)
            await session.flush()
            await dispatch(session, who["organization"].id, "lead.created", item, item.id)
            session.add(
                Activity(
                    organization_id=who["organization"].id,
                    lead_id=item.id,
                    actor_id=who["user"].id,
                    action="lead.created",
                    detail="Imported with source and basis evidence",
                )
            )
            created.append(public(item))
        await audited(session, who, request, "leads.imported")
        await session.commit()
        return {"created": created, "duplicates": duplicates}

    @router.post("/leads/{lead_id}/score")
    async def score_lead(
        lead_id: str, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        item = await find(session, Lead, who["organization"].id, lead_id)
        if item.status == "suppressed":
            raise HTTPException(403, "suppressed_recipient")
        item.score = min(
            100,
            (25 if item.company else 0)
            + (20 if item.domain else 0)
            + item.source_confidence // 4
            + (30 if item.lawful_basis != "not_established" else 0),
        )
        item.status = "qualified" if item.score >= 65 else "scored"
        session.add(
            Activity(
                organization_id=who["organization"].id,
                lead_id=item.id,
                actor_id=who["user"].id,
                action="lead.scored",
                detail=f"deterministic-v1: {item.score}",
            )
        )
        await session.commit()
        return public(item)

    @router.put("/leads/{lead_id}/stage")
    async def stage(
        lead_id: str,
        data: c.StageInput,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await write(request, who, session)
        item = await find(session, Lead, who["organization"].id, lead_id)
        if item.status == "suppressed":
            raise HTTPException(403, "suppressed_recipient")
        if data.status == "converted":
            raise HTTPException(403, "conversion_requires_verified_payment_event")
        item.status = data.status
        session.add(
            Activity(
                organization_id=who["organization"].id,
                lead_id=item.id,
                actor_id=who["user"].id,
                action="lead.stage_changed",
                detail=data.reason,
            )
        )
        await audited(session, who, request, "lead.updated", item.id)
        await session.commit()
        return public(item)

    @router.post("/suppressions", status_code=201)
    async def suppression(
        data: c.SuppressInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        await suppress(session, who["organization"].id, data.email, data.reason)
        await audited(session, who, request, "lead.suppressed")
        await session.commit()
        return {"status": "suppressed"}

    @router.post("/drafts", status_code=202)
    async def make_draft(
        data: c.DraftInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        lead = await find(session, Lead, who["organization"].id, data.lead_id)
        if lead.status == "suppressed":
            raise HTTPException(403, "suppressed_recipient")
        return public(
            await runtime.enqueue(
                session,
                who["organization"].id,
                who["user"].id,
                "draft",
                "AGT-07",
                data.idempotency_key,
                {"lead_id": data.lead_id},
            )
        )

    @router.put("/drafts/{draft_id}")
    async def edit_draft(
        draft_id: str,
        data: c.DraftEdit,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await write(request, who, session)
        item = await find(session, Draft, who["organization"].id, draft_id)
        if item.status not in {"draft", "pending_approval"}:
            raise HTTPException(409, "sent_draft_immutable")
        if item.version != data.expected_version:
            raise HTTPException(409, "draft_changed_refresh_before_editing")
        lead = await find(session, Lead, who["organization"].id, item.lead_id)
        brand = await find(session, Brand, who["organization"].id, lead.brand_id)
        await guard_draft(session, brand, lead, data.subject, data.body, item.claims)
        item.subject, item.body = data.subject, data.body
        item.version += 1
        item.status = "draft"
        pending = (
            await session.scalars(
                select(Approval).where(
                    Approval.organization_id == who["organization"].id,
                    Approval.status.in_(["pending", "approved"]),
                )
            )
        ).all()
        for authorization in pending:
            direct = authorization.subject_type == "draft" and authorization.subject_id == item.id
            batch = any(
                draft.get("draft_id") == item.id
                for draft in authorization.payload.get("drafts", [])
            )
            if direct or batch:
                authorization.status = "revoked"
        await audited(session, who, request, "draft.updated_approvals_revoked", item.id)
        await session.commit()
        return public(item)

    @router.post("/drafts/{draft_id}/request-approval", status_code=201)
    async def draft_approval(
        draft_id: str, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        item = await find(session, Draft, who["organization"].id, draft_id)
        if item.status not in {"draft", "pending_approval"}:
            raise HTTPException(409, "already_sent")
        approval = await freeze(
            session,
            who["organization"].id,
            who["user"].id,
            "draft",
            item.id,
            "send_email",
            draft_payload(item),
        )
        item.status = "pending_approval"
        await session.commit()
        return public(approval)

    @router.post("/approvals/{approval_id}/decision")
    async def decision(
        approval_id: str,
        data: c.Decision,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await require(session, request, who, {"owner", "admin"})
        item = await find(session, Approval, who["organization"].id, approval_id)
        if item.action_class == "send_bulk_campaign" and who["role"] != "owner":
            raise HTTPException(403, "owner_required")
        changed = await session.execute(
            update(Approval)
            .where(
                Approval.id == item.id,
                Approval.status == "pending",
                Approval.expires_at > time.time(),
            )
            .values(status=data.decision, decided_by=who["user"].id, decided_at=time.time())
        )
        if not changed.rowcount:
            raise HTTPException(409, "approval_not_pending_or_expired")
        await audited(session, who, request, "approval.decided", item.id)
        await session.commit()
        await session.refresh(item)
        return public(item)

    @router.post("/effects/execute")
    async def effect(data: c.Execute, request: Request, who=Depends(identity), session=Depends(db)):
        await write(request, who, session)
        org_id, actor_id = who["organization"].id, who["user"].id
        try:
            return await execute(
                session,
                settings,
                org_id,
                actor_id,
                data.approval_id,
                data.idempotency_key,
                data.execution_mode,
            )
        except HTTPException as error:
            await session.rollback()
            await record(
                session,
                org_id,
                actor_id,
                "effect.refused",
                data.approval_id,
                decision=str(error.detail),
                trace=request.state.trace_id,
            )
            await session.commit()
            raise

    @router.post("/inbox/simulate", status_code=201)
    async def inbound(
        data: c.Inbound, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        lead = await find(session, Lead, who["organization"].id, data.lead_id)
        previous = await session.scalar(
            select(Message).where(
                Message.organization_id == who["organization"].id,
                Message.idempotency_key == data.idempotency_key,
            )
        )
        if previous:
            if previous.lead_id != lead.id or previous.body != data.body:
                raise HTTPException(409, "idempotency_key_payload_conflict")
            return public(previous)
        classification = classify(data.body)
        if classification["label"] in {"unsubscribe", "complaint"}:
            await suppress(
                session,
                who["organization"].id,
                lead.email,
                "opt_out" if classification["label"] == "unsubscribe" else "complaint",
            )
        elif (
            classification["label"] not in {"auto_reply", "bounce_notice"}
            and lead.status != "suppressed"
        ):
            lead.status = "replied"
        item = Message(
            organization_id=who["organization"].id,
            lead_id=lead.id,
            direction="inbound",
            subject=data.subject,
            body=data.body,
            status="received",
            provider_id="sandbox:" + data.idempotency_key,
            classification=classification,
            idempotency_key=data.idempotency_key,
            simulated=True,
        )
        session.add(item)
        await session.flush()
        await audited(session, who, request, "message.received", item.id)
        if classification["label"] not in {"auto_reply", "bounce_notice"}:
            await session.execute(
                update(Enrollment)
                .where(
                    Enrollment.organization_id == who["organization"].id,
                    Enrollment.lead_id == lead.id,
                )
                .values(status="stopped")
            )
        await dispatch(session, who["organization"].id, "message.received", item, item.id)
        await session.commit()
        return public(item)

    @router.post("/messages/{message_id}/draft-reply", status_code=202)
    async def reply(
        message_id: str, data: c.Keyed, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        item = await find(session, Message, who["organization"].id, message_id)
        if item.direction != "inbound" or item.classification.get("label") not in {
            "interested",
            "meeting_request",
        }:
            raise HTTPException(409, "reply_requires_human_or_no_reply")
        lead = await find(session, Lead, who["organization"].id, item.lead_id)
        if lead.status == "suppressed":
            raise HTTPException(403, "suppressed_recipient")
        return public(
            await runtime.enqueue(
                session,
                who["organization"].id,
                who["user"].id,
                "reply",
                "AGT-08",
                data.idempotency_key,
                {"lead_id": lead.id, "message_id": item.id},
            )
        )

    @router.post("/content/generate", status_code=202)
    async def content(
        data: c.ContentInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        await find(session, Brand, who["organization"].id, data.brand_id)
        agent = {"seo": "AGT-13", "social": "AGT-14", "creative_brief": "AGT-15"}.get(
            data.type, "AGT-06"
        )
        return public(
            await runtime.enqueue(
                session,
                who["organization"].id,
                who["user"].id,
                data.type,
                agent,
                data.idempotency_key,
                {"brand_id": data.brand_id, "topic": data.topic, "content_type": data.type},
            )
        )

    @router.post("/content/{content_id}/request-approval", status_code=201)
    async def content_approval(
        content_id: str, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        item = await find(session, Content, who["organization"].id, content_id)
        approval = await freeze(
            session,
            who["organization"].id,
            who["user"].id,
            "content",
            item.id,
            "publish_content",
            {"content_id": item.id, "title": item.title, "body": item.body},
        )
        await session.commit()
        return public(approval)

    @router.post("/meetings/propose", status_code=201)
    async def propose(
        data: c.MeetingInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        lead = await find(session, Lead, who["organization"].id, data.lead_id)
        if lead.status == "suppressed":
            raise HTTPException(403, "suppressed_recipient")
        if data.starts_at <= time.time():
            raise HTTPException(422, "meeting_in_past")
        item = Meeting(
            organization_id=who["organization"].id,
            lead_id=lead.id,
            title=data.title,
            starts_at=data.starts_at,
            ends_at=data.starts_at + data.duration_minutes * 60,
            timezone=data.timezone,
        )
        session.add(item)
        await session.flush()
        approval = await freeze(
            session,
            who["organization"].id,
            who["user"].id,
            "meeting",
            item.id,
            "book_meeting",
            {
                "meeting_id": item.id,
                "lead_id": lead.id,
                "title": item.title,
                "starts_at": item.starts_at,
                "ends_at": item.ends_at,
                "timezone": item.timezone,
            },
        )
        await session.commit()
        return {"meeting": public(item), "approval": public(approval)}

    @router.post("/campaigns", status_code=201)
    async def campaign(
        data: c.CampaignInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        await find(session, Brand, who["organization"].id, data.brand_id)
        if len(set(data.lead_ids)) != len(data.lead_ids):
            raise HTTPException(422, "duplicate_campaign_contact")
        for lead_id in data.lead_ids:
            lead = await find(session, Lead, who["organization"].id, lead_id)
            if lead.brand_id != data.brand_id:
                raise HTTPException(422, "campaign_brand_mismatch")
        item = Campaign(organization_id=who["organization"].id, **data.model_dump())
        session.add(item)
        await session.flush()
        await audited(session, who, request, "campaign.created", item.id)
        await session.commit()
        return public(item)

    @router.post("/campaigns/{campaign_id}/request-approval", status_code=201)
    async def campaign_approval(
        campaign_id: str, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        item = await find(session, Campaign, who["organization"].id, campaign_id)
        if item.status == "completed":
            raise HTTPException(409, "campaign_completed")
        drafts = []
        for lead_id in item.lead_ids:
            draft = await session.scalar(
                select(Draft)
                .where(
                    Draft.organization_id == who["organization"].id,
                    Draft.lead_id == lead_id,
                    Draft.status.in_(["draft", "pending_approval"]),
                )
                .order_by(Draft.created_at.desc())
            )
            if not draft:
                raise HTTPException(409, "campaign_draft_missing")
            drafts.append(draft_payload(draft))
        approval = await freeze(
            session,
            who["organization"].id,
            who["user"].id,
            "campaign",
            item.id,
            "send_bulk_campaign",
            {
                "campaign_id": item.id,
                "name": item.name,
                "budget_micros": item.budget_micros,
                "drafts": drafts,
            },
        )
        item.status = "pending_approval"
        await session.commit()
        return public(approval)

    @router.post("/campaigns/{campaign_id}/pause")
    async def pause_campaign(
        campaign_id: str, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        item = await find(session, Campaign, who["organization"].id, campaign_id)
        if item.status == "completed":
            raise HTTPException(409, "campaign_completed")
        item.status = "paused"
        await audited(session, who, request, "campaign.paused", item.id)
        await session.commit()
        return public(item)

    @router.post("/checkouts", status_code=201)
    async def checkout(
        data: c.CheckoutInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session, owner=True)
        await find(session, Lead, who["organization"].id, data.lead_id)
        item = Checkout(
            organization_id=who["organization"].id,
            provider_ref="sandbox:" + str(uuid4()),
            **data.model_dump(exclude={"execution_mode"}),
        )
        session.add(item)
        await session.flush()
        await audited(session, who, request, "checkout.created", item.id)
        if data.execution_mode == "live":
            connection = await active(session, settings, who["organization"].id, "stripe")
            if not connection:
                raise HTTPException(409, "verified_active_provider_required")
            item.provider_ref, item.status = "pending:" + item.id, "creating"
            await runtime.enqueue(
                session,
                who["organization"].id,
                who["user"].id,
                "checkout",
                "AGT-08",
                "checkout:" + item.id,
                {
                    "checkout_id": item.id,
                    "connection_id": connection["id"],
                    "connection_version": connection["version"],
                },
            )
            return {**public(item), "simulated": False}
        await session.commit()
        return {**public(item), "simulated": True}

    @router.post("/checkouts/{checkout_id}/simulate-payment")
    async def simulate_payment(
        checkout_id: str,
        data: c.SandboxPayment,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await write(request, who, session, owner=True)
        item = await find(session, Checkout, who["organization"].id, checkout_id)
        if not item.provider_ref.startswith("sandbox:"):
            raise HTTPException(403, "cannot_simulate_real_checkout")
        body = json.dumps(
            {
                "event_id": f"{who['organization'].id}:{data.event_id}",
                "checkout_ref": item.provider_ref,
                "type": "payment.succeeded",
                "amount_minor": item.amount_minor,
                "currency": item.currency,
            }
        ).encode()
        timestamp = int(time.time())
        result = await payment_event(
            session,
            settings,
            body,
            timestamp,
            signature(settings.payment_webhook_secret, timestamp, body),
        )
        await audited(session, who, request, "payment.simulated", item.id)
        await session.commit()
        return result

    @router.post("/webhooks/payments")
    async def webhook(request: Request, session=Depends(db)):
        return await payment_event(
            session,
            settings,
            await request.body(),
            request.headers.get("x-webhook-timestamp"),
            request.headers.get("x-webhook-signature"),
        )

    @router.put("/customers/{customer_id}/onboarding")
    async def onboarding(
        customer_id: str,
        data: c.OnboardingInput,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await write(request, who, session)
        item = await find(session, Customer, who["organization"].id, customer_id)
        allowed = {step["step"] for step in item.onboarding}
        if not set(data.completed) <= allowed:
            raise HTTPException(422, "unknown_onboarding_step")
        item.onboarding = [
            {**step, "done": step["step"] in data.completed} for step in item.onboarding
        ]
        await audited(session, who, request, "customer.onboarding_updated", item.id)
        await session.commit()
        return public(item)

    @router.post("/support", status_code=201)
    async def support(
        data: c.SupportInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        customer = await find(session, Customer, who["organization"].id, data.customer_id)
        escalate = any(
            term in (data.subject + data.body).lower()
            for term in ["refund", "legal", "contract", "dispute", "cancel"]
        )
        item = SupportThread(
            organization_id=who["organization"].id,
            **data.model_dump(),
            status="escalated" if escalate else "open",
        )
        session.add(item)
        customer.health_score = max(0, 100 - (30 if escalate else 10))
        await session.flush()
        await audited(session, who, request, "support.created", item.id)
        await session.commit()
        return public(item)

    @router.put("/support/{thread_id}")
    async def support_response(
        thread_id: str,
        data: c.SupportResponse,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await write(request, who, session)
        item = await find(session, SupportThread, who["organization"].id, thread_id)
        if item.status == "escalated" and who["role"] not in {"owner", "admin"}:
            raise HTTPException(403, "escalation_requires_admin")
        item.response, item.status = data.response, data.status
        await audited(session, who, request, "support.updated", item.id)
        await session.commit()
        return public(item)

    @router.post("/workflows", status_code=201)
    async def workflow(
        data: c.WorkflowInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        combinations = {
            "lead.created": {"score_lead", "notify_owner"},
            "message.received": {"notify_owner"},
            "payment.succeeded": {"onboarding_checklist", "notify_owner"},
        }
        if data.action not in combinations[data.trigger]:
            raise HTTPException(422, "incompatible_workflow_action")
        item = Workflow(organization_id=who["organization"].id, **data.model_dump())
        session.add(item)
        await session.flush()
        await audited(session, who, request, "workflow.created", item.id)
        await session.commit()
        return public(item)

    @router.post("/workflows/{workflow_id}/run")
    async def run_workflow(
        workflow_id: str,
        data: c.WorkflowEvent,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await write(request, who, session)
        org_id = who["organization"].id
        item = await find(session, Workflow, org_id, workflow_id)
        if not item.enabled:
            raise HTTPException(409, "workflow_disabled")
        prior = await session.scalar(
            select(WorkflowRun).where(
                WorkflowRun.organization_id == org_id,
                WorkflowRun.workflow_id == item.id,
                WorkflowRun.event_id == data.idempotency_key,
            )
        )
        if prior:
            return public(prior)
        model = {"lead.created": Lead, "message.received": Message, "payment.succeeded": Payment}[
            item.trigger
        ]
        subject = await find(session, model, org_id, data.subject_id)
        output = {"action": item.action, "subject_id": subject.id, "external_effects": 0}
        if item.action == "score_lead":
            if subject.status == "suppressed":
                raise HTTPException(403, "suppressed_recipient")
            subject.score = min(
                100,
                (25 if subject.company else 0)
                + (20 if subject.domain else 0)
                + subject.source_confidence // 4
                + (30 if subject.lawful_basis != "not_established" else 0),
            )
            subject.status = "qualified" if subject.score >= 65 else "scored"
            output["score"] = subject.score
        run = WorkflowRun(
            organization_id=org_id,
            workflow_id=item.id,
            event_id=data.idempotency_key,
            status="succeeded",
            output=output,
        )
        session.add(run)
        await session.flush()
        await audited(session, who, request, "workflow.ran", run.id)
        await session.commit()
        return public(run)

    @router.post("/learning", status_code=201)
    async def learning(
        data: c.LearningInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        for evidence_id in data.evidence:
            found = False
            for model in (Task, Message, Payment, Campaign, Plan):
                if await session.scalar(
                    select(model.id).where(
                        model.organization_id == who["organization"].id, model.id == evidence_id
                    )
                ):
                    found = True
                    break
            if not found:
                raise HTTPException(422, "unknown_or_cross_tenant_evidence")
        item = Learning(organization_id=who["organization"].id, **data.model_dump())
        session.add(item)
        await session.flush()
        await audited(session, who, request, "learning.created", item.id)
        await session.commit()
        return public(item)

    @router.post("/tools/{tool_id}/invoke")
    async def tool(
        tool_id: str,
        data: c.ToolInput,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        agent = AGENTS.get(data.agent_id)
        configured = await session.scalar(
            select(Agent).where(
                Agent.organization_id == who["organization"].id, Agent.role_id == data.agent_id
            )
        )
        if not agent or tool_id not in agent["tools"] or (configured and not configured.enabled):
            await audited(session, who, request, "tool.permission_refused", tool_id)
            await session.commit()
            raise HTTPException(403, "agent_permission_ceiling")
        if tool_id == "TLS-02":
            brand_id = str(data.args.get("brand_id", ""))
            await find(session, Brand, who["organization"].id, brand_id)
            return {
                "passages": await retrieve(
                    session, who["organization"].id, brand_id, str(data.args.get("query", ""))[:500]
                )
            }
        if tool_id == "TLS-17":
            return await analytics(who, session)
        await audited(session, who, request, "tool.unregistered_or_unavailable", tool_id)
        await session.commit()
        raise HTTPException(403, "tool_requires_workflow_gateway")

    @router.get("/analytics")
    async def analytics(who=Depends(identity), session=Depends(db)):
        org_id = who["organization"].id
        counts = {}
        for name, model in [
            ("leads", Lead),
            ("drafts", Draft),
            ("messages", Message),
            ("meetings", Meeting),
            ("customers", Customer),
            ("tasks", Task),
        ]:
            counts[name] = await session.scalar(
                select(func.count()).select_from(model).where(model.organization_id == org_id)
            )
        messages = (
            await session.scalars(select(Message).where(Message.organization_id == org_id))
        ).all()
        outbound = [message for message in messages if message.direction == "outbound"]
        accepted = [
            message
            for message in outbound
            if message.status in {"sent", "delivered", "bounced", "complained"}
        ]
        delivered_leads = {message.lead_id for message in accepted}
        human_replies = [
            message
            for message in messages
            if message.direction == "inbound"
            and message.classification.get("label") not in {"auto_reply", "bounce_notice"}
        ]
        usage = (
            await session.scalars(select(ModelUsage).where(ModelUsage.organization_id == org_id))
        ).all()
        payments = (
            await session.scalars(select(Payment).where(Payment.organization_id == org_id))
        ).all()
        expenses = (
            await session.scalars(select(Expense).where(Expense.organization_id == org_id))
        ).all()
        total_micros = sum(entry.cost_micros for entry in usage) + sum(
            entry.amount_micros for entry in expenses
        )
        qualified = await session.scalar(
            select(func.count())
            .select_from(Lead)
            .where(Lead.organization_id == org_id, Lead.score >= 65)
        )
        simulated_revenue = {}
        real_revenue = {}
        for payment in payments:
            bucket = simulated_revenue if payment.simulated else real_revenue
            bucket[payment.currency] = bucket.get(payment.currency, 0) + payment.amount_minor
        counts.update(
            {
                "sent": len(accepted),
                "bounced": sum(message.status == "bounced" for message in outbound),
                "complaints": sum(message.status == "complained" for message in outbound),
                "queued_sends": sum(
                    message.status in {"queued", "dispatching"} for message in outbound
                ),
                "real_sends": sum(not message.simulated for message in accepted),
                "sandbox_sends": sum(message.simulated for message in accepted),
                "human_replies": len(human_replies),
                "reply_rate": min(
                    1,
                    len({m.lead_id for m in human_replies if m.lead_id in delivered_leads})
                    / max(1, len(delivered_leads)),
                ),
                "model_calls": len(usage),
                "cost_micros": sum(item.cost_micros for item in usage),
                "simulated_revenue_minor": simulated_revenue,
                "verified_revenue_minor": real_revenue,
                "by_agent_micros": dict(
                    Counter(
                        {
                            agent: sum(item.cost_micros for item in usage if item.agent_id == agent)
                            for agent in {item.agent_id for item in usage}
                        }
                    )
                ),
                "recorded_expenses_micros": sum(entry.amount_micros for entry in expenses),
                "real_expenses_micros": sum(
                    entry.amount_micros for entry in expenses if not entry.simulated
                ),
                "sandbox_expenses_micros": sum(
                    entry.amount_micros for entry in expenses if entry.simulated
                ),
                "recorded_total_cost_micros": total_micros,
                "recorded_cpl_micros": total_micros / qualified if qualified else None,
                "recorded_cac_micros": total_micros / counts["customers"]
                if counts["customers"]
                else None,
                "cost_note": (
                    "Recorded-cost ratios combine labelled sandbox and real records. "
                    "Unknown charges are held separately. "
                    "Include all expenses before treating them "
                    "as fully loaded CAC/CPL."
                ),
                "mode": settings.provider_mode,
                "simulated_deliveries": sum(m.simulated for m in accepted),
                "unsettled_model_attempts": sum(not item.settled for item in usage),
                "held_model_reservation_micros": sum(
                    item.reserved_micros for item in usage if not item.settled
                ),
            }
        )
        events = (
            await session.scalars(
                select(ProviderEvent).where(ProviderEvent.organization_id == org_id)
            )
        ).all()
        refunds = {"sandbox": {}, "real": {}}
        for event in events:
            if event.kind == "charge.refunded":
                bucket = refunds["sandbox" if event.simulated else "real"]
                bucket[event.currency] = bucket.get(event.currency, 0) - event.amount_minor
        counts["refunds_minor"] = refunds
        counts["net_simulated_revenue_minor"] = {
            currency: simulated_revenue.get(currency, 0) - refunds["sandbox"].get(currency, 0)
            for currency in set(simulated_revenue) | set(refunds["sandbox"])
        }
        counts["net_verified_revenue_minor"] = {
            currency: real_revenue.get(currency, 0) - refunds["real"].get(currency, 0)
            for currency in set(real_revenue) | set(refunds["real"])
        }
        return counts

    @router.post("/leads/import-csv")
    async def import_csv(
        data: c.CSVImport, request: Request, who=Depends(identity), session=Depends(db)
    ):
        try:
            parsed = list(csv.DictReader(io.StringIO(data.content)))
            if not parsed or len(parsed) > 100:
                raise ValueError("CSV needs between 1 and 100 contact rows")
            entries = [c.LeadInput(brand_id=data.brand_id, **row) for row in parsed]
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)[:300]) from None
        return await import_leads(c.LeadImport(leads=entries), request, who, session)

    @router.post("/expenses", status_code=201)
    async def expense(
        data: c.ExpenseInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session, owner=True)
        item = Expense(
            organization_id=who["organization"].id,
            **data.model_dump(),
        )
        session.add(item)
        await session.flush()
        await audited(session, who, request, "expense.recorded", item.id)
        await session.commit()
        return public(item)

    @router.post("/sequences", status_code=201)
    async def sequence(
        data: c.SequenceInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        await find(session, Brand, who["organization"].id, data.brand_id)
        item = Sequence(organization_id=who["organization"].id, **data.model_dump())
        session.add(item)
        await session.flush()
        await audited(session, who, request, "sequence.created", item.id)
        await session.commit()
        return public(item)

    @router.post("/sequences/{sequence_id}/enroll", status_code=201)
    async def enroll(
        sequence_id: str,
        data: c.EnrollInput,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await write(request, who, session)
        item = await find(session, Sequence, who["organization"].id, sequence_id)
        lead = await find(session, Lead, who["organization"].id, data.lead_id)
        if lead.brand_id != item.brand_id or lead.status == "suppressed":
            raise HTTPException(422, "sequence_contact_not_eligible")
        prior = await session.scalar(
            select(Enrollment).where(
                Enrollment.organization_id == who["organization"].id,
                Enrollment.sequence_id == item.id,
                Enrollment.lead_id == lead.id,
            )
        )
        if prior:
            return public(prior)
        enrollment = Enrollment(
            organization_id=who["organization"].id,
            sequence_id=item.id,
            lead_id=lead.id,
            created_by=who["user"].id,
            next_at=time.time() + item.delay_days * 86400,
        )
        session.add(enrollment)
        await session.flush()
        await audited(session, who, request, "sequence.enrolled", enrollment.id)
        await session.commit()
        return public(enrollment)

    @router.post("/notifications/{notification_id}/read")
    async def read_notification(
        notification_id: str, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await write(request, who, session)
        item = await find(session, Notification, who["organization"].id, notification_id)
        item.read = True
        await session.commit()
        return public(item)

    @router.get("/exports/workspace")
    async def export_workspace(request: Request, who=Depends(identity), session=Depends(db)):
        await require(session, request, who, {"owner"}, writes=False)
        exported, truncated = {}, []
        for name, model in {"brands": Brand, **RESOURCES}.items():
            result = (
                await session.scalars(
                    select(model)
                    .where(model.organization_id == who["organization"].id)
                    .limit(10001)
                )
            ).all()
            exported[name] = [public(row) for row in result[:10000]]
            if len(result) > 10000:
                truncated.append(name)
        await audited(session, who, request, "workspace.exported", who["organization"].id)
        await session.commit()
        return {
            "format": "ai-mos-workspace-v1",
            "organization_id": who["organization"].id,
            "mode": settings.provider_mode,
            "data": exported,
            "truncated_resources": truncated,
        }

    app.include_router(router)
