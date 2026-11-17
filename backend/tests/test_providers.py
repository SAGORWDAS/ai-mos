import base64
import hashlib
import hmac
import json
import time

import httpx
import pytest

from app.growth.providers import GoogleProvider, ProviderError, StripeProvider


@pytest.mark.asyncio
async def test_gmail_transport_receipt_and_timeout_uncertainty():
    def handle(request):
        assert request.url.host == "gmail.googleapis.com"
        raw = base64.urlsafe_b64decode(json.loads(request.content)["raw"])
        assert b"Message-ID:" in raw
        assert b"unsubscribe" in raw
        return httpx.Response(200, json={"id": "provider-message-1", "threadId": "thread-1"})

    provider = GoogleProvider(
        "unit-token", sender="qa@example.test", transport=httpx.MockTransport(handle)
    )
    result = await provider.send_email(
        "test@example.test", "Question", "Reply unsubscribe", "unique-send"
    )
    assert result["status"] == "sent"

    def timeout(request):
        raise httpx.ReadTimeout("test timeout")

    provider.transport = httpx.MockTransport(timeout)
    with pytest.raises(ProviderError) as error:
        await provider.send_email(
            "test@example.test", "Question", "Reply unsubscribe", "unique-send"
        )
    assert error.value.uncertain is True


@pytest.mark.asyncio
async def test_calendar_rechecks_and_missing_availability_fails_closed():
    paths = []

    def handle(request):
        paths.append(request.url.path)
        if request.url.path.endswith("freeBusy"):
            return httpx.Response(200, json={"calendars": {"primary": {"busy": []}}})
        return httpx.Response(200, json={"id": json.loads(request.content)["id"]})

    provider = GoogleProvider("unit-token", transport=httpx.MockTransport(handle))
    assert (
        await provider.book(
            "Test", time.time() + 3600, time.time() + 5400, "test@example.test", "booking-1"
        )
    )["status"] == "booked"
    assert paths[0].endswith("freeBusy")
    provider.transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"calendars": {}})
    )
    with pytest.raises(ProviderError, match="availability_unknown"):
        await provider.book(
            "Test", time.time() + 3600, time.time() + 5400, "test@example.test", "booking-2"
        )


@pytest.mark.asyncio
async def test_stripe_checkout_never_infers_payment_and_webhook_checks_raw_body():
    provider = StripeProvider(
        "unit-secret",
        "unit-webhook",
        httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"id": "cs_test_fixture", "url": "https://checkout.stripe.com/test"}
            )
        ),
    )
    result = await provider.checkout(
        "Test",
        1000,
        "USD",
        "https://example.test/success",
        "https://example.test/cancel",
        "checkout-1",
    )
    assert result["status"] == "pending"
    body = json.dumps({"id": "evt_test_fixture", "type": "checkout.session.completed"}).encode()
    stamp = int(time.time())
    signed = hmac.new(
        b"unit-webhook", str(stamp).encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    assert provider.verify_event(body, f"t={stamp},v1={signed}")["id"] == "evt_test_fixture"
    with pytest.raises(ProviderError, match="signature"):
        provider.verify_event(body + b" ", f"t={stamp},v1={signed}")


@pytest.mark.asyncio
async def test_placeholder_credentials_never_make_a_request():
    def unexpected(request):
        raise AssertionError("Placeholder credential reached network transport")

    provider = GoogleProvider(
        "placeholder-access-token",
        sender="qa@example.test",
        transport=httpx.MockTransport(unexpected),
    )
    with pytest.raises(ProviderError, match="credentials_missing"):
        await provider.send_email("test@example.test", "Test", "Test", "unique")
