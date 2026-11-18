"""Read-only preparation checks and separately labelled owner-reported pilot evidence."""

import hashlib
import json
import time
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import func, select

from app.contracts import Input
from app.deployment import configuration_checks, database_checks
from app.growth.gateway import month
from app.growth.model_registry import configured, eligible
from app.growth.models import (
    Budget,
    Effect,
    Integration,
    Lead,
    Message,
    ModelRegistry,
    ModelUsage,
    Payment,
    ProviderEvent,
    Suppression,
    ValidationRecord,
)
from app.models import Brand
from app.release import VERSION

KINDS = {
    "sending_dns": "Sending-domain SPF, DKIM and DMARC",
    "seed_delivery": "Seed-inbox placement and bounce check",
    "opt_out": "Opt-out, suppression and blocked re-send drill",
    "calendar_race": "Calendar conflict and uncertain-receipt drill",
    "payment_replay": "Signed payment retry, renewal and refund/dispute drill",
    "model_quality": "Representative model output and cost review",
    "recovery": "Backup restore and operator account recovery",
}


class EvidenceInput(Input):
    kind: Literal[
        "sending_dns",
        "seed_delivery",
        "opt_out",
        "calendar_race",
        "payment_replay",
        "model_quality",
        "recovery",
    ]
    outcome: Literal["passed", "failed"]
    reference: str = Field(min_length=3, max_length=300)
    note: str = Field(min_length=10, max_length=2000)


async def scope_hash(session, org_id, settings):
    connections = (
        await session.execute(
            select(Integration.id, Integration.version, Integration.status, Integration.enabled)
            .where(Integration.organization_id == org_id)
            .order_by(Integration.id)
        )
    ).all()
    brands = (
        await session.execute(
            select(
                Brand.id,
                Brand.positioning,
                Brand.icp,
                Brand.pricing,
                Brand.approved_claims,
                Brand.prohibited_claims,
                Brand.voice,
            )
            .where(Brand.organization_id == org_id)
            .order_by(Brand.id)
        )
    ).all()
    return hashlib.sha256(
        json.dumps(
            [
                org_id,
                settings.app_env,
                settings.public_api_url,
                VERSION,
                settings.validation_review_ref,
                settings.secure_cookies,
                settings.allowed_origins,
                settings.allow_unverified_models,
                [list(row) for row in connections],
                [list(row) for row in brands],
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()


def install_live_validation(app, settings, db, identity, require):
    from app.growth.connections import unseal
    from app.growth.runtime import public, record

    router = APIRouter(prefix="/v1/live-validation")

    @router.get("")
    async def report(
        request: Request,
        workflow: Literal["outreach", "acquisition"] = "acquisition",
        who=Depends(identity),
        session=Depends(db),
    ):
        await require(session, request, who, {"owner"}, writes=False)
        org_id = who["organization"].id
        connections = (
            await session.scalars(select(Integration).where(Integration.organization_id == org_id))
        ).all()
        await session.commit()
        checks = configuration_checks(settings)
        checks.insert(
            0,
            {
                "id": "validation_environment",
                "ready": settings.app_env == "validation",
                "detail": "Use the controlled HTTPS validation deployment for live drills.",
            },
        )
        checks.extend(await database_checks(session.bind))

        def check(name, ready, detail):
            checks.append({"id": name, "ready": bool(ready), "detail": detail})

        for provider in (
            ("openrouter", "brave", "gmail")
            if workflow == "acquisition"
            else ("openrouter", "gmail")
        ):
            connection = next((c for c in connections if c.provider == provider), None)
            check(
                provider,
                connection and connection.enabled and connection.status == "verified",
                f"Save, verify and explicitly enable {provider}; placeholders do not qualify.",
            )
        selected = next(
            (c for c in connections if c.provider == "openrouter" and c.status == "verified"), None
        )
        chat_ready = False
        if selected:
            binding = configured(
                settings,
                org_id,
                "chat",
                {
                    "id": selected.id,
                    "version": selected.version,
                    "credentials": unseal(settings, selected),
                },
            )
            if binding:
                entry = await session.scalar(
                    select(ModelRegistry).where(
                        ModelRegistry.organization_id == org_id,
                        ModelRegistry.operation == "chat",
                        ModelRegistry.model_id == binding["model_id"],
                    )
                )
                chat_ready = (
                    eligible(entry) and entry.source_fingerprint == binding["source_fingerprint"]
                )
        check("chat_catalog", chat_ready, "Selected chat model needs fresh catalog verification.")
        budget = await session.scalar(
            select(Budget).where(Budget.organization_id == org_id, Budget.period == month())
        )
        check(
            "budget",
            budget
            and budget.limit_micros > budget.spent_micros + budget.reserved_micros
            and budget.daily_send_cap > 0,
            "Set a small model budget and daily email cap.",
        )
        candidate_brands = (
            await session.scalars(
                select(Brand)
                .where(
                    Brand.organization_id == org_id,
                    Brand.positioning != "",
                    func.json_array_length(Brand.approved_claims) > 0,
                )
                .limit(500)
            )
        ).all()
        real_brand_ids = [b.id for b in candidate_brands if not b.voice.get("sandbox_only")]
        check(
            "business_brief",
            bool(real_brand_ids),
            "Enter your actual offer and approved claims; marked sandbox profiles are excluded.",
        )
        candidates = (
            await session.scalars(
                select(Lead.email)
                .where(
                    Lead.organization_id == org_id,
                    Lead.brand_id.in_(real_brand_ids),
                    Lead.lawful_basis == "consent",
                    func.length(Lead.basis_evidence) >= 10,
                    Lead.status != "suppressed",
                    ~select(Suppression.id)
                    .where(Suppression.organization_id == org_id, Suppression.address == Lead.email)
                    .exists(),
                )
                .limit(500)
            )
        ).all()
        contact = any(
            not address.rsplit("@", 1)[-1]
            .lower()
            .endswith(
                (
                    ".invalid",
                    ".test",
                    ".example",
                    ".localhost",
                    ".example.com",
                    ".example.net",
                    ".example.org",
                )
            )
            and address.rsplit("@", 1)[-1].lower()
            not in {"example.com", "example.net", "example.org", "localhost"}
            for address in candidates
        )
        check(
            "test_contact",
            contact,
            "Use a consenting seed contact on a non-demo domain with recorded contactability.",
        )
        check(
            "stop_switch",
            not who["organization"].emergency_stop,
            "The stop switch must permit the planned drill; test it again during validation.",
        )
        cutoff = time.time() - 14 * 86400

        async def count(model, *conditions):
            return await session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.organization_id == org_id, model.created_at >= cutoff, *conditions)
            )

        receipts = {
            "model_completions": await count(
                ModelUsage,
                ModelUsage.simulated.is_(False),
                ModelUsage.status == "succeeded",
                ModelUsage.provider_ref != "",
                ModelUsage.settled.is_(True),
            ),
            "searches": await count(
                ProviderEvent,
                ProviderEvent.simulated.is_(False),
                ProviderEvent.provider == "brave",
                ProviderEvent.kind == "search.completed",
            ),
            "sent_messages": await count(
                Message,
                Message.simulated.is_(False),
                Message.direction == "outbound",
                Message.status == "sent",
                Message.provider_id != "",
            ),
            "received_messages": await count(
                Message,
                Message.simulated.is_(False),
                Message.direction == "inbound",
                Message.provider_id != "",
            ),
            "verified_payments": await count(
                Payment, Payment.simulated.is_(False), Payment.status == "succeeded"
            ),
            "uncertain_effects": await count(Effect, Effect.status == "uncertain"),
            "unknown_model_charges": await count(
                ModelUsage, ModelUsage.simulated.is_(False), ModelUsage.settled.is_(False)
            ),
        }
        fingerprint = await scope_hash(session, org_id, settings)
        records = (
            await session.scalars(
                select(ValidationRecord)
                .where(ValidationRecord.organization_id == org_id)
                .order_by(ValidationRecord.created_at.desc(), ValidationRecord.id)
                .limit(101)
            )
        ).all()
        return {
            "checked_at": time.time(),
            "workflow": workflow,
            "checks": checks,
            "ready_to_begin_core_validation": all(c["ready"] for c in checks),
            "production_approved": False,
            "receipt_window_days": 14,
            "receipts": receipts,
            "records": [
                {
                    **public(r),
                    "current": r.scope_hash == fingerprint
                    and r.created_at >= time.time() - 30 * 86400,
                }
                for r in records[:100]
            ],
            "records_truncated": len(records) > 100,
            "evidence_kinds": KINDS,
            "note": "Preparation checks do not send messages or spend provider credit. "
            "Connected receipt counts exclude sandbox rows but do not prove inbox placement, "
            "business quality or the current connection version. Owner reports are assertions, "
            "not automated proof. Setup changes or 30 days stale owner reports. "
            "Optional Calendar, payments, publishing and ads retain their activation gates.",
        }

    @router.post("/evidence", status_code=201)
    async def evidence(
        data: EvidenceInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        # Recording a failed drill must remain available while the workspace is stopped.
        await require(session, request, who, {"owner"}, writes=False)
        org_id = who["organization"].id
        row = ValidationRecord(
            organization_id=org_id,
            created_by=who["user"].id,
            scope_hash=await scope_hash(session, org_id, settings),
            **data.model_dump(),
        )
        session.add(row)
        await session.flush()
        await record(session, org_id, who["user"].id, "validation.evidence_recorded", row.id)
        await session.commit()
        return public(row)

    app.include_router(router)
