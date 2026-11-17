"""Owner-reviewed, fixed-budget Meta link ads; partial effects are never blindly replayed."""

import asyncio
import hashlib
import json
import re
import time
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, field_validator
from sqlalchemy import select, update

from app.growth.connections import active
from app.growth.contracts import Keyed
from app.growth.creative import validate_raster
from app.growth.effects import freeze
from app.growth.knowledge import guard_content
from app.growth.models import Campaign, Content, Effect, Expense, ProviderEvent, Task
from app.growth.providers import ProviderError, require_secret
from app.growth.runtime import find, public, record
from app.models import Brand, Membership, Organization


class AdInput(Keyed):
    campaign_id: str
    content_id: str
    image_task_id: str
    landing_url: str = Field(max_length=1000)
    country: str = Field(pattern="^[A-Z]{2}$")
    currency: str = Field(pattern="^[A-Z]{3}$")
    lifetime_budget_minor: int = Field(ge=1, le=1_000_000)
    duration_days: int = Field(default=3, ge=1, le=7)
    ordinary_commercial_confirmed: bool = False
    activate: bool = False

    @field_validator("landing_url")
    @classmethod
    def https_url(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Use a public HTTPS landing page without embedded credentials")
        return value


class MetaProvider:
    def __init__(self, credentials, transport=None):
        self.credentials, self.transport = credentials, transport

    async def request(self, method, path, **kwargs):
        require_secret(self.credentials.get("access_token", ""))
        try:
            async with asyncio.timeout(20):
                async with httpx.AsyncClient(
                    transport=self.transport, timeout=15, follow_redirects=False, trust_env=False
                ) as client:
                    response = await client.request(
                        method,
                        "https://graph.facebook.com/v27.0/" + path,
                        headers={"Authorization": "Bearer " + self.credentials["access_token"]},
                        **kwargs,
                    )
            if response.status_code in {401, 403}:
                raise ProviderError("ads_grant_invalid")
            if response.status_code >= 500 or response.status_code in {408, 429}:
                raise ProviderError("ads_provider_unavailable", uncertain=method != "GET")
            if not 200 <= response.status_code < 300:
                raise ProviderError("ads_request_rejected")
            result = response.json()
            if not isinstance(result, dict) or result.get("error"):
                raise ProviderError("ads_invalid_response", uncertain=method != "GET")
            return result
        except (httpx.HTTPError, TimeoutError, ValueError):
            raise ProviderError("ads_transport_unknown", uncertain=method != "GET") from None

    def account(self):
        account = self.credentials.get("ad_account_id", "").removeprefix("act_")
        page = self.credentials.get("page_id", "")
        if not re.fullmatch(r"[0-9]{1,30}", account) or not re.fullmatch(r"[0-9]{1,30}", page):
            raise ProviderError("numeric_ad_account_and_page_required")
        return "act_" + account

    async def verify(self):
        account = self.account()
        result = await self.request("GET", account, params={"fields": "id,currency,account_status"})
        if result.get("account_status") != 1 or not re.fullmatch(
            r"[A-Z]{3}", result.get("currency", "")
        ):
            raise ProviderError("active_ad_account_required")
        page = await self.request("GET", self.credentials["page_id"], params={"fields": "id"})
        if str(page.get("id")) != self.credentials["page_id"]:
            raise ProviderError("ads_page_access_required")
        self.credentials["currency"] = result["currency"]
        return account + " / " + result["currency"]

    async def deploy(self, payload, image, checkpoint):
        account = self.account()
        progress = {}

        async def create(step, path, body):
            await checkpoint(progress)
            result = await self.request(
                "POST",
                path,
                data={
                    k: json.dumps(v) if isinstance(v, (list, dict, bool)) else str(v)
                    for k, v in body.items()
                },
            )
            value = str(result.get("id", ""))
            if not re.fullmatch(r"[0-9]{1,30}", value):
                raise ProviderError("ads_receipt_missing", uncertain=True)
            progress[step] = value
            await checkpoint(progress)
            return value

        try:
            async with asyncio.timeout(55):
                await checkpoint(progress)
                uploaded = await self.request("POST", account + "/adimages", data={"bytes": image})
                image_hash = next(iter(uploaded.get("images", {}).values()), {}).get("hash", "")
                if not re.fullmatch(r"[a-fA-F0-9]{16,64}", image_hash):
                    raise ProviderError("ads_image_receipt_missing", uncertain=True)
                progress["image_hash"] = image_hash
                await checkpoint(progress)
                campaign = await create(
                    "campaign_id",
                    account + "/campaigns",
                    {
                        "name": payload["title"][:100],
                        "objective": "OUTCOME_TRAFFIC",
                        "status": "PAUSED",
                        "special_ad_categories": [],
                        "spend_cap": payload["lifetime_budget_minor"],
                    },
                )
                start = int(time.time() + 600)
                adset = await create(
                    "adset_id",
                    account + "/adsets",
                    {
                        "name": "Reviewed audience",
                        "campaign_id": campaign,
                        "lifetime_budget": payload["lifetime_budget_minor"],
                        "start_time": start,
                        "end_time": start + payload["duration_days"] * 86400,
                        "billing_event": "IMPRESSIONS",
                        "optimization_goal": "LINK_CLICKS",
                        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                        "targeting": {
                            "geo_locations": {"countries": [payload["country"]]},
                            "age_min": 18,
                        },
                        "status": "PAUSED",
                    },
                )
                creative = await create(
                    "creative_id",
                    account + "/adcreatives",
                    {
                        "name": payload["title"][:100],
                        "object_story_spec": {
                            "page_id": self.credentials["page_id"],
                            "link_data": {
                                "link": payload["landing_url"],
                                "message": payload["body"],
                                "image_hash": image_hash,
                            },
                        },
                    },
                )
                ad = await create(
                    "ad_id",
                    account + "/ads",
                    {
                        "name": payload["title"][:100],
                        "adset_id": adset,
                        "creative": {"creative_id": creative},
                        "status": "PAUSED",
                    },
                )
                if payload["activate"]:
                    for identifier in [ad, adset, campaign]:
                        await checkpoint(progress)
                        result = await self.request("POST", identifier, data={"status": "ACTIVE"})
                        if result.get("success") is not True:
                            raise ProviderError("ads_activation_unknown", uncertain=True)
                    progress["activated"] = True
                    await checkpoint(progress)
                return {
                    "provider_id": campaign,
                    "status": "active" if payload["activate"] else "prepared_paused",
                    "progress": progress,
                    "budget_minor": payload["lifetime_budget_minor"],
                    "currency": payload["currency"],
                }
        except ProviderError as error:
            error.uncertain = error.uncertain or bool(progress)
            raise
        except TimeoutError:
            raise ProviderError("ads_deadline_unknown", uncertain=True) from None


async def check_ad(session, org_id, payload):
    campaign = await find(session, Campaign, org_id, payload["campaign_id"])
    content = await find(session, Content, org_id, payload["content_id"])
    image = await find(session, Task, org_id, payload["image_task_id"])
    if campaign.brand_id != content.brand_id or image.input.get("brand_id") != campaign.brand_id:
        raise HTTPException(422, "campaign_brand_mismatch")
    if content.title != payload["title"] or content.body != payload["body"]:
        raise HTTPException(409, "approval_payload_changed")
    brand = await find(session, Brand, org_id, campaign.brand_id)
    await guard_content(
        session, brand, content.title, content.title, content.body, content.citations
    )
    if image.status != "succeeded" or image.type != "creative_image":
        raise HTTPException(409, "image_not_ready")
    validate_raster(image.output["image_base64"])
    if hashlib.sha256(image.output["image_base64"].encode()).hexdigest() != payload["image_hash"]:
        raise HTTPException(409, "approved_image_changed")
    return brand, image


async def prepare_ads(dispatcher, session, effect, approval):
    org_id = effect.organization_id
    brand, image = await check_ad(session, org_id, effect.payload)
    if brand.voice.get("sandbox_only") or image.output.get("simulated", True):
        raise ProviderError("sample_assets_cannot_run_paid_ads")
    connection = await active(session, dispatcher.settings, org_id, "meta_ads")
    if not connection or (connection["id"], connection["version"]) != (
        effect.result.get("_connection_id"),
        effect.result.get("_connection_version"),
    ):
        raise ProviderError("connection_changed_or_disconnected")
    if connection["credentials"].get("currency") != effect.payload["currency"]:
        raise ProviderError("ad_account_currency_mismatch")
    effect_id = effect.id
    expected_version = connection["version"]

    async def checkpoint(progress):
        async with dispatcher.factory() as current:
            item = await find(current, Effect, org_id, effect_id)
            organization = await current.get(Organization, org_id)
            role = await current.scalar(
                select(Membership.role).where(
                    Membership.organization_id == org_id, Membership.user_id == approval.decided_by
                )
            )
            latest = await active(current, dispatcher.settings, org_id, "meta_ads")
            stopped = (
                organization.emergency_stop
                or role != "owner"
                or not latest
                or (latest["id"], latest["version"]) != (connection["id"], expected_version)
                or item.status != "dispatching"
            )
            item.result = {**item.result, "progress": dict(progress)}
            await current.commit()
            if stopped:
                raise ProviderError("ads_execution_stopped", uncertain=bool(progress))
            await check_ad(current, org_id, item.payload)

    return (
        connection,
        MetaProvider(connection["credentials"], dispatcher.transport),
        {
            "payload": effect.payload,
            "image": image.output["image_base64"],
            "checkpoint": checkpoint,
        },
    )


def install_advertising(app, settings, runtime, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.post("/advertising/{effect_id}/metrics")
    async def metrics(
        effect_id: str, data: Keyed, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner"}, writes=False)
        org_id = who["organization"].id
        item = await find(session, Effect, org_id, effect_id)
        if item.action != "launch_paid_ads":
            raise HTTPException(422, "not_an_ad_campaign")
        if item.result.get("simulated", True):
            return {
                "simulated": True,
                "spend": "0",
                "currency": item.payload["currency"],
                "clicks": 0,
                "impressions": 0,
            }
        event_key = (
            "admetrics:"
            + hashlib.sha256((effect_id + ":" + data.idempotency_key).encode()).hexdigest()
        )
        previous = await session.scalar(
            select(ProviderEvent).where(
                ProviderEvent.organization_id == org_id,
                ProviderEvent.provider == "meta_ads",
                ProviderEvent.event_id == event_key,
            )
        )
        if previous:
            return previous.evidence
        connection = await active(session, settings, org_id, "meta_ads")
        if not connection or connection["id"] != item.result.get("_connection_id"):
            raise HTTPException(409, "restore_ad_account_connection_first")
        provider_id = item.result.get("progress", {}).get("campaign_id")
        if not provider_id or not re.fullmatch(r"[0-9]{1,30}", provider_id):
            raise HTTPException(409, "provider_campaign_receipt_required")
        await session.commit()
        try:
            result = await MetaProvider(
                connection["credentials"], runtime.delivery.transport
            ).request(
                "GET",
                provider_id + "/insights",
                params={
                    "fields": "spend,impressions,clicks,account_currency",
                    "date_preset": "maximum",
                },
            )
            row = (result.get("data") or [{}])[0]
            spend = Decimal(str(row.get("spend", "0")))
            if not spend.is_finite() or spend < 0 or spend > Decimal("1000000000"):
                raise ValueError()
            currency = row.get("account_currency", item.payload["currency"])
            if currency != item.payload["currency"]:
                raise ValueError()
            evidence = {
                "effect_id": effect_id,
                "campaign_id": item.payload["campaign_id"],
                "spend": str(spend),
                "currency": currency,
                "clicks": int(row.get("clicks", 0)),
                "impressions": int(row.get("impressions", 0)),
                "simulated": False,
            }
            if evidence["clicks"] < 0 or evidence["impressions"] < 0:
                raise ValueError()
        except (ProviderError, ValueError, TypeError, InvalidOperation) as error:
            raise HTTPException(
                502, error.code if isinstance(error, ProviderError) else "ads_metrics_invalid"
            ) from None
        await session.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(emergency_stop=Organization.emergency_stop)
        )
        prior = await session.scalar(
            select(ProviderEvent).where(
                ProviderEvent.organization_id == org_id,
                ProviderEvent.provider == "meta_ads",
                ProviderEvent.event_id == event_key,
            )
        )
        if prior:
            return prior.evidence
        latest = await session.scalar(
            select(ProviderEvent)
            .where(
                ProviderEvent.organization_id == org_id,
                ProviderEvent.provider == "meta_ads",
                ProviderEvent.kind == "ads.insights",
                ProviderEvent.object_ref == provider_id,
            )
            .order_by(ProviderEvent.created_at.desc(), ProviderEvent.id)
            .limit(1)
        )
        old = Decimal(latest.evidence["spend"]) if latest else Decimal(0)
        if spend < old:
            raise HTTPException(409, "provider_spend_decrease_needs_manual_review")
        if currency == "USD" and spend > old:
            session.add(
                Expense(
                    organization_id=org_id,
                    category="advertising",
                    campaign_id=item.payload["campaign_id"],
                    amount_micros=int(
                        ((spend - old) * 1000000).to_integral_value(rounding=ROUND_CEILING)
                    ),
                    evidence="Meta cumulative spend receipt: " + event_key,
                    simulated=False,
                )
            )
        session.add(
            ProviderEvent(
                organization_id=org_id,
                provider="meta_ads",
                event_id=event_key,
                kind="ads.insights",
                object_ref=provider_id,
                occurred_at=time.time(),
                amount_minor=0,
                currency=currency,
                simulated=False,
                evidence=evidence,
            )
        )
        await session.commit()
        return evidence

    @router.post("/advertising/request-approval", status_code=201)
    async def request_approval(
        data: AdInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner"})
        if not data.ordinary_commercial_confirmed:
            raise HTTPException(422, "special_category_review_required")
        org_id = who["organization"].id
        content = await find(session, Content, org_id, data.content_id)
        image = await find(session, Task, org_id, data.image_task_id)
        connection = await active(session, settings, org_id, "meta_ads")
        payload = {
            **data.model_dump(exclude={"idempotency_key"}),
            "title": content.title,
            "body": content.body,
            "image_hash": hashlib.sha256(image.output.get("image_base64", "").encode()).hexdigest(),
            "connection_id": connection["id"] if connection else None,
            "connection_version": connection["version"] if connection else None,
        }
        await check_ad(session, org_id, payload)
        approval = await freeze(
            session,
            org_id,
            who["user"].id,
            "campaign",
            data.campaign_id,
            "launch_paid_ads",
            payload,
        )
        await session.commit()
        return public(approval)

    @router.post("/advertising/{effect_id}/pause")
    async def pause(
        effect_id: str, data: Keyed, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner"}, writes=False)
        org_id = who["organization"].id
        item = await find(session, Effect, org_id, effect_id)
        if item.action != "launch_paid_ads":
            raise HTTPException(422, "not_an_ad_campaign")
        if item.result.get("simulated", True):
            return {"status": "simulated_paused"}
        connection = await active(session, settings, org_id, "meta_ads")
        if not connection or connection["id"] != item.result.get("_connection_id"):
            raise HTTPException(409, "restore_ad_account_connection_or_pause_in_meta")
        provider_id = item.result.get("progress", {}).get("campaign_id")
        if not provider_id or not re.fullmatch(r"[0-9]{1,30}", provider_id):
            raise HTTPException(409, "review_provider_console_for_partial_campaign")
        await session.commit()
        try:
            result = await MetaProvider(
                connection["credentials"], runtime.delivery.transport
            ).request("POST", provider_id, data={"status": "PAUSED"})
            if result.get("success") is not True:
                raise ProviderError("pause_not_confirmed", uncertain=True)
        except ProviderError as error:
            raise HTTPException(502, error.code) from None
        await record(session, org_id, who["user"].id, "ads.paused", item.id)
        item.result = {**item.result, "paused_at": time.time()}
        await session.commit()
        return {"status": "paused", "provider_id": provider_id}

    app.include_router(router)
