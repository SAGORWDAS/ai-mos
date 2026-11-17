"""Versioned deterministic qualification from recorded facts; thresholds never grant consent."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select

from app.contracts import Input
from app.growth.models import Agent
from app.growth.runtime_helpers import score

MODEL_VERSION = "recorded-features-v2"


async def policy(session, org_id):
    return await session.scalar(
        select(Agent).where(Agent.organization_id == org_id, Agent.role_id == "AGT-05")
    )


async def apply_score(session, org_id, lead):
    configured = await policy(session, org_id)
    if configured and not configured.enabled:
        raise HTTPException(409, "qualification_agent_disabled")
    threshold = int((configured.config if configured else {}).get("qualification_threshold", 65))
    lead.score = score(lead)
    lead.score_model = MODEL_VERSION
    lead.qualification_threshold = threshold
    lead.score_features = {
        "company_recorded": bool(lead.company),
        "domain_recorded": bool(lead.domain),
        "source_confidence": lead.source_confidence,
        "contactability_recorded": lead.lawful_basis != "not_established",
    }
    if lead.status in {"discovered", "enriched", "scored", "qualified", "disqualified"}:
        lead.status = "qualified" if lead.score >= threshold else "scored"
    return lead.score


class PolicyInput(Input):
    threshold: int = Field(ge=1, le=100)


def install_qualification(app, db, identity, require):
    router = APIRouter(prefix="/v1/qualification-policy")

    @router.get("")
    async def read(who=Depends(identity), session=Depends(db)):
        configured = await policy(session, who["organization"].id)
        return {
            "threshold": (configured.config if configured else {}).get(
                "qualification_threshold", 65
            ),
            "model_version": MODEL_VERSION,
            "enabled": configured.enabled if configured else True,
            "note": "Applies to the next score. Existing scores keep their version and threshold. "
            "Qualification does not establish contact permission or predict conversion.",
        }

    @router.put("")
    async def save(data: PolicyInput, request: Request, who=Depends(identity), session=Depends(db)):
        from app.growth.runtime import record

        await require(session, request, who, {"owner"})
        org_id = who["organization"].id
        configured = await policy(session, org_id)
        if not configured:
            configured = Agent(
                organization_id=org_id,
                role_id="AGT-05",
                name="Lead Qualification Agent",
                enabled=True,
            )
            session.add(configured)
        configured.config = {**(configured.config or {}), "qualification_threshold": data.threshold}
        await record(session, org_id, who["user"].id, "qualification.policy_updated", "AGT-05")
        await session.commit()
        return await read(who, session)

    app.include_router(router)
