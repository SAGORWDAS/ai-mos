"""Tenant-scoped usage drilldown without exposing model prompts or customer messages."""

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select

from app.growth.models import ModelUsage, Task


def install_usage(app, db, identity):
    router = APIRouter(prefix="/v1")

    @router.get("/usage/attempts")
    async def attempts(
        day: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
        agent: str = Query(max_length=16),
        task_type: str = Query(max_length=40),
        status: str = Query(max_length=40),
        model: str = Query(max_length=200),
        simulated: bool = True,
        offset: int = Query(default=0, ge=0, le=1_000_000),
        who=Depends(identity),
        session=Depends(db),
    ):
        try:
            start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()
        except ValueError:
            raise HTTPException(422, "invalid_day") from None
        query = (
            select(
                ModelUsage.id,
                ModelUsage.request_id,
                ModelUsage.task_id,
                ModelUsage.created_at,
                ModelUsage.cost_micros,
                ModelUsage.reserved_micros,
                ModelUsage.settled,
                ModelUsage.input_tokens,
                ModelUsage.output_tokens,
                ModelUsage.cache_source_id,
            )
            .join(Task, Task.id == ModelUsage.task_id)
            .where(
                ModelUsage.organization_id == who["organization"].id,
                Task.organization_id == who["organization"].id,
                ModelUsage.created_at >= start,
                ModelUsage.created_at < start + 86400,
                ModelUsage.agent_id == agent,
                Task.type == task_type,
                ModelUsage.status == status,
                ModelUsage.model_id == model,
                ModelUsage.simulated == simulated,
            )
            .order_by(ModelUsage.created_at, ModelUsage.id)
        )
        records = (await session.execute(query.offset(offset).limit(101))).mappings().all()
        return {
            "items": [dict(r) for r in records[:100]],
            "next_offset": offset + 100 if len(records) > 100 else None,
        }

    @router.get("/usage/breakdown")
    async def breakdown(
        days: int = Query(default=30, ge=1, le=365),
        agent: str = Query(default="", max_length=16),
        task_type: str = Query(default="", max_length=40),
        status: str = Query(default="", max_length=40),
        who=Depends(identity),
        session=Depends(db),
    ):
        day = (
            func.date(ModelUsage.created_at, "unixepoch")
            if session.bind.dialect.name == "sqlite"
            else func.date(func.timezone("UTC", func.to_timestamp(ModelUsage.created_at)))
        )
        query = select(
            day.label("day"),
            ModelUsage.agent_id,
            Task.type.label("task_type"),
            ModelUsage.model_id,
            ModelUsage.status,
            ModelUsage.simulated,
            func.count(ModelUsage.id).label("attempts"),
            func.sum(ModelUsage.cost_micros).label("cost_micros"),
            func.sum(
                case((ModelUsage.settled.is_(False), ModelUsage.reserved_micros), else_=0)
            ).label("held_micros"),
            func.sum(ModelUsage.input_tokens).label("input_tokens"),
            func.sum(ModelUsage.output_tokens).label("output_tokens"),
        )
        query = query.join(Task, Task.id == ModelUsage.task_id).where(
            ModelUsage.organization_id == who["organization"].id,
            Task.organization_id == who["organization"].id,
            ModelUsage.created_at >= time.time() - days * 86400,
        )
        for column, value in [
            (ModelUsage.agent_id, agent),
            (Task.type, task_type),
            (ModelUsage.status, status),
        ]:
            if value:
                query = query.where(column == value)
        query = query.group_by(
            day,
            ModelUsage.agent_id,
            Task.type,
            ModelUsage.model_id,
            ModelUsage.status,
            ModelUsage.simulated,
        ).order_by(
            day.desc(),
            ModelUsage.agent_id,
            Task.type,
            ModelUsage.model_id,
            ModelUsage.status,
            ModelUsage.simulated,
        )
        rows = (await session.execute(query.limit(1001))).mappings().all()
        return {
            "items": [dict(row) for row in rows[:1000]],
            "truncated": len(rows) > 1000,
            "days": days,
            "note": "Known USD costs and holds are separate. Narrow filters if truncated. "
            "No prompts or message bodies are returned.",
        }

    app.include_router(router)
