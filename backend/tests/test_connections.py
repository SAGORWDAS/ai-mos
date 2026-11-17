import base64
import hashlib
import hmac
import json
import sqlite3
import time

import httpx
from test_foundation import signup
from test_growth import approve, brand_and_lead, drain, key, make_draft, rows

from app.growth import connections
from app.growth.providers import StripeProvider


def connect_gmail(client, monkeypatch):
    original = connections.verify

    async def verified(settings, item):
        return await original(
            settings,
            item,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"emailAddress": "sender@example.test"})
            ),
        )

    monkeypatch.setattr(connections, "verify", verified)
    saved = client.put(
        "/v1/connections/gmail",
        json={
            "account_ref": "sender@example.test",
            "credentials": {"access_token": "unit-token", "sender": "sender@example.test"},
        },
    )
    assert saved.status_code == 200, saved.text
    assert client.post("/v1/connections/gmail/verify").json()["status"] == "verified"
    assert client.post("/v1/connections/gmail/activate").json()["enabled"] is True


def queue_live(client, approval):
    result = client.post(
        "/v1/effects/execute",
        json={"approval_id": approval["id"], "idempotency_key": key(), "execution_mode": "live"},
    )
    assert result.status_code == 200, result.text
    return result.json()


def test_placeholder_credentials_are_encrypted_scoped_and_cannot_activate(clients, tmp_path):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    secret = "placeholder-openrouter-secret"
    result = a.put(
        "/v1/connections/openrouter",
        json={
            "account_ref": "Local test",
            "credentials": {"api_key": secret, "model_id": "placeholder/model"},
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "placeholder"
    assert a.post("/v1/connections/openrouter/verify").json()["status"] == "placeholder"
    assert a.post("/v1/connections/openrouter/activate").status_code == 409
    assert secret not in a.get("/v1/connections").text
    assert b.get("/v1/connections").json() == []
    assert a.get("/v1/data/integrations").status_code == 404
    assert secret not in a.get("/v1/exports/workspace").text
    with sqlite3.connect(tmp_path / "test.db") as db:
        ciphertext = db.execute("SELECT token_ciphertext FROM integrations").fetchone()[0]
        assert secret not in ciphertext
    assert a.post("/v1/connections/openrouter/disconnect").status_code == 200


def test_live_dispatch_waits_for_receipt_and_sandbox_stays_explicit(clients, monkeypatch):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    connect_gmail(client, monkeypatch)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"id": "provider-receipt", "threadId": "thread-1"})

    client.app.state.runtime.delivery.transport = httpx.MockTransport(handle)
    approval = approve(client, make_draft(client, lead))
    queued = queue_live(client, approval)
    assert queued["simulated"] is False
    assert rows(client, "messages")[0]["status"] == "queued"
    assert client.get("/v1/analytics").json()["sent"] == 0
    drain(client)
    assert rows(client, "messages")[0]["status"] == "sent"
    assert rows(client, "effects")[0]["status"] == "succeeded"
    assert client.get("/v1/analytics").json()["real_sends"] == 1
    assert len(calls) == 1
    # A sandbox request cannot become live merely because credentials are enabled.
    other = approve(client, make_draft(client, lead))
    result = client.post(
        "/v1/effects/execute", json={"approval_id": other["id"], "idempotency_key": key()}
    )
    assert result.json()["simulated"] is True
    drain(client)
    assert len(calls) == 1


def test_ambiguous_send_is_never_retried_and_can_be_reconciled(clients, monkeypatch):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    connect_gmail(client, monkeypatch)
    sends = []

    def handle(request):
        if request.method == "POST":
            sends.append(request)
            raise httpx.ReadTimeout("receipt lost")
        return httpx.Response(200, json={"messages": [{"id": "found-receipt"}]})

    client.app.state.runtime.delivery.transport = httpx.MockTransport(handle)
    queued = queue_live(client, approve(client, make_draft(client, lead)))
    drain(client)
    assert rows(client, "effects")[0]["status"] == "uncertain"
    drain(client)
    assert len(sends) == 1
    result = client.post(f"/v1/effects/{queued['effect_id']}/reconcile")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "reconciled"
    assert rows(client, "messages")[0]["provider_id"] == "found-receipt"
    assert len(sends) == 1


def test_suppression_between_queue_and_dispatch_blocks_provider(clients, monkeypatch):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    connect_gmail(client, monkeypatch)

    def unexpected(request):
        raise AssertionError("Suppressed contact reached provider")

    client.app.state.runtime.delivery.transport = httpx.MockTransport(unexpected)
    queue_live(client, approve(client, make_draft(client, lead)))
    client.post("/v1/suppressions", json={"email": lead["email"], "reason": "manual"})
    drain(client)
    assert rows(client, "effects")[0]["status"] == "failed"
    assert rows(client, "effects")[0]["result"]["receipt"]["error"] == "suppressed_recipient"


def test_provider_inbox_deduplicates_and_suppresses_before_followup(clients, monkeypatch):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    connect_gmail(client, monkeypatch)
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == "GET"
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                200, json={"messages": [{"id": "inbound-1"}], "nextPageToken": "page-two"}
            )
        return httpx.Response(
            200,
            json={
                "id": "inbound-1",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [
                        {"name": "From", "value": lead["email"]},
                        {"name": "Subject", "value": "Please stop"},
                    ],
                    "body": {
                        "data": base64.urlsafe_b64encode(
                            b"Unsubscribe and do not contact me again."
                        ).decode()
                    },
                },
            },
        )

    client.app.state.runtime.delivery.transport = httpx.MockTransport(handle)
    first = client.post("/v1/inbox/sync", json={})
    assert first.status_code == 200, first.text
    assert first.json()["imported"] == 1
    assert first.json()["next_cursor"] == "page-two"
    assert rows(client, "leads")[0]["status"] == "suppressed"
    assert rows(client, "messages")[0]["simulated"] is False
    second = client.post("/v1/inbox/sync", json={})
    assert second.json()["duplicates"] == 1
    assert len(rows(client, "messages")) == 1


def test_connected_checkout_only_signed_matching_receipt_converts_customer(clients, monkeypatch):
    client, outsider = clients
    owner = signup(client)
    signup(outsider, "outside@example.test")
    _, lead = brand_and_lead(client)
    original_verify, original_checkout = connections.verify, StripeProvider.checkout
    checkout_calls = []

    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json={"id": "acct_unit", "charges_enabled": True})
        checkout_calls.append(request)
        return httpx.Response(
            200, json={"id": "cs_unit", "url": "https://checkout.stripe.com/c/pay/cs_unit"}
        )

    transport = httpx.MockTransport(handle)

    async def verify(settings, item):
        return await original_verify(settings, item, transport)

    async def checkout(self, *args, **kwargs):
        self.transport = transport
        return await original_checkout(self, *args, **kwargs)

    monkeypatch.setattr(connections, "verify", verify)
    monkeypatch.setattr(StripeProvider, "checkout", checkout)
    assert (
        client.put(
            "/v1/connections/stripe",
            json={
                "account_ref": "Unit merchant",
                "credentials": {
                    "secret_key": "sk_test_unit",
                    "webhook_secret": "whsec_unit",
                    "success_url": "https://example.test/thanks",
                    "cancel_url": "https://example.test/cancel",
                },
            },
        ).status_code
        == 200
    )
    assert client.post("/v1/connections/stripe/verify").status_code == 200
    assert client.post("/v1/connections/stripe/activate").status_code == 200
    created = client.post(
        "/v1/checkouts",
        json={
            "lead_id": lead["id"],
            "description": "Service package",
            "amount_minor": 7500,
            "currency": "USD",
            "execution_mode": "live",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "creating"
    drain(client)
    assert rows(client, "checkouts")[0]["provider_ref"] == "cs_unit"
    assert len(checkout_calls) == 1
    assert not rows(client, "customers")
    assert (
        client.post(
            f"/v1/checkouts/{created.json()['id']}/simulate-payment",
            json={"event_id": "fake-event"},
        ).status_code
        == 403
    )
    event = {
        "id": "evt_unit",
        "type": "checkout.session.completed",
        "livemode": False,
        "data": {
            "object": {
                "id": "cs_unit",
                "payment_status": "paid",
                "amount_total": 7500,
                "currency": "usd",
            }
        },
    }
    body = json.dumps(event).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        b"whsec_unit", timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    url = f"/v1/webhooks/stripe/{owner['organization']['id']}"
    assert outsider.post(url, content=body).status_code == 401
    verified = outsider.post(
        url, content=body, headers={"stripe-signature": f"t={timestamp},v1={signature}"}
    )
    assert verified.status_code == 200, verified.text
    assert len(rows(client, "customers")) == 1
    assert rows(client, "payments")[0]["simulated"] is True
    assert (
        outsider.post(
            url, content=body, headers={"stripe-signature": f"t={timestamp},v1={signature}"}
        ).status_code
        == 200
    )
    assert len(rows(client, "payments")) == 1


def test_live_model_failure_retains_unknown_cost_but_records_known_charge(clients):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    runtime = client.app.state.runtime
    runtime.settings.provider_mode = "openrouter"
    runtime.settings.openrouter_api_key = "unit-key"
    runtime.settings.model_id = "unit/model"
    runtime.gateway.transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"not-json")
    )
    assert (
        client.post(
            "/v1/drafts", json={"lead_id": lead["id"], "idempotency_key": key()}
        ).status_code
        == 202
    )
    drain(client)
    assert rows(client, "model_usage")[0]["status"] == "invalid_output"
    assert client.get("/v1/budgets/current").json()["reserved_micros"] == 20000
    runtime.gateway.transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "usage": {"cost": 0.004, "prompt_tokens": 10, "completion_tokens": 5},
                "choices": [{"message": {"content": "broken-json"}}],
            },
        )
    )
    assert (
        client.post(
            "/v1/drafts", json={"lead_id": lead["id"], "idempotency_key": key()}
        ).status_code
        == 202
    )
    drain(client)
    budget = client.get("/v1/budgets/current").json()
    assert budget["reserved_micros"] == 20000
    assert budget["spent_micros"] == 4000
    assert len(rows(client, "model_usage")) == 2
