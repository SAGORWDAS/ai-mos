"""Constrain research and strategy to recorded facts and owner-entered spending bounds."""

from sqlalchemy import select

from app.growth.models import Command, Plan

CHANNELS = {"approved_email", "owned_content", "organic_social", "paid_social"}
GUIDANCE = {"validate_one_offer", "compare_small_segments", "review_evidence_first"}


async def strategy_seed(session, task, brand):
    allowance = 0
    if task.plan_id:
        parsed = await session.scalar(
            select(Command.parsed)
            .join(Plan, Plan.command_id == Command.id)
            .where(
                Plan.organization_id == task.organization_id,
                Plan.id == task.plan_id,
                Command.organization_id == task.organization_id,
            )
        )
        allowance = (parsed or {}).get("campaign_budget_micros", 0)
    return {
        "audience": brand.icp.get("segments", []),
        "positioning": brand.positioning,
        "pricing_evidence": brand.pricing,
        "approval_required": True,
        "autonomous_spend": False,
        "campaign_budget_micros": allowance,
        "currency": "USD",
        "channel_plan": [
            {"channel": "approved_email", "min_budget_micros": 0, "max_budget_micros": allowance}
        ],
        "guidance": "validate_one_offer",
    }


def validate_strategy(output, seed):
    if not isinstance(output, dict) or set(output) != set(seed):
        raise ValueError("strategy_shape_rejected")
    for key in set(seed) - {"audience", "channel_plan", "guidance"}:
        if output[key] != seed[key]:
            raise ValueError("strategy_unapproved_fact_or_budget")
    if (
        not isinstance(output["audience"], list)
        or any(a not in seed["audience"] for a in output["audience"])
        or (seed["audience"] and not output["audience"])
    ):
        raise ValueError("strategy_unapproved_audience")
    if output["guidance"] not in GUIDANCE:
        raise ValueError("strategy_unapproved_guidance")
    plans = output["channel_plan"]
    if not isinstance(plans, list) or not 1 <= len(plans) <= 4:
        raise ValueError("strategy_channel_plan_required")
    seen, maximum = set(), 0
    for plan in plans:
        if not isinstance(plan, dict) or set(plan) != {
            "channel",
            "min_budget_micros",
            "max_budget_micros",
        }:
            raise ValueError("strategy_channel_shape_rejected")
        channel = plan["channel"]
        low, high = plan["min_budget_micros"], plan["max_budget_micros"]
        if (
            channel not in CHANNELS
            or channel in seen
            or type(low) is not int
            or type(high) is not int
            or not 0 <= low <= high
        ):
            raise ValueError("strategy_channel_range_rejected")
        seen.add(channel)
        maximum += high
    if maximum > seed["campaign_budget_micros"]:
        raise ValueError("strategy_budget_exceeded")


def validate_research(output, seed):
    if not isinstance(output, dict) or set(output) != set(seed):
        raise ValueError("research_shape_rejected")
    if any(output[key] != seed[key] for key in set(seed) - {"findings"}):
        raise ValueError("research_unverified_method_or_claim")
    findings = output["findings"]
    if not isinstance(findings, list) or len(findings) > len(seed["findings"]):
        raise ValueError("research_citations_required")
    seen = set()
    for row in findings:
        if not isinstance(row, dict) or row not in seed["findings"] or row["chunk_id"] in seen:
            raise ValueError("research_uncited_or_modified_evidence")
        seen.add(row["chunk_id"])
