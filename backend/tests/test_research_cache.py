import time

import httpx
from sqlalchemy import select
from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows

from app.growth import connections, discovery
from app.growth.models import Task
from app.tenancy import tenant_scope


def test_search_cache_price_accrual_and_account_scope(clients, monkeypatch):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    brand, _ = brand_and_lead(a)
    other, _ = brand_and_lead(b)

    async def verified(settings, item):
        return {"status": "verified", "account_ref": "Controlled search fixture"}

    monkeypatch.setattr(connections, "verify", verified)
    for client in (a, b):
        assert (
            client.put(
                "/v1/connections/brave",
                json={
                    "account_ref": "Fixture",
                    "credentials": {"api_key": "unit-search", "search_price_micros": "101"},
                },
            ).status_code
            == 200
        )
        assert client.post("/v1/connections/brave/verify").status_code == 200
        assert client.post("/v1/connections/brave/activate").status_code == 200
    requests = []

    def provider(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {"title": "Fixture shop", "url": "https://shop.example.test"},
                        {"title": "Fixture agency", "url": "https://agency.example.test"},
                    ]
                }
            },
        )

    a.app.state.runtime.search_transport = httpx.MockTransport(provider)

    def search(client, business):
        result = client.post(
            "/v1/prospects/search",
            json={
                "brand_id": business["id"],
                "query": "synthetic business sites",
                "connected_provider": True,
                "idempotency_key": key(),
            },
        )
        assert result.status_code == 202, result.text
        drain(client)
        return next(t["output"] for t in rows(client, "tasks") if t["id"] == result.json()["id"])

    first = search(a, brand)
    second = search(a, brand)
    third = search(b, other)
    assert len(requests) == 2
    assert first["search_cost_micros"] == third["search_cost_micros"] == 101
    assert second["cached"] is True and second["search_cost_micros"] == 0
    assert second["source_search_cost_micros"] == 101
    assert sum(r["allocated_search_cost_micros"] for r in first["results"]) == 101
    assert all(r["retrieved_at"] > 0 for r in first["results"])
    assert sum(e["amount_micros"] for e in rows(a, "expenses")) == 101
    assert sum(e["amount_micros"] for e in rows(b, "expenses")) == 101
    assert (
        a.put(
            "/v1/connections/brave",
            json={
                "account_ref": "Fixture",
                "credentials": {"api_key": "unit-search", "search_price_micros": "-1"},
            },
        ).status_code
        == 422
    )


def test_contact_cache_preserves_observation_age_scope_and_force_refresh(clients, monkeypatch):
    a, _ = clients
    signup(a)
    brand, _ = brand_and_lead(a)
    fetches = []

    async def fetch(url):
        fetches.append(url)
        return "Contact us at shop@shop.example.test", url

    monkeypatch.setattr(discovery, "fetch_text", fetch)

    def enrich(refresh=False):
        result = a.post(
            "/v1/prospects/enrich",
            json={
                "brand_id": brand["id"],
                "url": "https://shop.example.test/contact",
                "refresh": refresh,
                "idempotency_key": key(),
            },
        )
        assert result.status_code == 202, result.text
        drain(a)
        return next(t for t in rows(a, "tasks") if t["id"] == result.json()["id"])

    first = enrich()
    second = enrich()
    assert len(fetches) == 1 and second["output"]["cached"] is True
    assert first["output"]["observed_at"] == second["output"]["observed_at"]
    lead = next(
        contact for contact in rows(a, "leads") if contact["email"] == "shop@shop.example.test"
    )
    assert (
        lead["source_ref"] == "https://shop.example.test/contact" and lead["source_observed_at"] > 0
    )
    enrich(True)
    assert len(fetches) == 2

    async def age_observations():
        async with a.app.state.factory() as session:
            await tenant_scope(session, brand["organization_id"])
            for task in (await session.scalars(select(Task))).all():
                task.output = {**task.output, "observed_at": time.time() - 91 * 86400}
            await session.commit()

    a.portal.call(age_observations)
    assert enrich()["output"]["cached"] is False
    assert len(fetches) == 3
