import base64
from urllib.parse import parse_qs

import httpx
import pytest
from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows

from app.growth import connections
from app.growth.creative import placeholder_png, validate_raster

VERIFY = connections.verify


def connection(client, monkeypatch, provider, credentials):
    original = VERIFY

    async def verify(settings, item):
        def handler(request):
            if request.url.path.endswith("act_123"):
                return httpx.Response(
                    200, json={"id": "act_123", "currency": "USD", "account_status": 1}
                )
            return httpx.Response(200, json={"id": "456"})

        return await original(settings, item, httpx.MockTransport(handler))

    monkeypatch.setattr(connections, "verify", verify)
    assert (
        client.put(
            "/v1/connections/" + provider,
            json={"account_ref": "Fixture", "credentials": credentials},
        ).status_code
        == 200
    )
    assert client.post("/v1/connections/" + provider + "/verify").status_code == 200
    assert client.post("/v1/connections/" + provider + "/activate").status_code == 200


def assets(a, brand, connected=False):
    a.post(
        "/v1/content/generate",
        json={
            "brand_id": brand["id"],
            "type": "article",
            "topic": "Our service",
            "idempotency_key": key(),
        },
    )
    response = a.post(
        "/v1/creative/images",
        json={
            "brand_id": brand["id"],
            "brief": "Simple black and white abstract shapes",
            "connected_provider": connected,
            "idempotency_key": key(),
        },
    )
    assert response.status_code == 202, response.text
    drain(a)
    task = next(t for t in rows(a, "tasks") if t["id"] == response.json()["id"])
    assert task["status"] == "succeeded", task
    return rows(a, "content_items")[0], task


def test_private_raster_generation_is_costed_scoped_and_not_in_task_lists(clients):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    brand, _ = brand_and_lead(a)
    _, image = assets(a, brand)
    assert "image_base64" not in image["output"]
    response = a.get("/v1/creative/images/" + image["id"])
    assert response.content == placeholder_png()
    assert response.headers["content-type"] == "image/png"
    assert b.get("/v1/creative/images/" + image["id"]).status_code == 404
    assert any(u["task_id"] == image["id"] and u["simulated"] for u in rows(a, "model_usage"))
    with pytest.raises(ValueError):
        validate_raster(base64.b64encode(b"<svg>script</svg>").decode())
    with pytest.raises(ValueError):
        validate_raster(base64.b64encode(b"\xff\xd8\xff").decode())


def test_connected_image_contract_and_unknown_cost_hold(clients, monkeypatch):
    a, _ = clients
    signup(a)
    brand, _ = brand_and_lead(a)
    connection(
        a,
        monkeypatch,
        "openrouter",
        {"api_key": "unit-key", "model_id": "fixture/chat", "image_model_id": "fixture/image"},
    )
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "id": "image-fixture",
                "data": [
                    {
                        "b64_json": base64.b64encode(placeholder_png()).decode(),
                        "media_type": "image/png",
                    }
                ],
                "usage": {},
            },
        )

    a.app.state.runtime.gateway.transport = httpx.MockTransport(handler)
    result = a.post(
        "/v1/creative/images",
        json={
            "brand_id": brand["id"],
            "brief": "Abstract shapes for our agency",
            "connected_provider": True,
            "idempotency_key": key(),
        },
    )
    drain(a)
    assert calls[0].url.path == "/api/v1/images"
    usage = next(u for u in rows(a, "model_usage") if u["task_id"] == result.json()["id"])
    assert usage["settled"] is False
    assert usage["status"] == "provider_cost_unknown"
    assert a.get("/v1/creative/images/" + result.json()["id"]).status_code == 200


@pytest.mark.parametrize("fail_partial", [False, True])
def test_meta_full_contract_cap_approval_partial_receipts_and_replay(
    clients, monkeypatch, fail_partial
):
    a, _ = clients
    signup(a)
    brand, lead = brand_and_lead(a)
    connection(
        a,
        monkeypatch,
        "meta_ads",
        {"access_token": "unit-meta", "ad_account_id": "123", "page_id": "456"},
    )
    # A live-provider response is controlled here; no actual generation or ad purchase occurs.
    connection(
        a,
        monkeypatch,
        "openrouter",
        {"api_key": "unit-key", "model_id": "fixture/chat", "image_model_id": "fixture/image"},
    )

    def generate(request):
        import json

        json.loads(request.content)
        if request.url.path.endswith("/images"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "b64_json": base64.b64encode(placeholder_png()).decode(),
                            "media_type": "image/png",
                        }
                    ],
                    "usage": {"cost": 0.001},
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "title": "Our service",
                                    "body": brand["positioning"]
                                    + "\n\n"
                                    + brand["approved_claims"][0],
                                    "citations": [],
                                }
                            )
                        }
                    }
                ],
                "usage": {"cost": 0},
            },
        )

    # Generate grounded copy in sandbox first, then connect only the requested image operation.
    a.post("/v1/connections/openrouter/disconnect")
    content, _ = assets(a, brand)
    connection(
        a,
        monkeypatch,
        "openrouter",
        {"api_key": "unit-key", "model_id": "fixture/chat", "image_model_id": "fixture/image"},
    )
    a.app.state.runtime.gateway.transport = httpx.MockTransport(generate)
    image = a.post(
        "/v1/creative/images",
        json={
            "brand_id": brand["id"],
            "brief": "A neutral abstract illustration",
            "connected_provider": True,
            "idempotency_key": key(),
        },
    ).json()
    drain(a)
    campaign = a.post(
        "/v1/campaigns",
        json={"brand_id": brand["id"], "name": "Paid fixture", "lead_ids": [lead["id"]]},
    ).json()
    payload = {
        "campaign_id": campaign["id"],
        "content_id": content["id"],
        "image_task_id": image["id"],
        "landing_url": "https://example.test/offer",
        "country": "US",
        "currency": "USD",
        "lifetime_budget_minor": 500,
        "duration_days": 3,
        "activate": True,
        "ordinary_commercial_confirmed": True,
        "idempotency_key": key(),
    }
    review = a.post("/v1/advertising/request-approval", json=payload)
    assert review.status_code == 201, review.text
    approval = review.json()
    assert (
        a.post(
            f"/v1/approvals/{approval['id']}/decision", json={"decision": "approved"}
        ).status_code
        == 200
    )
    calls = []

    def meta(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "spend": "1.23",
                            "account_currency": "USD",
                            "clicks": "4",
                            "impressions": "100",
                        }
                    ]
                },
            )
        body = parse_qs(request.content.decode())
        calls.append((request.url.path, body))
        if (
            body.get("status") == ["ACTIVE"]
            or body.get("status") == ["PAUSED"]
            and not request.url.path.endswith(("/campaigns", "/adsets", "/ads"))
        ):
            return httpx.Response(200, json={"success": True})
        if request.url.path.endswith("/adimages"):
            return httpx.Response(200, json={"images": {"fixture": {"hash": "a" * 32}}})
        if fail_partial and request.url.path.endswith("/adcreatives"):
            return httpx.Response(503)
        return httpx.Response(200, json={"id": str(100 + len(calls))})

    a.app.state.runtime.delivery.transport = httpx.MockTransport(meta)
    action = {"approval_id": approval["id"], "idempotency_key": key(), "execution_mode": "live"}
    response = a.post("/v1/effects/execute", json=action)
    assert response.status_code == 200, response.text
    drain(a)
    effect = next(e for e in rows(a, "effects") if e["id"] == response.json()["effect_id"])
    assert effect["status"] == ("uncertain" if fail_partial else "succeeded"), effect
    assert effect["result"]["progress"]["campaign_id"]
    budget = [body for path, body in calls if path.endswith("/adsets")][0]
    assert budget["lifetime_budget"] == ["500"]
    assert budget["status"] == ["PAUSED"]
    before = len(calls)
    assert a.post("/v1/effects/execute", json=action).status_code == 200
    drain(a)
    assert len(calls) == before
    if not fail_partial:
        metric_key = {"idempotency_key": key()}
        metric = a.post(f"/v1/advertising/{effect['id']}/metrics", json=metric_key)
        assert metric.status_code == 200, metric.text
        assert metric.json()["spend"] == "1.23"
        assert (
            a.post(
                f"/v1/advertising/{effect['id']}/metrics", json={"idempotency_key": key()}
            ).status_code
            == 200
        )
        assert (
            a.post(f"/v1/advertising/{effect['id']}/metrics", json=metric_key).json()
            == metric.json()
        )
        expenses = [e for e in rows(a, "expenses") if e["category"] == "advertising"]
        assert len(expenses) == 1 and expenses[0]["amount_micros"] == 1_230_000
    assert a.post("/v1/org/emergency-stop", json={"enabled": True}).status_code == 200
    paused = a.post(f"/v1/advertising/{effect['id']}/pause", json={"idempotency_key": key()})
    assert paused.status_code == 200, paused.text
