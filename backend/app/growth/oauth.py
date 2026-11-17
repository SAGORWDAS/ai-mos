import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, update

from app.growth import connections
from app.growth.models import Integration
from app.growth.providers import ProviderError, require_secret
from app.growth.runtime import record
from app.models import Membership, Organization
from app.tenancy import tenant_scope

SCOPES = {
    "gmail": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly",
    "calendar": "https://www.googleapis.com/auth/calendar.events "
    "https://www.googleapis.com/auth/calendar.readonly "
    "https://www.googleapis.com/auth/calendar.freebusy",
}


def install_oauth(app, runtime, settings, db, identity, require):
    router = APIRouter(prefix="/v1")
    runtime.oauth_transport = None

    @router.post("/connections/{provider}/oauth/start")
    async def start(provider: str, request: Request, who=Depends(identity), session=Depends(db)):
        await require(session, request, who, {"owner"})
        if provider not in SCOPES:
            raise HTTPException(404, "oauth_provider_not_supported")
        item = await session.scalar(
            select(Integration).where(
                Integration.organization_id == who["organization"].id,
                Integration.provider == provider,
            )
        )
        if not item or not item.token_ciphertext:
            raise HTTPException(409, "save_oauth_client_configuration_first")
        credentials = connections.unseal(settings, item)
        try:
            require_secret(credentials.get("client_id", ""))
            require_secret(credentials.get("client_secret", ""))
        except ProviderError:
            raise HTTPException(409, "oauth_client_credentials_required") from None
        public = settings.public_api_url.rstrip("/")
        parsed = urlsplit(public)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
        ):
            raise HTTPException(409, "https_public_api_url_required")
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        redirect = f"{public}/v1/oauth/google/{item.organization_id}/{provider}/callback"
        credentials.update(
            {
                "_oauth_state_hash": hashlib.sha256(state.encode()).hexdigest(),
                "_oauth_verifier": verifier,
                "_oauth_expires": time.time() + 600,
                "_oauth_actor": who["user"].id,
                "_oauth_redirect": redirect,
            }
        )
        item.token_ciphertext = connections.seal(
            settings, provider, item.organization_id, credentials
        )
        item.enabled, item.status = False, "oauth_pending"
        item.sync_enabled = False
        item.sync_next_at = 0
        item.version += 1
        await record(
            session, item.organization_id, who["user"].id, "connection.oauth_started", item.id
        )
        await session.commit()
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        return {
            "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?"
            + urlencode(
                {
                    "client_id": credentials["client_id"],
                    "redirect_uri": redirect,
                    "response_type": "code",
                    "scope": SCOPES[provider],
                    "access_type": "offline",
                    "prompt": "consent",
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            ),
            "redirect_uri": redirect,
            "expires_in": 600,
        }

    @router.get("/oauth/google/{org_id}/{provider}/callback")
    async def callback(
        org_id: str,
        provider: str,
        request: Request,
        state: str = "",
        code: str = "",
        session=Depends(db),
    ):
        if provider not in SCOPES or not 20 <= len(state) <= 200 or not 1 <= len(code) <= 4000:
            raise HTTPException(400, "invalid_oauth_callback")
        await tenant_scope(session, organization_id=org_id)
        await session.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(emergency_stop=Organization.emergency_stop)
        )
        if await session.scalar(
            select(Organization.emergency_stop).where(Organization.id == org_id)
        ):
            raise HTTPException(423, "workspace_paused")
        item = await session.scalar(
            select(Integration).where(
                Integration.organization_id == org_id, Integration.provider == provider
            )
        )
        if not item or item.status != "oauth_pending":
            raise HTTPException(400, "oauth_attempt_missing_or_used")
        credentials = connections.unseal(settings, item)
        if credentials.get("_oauth_expires", 0) <= time.time() or not hmac.compare_digest(
            credentials.get("_oauth_state_hash", ""), hashlib.sha256(state.encode()).hexdigest()
        ):
            raise HTTPException(400, "oauth_state_invalid_or_expired")
        actor = credentials.get("_oauth_actor")
        if not await session.scalar(
            select(Membership.id).where(
                Membership.organization_id == org_id,
                Membership.user_id == actor,
                Membership.role == "owner",
            )
        ):
            raise HTTPException(403, "oauth_owner_changed")
        redirect, verifier = credentials["_oauth_redirect"], credentials["_oauth_verifier"]
        credentials = {
            key: value for key, value in credentials.items() if not key.startswith("_oauth_")
        }
        item.token_ciphertext = connections.seal(settings, provider, org_id, credentials)
        item.status = "configured"
        expected_version = item.version
        await session.commit()  # Claim state before exchanging a single-use authorization code.
        try:
            async with httpx.AsyncClient(timeout=20, transport=runtime.oauth_transport) as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": credentials["client_id"],
                        "client_secret": credentials["client_secret"],
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect,
                        "code_verifier": verifier,
                    },
                )
                response.raise_for_status()
                tokens = response.json()
            require_secret(tokens.get("access_token", ""))
            credentials.pop("access_token", None)
            credentials.pop("refresh_token", None)
            credentials["access_token"] = tokens["access_token"]
            if tokens.get("refresh_token"):
                credentials["refresh_token"] = tokens["refresh_token"]
            if provider == "gmail":
                credentials.pop("sender", None)
        except (httpx.HTTPError, ValueError, TypeError, ProviderError):
            raise HTTPException(502, "oauth_exchange_failed_start_again") from None
        await session.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(emergency_stop=Organization.emergency_stop)
        )
        await session.refresh(item)
        if not await session.scalar(
            select(Membership.id).where(
                Membership.organization_id == org_id,
                Membership.user_id == actor,
                Membership.role == "owner",
            )
        ):
            raise HTTPException(403, "oauth_owner_changed")
        if (
            item.version != expected_version
            or item.status == "revoked"
            or await session.scalar(
                select(Organization.emergency_stop).where(Organization.id == org_id)
            )
        ):
            raise HTTPException(409, "connection_changed_or_workspace_paused")
        item.token_ciphertext = connections.seal(settings, provider, org_id, credentials)
        result = await connections.verify(settings, item, transport=runtime.oauth_transport)
        item.status, item.account_ref = result["status"], result["account_ref"]
        item.enabled = False
        await record(session, org_id, actor, "connection.oauth_completed", item.id)
        await session.commit()
        return HTMLResponse(
            '<!doctype html><html lang="en"><title>Google connected</title><main>'
            "<h1>Google account verified</h1><p>Return to Integrations to review and enable "
            "the connection. It remains disabled.</p></main></html>",
            headers={
                "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
                "Referrer-Policy": "no-referrer",
            },
        )

    app.include_router(router)
