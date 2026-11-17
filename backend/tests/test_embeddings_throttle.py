import asyncio
import json

import httpx
from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows

from app.throttling import AuthLimiter


def source(client, brand, text):
    response = client.post(
        f"/v1/brands/{brand['id']}/documents",
        json={"title": text[:60], "content": text, "source_uri": "Synthetic embedding fixture"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_embedding_workflow_sandbox_cache_and_tenant_scope(clients):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    brand, _ = brand_and_lead(a)
    doc = source(a, brand, "Retailer websites and online storefront design.")
    path = f"/v1/brands/{brand['id']}/documents/{doc['id']}/embed"
    assert b.post(path, json={"idempotency_key": key()}).status_code == 404
    assert a.post(path, json={"idempotency_key": key()}).status_code == 202
    drain(a)
    assert rows(a, "brand_documents")[0]["status"] == "embedded"
    assert a.post(path, json={"idempotency_key": key()}).status_code == 202
    drain(a)
    assert len(rows(a, "model_usage")) == 1
    assert (
        a.post(
            f"/v1/brands/{brand['id']}/semantic-search",
            json={"query": "retailer storefront design", "idempotency_key": key()},
        ).status_code
        == 202
    )
    drain(a)
    result = rows(a, "tasks")[0]["output"]
    assert result["simulated"] is True
    assert result["passages"][0]["document_id"] == doc["id"]
    assert len(rows(a, "model_usage")) == 2


def test_connected_embedding_contract_costs_and_nonlexical_similarity(clients):
    a, _ = clients
    signup(a)
    brand, _ = brand_and_lead(a)
    first = source(a, brand, "We craft digital storefronts for independent shops.")
    second = source(a, brand, "Bookkeeping and tax preparation for accountants.")
    runtime = a.app.state.runtime
    runtime.settings.provider_mode = "openrouter"
    runtime.settings.openrouter_api_key = "unit-key"
    runtime.settings.embedding_model_id = "unit/embedding"
    calls = []

    def handle(request):
        calls.append(request)
        assert request.url.path.endswith("/embeddings")
        payload = json.loads(request.content)
        vectors = [
            {
                "index": index,
                "embedding": [1, 0]
                if "storefront" in value or "retail websites" in value
                else [0, 1],
            }
            for index, value in enumerate(payload["input"])
        ]
        return httpx.Response(
            200,
            json={
                "id": "embedding-" + str(len(calls)),
                "model": "unit/embedding",
                "data": vectors,
                "usage": {"cost": 0.000001, "prompt_tokens": 10},
            },
        )

    runtime.gateway.transport = httpx.MockTransport(handle)
    for doc in [first, second]:
        assert (
            a.post(
                f"/v1/brands/{brand['id']}/documents/{doc['id']}/embed",
                json={"idempotency_key": key(), "connected_provider": True},
            ).status_code
            == 202
        )
    drain(a)
    assert (
        a.post(
            f"/v1/brands/{brand['id']}/semantic-search",
            json={"query": "retail websites", "idempotency_key": key(), "connected_provider": True},
        ).status_code
        == 202
    )
    drain(a)
    result = rows(a, "tasks")[0]["output"]
    assert result["simulated"] is False
    assert result["passages"][0]["document_id"] == first["id"]
    assert result["passages"][0]["score"] == 1
    assert len(calls) == 3
    assert a.get("/v1/budgets/current").json()["spent_micros"] == 3


def test_auth_throttle_shared_between_instances_with_atomic_cap(clients):
    a, _ = clients
    first = AuthLimiter(a.app.state.factory, "unit-throttle-secret", limit=5)
    second = AuthLimiter(a.app.state.factory, "unit-throttle-secret", limit=5)

    async def exercise():
        return await asyncio.gather(
            *[(first if index % 2 else second).allow("synthetic-peer") for index in range(20)]
        )

    results = a.portal.call(exercise)
    assert sum(results) == 5
    assert a.portal.call(second.allow, "synthetic-peer") is False
    assert a.portal.call(second.allow, "different-peer") is True
