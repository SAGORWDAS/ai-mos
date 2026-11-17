import base64
import hashlib
import hmac
import json
import time

import httpx
from test_foundation import signup
from test_growth import brand_and_lead, drain, key, make_draft, rows

from app.growth import connections

SVIX_KEY = b"unit-test-signing-key-32-bytes!!!"


def connect(client, monkeypatch, provider, credentials):
    original = connections.verify

    async def verify(settings, item):
        return await original(
            settings,
            item,
            httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "data": [{"name": "example.test", "status": "verified"}],
                        "web": {"results": []},
                    },
                )
            ),
        )

    monkeypatch.setattr(connections, "verify", verify)
    assert (
        client.put(
            "/v1/connections/" + provider,
            json={"account_ref": "Unit test provider", "credentials": credentials},
        ).status_code
        == 200
    )
    assert client.post("/v1/connections/" + provider + "/verify").status_code == 200
    assert client.post("/v1/connections/" + provider + "/activate").status_code == 200


def batch(client):
    brand, lead = brand_and_lead(client)
    second = client.post(
        "/v1/leads/import",
        json={
            "leads": [
                {
                    "brand_id": brand["id"],
                    "name": "Second opt-in contact",
                    "email": "second@example.test",
                    "source": "Synthetic opt-in fixture",
                    "lawful_basis": "consent",
                    "basis_evidence": "Synthetic fixture only",
                }
            ]
        },
    ).json()["created"][0]
    make_draft(client, lead)
    make_draft(client, second)
    campaign = client.post(
        "/v1/campaigns",
        json={
            "brand_id": brand["id"],
            "name": "Reviewed opt-in fixture",
            "lead_ids": [lead["id"], second["id"]],
        },
    ).json()
    approval = client.post(f"/v1/campaigns/{campaign['id']}/request-approval").json()
    assert (
        client.post(
            f"/v1/approvals/{approval['id']}/decision", json={"decision": "approved"}
        ).status_code
        == 200
    )
    return approval, lead


def test_live_bulk_dispatch_and_verified_delivery_bounce_webhooks(clients, monkeypatch):
    a, b = clients
    owner = signup(a)
    approval, lead = batch(a)
    connect(
        a,
        monkeypatch,
        "resend",
        {
            "api_key": "unit-esp-key",
            "sender": "sender@example.test",
            "webhook_secret": "whsec_" + base64.b64encode(SVIX_KEY).decode(),
        },
    )
    calls = []

    def handle(request):
        calls.append(request)
        assert request.url.host == "api.resend.com"
        assert len(json.loads(request.content)) == 2
        assert request.headers["idempotency-key"]
        return httpx.Response(200, json={"data": [{"id": "receipt-1"}, {"id": "receipt-2"}]})

    a.app.state.runtime.delivery.transport = httpx.MockTransport(handle)
    result = a.post(
        "/v1/effects/execute",
        json={"approval_id": approval["id"], "idempotency_key": key(), "execution_mode": "live"},
    )
    assert result.status_code == 200, result.text
    assert all(message["status"] == "queued" for message in rows(a, "messages"))
    drain(a)
    assert len(calls) == 1
    assert all(message["status"] == "sent" for message in rows(a, "messages"))
    assert rows(a, "campaigns")[0]["status"] == "completed"
    path = f"/v1/webhooks/resend/{owner['organization']['id']}"

    def callback(event_id, kind):
        body = json.dumps({"type": kind, "data": {"email_id": "receipt-1"}}).encode()
        timestamp = str(int(time.time()))
        sig = base64.b64encode(
            hmac.new(
                SVIX_KEY, (event_id + "." + timestamp + ".").encode() + body, hashlib.sha256
            ).digest()
        ).decode()
        assert b.post(path, content=body).status_code == 401
        return b.post(
            path,
            content=body,
            headers={
                "svix-id": event_id,
                "svix-timestamp": timestamp,
                "svix-signature": "v1," + sig,
            },
        )

    assert callback("event-delivery", "email.delivered").status_code == 200
    assert (
        next(m for m in rows(a, "messages") if m["provider_id"] == "receipt-1")["status"]
        == "delivered"
    )
    assert callback("event-bounce", "email.bounced").status_code == 200
    assert any(lead["status"] == "suppressed" for lead in rows(a, "leads"))
    assert callback("event-bounce", "email.bounced").json()["status"] == "duplicate"
    assert callback("late-delivery", "email.delivered").status_code == 200
    assert (
        next(m for m in rows(a, "messages") if m["provider_id"] == "receipt-1")["status"]
        == "bounced"
    )


def test_unknown_bulk_receipt_never_retries(clients, monkeypatch):
    a, _ = clients
    signup(a)
    approval, _ = batch(a)
    connect(a, monkeypatch, "resend", {"api_key": "unit-esp-key", "sender": "sender@example.test"})
    calls = []

    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout("Receipt lost")

    a.app.state.runtime.delivery.transport = httpx.MockTransport(handle)
    response = a.post(
        "/v1/effects/execute",
        json={"approval_id": approval["id"], "idempotency_key": key(), "execution_mode": "live"},
    )
    assert response.status_code == 200
    drain(a)
    drain(a)
    assert len(calls) == 1
    assert rows(a, "effects")[0]["status"] == "uncertain"
    assert all(m["status"] == "uncertain" for m in rows(a, "messages"))


def test_prospect_research_sandbox_and_connected_results_never_infer_contacts(clients, monkeypatch):
    a, _ = clients
    signup(a)
    brand, _ = brand_and_lead(a)
    assert (
        a.post(
            "/v1/prospects/search",
            json={"brand_id": brand["id"], "query": "retailer websites", "idempotency_key": key()},
        ).status_code
        == 202
    )
    drain(a)
    assert rows(a, "tasks")[0]["output"]["simulated"] is True
    connect(a, monkeypatch, "brave", {"api_key": "unit-search-key"})
    calls = []

    def handle(request):
        calls.append(request)
        assert request.headers["x-subscription-token"] == "unit-search-key"
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "Supplied search fixture",
                            "url": "https://prospect.example.test",
                            "description": "A synthetic retailer result",
                        },
                        {"title": "Bad protocol", "url": "javascript:alert(1)"},
                    ]
                }
            },
        )

    a.app.state.runtime.search_transport = httpx.MockTransport(handle)
    request = {
        "brand_id": brand["id"],
        "query": "retailer websites",
        "connected_provider": True,
        "idempotency_key": key(),
    }
    assert a.post("/v1/prospects/search", json=request).status_code == 202
    assert a.post("/v1/prospects/search", json=request).status_code == 202
    drain(a)
    results = rows(a, "tasks")[0]["output"]["results"]
    assert len(calls) == 1 and len(results) == 1
    assert results[0]["contactability"] == "not_established" and "email" not in results[0]
    assert len(rows(a, "leads")) == 1
    assert len(rows(a, "provider_events")) == 1
