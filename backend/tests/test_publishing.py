import json

import httpx
import pytest
from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows

from app.growth import connections
from app.growth.providers import ProviderError
from app.growth.publishing import PublishingProvider


def content(client):
    brand, _ = brand_and_lead(client)
    assert (
        client.post(
            "/v1/content/generate",
            json={
                "brand_id": brand["id"],
                "type": "article",
                "topic": "Our approved service",
                "idempotency_key": key(),
            },
        ).status_code
        == 202
    )
    drain(client)
    return brand, rows(client, "content_items")[0]


def approval(client, item, channel="wordpress"):
    response = client.post(f"/v1/content/{item['id']}/channel-approval", json={"channel": channel})
    assert response.status_code == 201, response.text
    result = response.json()
    assert (
        client.post(
            f"/v1/approvals/{result['id']}/decision", json={"decision": "approved"}
        ).status_code
        == 200
    )
    return result


def connect(client, monkeypatch, channel="wordpress"):
    original = connections.verify

    async def verify(settings, item):
        return await original(
            settings,
            item,
            httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"sites": [{"ID": 123}], "sub": "member123"}
                )
            ),
        )

    monkeypatch.setattr(connections, "verify", verify)
    credentials = {"access_token": "unit-publishing-token"}
    if channel == "wordpress":
        credentials["site_id"] = "123"
    assert (
        client.put(
            f"/v1/connections/{channel}",
            json={"account_ref": "Synthetic provider", "credentials": credentials},
        ).status_code
        == 200
    )
    result = client.post(f"/v1/connections/{channel}/verify")
    assert result.status_code == 200, result.text
    assert client.post(f"/v1/connections/{channel}/activate").status_code == 200


def test_channel_sandbox_is_scoped_approved_and_idempotent(clients):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    _, item = content(a)
    assert (
        b.post(
            f"/v1/content/{item['id']}/channel-approval", json={"channel": "linkedin"}
        ).status_code
        == 404
    )
    approved = approval(a, item, "linkedin")
    body = {"approval_id": approved["id"], "idempotency_key": key(), "execution_mode": "sandbox"}
    first = a.post("/v1/effects/execute", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["simulated"] is True
    assert first.json() == a.post("/v1/effects/execute", json=body).json()
    assert len(rows(a, "effects")) == 1
    assert a.post("/v1/effects/execute", json={**body, "execution_mode": "live"}).status_code == 409


@pytest.mark.parametrize("channel", ["wordpress", "linkedin"])
def test_channel_dispatch_receipt_and_uncertain_result_never_reposts(clients, monkeypatch, channel):
    a, _ = clients
    signup(a)
    _, item = content(a)
    connect(a, monkeypatch, channel)
    approved = approval(a, item, channel)
    calls = []

    def publish(request):
        calls.append(request)
        assert request.method == "POST"
        assert request.url.host in {"public-api.wordpress.com", "api.linkedin.com"}
        if channel == "wordpress":
            return httpx.Response(201, json={"id": 456, "link": "https://example.test/article"})
        # A malformed success receipt is ambiguous, not permission to repost.
        return httpx.Response(201, headers={"x-restli-id": "invalid-receipt"})

    a.app.state.runtime.delivery.transport = httpx.MockTransport(publish)
    body = {"approval_id": approved["id"], "idempotency_key": key(), "execution_mode": "live"}
    queued = a.post("/v1/effects/execute", json=body)
    assert queued.status_code == 200, queued.text
    assert queued.json()["status"] == "queued"
    drain(a)
    effect = rows(a, "effects")[0]
    assert effect["status"] == ("succeeded" if channel == "wordpress" else "uncertain")
    assert len(calls) == 1
    assert a.post("/v1/effects/execute", json=body).status_code == 200
    drain(a)
    assert len(calls) == 1
    if channel == "linkedin":
        assert a.post(f"/v1/effects/{effect['id']}/reconcile").json()["retry_send_allowed"] is False


def test_queued_publication_rechecks_current_facts(clients, monkeypatch):
    a, _ = clients
    signup(a)
    brand, item = content(a)
    connect(a, monkeypatch)
    approved = approval(a, item)
    response = a.post(
        "/v1/effects/execute",
        json={"approval_id": approved["id"], "idempotency_key": key(), "execution_mode": "live"},
    )
    assert response.status_code == 200
    a.put(
        f"/v1/brands/{brand['id']}",
        json={
            "name": brand["name"],
            "approved_claims": [],
            "positioning": "Changed approved offer",
        },
    )
    a.app.state.runtime.delivery.transport = httpx.MockTransport(
        lambda request: pytest.fail("Withdrawn facts must not reach provider")
    )
    drain(a)
    assert rows(a, "effects")[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_provider_validates_identity_and_escapes_article_html(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(201, json={"id": 1})

    provider = PublishingProvider(
        "wordpress", {"access_token": "unit-token", "site_id": "123"}, httpx.MockTransport(handler)
    )
    await provider.publish("<script>Example</script>", "<script>untrusted</script>")
    assert "<script>" not in json.loads(calls[0].content)["content"]
    assert "<script>" not in json.loads(calls[0].content)["title"]
    bad = PublishingProvider(
        "linkedin",
        {"access_token": "unit-token", "author_urn": "urn:li:person:other"},
        httpx.MockTransport(lambda request: httpx.Response(200, json={"sub": "owner"})),
    )
    with pytest.raises(ProviderError, match="identity_mismatch"):
        await bad.verify()
    import asyncio

    from app.growth import publishing

    monkeypatch.setattr(publishing, "REQUEST_DEADLINE_SECONDS", 0.01)

    async def slow(request):
        await asyncio.sleep(0.1)
        return httpx.Response(201, json={"id": 1})

    delayed = PublishingProvider(
        "wordpress", {"access_token": "unit-token", "site_id": "123"}, httpx.MockTransport(slow)
    )
    with pytest.raises(ProviderError) as failure:
        await delayed.publish("Example", "Approved body")
    assert failure.value.uncertain is True
