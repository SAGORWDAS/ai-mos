"""Provider transports. They are not allowed to bypass the workflow gateway.

HTTP contracts are exercised with mock transports. Sandbox remains the application's
active execution path until tenant credentials and provider preflight are verified.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time
from collections import OrderedDict
from datetime import UTC, datetime
from email.message import EmailMessage
from urllib.parse import quote

import httpx


class ProviderError(Exception):
    def __init__(self, code, uncertain=False):
        super().__init__(code)
        self.code, self.uncertain = code, uncertain


def require_secret(value):
    if not value or value.lower().startswith(("placeholder", "replace-", "your-", "<")):
        raise ProviderError("provider_credentials_missing")


class GoogleProvider:
    _availability_cache = OrderedDict()

    def __init__(self, access_token, sender="", calendar_id="primary", transport=None):
        self.access_token, self.sender, self.calendar_id = access_token, sender, calendar_id
        self.transport = transport

    async def request(self, method, url, **kwargs):
        require_secret(self.access_token)
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=30) as client:
                response = await client.request(
                    method, url, headers={"Authorization": f"Bearer {self.access_token}"}, **kwargs
                )
        except httpx.TransportError:
            raise ProviderError("provider_transport_failure", uncertain=method != "GET") from None
        if response.status_code in {401, 403}:
            raise ProviderError("provider_grant_invalid")
        if response.status_code == 429:
            raise ProviderError("provider_quota_exhausted")
        if response.status_code >= 500:
            raise ProviderError("provider_unavailable", uncertain=method != "GET")
        if response.status_code >= 400:
            raise ProviderError("provider_request_rejected")
        try:
            result = response.json()
        except ValueError:
            raise ProviderError("provider_invalid_response", uncertain=method != "GET") from None
        return result

    async def refresh(self, client_id, client_secret, refresh_token):
        for value in (client_id, client_secret, refresh_token):
            require_secret(value)
        async with httpx.AsyncClient(transport=self.transport, timeout=20) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                },
            )
        if response.status_code != 200:
            raise ProviderError("provider_refresh_failed")
        result = response.json()
        if not result.get("access_token"):
            raise ProviderError("provider_invalid_response")
        self.access_token = result["access_token"]
        return {
            "access_token": self.access_token,
            "expires_at": time.time() + int(result.get("expires_in", 0)),
        }

    @staticmethod
    def message_id(idempotency_key):
        return hashlib.sha256(idempotency_key.encode()).hexdigest() + "@ai-mos.local"

    async def send_email(self, recipient, subject, body, idempotency_key):
        if not self.sender or any(char in self.sender for char in "\r\n"):
            raise ProviderError("sender_required")
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self.sender, recipient, subject
        message["Message-ID"] = "<" + self.message_id(idempotency_key) + ">"
        message["Auto-Submitted"] = "auto-generated"
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = await self.request(
            "POST",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            json={"raw": raw},
        )
        if not result.get("id"):
            raise ProviderError("provider_receipt_missing", uncertain=True)
        # Gmail acceptance does not prove inbox delivery.
        return {"provider_id": result["id"], "thread_id": result.get("threadId"), "status": "sent"}

    async def reconcile_email(self, idempotency_key):
        result = await self.request(
            "GET",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params={
                "q": "in:sent rfc822msgid:" + self.message_id(idempotency_key),
                "maxResults": 2,
            },
        )
        messages = result.get("messages", [])
        if len(messages) == 1:
            return {"status": "found", "provider_id": messages[0]["id"]}
        return {"status": "ambiguous" if messages else "not_found", "retry_send_allowed": False}

    async def inbox_page(self, page_token=None):
        result = await self.request(
            "GET",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params={
                "labelIds": "INBOX",
                "maxResults": 20,
                **({"pageToken": page_token} if page_token else {}),
            },
        )
        limit = asyncio.Semaphore(5)

        async def fetch(entry):
            async with limit:
                return await self.request(
                    "GET",
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/"
                    + quote(entry["id"], safe=""),
                    params={"format": "full"},
                )

        messages = await asyncio.gather(
            *(fetch(entry) for entry in result.get("messages", [])[:20])
        )
        return {"messages": messages, "next_cursor": result.get("nextPageToken")}

    async def availability(self, starts_at, ends_at, *, use_cache=False):
        cache_key = (
            hashlib.sha256(self.access_token.encode()).hexdigest(),
            self.calendar_id,
            starts_at,
            ends_at,
        )
        cached = self._availability_cache.get(cache_key) if use_cache else None
        if cached and cached[0] > time.monotonic():
            return cached[1]
        result = await self.request(
            "POST",
            "https://www.googleapis.com/calendar/v3/freeBusy",
            json={
                "timeMin": datetime.fromtimestamp(starts_at, UTC).isoformat(),
                "timeMax": datetime.fromtimestamp(ends_at, UTC).isoformat(),
                "items": [{"id": self.calendar_id}],
            },
        )
        calendar = result.get("calendars", {}).get(self.calendar_id)
        if not calendar or calendar.get("errors") or "busy" not in calendar:
            raise ProviderError("availability_unknown")
        available = not calendar["busy"]
        if use_cache:
            self._availability_cache[cache_key] = (time.monotonic() + 45, available)
            self._availability_cache.move_to_end(cache_key)
            while len(self._availability_cache) > 256:
                self._availability_cache.popitem(last=False)
        return available

    async def book(self, title, starts_at, ends_at, attendee, idempotency_key):
        if not await self.availability(starts_at, ends_at):
            raise ProviderError("meeting_slot_unavailable")
        event_id = hashlib.sha256(idempotency_key.encode()).hexdigest()
        url = "https://www.googleapis.com/calendar/v3/calendars/" + quote(self.calendar_id, safe="")
        result = await self.request(
            "POST",
            url + "/events",
            params={"sendUpdates": "all"},
            json={
                "id": event_id,
                "summary": title,
                "start": {"dateTime": datetime.fromtimestamp(starts_at, UTC).isoformat()},
                "end": {"dateTime": datetime.fromtimestamp(ends_at, UTC).isoformat()},
                "attendees": [{"email": attendee}],
            },
        )
        if result.get("id") != event_id:
            raise ProviderError("provider_receipt_mismatch", uncertain=True)
        return {"provider_id": event_id, "status": "booked", "url": result.get("htmlLink")}

    async def reconcile_booking(self, idempotency_key):
        event_id = hashlib.sha256(idempotency_key.encode()).hexdigest()
        try:
            result = await self.request(
                "GET",
                "https://www.googleapis.com/calendar/v3/calendars/"
                + quote(self.calendar_id, safe="")
                + "/events/"
                + event_id,
            )
        except ProviderError:
            return {"status": "not_confirmed", "retry_send_allowed": False}
        if result.get("id") == event_id and result.get("status") != "cancelled":
            return {"status": "found", "provider_id": event_id}
        return {"status": "not_confirmed", "retry_send_allowed": False}


class StripeProvider:
    def __init__(self, secret_key, webhook_secret, transport=None):
        self.secret_key, self.webhook_secret, self.transport = secret_key, webhook_secret, transport

    async def checkout(
        self,
        description,
        amount_minor,
        currency,
        success_url,
        cancel_url,
        idempotency_key,
        recurring=False,
        local_ref=None,
        org_ref=None,
    ):
        require_secret(self.secret_key)
        if not success_url.startswith("https://") or not cancel_url.startswith("https://"):
            raise ProviderError("https_return_urls_required")
        fields = {
            "mode": "subscription" if recurring else "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][unit_amount]": str(amount_minor),
            "line_items[0][price_data][product_data][name]": description,
        }
        if recurring:
            fields["line_items[0][price_data][recurring][interval]"] = "month"
            if local_ref and org_ref:
                fields["subscription_data[metadata][ai_mos_checkout_id]"] = local_ref
                fields["subscription_data[metadata][ai_mos_organization_id]"] = org_ref
        if local_ref and org_ref:
            fields["metadata[ai_mos_checkout_id]"] = local_ref
            fields["metadata[ai_mos_organization_id]"] = org_ref
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=30) as client:
                response = await client.post(
                    "https://api.stripe.com/v1/checkout/sessions",
                    auth=(self.secret_key, ""),
                    headers={"Idempotency-Key": idempotency_key},
                    data=fields,
                )
        except httpx.TransportError:
            raise ProviderError("checkout_transport_failure", uncertain=True) from None
        if response.status_code != 200:
            raise ProviderError("checkout_provider_error", uncertain=response.status_code >= 500)
        result = response.json()
        if not result.get("id") or not str(result.get("url", "")).startswith(
            "https://checkout.stripe.com/"
        ):
            raise ProviderError("invalid_checkout_receipt", uncertain=True)
        return {"provider_ref": result["id"], "url": result["url"], "status": "pending"}

    def verify_event(self, raw_body, header):
        require_secret(self.webhook_secret)
        parts = [entry.split("=", 1) for entry in (header or "").split(",") if "=" in entry]
        timestamps = [value for key, value in parts if key == "t"]
        signatures = [value for key, value in parts if key == "v1"]
        try:
            timestamp = int(timestamps[0])
        except (IndexError, ValueError):
            raise ProviderError("webhook_signature_invalid") from None
        expected = hmac.new(
            self.webhook_secret.encode(), str(timestamp).encode() + b"." + raw_body, hashlib.sha256
        ).hexdigest()
        if abs(time.time() - timestamp) > 300 or not any(
            hmac.compare_digest(expected, item) for item in signatures
        ):
            raise ProviderError("webhook_signature_invalid")
        try:
            result = json.loads(raw_body)
        except ValueError:
            raise ProviderError("webhook_payload_invalid") from None
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("id"), str)
            or not 1 <= len(result["id"]) <= 200
            or not isinstance(result.get("type"), str)
            or not 1 <= len(result["type"]) <= 80
        ):
            raise ProviderError("webhook_payload_invalid")
        return result
