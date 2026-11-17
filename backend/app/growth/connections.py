import json

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import select

from app.growth.models import Integration
from app.growth.providers import GoogleProvider, ProviderError, require_secret
from app.tenancy import tenant_scope

PROVIDERS = {
    "meta_ads",
    "openrouter",
    "gmail",
    "calendar",
    "stripe",
    "resend",
    "brave",
    "wordpress",
    "linkedin",
}
FIELDS = {
    "meta_ads": {"access_token", "ad_account_id", "page_id", "currency"},
    "wordpress": {"access_token", "site_id"},
    "linkedin": {"access_token", "author_urn"},
    "resend": {"api_key", "sender", "webhook_secret"},
    "brave": {"api_key", "search_price_micros"},
    "openrouter": {"api_key", "model_id", "embedding_model_id", "image_model_id"},
    "gmail": {"access_token", "sender", "refresh_token", "client_id", "client_secret"},
    "calendar": {"access_token", "calendar_id", "refresh_token", "client_id", "client_secret"},
    "stripe": {"secret_key", "webhook_secret", "success_url", "cancel_url"},
}


def cipher(settings):
    try:
        return Fernet(settings.token_encryption_key.encode())
    except (ValueError, TypeError):
        raise HTTPException(409, "valid_credential_encryption_key_required") from None


def seal(settings, provider, org_id, credentials):
    envelope = {"provider": provider, "organization_id": org_id, "credentials": credentials}
    return cipher(settings).encrypt(json.dumps(envelope).encode()).decode()


def unseal(settings, item):
    try:
        payload = json.loads(cipher(settings).decrypt(item.token_ciphertext.encode()))
    except (InvalidToken, ValueError, KeyError):
        raise HTTPException(409, "credentials_cannot_be_decrypted") from None
    if (
        payload.get("provider") != item.provider
        or payload.get("organization_id") != item.organization_id
    ):
        raise HTTPException(409, "credential_scope_mismatch")
    return payload["credentials"]


def public_connection(item):
    return {
        "id": item.id,
        "provider": item.provider,
        "account_ref": item.account_ref,
        "status": item.status,
        "enabled": item.enabled,
        "version": item.version,
        "sync_enabled": item.sync_enabled,
        "auto_draft_replies": item.auto_draft_replies,
        "sync_interval_minutes": item.sync_interval_minutes,
        "sync_last_at": item.sync_last_at,
        "sync_error": item.sync_error,
    }


async def active(session, settings, org_id, provider):
    await tenant_scope(session, organization_id=org_id)
    item = await session.scalar(
        select(Integration).where(
            Integration.organization_id == org_id,
            Integration.provider == provider,
            Integration.status == "verified",
            Integration.enabled.is_(True),
        )
    )
    if not item:
        return None
    return {**public_connection(item), "credentials": unseal(settings, item)}


def is_placeholder(credentials):
    tokens = [
        value
        for key, value in credentials.items()
        if key in {"api_key", "access_token", "secret_key", "refresh_token"}
    ]
    return not tokens or any(
        not value or value.lower().startswith(("placeholder", "replace-", "your-"))
        for value in tokens
    )


async def verify(settings, item, transport=None):
    credentials = unseal(settings, item)
    if is_placeholder(credentials):
        return {"status": "placeholder", "account_ref": item.account_ref}
    try:
        if item.provider == "meta_ads":
            from app.growth.advertising import MetaProvider

            identity = await MetaProvider(credentials, transport).verify()
            item.token_ciphertext = seal(settings, item.provider, item.organization_id, credentials)
        elif item.provider in {"wordpress", "linkedin"}:
            from app.growth.publishing import PublishingProvider

            provider = PublishingProvider(item.provider, credentials, transport)
            identity = await provider.verify()
            item.token_ciphertext = seal(settings, item.provider, item.organization_id, credentials)
        elif item.provider in {"gmail", "calendar"}:
            google = GoogleProvider(credentials.get("access_token", ""), transport=transport)
            if not google.access_token and credentials.get("refresh_token"):
                refreshed = await google.refresh(
                    credentials.get("client_id", ""),
                    credentials.get("client_secret", ""),
                    credentials["refresh_token"],
                )
                credentials.update(refreshed)
                item.token_ciphertext = seal(
                    settings, item.provider, item.organization_id, credentials
                )
            if item.provider == "gmail":
                result = await google.request(
                    "GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile"
                )
                identity = result.get("emailAddress")
                if not identity:
                    raise ProviderError("provider_identity_missing")
                if credentials.get("sender") and credentials["sender"].lower() != identity.lower():
                    raise ProviderError("sender_identity_mismatch")
                credentials["sender"] = identity
                item.token_ciphertext = seal(
                    settings, item.provider, item.organization_id, credentials
                )
            else:
                from urllib.parse import quote

                result = await google.request(
                    "GET",
                    "https://www.googleapis.com/calendar/v3/calendars/"
                    + quote(credentials.get("calendar_id") or "primary", safe=""),
                )
                identity = result.get("id")
                if not identity:
                    raise ProviderError("provider_identity_missing")
        else:
            async with httpx.AsyncClient(transport=transport, timeout=20) as client:
                if item.provider == "openrouter":
                    key = credentials.get("api_key", "")
                    require_secret(key)
                    if not credentials.get("model_id"):
                        raise ProviderError("model_id_required")
                    response = await client.get(
                        "https://openrouter.ai/api/v1/key",
                        headers={"Authorization": f"Bearer {key}"},
                    )
                    identity = item.account_ref
                elif item.provider == "resend":
                    key = credentials.get("api_key", "")
                    require_secret(key)
                    require_secret(credentials.get("webhook_secret", ""))
                    sender = credentials.get("sender", "")
                    if "@" not in sender or any(char in sender for char in "\r\n<> "):
                        raise ProviderError("simple_sender_address_required")
                    response = await client.get(
                        "https://api.resend.com/domains", headers={"Authorization": "Bearer " + key}
                    )
                    if response.status_code == 200 and not any(
                        row.get("name", "").lower() == sender.rsplit("@", 1)[1].lower()
                        and row.get("status") == "verified"
                        for row in response.json().get("data", [])
                    ):
                        raise ProviderError("verified_sending_domain_required")
                    identity = sender
                elif item.provider == "brave":
                    key = credentials.get("api_key", "")
                    require_secret(key)
                    response = await client.get(
                        "https://api.search.brave.com/res/v1/web/search",
                        params={"q": "example.com", "count": 1},
                        headers={"X-Subscription-Token": key},
                    )
                    identity = item.account_ref
                else:
                    require_secret(credentials.get("secret_key", ""))
                    require_secret(credentials.get("webhook_secret", ""))
                    if not all(
                        credentials.get(key, "").startswith("https://")
                        for key in ["success_url", "cancel_url"]
                    ):
                        raise ProviderError("https_return_urls_required")
                    response = await client.get(
                        "https://api.stripe.com/v1/account", auth=(credentials["secret_key"], "")
                    )
                    identity = response.json().get("id") if response.status_code == 200 else None
                if response.status_code != 200:
                    raise ProviderError("provider_credentials_not_verified")
                if item.provider == "stripe" and not response.json().get("charges_enabled"):
                    raise ProviderError("merchant_charges_not_enabled")
        return {"status": "verified", "account_ref": identity or item.account_ref}
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "provider_verification_failed") from None
    except ProviderError as error:
        raise HTTPException(409, error.code) from None
