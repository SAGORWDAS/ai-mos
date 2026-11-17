"""Signed first-party enquiry attribution. No visitor identifiers or tracking cookies."""

import base64
import hashlib
import hmac
import json
import time
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from app.contracts import Input
from app.growth.models import Campaign, Content
from app.growth.runtime import find


class TrackingLink(Input):
    content_id: str
    channel: Literal["email", "website", "social", "paid_ad", "referral", "other"] = "website"
    expires_days: int = Field(default=30, ge=1, le=90)


def sign_tracking(settings, payload):
    if not settings.token_encryption_key:
        raise HTTPException(409, "persistent_signing_key_required")
    encoded = (
        base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        )
        .decode()
        .rstrip("=")
    )
    signature = hmac.new(
        settings.token_encryption_key.encode(),
        ("campaign-link:" + encoded).encode(),
        hashlib.sha256,
    ).hexdigest()
    return encoded + "." + signature


def verify_tracking(settings, token, org_id, content_id):
    try:
        encoded, signature = token.split(".")
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(raw)
        if not hmac.compare_digest(sign_tracking(settings, payload), token):
            raise ValueError()
        if (
            payload["org"] != org_id
            or payload["content"] != content_id
            or payload["expires"] < time.time()
            or payload["channel"]
            not in {"email", "website", "social", "paid_ad", "referral", "other"}
        ):
            raise ValueError()
        return payload
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, "invalid_or_expired_campaign_link") from None


def install_tracking(app, settings, db, identity, require):
    router = APIRouter(prefix="/v1")

    @router.post("/campaigns/{campaign_id}/tracking-link")
    async def link(
        campaign_id: str,
        data: TrackingLink,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await require(session, request, who, {"owner", "admin", "member"})
        org_id = who["organization"].id
        campaign = await find(session, Campaign, org_id, campaign_id)
        content = await find(session, Content, org_id, data.content_id)
        if campaign.brand_id != content.brand_id:
            raise HTTPException(422, "campaign_brand_mismatch")
        if content.status != "published_local":
            raise HTTPException(409, "publish_owned_page_first")
        expires = int(time.time() + data.expires_days * 86400)
        token = sign_tracking(
            settings,
            {
                "org": org_id,
                "content": content.id,
                "campaign": campaign.id,
                "channel": data.channel,
                "expires": expires,
            },
        )
        from app.growth.publication import public_base

        base = public_base(settings) or "/api"
        return {
            "url": f"{base}/v1/public/{org_id}/{content.id}?"
            + urlencode({"campaign_token": token}),
            "expires_at": expires,
            "note": "Enquiries record the signed source. No cookie is set; "
            "marketing permission is not established.",
        }

    app.include_router(router)
