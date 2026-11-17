"""Reusable campaign preparation. Business facts are runtime input, never build input."""

import asyncio
from types import SimpleNamespace
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, field_validator
from sqlalchemy import select, update

from app.growth.contracts import CommandInput, Keyed
from app.growth.effects import draft_payload, freeze
from app.growth.models import (
    Campaign,
    Command,
    Content,
    Draft,
    Integration,
    Lead,
    Task,
    TaskDependency,
)
from app.growth.qualification import apply_score
from app.growth.runtime import find, public, record
from app.models import Brand, Organization

RESEARCH_DEADLINE_SECONDS = 65


class Start(CommandInput):
    lead_ids: list[str] = Field(default_factory=list, max_length=20)
    search_query: str = Field(default="", max_length=300)
    connected_research: bool = False


class BusinessBrief(Keyed):
    name: str = Field(min_length=1, max_length=120)
    offer: str = Field(min_length=10, max_length=600)
    audience: str = Field(min_length=3, max_length=300)
    objective: str = Field(min_length=8, max_length=500)
    sample: bool = False
    connected_research: bool = False

    @field_validator("offer")
    @classmethod
    def concise_offer(cls, value):
        if len(value.split()) > 80:
            raise ValueError("Keep the approved offer to 80 words or fewer for outreach")
        return value


def install_autopilot(app, runtime, settings, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.get("/setup/readiness")
    async def readiness(who=Depends(identity), session=Depends(db)):
        org_id = who["organization"].id
        connections = (
            await session.scalars(select(Integration).where(Integration.organization_id == org_id))
        ).all()
        base = settings.public_api_url.rstrip("/")
        from app.growth.publication import public_base

        canonical_base = public_base(settings)
        guides = {
            "meta_ads": (
                "Owner-reviewed paid link ads",
                "Meta access token, ad account ID, page ID; active billing and ads grants",
            ),
            "wordpress": (
                "Publish reviewed website articles",
                "WordPress.com OAuth token and numeric site ID",
            ),
            "linkedin": (
                "Publish reviewed member posts",
                "LinkedIn token with openid/profile and w_member_social grants",
            ),
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
            "seo": {
                "public_indexing_active": bool(canonical_base and settings.public_indexing_enabled),
                "sitemap_url": f"{canonical_base}/v1/public/{org_id}/sitemap.xml"
                if canonical_base
                else "",
                "note": "The private workspace stays noindex. "
                "Only approved public pages can be indexed.",
            },
            "production_gate": "Production deployment review and live acceptance remain required",
            "live_checks": [
                "Model output quality and actual cost on representative examples",
                "Sending-domain authentication, inbox placement and opt-out drill",
                "Calendar conflict and receipt reconciliation drill",
                "Signed payment retry, renewal and refund/dispute drills",
                "HTTPS, restricted database roles, backup recovery, monitoring and load review",
            ],
        }

    async def launch(data, request, who, session, setup_request=None):
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
            prior_request = {"campaign_budget_micros": 0, **previous.input.get("request", {})}
            if previous.type != "plan" or prior_request != parsed:
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
        campaign = Campaign(
            organization_id=org_id,
            brand_id=brand.id,
            name=data.objective[:160],
            budget_micros=data.campaign_budget_micros,
            lead_ids=data.lead_ids,
        )
        session.add(campaign)
        await session.flush()
        command = Command(
            organization_id=org_id,
            created_by=actor,
            brand_id=brand.id,
            raw=data.objective,
            parsed={**parsed, "campaign_id": campaign.id},
        )
        session.add(command)
        await session.flush()
        payload = {"command_id": command.id, "request": parsed, "campaign_id": campaign.id}
        if setup_request is not None:
            payload["setup_request"] = setup_request
        task = await runtime.enqueue(
            session,
            org_id,
            actor,
            "plan",
            "AGT-01",
            data.idempotency_key,
            payload,
        )
        return {"status": "queued", "task": public(task)}

    @router.post("/autopilot/start", status_code=202)
    async def start(data: Start, request: Request, who=Depends(identity), session=Depends(db)):
        return await launch(data, request, who, session)

    @router.post("/setup/start", status_code=202)
    async def setup(
        data: BusinessBrief, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner"})
        org_id = who["organization"].id
        await session.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(emergency_stop=Organization.emergency_stop)
        )
        supplied = data.model_dump(exclude={"idempotency_key"})
        prior = await session.scalar(
            select(Task).where(
                Task.organization_id == org_id, Task.idempotency_key == data.idempotency_key
            )
        )
        if prior:
            if prior.input.get("setup_request") != supplied:
                raise HTTPException(409, "idempotency_key_payload_conflict")
            return {"status": "queued", "task": public(prior)}
        name = (
            (data.name[:100] + " (sample " + data.idempotency_key[:8] + ")")
            if data.sample
            else data.name
        )
        if await session.scalar(
            select(Brand.id).where(Brand.organization_id == org_id, Brand.name == name)
        ):
            raise HTTPException(
                409, "brand_name_already_exists_use_autopilot_for_existing_business"
            )
        business = Brand(
            organization_id=org_id,
            name=name,
            positioning=data.offer,
            icp={"segments": [data.audience]},
            voice={"sandbox_only": data.sample},
            approved_claims=[data.offer],
            prohibited_claims=["guaranteed revenue"],
        )
        session.add(business)
        await session.flush()
        selected = []
        if data.sample:
            lead = Lead(
                organization_id=org_id,
                brand_id=business.id,
                name="Fictional shop owner",
                email=f"sample-{business.id}@example.invalid",
                company="Fictional shop",
                domain="example.invalid",
                source="Fictional sandbox fixture",
                lawful_basis="consent",
                basis_evidence="Synthetic fixture; no real person or consent",
            )
            session.add(lead)
            await session.flush()
            selected = [lead.id]
        await record(session, org_id, who["user"].id, "setup.business_created", business.id)
        return await launch(
            Start(
                brand_id=business.id,
                objective=data.objective,
                search_query=data.audience,
                connected_research=data.connected_research and not data.sample,
                lead_ids=selected,
                idempotency_key=data.idempotency_key,
            ),
            request,
            who,
            session,
            setup_request=supplied,
        )

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
                input={"lead_id": lead_id, "campaign_id": command.parsed.get("campaign_id")},
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
                    "campaign_id": command.parsed.get("campaign_id"),
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
        input={"brand_id": plan.brand_id, "campaign_id": command.parsed.get("campaign_id")},
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
    try:
        async with asyncio.timeout(RESEARCH_DEADLINE_SECONDS):
            return await _research(runtime, session, task)
    except TimeoutError:
        raise HTTPException(504, "prospect_research_deadline_exceeded") from None


async def _research(runtime, session, task):
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
    prepared = []
    if task.input.get("campaign_id") and task.plan_id:
        await runtime.checkpoint(
            session, task.organization_id, task.id, task.created_by, task.attempt
        )
        campaign = await find(session, Campaign, task.organization_id, task.input["campaign_id"])
        emails = {email for page in imported for email in page.get("observed_addresses", [])}
        leads = (
            await session.scalars(
                select(Lead)
                .where(
                    Lead.organization_id == task.organization_id,
                    Lead.brand_id == campaign.brand_id,
                    Lead.email.in_(emails),
                    Lead.status != "suppressed",
                )
                .limit(max(0, 20 - len(campaign.lead_ids)))
            )
        ).all()
        review = await session.scalar(
            select(Task).where(
                Task.organization_id == task.organization_id,
                Task.plan_id == task.plan_id,
                Task.type == "prepare_review",
            )
        )
        for lead in leads:
            if lead.id in campaign.lead_ids:
                continue
            await apply_score(session, task.organization_id, lead)
            job_key = f"autopilot:{task.plan_id}:observed:{lead.id}"
            child = await session.scalar(
                select(Task).where(
                    Task.organization_id == task.organization_id, Task.idempotency_key == job_key
                )
            )
            if not child:
                child = Task(
                    organization_id=task.organization_id,
                    plan_id=task.plan_id,
                    created_by=task.created_by,
                    agent_id="AGT-07",
                    type="draft",
                    status="ready",
                    idempotency_key=job_key,
                    input={"lead_id": lead.id, "campaign_id": campaign.id},
                )
                session.add(child)
                await session.flush()
                if review:
                    session.add(
                        TaskDependency(
                            organization_id=task.organization_id,
                            task_id=review.id,
                            depends_on_id=child.id,
                        )
                    )
            prepared.append(child.id)
        campaign.lead_ids = list(dict.fromkeys(campaign.lead_ids + [lead.id for lead in leads]))[
            :20
        ]
        await session.commit()
    return {
        **result,
        "page_imports": imported,
        "pages_skipped": skipped,
        "draft_task_ids": prepared,
        "note": "Observed contacts are scored and drafted automatically. "
        "Contactability review is required before sending.",
    }
