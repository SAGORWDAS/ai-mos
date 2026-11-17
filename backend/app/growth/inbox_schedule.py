import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select, text, update

from app.contracts import Input
from app.growth.connections import active
from app.growth.inbox import import_page
from app.growth.models import Integration
from app.growth.providers import GoogleProvider, ProviderError
from app.growth.runtime import record
from app.models import Membership, Organization
from app.tenancy import tenant_scope


class Schedule(Input):
    enabled: bool
    auto_draft_replies: bool = False
    interval_minutes: int = Field(default=10, ge=5, le=1440)


def install_inbox_schedule(app, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.post("/connections/gmail/sync-schedule")
    async def schedule(
        data: Schedule, request: Request, who=Depends(identity), session=Depends(db)
    ):
        enabled_work = data.enabled or data.auto_draft_replies
        await require(session, request, who, {"owner"}, writes=enabled_work)
        item = await session.scalar(
            select(Integration).where(
                Integration.organization_id == who["organization"].id,
                Integration.provider == "gmail",
            )
        )
        if not item or (enabled_work and (item.status != "verified" or not item.enabled)):
            raise HTTPException(409, "enabled_gmail_required")
        item.sync_enabled, item.sync_interval_minutes = data.enabled, data.interval_minutes
        item.auto_draft_replies = data.auto_draft_replies
        item.sync_cursor, item.sync_next_at = "", 0
        await record(
            session, who["organization"].id, who["user"].id, "inbox.schedule_updated", item.id
        )
        await session.commit()
        return {
            "enabled": item.sync_enabled,
            "interval_minutes": item.sync_interval_minutes,
            "auto_draft_replies": item.auto_draft_replies,
        }

    app.include_router(router)


class InboxScheduler:
    def __init__(self, factory, settings, delivery):
        self.factory, self.settings, self.delivery = factory, settings, delivery

    async def tick(self):
        async with self.factory() as session:
            if session.bind.dialect.name == "postgresql":
                picked = (
                    (await session.execute(text("SELECT * FROM claim_next_inbox()")))
                    .mappings()
                    .first()
                )
                await session.commit()
                if not picked:
                    return False
                await tenant_scope(session, organization_id=picked["org_id"])
                item = await session.get(Integration, picked["integration_id"])
            else:
                item = await session.scalar(
                    select(Integration)
                    .join(Organization, Organization.id == Integration.organization_id)
                    .where(
                        Integration.provider == "gmail",
                        Integration.status == "verified",
                        Integration.enabled.is_(True),
                        Integration.sync_enabled.is_(True),
                        Integration.sync_next_at <= time.time(),
                        Organization.emergency_stop.is_(False),
                    )
                    .order_by(Integration.sync_next_at)
                    .limit(1)
                )
                if not item:
                    return False
                claimed = await session.execute(
                    update(Integration)
                    .where(Integration.id == item.id, Integration.sync_next_at == item.sync_next_at)
                    .values(sync_next_at=time.time() + item.sync_interval_minutes * 60)
                )
                await session.commit()
                if not claimed.rowcount:
                    return True
            org_id, item_id, version = item.organization_id, item.id, item.version
            actor = await session.scalar(
                select(Membership.user_id)
                .where(Membership.organization_id == org_id, Membership.role == "owner")
                .limit(1)
            )
            if not actor:
                return True
            try:
                connection = await active(session, self.settings, org_id, "gmail")
                if not connection:
                    return True
                credentials = connection["credentials"]
                provider = GoogleProvider(
                    credentials.get("access_token", ""), transport=self.delivery.transport
                )
                cursor = item.sync_cursor or None
                await session.commit()
                if credentials.get("refresh_token"):
                    await provider.refresh(
                        credentials.get("client_id", ""),
                        credentials.get("client_secret", ""),
                        credentials["refresh_token"],
                    )
                page = await provider.inbox_page(cursor)
                await session.execute(
                    update(Organization)
                    .where(Organization.id == org_id)
                    .values(emergency_stop=Organization.emergency_stop)
                )
                await session.refresh(item)
                if (
                    item.version != version
                    or not item.sync_enabled
                    or not item.enabled
                    or item.status != "verified"
                    or await session.scalar(
                        select(Organization.emergency_stop).where(Organization.id == org_id)
                    )
                ):
                    return True
                await import_page(
                    session,
                    org_id,
                    connection["account_ref"],
                    page["messages"],
                    auto_draft=item.auto_draft_replies,
                    actor_id=actor,
                )
                item.sync_last_at, item.sync_error = time.time(), ""
                item.sync_cursor = page.get("next_cursor") or ""
                # Drain one page per idle tick, then return to the selected polling interval.
                if item.sync_cursor:
                    item.sync_next_at = time.time() + 2
                await record(session, org_id, actor, "inbox.scheduled_sync", item.id)
                await session.commit()
            except (ProviderError, HTTPException) as error:
                await session.rollback()
                await tenant_scope(session, organization_id=org_id)
                item = await session.get(Integration, item_id)
                if item and item.version == version:
                    item.sync_error = (
                        error.code
                        if isinstance(error, ProviderError)
                        else "provider_configuration_error"
                    )
                    await session.commit()
        return True
