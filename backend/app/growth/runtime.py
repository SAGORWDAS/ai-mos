import asyncio
import json
import logging
import time
from pathlib import Path
from uuid import uuid4

import yaml
from fastapi import HTTPException
from jsonschema import ValidationError, validate
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from app.growth.connections import active
from app.growth.gateway import GatewayError, ModelGateway
from app.growth.knowledge import claim_sources, draft_text, guard_content, guard_draft, retrieve
from app.growth.models import (
    Agent,
    Checkout,
    Command,
    Content,
    Draft,
    Enrollment,
    Lead,
    Message,
    Plan,
    Sequence,
    Suppression,
    Task,
    TaskDependency,
)
from app.growth.planning_evidence import strategy_seed, validate_research, validate_strategy
from app.growth.providers import ProviderError, StripeProvider
from app.models import AuditLog, Brand, Membership, Organization
from app.observability import emit, task_trace
from app.tenancy import tenant_scope

ROOT = Path(__file__).resolve().parents[3]
if not (ROOT / "spec/agents.yaml").exists():
    ROOT = Path(__file__).resolve().parent / "data"
SPEC = yaml.safe_load((ROOT / "spec/agents.yaml").read_text(encoding="utf-8"))
AGENTS = {item["id"]: item for item in SPEC["agents"]}
log = logging.getLogger("ai_mos.runtime")


def public(row):
    result = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    result.pop("source_fingerprint", None)
    result.pop("scope_hash", None)
    if isinstance(row, Task) and isinstance(result.get("output"), dict):
        result["output"] = {
            key: value for key, value in result["output"].items() if key != "image_base64"
        }
    return result


async def find(session, model, org_id, record_id):
    await tenant_scope(session, organization_id=org_id)
    row = await session.scalar(
        select(model).where(model.id == record_id, model.organization_id == org_id)
    )
    if not row:
        raise HTTPException(404, "not_found")
    return row


async def record(
    session,
    org_id,
    actor_id,
    action,
    subject="",
    decision="allowed",
    trace=None,
    agent_id=None,
    tool_id=None,
):
    await tenant_scope(session, org_id, actor_id)
    task_id = None
    if action.startswith("task."):
        task = await session.scalar(
            select(Task).where(Task.organization_id == org_id, Task.id == subject)
        )
        if task:
            trace = await task_trace(session, org_id, task)
            task_id, agent_id = task.id, task.agent_id
    trace = trace or str(uuid4())
    session.add(
        AuditLog(
            organization_id=org_id,
            actor_id=actor_id,
            action=action,
            subject_id=subject,
            decision=decision,
            trace_id=trace,
        )
    )
    emit(
        action,
        org_id=org_id,
        task_id=task_id,
        actor_id=actor_id,
        trace_id=trace,
        agent_id=agent_id,
        tool_id=tool_id,
        decision=decision,
    )


def acyclic(tasks, dependencies):
    ids = {task["local_id"] for task in tasks}
    if len(ids) != len(tasks):
        raise ValueError("duplicate_task_id")
    graph = {key: [] for key in ids}
    for child, parent in dependencies:
        if child not in ids or parent not in ids:
            raise ValueError("unknown_dependency")
        graph[child].append(parent)
    done, active = set(), set()

    def walk(key):
        if key in active:
            raise ValueError("dependency_cycle")
        if key in done:
            return
        active.add(key)
        for parent in graph[key]:
            walk(parent)
        active.remove(key)
        done.add(key)

    for key in graph:
        walk(key)


class Runtime:
    def __init__(self, factory, settings):
        self.factory, self.settings = factory, settings
        self.gateway = ModelGateway(factory, settings)
        self.search_transport = None
        from app.growth.delivery import Dispatcher

        self.delivery = Dispatcher(factory, settings)
        from app.growth.inbox_schedule import InboxScheduler

        self.inbox = InboxScheduler(factory, settings, self.delivery)

    async def enqueue(self, session, org_id, actor_id, kind, agent_id, key, payload, plan_id=None):
        previous = await session.scalar(
            select(Task).where(Task.organization_id == org_id, Task.idempotency_key == key)
        )
        if previous:
            if previous.type != kind or previous.input != payload:
                raise HTTPException(409, "idempotency_key_payload_conflict")
            return previous
        item = Task(
            organization_id=org_id,
            created_by=actor_id,
            type=kind,
            agent_id=agent_id,
            idempotency_key=key,
            input=payload,
            plan_id=plan_id,
        )
        session.add(item)
        try:
            await session.flush()
            await record(session, org_id, actor_id, "task.created", item.id)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            previous = await session.scalar(
                select(Task).where(Task.organization_id == org_id, Task.idempotency_key == key)
            )
            if previous and previous.type == kind and previous.input == payload:
                return previous
            raise HTTPException(409, "idempotency_key_payload_conflict") from None
        return item

    async def loop(self):
        while True:
            try:
                worked = await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Worker tick failed")
                worked = False
            await asyncio.sleep(0 if worked else self.settings.worker_poll_seconds)

    async def tick(self):
        if await self.delivery.tick():
            return True
        async with self.factory() as session:
            if session.bind.dialect.name == "postgresql":
                claimed_row = (
                    (await session.execute(text("SELECT * FROM claim_next_task()")))
                    .mappings()
                    .first()
                )
                await session.commit()
                if not claimed_row:
                    return await self.sequence_tick(session) or await self.inbox.tick()
                await tenant_scope(session, claimed_row["org_id"], claimed_row["actor_id"])
                task = await session.get(Task, claimed_row["job_id"])
                if task.status == "failed":
                    if task.plan_id:
                        await self.schedule(session, task.organization_id, task.plan_id)
                    return True
            else:
                task = await self.claim_local(session)
                if task is None:
                    return await self.sequence_tick(session) or await self.inbox.tick()
                if task is False:
                    return True
            role = await session.scalar(
                select(Membership.role).where(
                    Membership.organization_id == task.organization_id,
                    Membership.user_id == task.created_by,
                )
            )
            if role not in {"owner", "admin", "member"}:
                task.status, task.error_code = "blocked", "membership_changed"
                await session.commit()
                return True
            configured = await session.scalar(
                select(Agent).where(
                    Agent.organization_id == task.organization_id, Agent.role_id == task.agent_id
                )
            )
            if configured and not configured.enabled:
                task.status, task.error_code = "blocked", "agent_disabled"
                await session.commit()
                return True
            await record(session, task.organization_id, task.created_by, "task.started", task.id)
            await session.commit()
        try:
            output = await self.execute(task)
            async with self.factory() as session:
                await tenant_scope(session, task.organization_id, task.created_by)
                await session.execute(
                    update(Task)
                    .where(
                        Task.id == task.id, Task.status == "running", Task.attempt == task.attempt
                    )
                    .values(
                        status="succeeded",
                        output=output,
                        error_code="",
                        finished_at=time.time(),
                        leased_until=None,
                    )
                )
                await record(
                    session, task.organization_id, task.created_by, "task.succeeded", task.id
                )
                await session.commit()
                if task.plan_id:
                    await self.schedule(session, task.organization_id, task.plan_id)
        except (GatewayError, HTTPException, ValueError, ValidationError) as error:
            code = str(error.detail) if isinstance(error, HTTPException) else str(error)[:120]
            await self.fail(task, code)
        except Exception as error:
            emit(
                "task.unexpected_failure",
                org_id=task.organization_id,
                task_id=task.id,
                agent_id=task.agent_id,
                trace_id=task.id,
                exception_type=type(error).__name__,
            )
            await self.fail(task, "internal_error")
        return True

    async def claim_local(self, session):
        await session.execute(
            update(Task)
            .where(Task.status == "running", Task.leased_until < time.time(), Task.attempt < 3)
            .values(status="ready")
        )
        await session.execute(
            update(Task)
            .where(Task.status == "running", Task.leased_until < time.time(), Task.attempt >= 3)
            .values(status="failed", error_code="attempt_limit")
        )
        await session.commit()
        task = await session.scalar(
            select(Task)
            .join(Organization, Organization.id == Task.organization_id)
            .where(Task.status == "ready", Organization.emergency_stop.is_(False))
            .order_by(Task.created_at)
            .limit(1)
        )
        if not task:
            return None
        changed = await session.execute(
            update(Task)
            .where(Task.id == task.id, Task.status == "ready")
            .values(status="running", attempt=Task.attempt + 1, leased_until=time.time() + 90)
        )
        await session.commit()
        if not changed.rowcount:
            return False
        await session.refresh(task)
        return task

    async def fail(self, task, code):
        async with self.factory() as session:
            await tenant_scope(session, task.organization_id, task.created_by)
            await session.execute(
                update(Task)
                .where(Task.id == task.id, Task.status == "running", Task.attempt == task.attempt)
                .values(
                    status="blocked"
                    if code
                    in {
                        "budget_exhausted",
                        "emergency_stop",
                        "suppressed_recipient",
                        "model_registry_verification_required",
                        "model_request_allowance_exceeded",
                        "model_connection_changed",
                    }
                    else "failed",
                    error_code=code,
                    leased_until=None,
                    finished_at=time.time(),
                )
            )
            await record(
                session,
                task.organization_id,
                task.created_by,
                "task.failed",
                task.id,
                decision=code,
            )
            await session.commit()
            if task.plan_id:
                await self.schedule(session, task.organization_id, task.plan_id)

    async def sequence_tick(self, session):
        if session.bind.dialect.name == "postgresql":
            candidate = (
                (await session.execute(text("SELECT * FROM claim_next_enrollment()")))
                .mappings()
                .first()
            )
            await session.commit()
            if not candidate:
                return False
            await tenant_scope(session, candidate["org_id"], candidate["actor_id"])
            enrollment = await session.get(Enrollment, candidate["enrollment_id"])
        else:
            enrollment = await session.scalar(
                select(Enrollment)
                .join(Organization, Organization.id == Enrollment.organization_id)
                .where(
                    Enrollment.status == "active",
                    Enrollment.next_at <= time.time(),
                    Organization.emergency_stop.is_(False),
                )
                .order_by(Enrollment.next_at)
                .limit(1)
            )
            if not enrollment:
                return False
            changed = await session.execute(
                update(Enrollment)
                .where(
                    Enrollment.id == enrollment.id,
                    Enrollment.status == "active",
                    Enrollment.next_at <= time.time(),
                )
                .values(status="processing")
            )
            if not changed.rowcount:
                await session.rollback()
                return True
        sequence = await find(session, Sequence, enrollment.organization_id, enrollment.sequence_id)
        lead = await find(session, Lead, enrollment.organization_id, enrollment.lead_id)
        if not sequence.enabled or lead.status in {
            "suppressed",
            "replied",
            "meeting_set",
            "converted",
        }:
            enrollment.status = "stopped"
        elif enrollment.step >= sequence.max_steps:
            enrollment.status = "completed"
        else:
            step_key = f"sequence:{enrollment.id}:{enrollment.step}"
            task = await session.scalar(
                select(Task).where(
                    Task.organization_id == enrollment.organization_id,
                    Task.idempotency_key == step_key,
                )
            )
            if not task:
                session.add(
                    Task(
                        organization_id=enrollment.organization_id,
                        created_by=enrollment.created_by,
                        agent_id="AGT-09",
                        type="draft",
                        idempotency_key=step_key,
                        input={"lead_id": lead.id, "sequence_id": sequence.id, "auto_review": True},
                    )
                )
            enrollment.step += 1
            enrollment.next_at = time.time() + sequence.delay_days * 86400
            enrollment.status = "active"
            await record(
                session,
                enrollment.organization_id,
                enrollment.created_by,
                "sequence.draft_queued",
                enrollment.id,
            )
        await session.commit()
        return True

    async def schedule(self, session, org_id, plan_id):
        plan = await find(session, Plan, org_id, plan_id)
        if plan.status not in {"approved", "running"}:
            return
        rows = (
            await session.scalars(
                select(Task).where(Task.organization_id == org_id, Task.plan_id == plan_id)
            )
        ).all()
        states = {item.id: item.status for item in rows}
        for item in rows:
            if item.status != "created":
                continue
            parents = (
                await session.scalars(
                    select(TaskDependency.depends_on_id).where(
                        TaskDependency.organization_id == org_id, TaskDependency.task_id == item.id
                    )
                )
            ).all()
            if any(states.get(parent) in {"failed", "blocked", "cancelled"} for parent in parents):
                item.status, item.error_code = "blocked", "dependency_failed"
            elif all(states.get(parent) == "succeeded" for parent in parents):
                item.status = "ready"
        plan.status = "running"
        if rows and all(item.status == "succeeded" for item in rows):
            plan.status = "completed"
        elif any(item.status in {"failed", "blocked", "cancelled"} for item in rows):
            plan.status = "blocked"
        await session.commit()

    async def execute(self, task):
        async with self.factory() as session:
            await self.checkpoint(
                session, task.organization_id, task.id, task.created_by, task.attempt
            )
            org = await session.get(Organization, task.organization_id)
            if org.emergency_stop:
                raise GatewayError("emergency_stop")
            if task.type in {"draft", "reply"}:
                prior = await session.scalar(
                    select(Draft).where(
                        Draft.organization_id == task.organization_id, Draft.task_id == task.id
                    )
                )
                if prior:
                    return {"draft_id": prior.id}
            if task.type == "prepare_review":
                from app.growth.autopilot import prepare_review

                return await prepare_review(session, task)
            if task.type == "autopilot_research":
                from app.growth.autopilot import research

                return await research(self, session, task)
            if task.type == "creative_image":
                from app.growth.creative import generate_image

                return await generate_image(self, session, task)
            if task.type in {
                "content",
                "landing_page",
                "article",
                "seo",
                "social",
                "creative_brief",
            }:
                prior = await session.scalar(
                    select(Content).where(
                        Content.organization_id == task.organization_id, Content.task_id == task.id
                    )
                )
                if prior:
                    return {
                        "content_id": prior.id,
                        "title": prior.title,
                        "body": prior.body,
                        "citations": prior.citations,
                    }
            if task.type in {"embed_document", "semantic_search"}:
                from app.growth.embeddings import execute_embedding

                return await execute_embedding(self, session, task)
            if task.type == "prospect_search":
                from app.growth.discovery import discover

                try:
                    return await discover(session, self.settings, task, self.search_transport)
                except ProviderError as error:
                    raise GatewayError(error.code) from None
            if task.type == "prospect_enrich":
                from app.growth.discovery import enrich

                return await enrich(session, task)
            if task.type == "checkout":
                checkout = await find(
                    session, Checkout, task.organization_id, task.input["checkout_id"]
                )
                connection = await active(session, self.settings, task.organization_id, "stripe")
                if (
                    not connection
                    or connection["id"] != task.input["connection_id"]
                    or connection["version"] != task.input["connection_version"]
                ):
                    raise GatewayError("connection_changed_or_disconnected")
                credentials = connection["credentials"]
                provider = StripeProvider(
                    credentials.get("secret_key", ""), credentials.get("webhook_secret", "")
                )
                await session.commit()
                try:
                    receipt = await provider.checkout(
                        checkout.description,
                        checkout.amount_minor,
                        checkout.currency,
                        credentials.get("success_url", ""),
                        credentials.get("cancel_url", ""),
                        "checkout:" + checkout.id,
                        checkout.recurring,
                        local_ref=checkout.id,
                        org_ref=task.organization_id,
                    )
                except ProviderError as error:
                    checkout.status = "uncertain" if error.uncertain else "failed"
                    await session.commit()
                    raise GatewayError(error.code) from None
                await session.refresh(checkout)
                checkout.provider_ref, checkout.url = receipt["provider_ref"], receipt["url"]
                if checkout.status != "paid":
                    checkout.status = "pending"
                await session.commit()
                return {"checkout_id": checkout.id, "url": checkout.url, "status": "pending"}
            if task.type == "plan":
                command = await find(
                    session, Command, task.organization_id, task.input["command_id"]
                )
                prior = await session.scalar(
                    select(Plan).where(
                        Plan.organization_id == task.organization_id, Plan.command_id == command.id
                    )
                )
                if prior:
                    if command.parsed.get("auto_execute"):
                        await self.schedule(session, task.organization_id, prior.id)
                    return {"plan_id": prior.id}
                brand = await find(session, Brand, task.organization_id, command.brand_id)
                parsed = command.parsed
                seed = self.plan_template(command, brand)
                await session.commit()
                payload = await self.gateway.generate(
                    task,
                    "Create a plan matching this JSON schema and facts. Return only JSON.\n"
                    + json.dumps(
                        {
                            "schema": json.loads((ROOT / "spec/schemas/plan.json").read_text()),
                            "business": public(brand),
                            "objective": parsed,
                        }
                    ),
                    seed,
                    sandbox_only=bool(brand.voice.get("sandbox_only")),
                )
                await self.checkpoint(
                    session, task.organization_id, task.id, task.created_by, task.attempt
                )
                validate(payload, json.loads((ROOT / "spec/schemas/plan.json").read_text()))
                acyclic(payload["tasks"], payload["dependencies"])
                if payload.get("missing_information") or payload["final_status"] != "ready":
                    raise ValueError("plan_needs_information")
                supported = {"research", "strategy", "content", "report"}
                for work in payload["tasks"]:
                    if work["agent_id"] not in AGENTS or work["type"] not in supported:
                        raise ValueError("unsupported_plan_task")
                await self.gateway.remember(session, task, payload)
                # A crash after result persistence must not duplicate the plan.
                plan = await session.scalar(
                    select(Plan).where(
                        Plan.organization_id == task.organization_id, Plan.command_id == command.id
                    )
                )
                if plan:
                    return {"plan_id": plan.id}
                plan = Plan(
                    organization_id=task.organization_id,
                    command_id=command.id,
                    brand_id=brand.id,
                    objective=command.raw,
                    payload=payload,
                )
                session.add(plan)
                await session.flush()
                mapping = {}
                for work in payload["tasks"]:
                    item = Task(
                        organization_id=task.organization_id,
                        plan_id=plan.id,
                        created_by=task.created_by,
                        type=work["type"],
                        agent_id=work["agent_id"],
                        idempotency_key=f"plan:{plan.id}:{work['local_id']}",
                        status="created",
                        input={"brand_id": brand.id, "description": work["description"]},
                    )
                    session.add(item)
                    await session.flush()
                    mapping[work["local_id"]] = item.id
                for child, parent in payload["dependencies"]:
                    session.add(
                        TaskDependency(
                            organization_id=task.organization_id,
                            task_id=mapping[child],
                            depends_on_id=mapping[parent],
                        )
                    )
                command.status = "planned"
                from app.growth.autopilot import extend_graph

                await extend_graph(session, task, command, plan, mapping.values())
                await record(
                    session, task.organization_id, task.created_by, "plan.created", plan.id
                )
                await session.commit()
                if command.parsed.get("auto_execute"):
                    await self.schedule(session, task.organization_id, plan.id)
                return {"plan_id": plan.id, "mode": self.settings.provider_mode}

            if task.type in {"draft", "reply"}:
                lead = await find(session, Lead, task.organization_id, task.input["lead_id"])
                suppressed = await session.scalar(
                    select(Suppression.id).where(
                        Suppression.organization_id == task.organization_id,
                        Suppression.address == lead.email,
                    )
                )
                if suppressed or lead.status == "suppressed":
                    raise GatewayError("suppressed_recipient")
                inbound = None
                if task.type == "reply":
                    inbound = await find(
                        session, Message, task.organization_id, task.input["message_id"]
                    )
                brand = await find(session, Brand, task.organization_id, lead.brand_id)
                citations = await claim_sources(session, brand)
                if not citations:
                    raise ValueError("approved_brand_claim_required")
                selected = citations[:1]
                body = draft_text(brand, lead, selected)
                if inbound:
                    body = "Thanks for your reply.\n\n" + body
                prefix = (
                    "Following up from"
                    if task.input.get("sequence_id") and lead.status == "contacted"
                    else "A question from"
                )
                seed = {
                    "subject": f"{prefix} {brand.name}"[:90],
                    "body": body,
                    "claims": selected,
                    "word_count": len(body.split()),
                    "personalisation": [{"text": lead.personalisation, "evidence_ref": lead.id}]
                    if lead.personalisation and lead.personalisation_evidence
                    else [],
                    "cta": "question",
                    "confidence": 1.0,
                }
                await session.commit()
                output = await self.gateway.generate(
                    task,
                    json.dumps(
                        {
                            "instruction": "Use only the supplied claims; preserve opt-out.",
                            "schema": json.loads(
                                (ROOT / "spec/schemas/outreach_draft.json").read_text()
                            ),
                            "brand": public(brand),
                            "contact": {
                                "name": lead.name,
                                "approved_personalisation": lead.personalisation
                                if lead.personalisation_evidence
                                else "",
                            },
                            "inbound_message": inbound.body if inbound else None,
                            "required_body_template": body,
                            "suggested_subject": seed["subject"],
                            "claims": selected,
                        }
                    ),
                    seed,
                    sandbox_only=bool(brand.voice.get("sandbox_only")),
                )
                await self.checkpoint(
                    session, task.organization_id, task.id, task.created_by, task.attempt
                )
                await session.refresh(brand)
                await session.refresh(lead)
                for correction in range(2):
                    try:
                        validate(
                            output,
                            json.loads((ROOT / "spec/schemas/outreach_draft.json").read_text()),
                        )
                        await guard_draft(
                            session,
                            brand,
                            lead,
                            output["subject"],
                            output["body"],
                            output["claims"],
                        )
                        if "unsubscribe" not in output["body"].lower():
                            raise HTTPException(422, "opt_out_required")
                        break
                    except (HTTPException, ValidationError) as error:
                        if correction:
                            raise
                        reason = (
                            str(error.detail)
                            if isinstance(error, HTTPException)
                            else "schema_invalid"
                        )
                        await session.commit()
                        output = await self.gateway.generate(
                            task,
                            json.dumps(
                                {
                                    "instruction": "Correct once using only approved facts; "
                                    "return the template and preserve the opt-out.",
                                    "rejection": reason,
                                    "approved_output_template": seed,
                                    "schema": json.loads(
                                        (ROOT / "spec/schemas/outreach_draft.json").read_text()
                                    ),
                                }
                            ),
                            seed,
                            sandbox_only=bool(brand.voice.get("sandbox_only")),
                        )
                        await self.checkpoint(
                            session, task.organization_id, task.id, task.created_by, task.attempt
                        )
                        await session.refresh(brand)
                        await session.refresh(lead)
                await self.gateway.remember(session, task, output)
                existing = await session.scalar(
                    select(Draft).where(
                        Draft.organization_id == task.organization_id, Draft.task_id == task.id
                    )
                )
                if existing:
                    return {"draft_id": existing.id}
                draft = Draft(
                    organization_id=task.organization_id,
                    lead_id=lead.id,
                    task_id=task.id,
                    subject=output["subject"],
                    body=output["body"],
                    claims=output["claims"],
                )
                session.add(draft)
                await session.flush()
                if task.input.get("auto_review"):
                    from app.growth.effects import draft_payload, freeze

                    await freeze(
                        session,
                        task.organization_id,
                        task.created_by,
                        "draft",
                        draft.id,
                        "send_email",
                        draft_payload(draft),
                    )
                    draft.status = "pending_approval"
                await record(
                    session, task.organization_id, task.created_by, "draft.created", draft.id
                )
                await session.commit()
                saved_draft_id = draft.id
                if task.type == "reply" and task.input.get("auto_review"):
                    from app.growth.reply_policy import maybe_send

                    await maybe_send(self, session, task, draft)
                return {"draft_id": saved_draft_id, "mode": self.settings.provider_mode}

            brand = await find(session, Brand, task.organization_id, task.input["brand_id"])
            citations = await claim_sources(session, brand)
            if task.type in {
                "content",
                "seo",
                "social",
                "creative_brief",
                "landing_page",
                "article",
            }:
                if not citations:
                    raise ValueError("approved_brand_claim_required")
                seed = {
                    "title": task.input.get("topic", brand.name),
                    "body": brand.positioning + "\n\n" + "\n\n".join(c["text"] for c in citations),
                    "citations": citations,
                }
            elif task.type == "research":
                seed = {
                    "method": "local_evidence_retrieval",
                    "external_research": False,
                    "findings": await retrieve(
                        session, task.organization_id, brand.id, brand.positioning or brand.name
                    ),
                    "limitations": ["No external market data has been retrieved in sandbox mode."],
                }
            elif task.type == "strategy":
                seed = await strategy_seed(session, task, brand)
            elif task.type == "report":
                seed = {
                    "summary": "Internal work completed; external execution needs approval.",
                    "external_effects": 0,
                }
            else:
                raise ValueError("unregistered_task_type")
            await session.commit()
            output = await self.gateway.generate(
                task,
                json.dumps(
                    {
                        "task": task.type,
                        "input": task.input,
                        "brand": public(brand),
                        "required_shape_example": seed,
                    }
                ),
                seed,
                sandbox_only=bool(brand.voice.get("sandbox_only")),
            )
            await self.checkpoint(
                session, task.organization_id, task.id, task.created_by, task.attempt
            )
            await session.refresh(brand)
            if task.type in {"research", "strategy"}:
                try:
                    if task.type == "research":
                        validate_research(output, seed)
                    else:
                        current_seed = await strategy_seed(session, task, brand)
                        if current_seed != seed:
                            raise ValueError("strategy_source_changed_during_generation")
                        validate_strategy(output, seed)
                except (ValueError, TypeError, KeyError):
                    await session.rollback()
                    await self.gateway.reject(task)
                    raise ValueError("research_or_strategy_grounding_rejected") from None
                await self.gateway.remember(session, task, output)
                await session.commit()
            if "body" in seed:
                await guard_content(
                    session,
                    brand,
                    output.get("title", ""),
                    seed["title"],
                    output.get("body", ""),
                    output.get("citations", []),
                )
                content = Content(
                    organization_id=task.organization_id,
                    task_id=task.id,
                    brand_id=brand.id,
                    type=task.input.get("content_type", task.type),
                    title=str(output["title"])[:200],
                    body=output["body"],
                    citations=output["citations"],
                )
                await self.gateway.remember(session, task, output)
                session.add(content)
                await session.flush()
                output["content_id"] = content.id
                await session.commit()
            return output

    @staticmethod
    async def checkpoint(session, org_id, task_id=None, actor_id=None, attempt=None):
        await tenant_scope(session, org_id, actor_id)
        await session.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(emergency_stop=Organization.emergency_stop)
        )
        if await session.scalar(
            select(Organization.emergency_stop).where(Organization.id == org_id)
        ):
            raise GatewayError("emergency_stop")
        if task_id:
            state = await session.execute(
                select(Task.status, Task.attempt).where(
                    Task.organization_id == org_id, Task.id == task_id
                )
            )
            current = state.first()
            if not current or current.status != "running" or current.attempt != attempt:
                raise GatewayError("task_cancelled_or_lease_changed")
        if actor_id:
            role = await session.scalar(
                select(Membership.role).where(
                    Membership.organization_id == org_id, Membership.user_id == actor_id
                )
            )
            if role not in {"owner", "admin", "member"}:
                raise GatewayError("membership_changed")

    @staticmethod
    def plan_template(command, brand):
        parsed = command.parsed
        types = [
            ("research", "AGT-02", "Review supplied brand evidence"),
            ("strategy", "AGT-03", "Define a narrow campaign approach"),
            ("content", "AGT-06", "Create a grounded campaign brief"),
            ("report", "AGT-10", "Summarise internal work and next approvals"),
        ]
        return {
            "objective": command.raw,
            "business_goal": parsed["goal"],
            "target_audience": {
                "segment": parsed["audience"],
                "size_estimate": parsed["target"],
                "geo": brand.icp.get("geographies") or ["Not specified"],
            },
            "execution_plan": (
                "Review evidence, prepare strategy and content, then review results. "
                "External execution is a separate approved action."
            ),
            "assigned_agents": [agent for _, agent, _ in types],
            "tasks": [
                {
                    "local_id": f"t{i + 1}",
                    "type": kind,
                    "agent_id": agent,
                    "description": description,
                    "estimated_cost_usd": 0,
                }
                for i, (kind, agent, description) in enumerate(types)
            ],
            "dependencies": [["t2", "t1"], ["t3", "t2"], ["t4", "t3"]],
            "estimated_cost_usd": 0,
            "required_approvals": [
                {
                    "action_class": "send_email",
                    "reason": "Every outbound message",
                    "approver_role": "owner",
                }
            ],
            "success_metrics": [
                {
                    "metric": "qualified_leads",
                    "target": parsed["target"],
                    "window_days": parsed["window_days"],
                }
            ],
            "risks": [
                {
                    "risk": "The offer and evidence require human validation",
                    "mitigation": "Review brand facts and campaign outputs",
                }
            ],
            "final_status": "ready",
        }
