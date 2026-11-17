"""Structured operational events with an explicit data allowlist, never request bodies."""

import json
import logging
import re

from sqlalchemy import select

ALLOWED = {
    "org_id",
    "actor_id",
    "task_id",
    "agent_id",
    "tool_id",
    "trace_id",
    "request_id",
    "action",
    "decision",
    "status",
    "duration_ms",
    "route",
    "method",
    "exception_type",
}
DECISIONS = {
    "allowed",
    "forbidden_role",
    "membership_changed",
    "emergency_stop",
    "budget_exhausted",
    "agent_permission_ceiling",
    "contactability_not_established",
    "suppressed_recipient",
    "invalid_tool_input",
    "tool_guard_refused",
    "grounding_rejected",
    "invalid_output",
    "task_cancelled_or_lease_changed",
}
logger = logging.getLogger("ai_mos.events")


def emit(action, **fields):
    event = {"action": str(action)[:100]}
    for key, value in fields.items():
        if key in ALLOWED and value is not None:
            if key == "decision" and value not in DECISIONS:
                value = "refused"
            if key in {"agent_id", "tool_id"} and not re.fullmatch(
                r"(?:AGT|TLS)-[0-9]{2}", str(value)
            ):
                value = "unregistered"
            event[key] = value if isinstance(value, (int, float, bool)) else str(value)[:200]
    logger.info(json.dumps(event, sort_keys=True, ensure_ascii=True))


async def task_trace(session, org_id, task):
    from app.growth.models import Command, Plan

    command_id = task.input.get("command_id")
    if command_id and await session.scalar(
        select(Command.id).where(Command.organization_id == org_id, Command.id == command_id)
    ):
        return command_id
    if task.plan_id:
        command_id = await session.scalar(
            select(Plan.command_id).where(Plan.organization_id == org_id, Plan.id == task.plan_id)
        )
        if command_id:
            return command_id
    return task.id
