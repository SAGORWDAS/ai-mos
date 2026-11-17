"""Reusable campaign preparation. Business facts are runtime input, never build input."""

from types import SimpleNamespace
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select

from app.growth.contracts import CommandInput
from app.growth.effects import draft_payload, freeze
from app.growth.models import Command, Content, Draft, Integration, Lead, Task, TaskDependency
from app.growth.runtime import find, public, record
from app.models import Brand


class Start(CommandInput):
    lead_ids: list[str] = Field(default_factory=list, max_length=20)
    search_query: str = Field(default="", max_length=300)
    connected_research: bool = False


def install_autopilot(app, runtime, settings, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.get("/setup/readiness")
    async def readiness(who=Depends(identity), session=Depends(db)):
        org_id = who["organization"].id
        connections = (
            await session.scalars(select(Integration).where(Integration.organization_id == org_id))
        ).all()
        base = settings.public_api_url.rstrip("/")
        guides = {
            "openrouter": ("AI planning and copy", "API key and exact model ID"),
            "brave": ("Prospect website research", "Brave Search API key"),
            "gmail": ("Individual outreach and inbox", "Google OAuth client and sending address"),
            "resend": ("Opt-in bulk campaigns", "API key, verified sender and webhook secret"),
            "calendar": ("Meeting bookings", "Google OAuth client and calendar ID"),
            "stripe": ("Checkout and payment tracking", "Merchant account, key and webhook secret"),
        }
        providers = []
        for provider, (purpose, needs) in guides.items():
            item = next((row for row in connections if row.provider == provider), None)
            callback = ""
            if provider in {"gmail", "calendar"}:
                callback = f"{base}/v1/oauth/google/{org_id}/{provider}/callback"
            elif provider in {"stripe", "resend"}:
                callback = f"{base}/v1/webhooks/{provider}/{org_id}"
            providers.append(
                {
                    "provider": provider,
                    "purpose": purpose,
                    "needs": needs,
                    "status": item.status if item else "not_connected",
                    "enabled": bool(item and item.status == "verified" and item.enabled),
                    "callback_url": callback,
                }
            )
        return {
            "platform_available": True,
            "business_details_required_to_install": False,
            "business_details_entered": "Inside Brand Brain when starting a campaign",
            "providers": providers,
            "hosting": {
                "postgresql": settings.database_url.startswith("postgresql"),
                "https_callbacks": urlsplit(base).scheme == "https",
                "secure_cookies": settings.secure_cookies,
            },
            "production_ready": False,
            "production_gate": "Production deployment review and live acceptance remain required",
            "live_checks": [
                "Model output quality and actual cost on representative examples",
                "Sending-domain authentication, inbox placement and opt-out drill",
                "Calendar conflict and receipt reconciliation drill",
                "Signed payment retry, renewal and refund/dispute drills",
                "HTTPS, restricted database roles, backup recovery, monitoring and load review",
            ],
        }

    @router.post("/autopilot/start", status_code=202)
    async def start(data: Start, request: Request, who=Depends(identity), session=Depends(db)):
        await require(session, request, who, {"owner"})
        org_id, actor = who["organization"].id, who["user"].id
        brand = await find(session, Brand, org_id, data.brand_id)
        parsed = data.model_dump(exclude={"idempotency_key"})
        parsed["audience"] = data.audience or ", ".join(brand.icp.get("segments", []))
        parsed["auto_execute"] = True
        previous = await session.scalar(
            select(Task).where(
                Task.organization_id == org_id, Task.idempotency_key == data.idempotency_key
            )
        )
        if previous:
            if previous.type != "plan" or previous.input.get("request") != parsed:
                raise HTTPException(409, "idempotency_key_payload_conflict")
            return {"status": "queued", "task": public(previous)}
        missing = [
            key
            for key, present in {
                "offer": bool(brand.positioning.strip()),
                "audience": bool(parsed["audience"].strip()),
                "approved_facts": bool(brand.approved_claims),
            }.items()
            if not present
        ]
        if missing:
            return {
                "status": "needs_information",
                "missing_fields": missing,
                "message": "Add these campaign facts in Brand Brain; the platform is available.",
            }
        if len(set(data.lead_ids)) != len(data.lead_ids):
            raise HTTPException(422, "duplicate_selected_contact")
        for lead_id in data.lead_ids:
            lead = await find(session, Lead, org_id, lead_id)
            if lead.brand_id != brand.id:
                raise HTTPException(422, "contacts_must_match_campaign_brand")
            if lead.status == "suppressed" or lead.lawful_basis == "not_established":
                raise HTTPException(409, "review_contactability_before_automatic_drafting")
        if data.connected_research:
            connection = next(
                (
                    row
                    for row in (
                        await session.scalars(
                            select(Integration).where(Integration.organization_id == org_id)
                        )
                    ).all()
                    if row.provider == "brave"
                ),
                None,
            )
            if not connection or not connection.enabled or connection.status != "verified":
                raise HTTPException(409, "enable_search_connection_first")
            if len(data.search_query.strip()) < 3:
                raise HTTPException(422, "search_query_required")
        command = Command(
            organization_id=org_id,
            created_by=actor,
            brand_id=brand.id,
            raw=data.objective,
            parsed=parsed,
        )
        session.add(command)
        await session.flush()
        task = await runtime.enqueue(
            session,
            org_id,
            actor,
            "plan",
            "AGT-01",
            data.idempotency_key,
            {"command_id": command.id, "request": parsed},
        )
        return {"status": "queued", "task": public(task)}

    app.include_router(router)


async def extend_graph(session, task, command, plan, original_tasks):
    """Only the owner-started endpoint sets auto_execute; external effects are excluded."""
    if not command.parsed.get("auto_execute"):
        return
    children = []
    for index, lead_id in enumerate(command.parsed.get("lead_ids", [])):
        children.append(
            Task(
                organization_id=task.organization_id,
                plan_id=plan.id,
                created_by=task.created_by,
                agent_id="AGT-07",
                type="draft",
                status="created",
                idempotency_key=f"autopilot:{plan.id}:draft:{index}",
                input={"lead_id": lead_id},
            )
        )
    if command.parsed.get("search_query"):
        children.append(
            Task(
                organization_id=task.organization_id,
                plan_id=plan.id,
                created_by=task.created_by,
                agent_id="AGT-02",
                type="autopilot_research",
                status="created",
                idempotency_key=f"autopilot:{plan.id}:search",
                input={
                    "brand_id": plan.brand_id,
                    "query": command.parsed["search_query"],
                    "connected_provider": command.parsed["connected_research"],
                },
            )
        )
    session.add_all(children)
    await session.flush()
    review = Task(
        organization_id=task.organization_id,
        plan_id=plan.id,
        created_by=task.created_by,
        agent_id="AGT-01",
        type="prepare_review",
        status="created",
        idempotency_key=f"autopilot:{plan.id}:review",
        input={"brand_id": plan.brand_id},
    )
    session.add(review)
    await session.flush()
    for parent in list(original_tasks) + [child.id for child in children]:
        session.add(
            TaskDependency(
                organization_id=task.organization_id, task_id=review.id, depends_on_id=parent
            )
        )
    plan.status = "approved"
    await record(
        session, task.organization_id, task.created_by, "autopilot.internal_authorized", plan.id
    )


async def prepare_review(session, task):
    current = await find(session, Task, task.organization_id, task.id)
    if current.input.get("review_result"):
        return current.input["review_result"]
    tasks = (
        await session.scalars(
            select(Task.id).where(
                Task.organization_id == task.organization_id, Task.plan_id == task.plan_id
            )
        )
    ).all()
    approvals = []
    for draft in (
        await session.scalars(
            select(Draft).where(
                Draft.organization_id == task.organization_id, Draft.task_id.in_(tasks)
            )
        )
    ).all():
        approval = await freeze(
            session,
            task.organization_id,
            task.created_by,
            "draft",
            draft.id,
            "send_email",
            draft_payload(draft),
        )
        draft.status = "pending_approval"
        approvals.append(approval.id)
    for content in (
        await session.scalars(
            select(Content).where(
                Content.organization_id == task.organization_id, Content.task_id.in_(tasks)
            )
        )
    ).all():
        approval = await freeze(
            session,
            task.organization_id,
            task.created_by,
            "content",
            content.id,
            "publish_content",
            {"content_id": content.id, "title": content.title, "body": content.body},
        )
        approvals.append(approval.id)
    result = {
        "approval_ids": approvals,
        "next_step": "Review prepared work in Approvals",
        "external_actions_executed": False,
    }
    current.input = {**current.input, "review_result": result}
    await session.commit()
    return result


async def research(runtime, session, task):
    from app.growth.discovery import discover, enrich

    result = await discover(session, runtime.settings, task, runtime.search_transport)
    imported, skipped = [], []
    for suggestion in result.get("results", [])[:3]:
        candidate = SimpleNamespace(
            id=task.id,
            organization_id=task.organization_id,
            created_by=task.created_by,
            attempt=task.attempt,
            input={"brand_id": task.input["brand_id"], "url": suggestion["url"], "company": ""},
        )
        try:
            imported.append(await enrich(session, candidate))
        except HTTPException as error:
            await session.rollback()
            skipped.append({"url": suggestion["url"], "reason": str(error.detail)})
    return {
        **result,
        "page_imports": imported,
        "pages_skipped": skipped,
        "note": "Observed addresses require contactability review before outreach.",
    }
