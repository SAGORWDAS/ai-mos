"""Reviewed channel publishing through fixed provider origins and durable effects."""

import asyncio
import html
import re
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.contracts import Input
from app.growth.connections import active
from app.growth.effects import freeze
from app.growth.knowledge import guard_content
from app.growth.models import Content
from app.growth.providers import ProviderError, require_secret
from app.growth.runtime import find, public
from app.models import Brand

CHANNELS = {"wordpress", "linkedin"}
REQUEST_DEADLINE_SECONDS = 30


class ChannelInput(Input):
    channel: Literal["wordpress", "linkedin"]


class PublishingProvider:
    def __init__(self, channel, credentials, transport=None):
        if channel not in CHANNELS:
            raise ProviderError("unknown_publishing_channel")
        self.channel, self.credentials, self.transport = channel, credentials, transport

    async def request(self, method, url, **kwargs):
        token = self.credentials.get("access_token", "")
        require_secret(token)
        headers = {"Authorization": "Bearer " + token}
        if self.channel == "linkedin":
            headers.update({"Linkedin-Version": "202609", "X-Restli-Protocol-Version": "2.0.0"})
        try:
            async with asyncio.timeout(REQUEST_DEADLINE_SECONDS):
                async with httpx.AsyncClient(
                    transport=self.transport, timeout=25, follow_redirects=False, trust_env=False
                ) as client:
                    response = await client.request(method, url, headers=headers, **kwargs)
        except (httpx.HTTPError, TimeoutError):
            raise ProviderError("publishing_transport_failure", uncertain=method != "GET") from None
        if response.status_code in {401, 403}:
            raise ProviderError("publishing_permission_required")
        if response.status_code >= 500 or response.status_code in {408, 429}:
            raise ProviderError("publishing_provider_unavailable", uncertain=method != "GET")
        if not 200 <= response.status_code < 300:
            raise ProviderError("publishing_request_rejected")
        return response

    async def verify(self):
        if self.channel == "wordpress":
            site = self.credentials.get("site_id", "")
            if not re.fullmatch(r"[0-9]{1,20}", site):
                raise ProviderError("numeric_wordpress_site_id_required")
            response = await self.request(
                "GET", "https://public-api.wordpress.com/rest/v1.1/me/sites"
            )
            if not any(str(row.get("ID")) == site for row in response.json().get("sites", [])):
                raise ProviderError("wordpress_site_membership_required")
            return "WordPress site " + site
        response = await self.request("GET", "https://api.linkedin.com/v2/userinfo")
        subject = str(response.json().get("sub", ""))
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", subject):
            raise ProviderError("linkedin_identity_missing")
        author = "urn:li:person:" + subject
        if self.credentials.get("author_urn") not in {None, "", author}:
            raise ProviderError("linkedin_author_identity_mismatch")
        self.credentials["author_urn"] = author
        return author

    async def publish(self, title, body):
        if self.channel == "wordpress":
            site = self.credentials.get("site_id", "")
            if not re.fullmatch(r"[0-9]{1,20}", site):
                raise ProviderError("numeric_wordpress_site_id_required")
            response = await self.request(
                "POST",
                f"https://public-api.wordpress.com/wp/v2/sites/{site}/posts",
                json={
                    "title": html.escape(title),
                    "content": "<p>" + html.escape(body).replace("\n", "<br>") + "</p>",
                    "status": "publish",
                },
            )
            try:
                result = response.json()
                if not result.get("id"):
                    raise ValueError()
                return {
                    "provider_id": str(result["id"]),
                    "url": str(result.get("link", "")),
                    "status": "published",
                }
            except (ValueError, TypeError, AttributeError):
                raise ProviderError("publishing_receipt_missing", uncertain=True) from None
        author = self.credentials.get("author_urn", "")
        if not re.fullmatch(r"urn:li:person:[A-Za-z0-9_-]{1,100}", author):
            raise ProviderError("verified_linkedin_member_required")
        text = title + "\n\n" + body
        if len(text) > 3000:
            raise ProviderError("linkedin_text_exceeds_3000_characters")
        response = await self.request(
            "POST",
            "https://api.linkedin.com/rest/posts",
            json={
                "author": author,
                "commentary": text,
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            },
        )
        receipt = response.headers.get("x-restli-id", "")
        if not re.fullmatch(r"urn:li:(share|ugcPost):[0-9]+", receipt):
            raise ProviderError("publishing_receipt_missing", uncertain=True)
        return {"provider_id": receipt, "status": "published"}


async def check_publication(session, org_id, payload):
    item = await find(session, Content, org_id, payload["content_id"])
    if item.title != payload["title"] or item.body != payload["body"]:
        raise HTTPException(409, "approval_payload_changed")
    brand = await find(session, Brand, org_id, item.brand_id)
    await guard_content(session, brand, item.title, item.title, item.body, item.citations)
    return item, brand


async def prepare_publication(session, settings, effect, approval, transport):
    payload = effect.payload
    _, brand = await check_publication(session, effect.organization_id, payload)
    if brand.voice.get("sandbox_only"):
        raise ProviderError("sample_business_is_sandbox_only")
    connection = await active(session, settings, effect.organization_id, payload["channel"])
    if not connection or (connection["id"], connection["version"]) != (
        effect.result.get("_connection_id"),
        effect.result.get("_connection_version"),
    ):
        raise ProviderError("connection_changed_or_disconnected")
    return (
        connection,
        PublishingProvider(payload["channel"], connection["credentials"], transport),
        {"title": payload["title"], "body": payload["body"]},
    )


def install_publishing(app, settings, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.post("/content/{content_id}/channel-approval", status_code=201)
    async def request_publication(
        content_id: str,
        data: ChannelInput,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await require(session, request, who, {"owner", "admin"})
        org_id = who["organization"].id
        item = await find(session, Content, org_id, content_id)
        if data.channel == "linkedin" and len(item.title + "\n\n" + item.body) > 3000:
            raise HTTPException(422, "linkedin_text_exceeds_3000_characters")
        connection = await active(session, settings, org_id, data.channel)
        payload = {
            "content_id": item.id,
            "title": item.title,
            "body": item.body,
            "channel": data.channel,
            "connection_id": connection["id"] if connection else None,
            "connection_version": connection["version"] if connection else None,
        }
        await check_publication(session, org_id, payload)
        approval = await freeze(
            session, org_id, who["user"].id, "content", item.id, "publish_channel", payload
        )
        await session.commit()
        return public(approval)

    app.include_router(router)
