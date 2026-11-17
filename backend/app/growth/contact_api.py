from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select

from app.contracts import Input
from app.growth.models import Approval, Draft, Lead
from app.growth.runtime import find, public, record


class ContactEdit(Input):
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=120)
    company: str = Field(default="", max_length=200)
    domain: str = Field(default="", max_length=250)
    lawful_basis: Literal["consent", "legitimate_interest", "not_established"] = "not_established"
    basis_evidence: str = Field(default="", max_length=2000)
    personalisation: str = Field(default="", max_length=400)
    personalisation_evidence: str = Field(default="", max_length=2000)


def install_contacts(app, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.put("/leads/{lead_id}")
    async def edit(
        lead_id: str,
        data: ContactEdit,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await require(session, request, who, {"owner", "admin", "member"})
        lead = await find(session, Lead, who["organization"].id, lead_id)
        if lead.status == "suppressed":
            raise HTTPException(403, "suppressed_contact_cannot_be_reactivated")
        if lead.version != data.expected_version:
            raise HTTPException(409, "contact_changed_refresh_before_editing")
        if data.lawful_basis != "not_established" and len(data.basis_evidence.strip()) < 10:
            raise HTTPException(422, "contactability_evidence_required")
        if data.personalisation and len(data.personalisation_evidence.strip()) < 10:
            raise HTTPException(422, "personalisation_evidence_required")
        for field, value in data.model_dump(exclude={"expected_version"}).items():
            setattr(lead, field, value)
        lead.version += 1
        approvals = (
            await session.scalars(
                select(Approval).where(
                    Approval.organization_id == who["organization"].id,
                    Approval.status.in_(["pending", "approved"]),
                )
            )
        ).all()
        draft_ids = set(
            (
                await session.scalars(
                    select(Draft.id).where(
                        Draft.organization_id == who["organization"].id, Draft.lead_id == lead.id
                    )
                )
            ).all()
        )
        for approval in approvals:
            if (
                approval.payload.get("lead_id") == lead.id
                or approval.subject_id in draft_ids
                or any(row.get("lead_id") == lead.id for row in approval.payload.get("drafts", []))
            ):
                approval.status = "invalidated"
        await record(session, who["organization"].id, who["user"].id, "contact.updated", lead.id)
        await session.commit()
        return public(lead)

    app.include_router(router)
