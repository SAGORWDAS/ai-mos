import asyncio
import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
from sqlalchemy import update
from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows

from app.growth import connections, gateway
from app.growth.model_pricing import request_pricing
from app.growth.models import Budget, ModelRegistry, Task
from app.models import Organization
from app.tenancy import tenant_scope

VERIFY = connections.verify
PRICE = {"prompt": "0.000001", "completion": "0.000002", "image": "0.04", "request": "0"}


def setup(a, monkeypatch, cap=None):
    signup(a)
    brand, _ = brand_and_lead(a)
    state = {"price": copy.deepcopy(PRICE), "available": True, "generations": 0}

    def provider(request):
        if request.url.path.endswith("/key"):
            return httpx.Response(200, json={"data": {"label": "Controlled key"}})
        if request.url.path.endswith("/models"):
            if not state["available"]:
                raise httpx.ReadTimeout("Controlled catalog outage")
            return httpx.Response(
                200, json={"data": [{"id": request.url.params["q"], "pricing": state["price"]}]}
            )
        state["generations"] += 1
        state["payload"] = json.loads(request.content)
        seed = json.loads(json.loads(request.content)["messages"][-1]["content"])[
            "required_shape_example"
        ]
        return httpx.Response(
            200,
            json={
                "id": "fixture-generation",
                "usage": {"cost": 0.0003},
                "choices": [{"message": {"content": json.dumps(seed)}}],
            },
        )

    transport = httpx.MockTransport(provider)

    async def verify(settings, item):
        return await VERIFY(settings, item, transport)

    monkeypatch.setattr(connections, "verify", verify)
    runtime = a.app.state.runtime
    runtime.gateway.transport = transport
    runtime.settings.allow_unverified_models = False
    credentials = {
        "api_key": "unit-model-key",
        "model_id": "fixture/chat",
        "embedding_model_id": "fixture/embed",
        "image_model_id": "fixture/image",
    }
    if cap is not None:
        credentials["max_cost_micros"] = str(cap)
    assert (
        a.put(
            "/v1/connections/openrouter",
            json={"account_ref": "Fixture", "credentials": credentials},
        ).status_code
        == 200
    )
    assert a.post("/v1/connections/openrouter/verify").status_code == 200
    assert a.post("/v1/connections/openrouter/activate").status_code == 200
    return brand, state, credentials


def generate(a, brand, topic="Our recorded offer"):
    result = a.post(
        "/v1/content/generate",
        json={"brand_id": brand["id"], "type": "article", "topic": topic, "idempotency_key": key()},
    )
    assert result.status_code == 202, result.text
    drain(a)
    return next(t for t in rows(a, "tasks") if t["id"] == result.json()["id"])


def test_verified_catalog_and_usage_price_snapshots_are_scoped_and_historical(clients, monkeypatch):
    a, b = clients
    brand, state, _ = setup(a, monkeypatch)
    signup(b, "other@example.test")
    catalog = a.get("/v1/model-registry").json()
    assert len(catalog["models"]) == 3
    assert all(m["eligible"] for m in catalog["models"])
    assert "source_fingerprint" not in str(catalog) and "unit-model-key" not in str(catalog)
    assert b.get("/v1/model-registry").json()["models"] == []
    first = generate(a, brand)
    assert first["status"] == "succeeded", first
    usage = next(u for u in rows(a, "model_usage") if u["task_id"] == first["id"])
    assert usage["model_registry_id"]
    assert usage["model_price_snapshot"]["pricing"]["rates"] == PRICE
    assert usage["cost_micros"] == 300 and usage["simulated"] is False
    state["price"]["prompt"] = "0.000003"
    assert a.post("/v1/model-registry/refresh").status_code == 200
    old = next(u for u in rows(a, "model_usage") if u["id"] == usage["id"])
    assert old["model_price_snapshot"] == usage["model_price_snapshot"]
    current = next(
        m for m in a.get("/v1/model-registry").json()["models"] if m["operation"] == "chat"
    )
    assert current["price_snapshot"]["rates"]["prompt"] == "0.000003"

    # Expired metadata blocks even a cached output and a development override in production.
    async def expire():
        async with a.app.state.factory() as session:
            await tenant_scope(session, brand["organization_id"])
            await session.execute(update(ModelRegistry).values(verified_at=time.time() - 8 * 86400))
            await session.commit()

    a.portal.call(expire)
    state["available"] = False
    a.app.state.runtime.settings.allow_unverified_models = True
    a.app.state.runtime.settings.app_env = "production"
    refused = generate(a, brand)
    assert refused["status"] == "blocked" and state["generations"] == 1
    held = next(u for u in rows(a, "model_usage") if u["task_id"] == refused["id"])
    assert held["status"] == "unverified_model_refused"
    assert held["cost_micros"] == held["reserved_micros"] == 0 and held["settled"]


def test_key_rotation_and_partial_catalog_failure_do_not_reuse_old_authority(clients, monkeypatch):
    a, _ = clients
    brand, state, credentials = setup(a, monkeypatch)
    first = generate(a, brand)
    assert first["status"] == "succeeded"
    original = next(
        m for m in a.get("/v1/model-registry").json()["models"] if m["operation"] == "chat"
    )
    state["available"] = False
    # A transient outage retains a still-fresh snapshot for the same connection only.
    refreshed = a.post("/v1/model-registry/refresh").json()
    assert all(m["eligible"] for m in refreshed["models"])
    credentials["api_key"] = "unit-replacement-key"
    a.put("/v1/connections/openrouter", json={"account_ref": "Fixture", "credentials": credentials})
    assert a.post("/v1/connections/openrouter/verify").status_code == 200
    assert a.post("/v1/connections/openrouter/activate").status_code == 200
    current = a.get("/v1/model-registry").json()["models"]
    assert all(not m["eligible"] for m in current)
    assert all(m["source_connection_version"] == 2 for m in current)
    refused = generate(a, brand, "Another offer")
    assert refused["status"] == "blocked" and state["generations"] == 1
    assert original["source_connection_version"] == 1
    state["available"] = True
    assert a.post("/v1/model-registry/refresh").status_code == 200
    assert generate(a, brand, "Newly verified offer")["status"] == "succeeded"


def test_expired_catalog_refreshes_automatically_before_paid_generation(clients, monkeypatch):
    a, _ = clients
    brand, state, _ = setup(a, monkeypatch)

    async def expire():
        async with a.app.state.factory() as session:
            await tenant_scope(session, brand["organization_id"])
            await session.execute(
                update(ModelRegistry).values(
                    verified_at=time.time() - 8 * 86400, last_checked_at=time.time() - 8 * 86400
                )
            )
            await session.commit()

    a.portal.call(expire)
    state["price"]["prompt"] = "0.000004"
    task = generate(a, brand)
    assert task["status"] == "succeeded" and state["generations"] == 1
    usage = next(u for u in rows(a, "model_usage") if u["task_id"] == task["id"])
    assert usage["model_price_snapshot"]["pricing"]["rates"]["prompt"] == "0.000004"
    assert usage["model_price_snapshot"]["verified_at"] >= time.time() - 60


def test_stop_is_rechecked_at_atomic_model_reservation(clients, monkeypatch):
    a, _ = clients
    brand, state, _ = setup(a, monkeypatch)
    original = gateway.ensure_budget

    async def stop_before_reservation(session, org_id):
        budget = await original(session, org_id)
        await session.execute(
            update(Organization).where(Organization.id == org_id).values(emergency_stop=True)
        )
        await session.commit()
        return budget

    monkeypatch.setattr(gateway, "ensure_budget", stop_before_reservation)
    task = generate(a, brand)
    assert task["status"] == "blocked" and state["generations"] == 0
    usage = rows(a, "model_usage")[0]
    assert usage["status"] == "policy_refused" and usage["cost_micros"] == 0
    assert a.get("/v1/budgets/current").json()["reserved_micros"] == 0


def test_request_allowance_refuses_without_a_charge_and_sends_price_ceiling(clients, monkeypatch):
    a, _ = clients
    brand, state, _ = setup(a, monkeypatch, cap=0)
    assert a.get("/v1/model-registry").json()["request_allowance_micros"] == 0
    task = generate(a, brand)
    assert task["status"] == "blocked" and state["generations"] == 0
    usage = rows(a, "model_usage")[0]
    assert usage["status"] == "request_cap_refused" and usage["settled"]
    assert usage["cost_micros"] == usage["reserved_micros"] == 0


def test_verified_rates_bound_chat_routing_and_oversized_estimates_are_refused(
    clients, monkeypatch
):
    a, _ = clients
    brand, state, _ = setup(a, monkeypatch)
    assert generate(a, brand)["status"] == "succeeded"
    assert state["payload"]["provider"] == {
        "sort": "price",
        "max_price": {"prompt": 1.0, "completion": 2.0, "request": 0.0},
    }
    state["price"]["prompt"] = "0.01"
    assert a.post("/v1/model-registry/refresh").status_code == 200
    task = generate(a, brand, "Different request with expensive advertised rates")
    assert task["status"] == "blocked" and state["generations"] == 1
    usage = next(u for u in rows(a, "model_usage") if u["task_id"] == task["id"])
    assert usage["status"] == "request_cap_refused" and usage["reserved_micros"] == 0


def test_budget_policy_carries_to_next_month_without_carrying_spend(clients, monkeypatch):
    a, _ = clients
    signup(a)
    changed = a.put("/v1/budgets/current", json={"limit_micros": 750000, "daily_send_cap": 3})
    assert changed.status_code == 200, changed.text
    old = changed.json()

    async def spend():
        async with a.app.state.factory() as session:
            await tenant_scope(session, old["organization_id"])
            await session.execute(
                update(Budget)
                .where(Budget.id == old["id"])
                .values(spent_micros=50000, reserved_micros=10000)
            )
            await session.commit()

    a.portal.call(spend)
    year, month = map(int, old["period"].split("-"))
    next_period = f"{year + (month == 12)}-{month % 12 + 1:02}"
    monkeypatch.setattr(gateway, "month", lambda: next_period)
    current = a.get("/v1/budgets/current").json()
    assert current["period"] == next_period and current["limit_micros"] == 750000
    assert current["daily_send_cap"] == 3
    assert current["spent_micros"] == current["reserved_micros"] == 0


def test_concurrent_jobs_share_one_expired_catalog_refresh(clients, monkeypatch):
    a, _ = clients
    brand, state, _ = setup(a, monkeypatch)

    async def expire():
        async with a.app.state.factory() as session:
            await tenant_scope(session, brand["organization_id"])
            await session.execute(
                update(ModelRegistry).values(verified_at=time.time() - 8 * 86400, last_checked_at=0)
            )
            await session.commit()

    a.portal.call(expire)
    entered, release = Event(), Event()
    checks = []
    original = gateway.catalog_candidates

    async def delayed(*args):
        checks.append(1)
        entered.set()
        await asyncio.to_thread(release.wait, 10)
        return await original(*args)

    monkeypatch.setattr(gateway, "catalog_candidates", delayed)
    for topic in ["First campaign", "Second campaign"]:
        assert (
            a.post(
                "/v1/content/generate",
                json={
                    "brand_id": brand["id"],
                    "type": "article",
                    "topic": topic,
                    "idempotency_key": key(),
                },
            ).status_code
            == 202
        )
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(drain, a)
        try:
            assert entered.wait(5)
            second = pool.submit(drain, a)
            # Both workers are active before the catalog result arrives.
            time.sleep(0.35)
        finally:
            release.set()
        first.result(timeout=15)
        second.result(timeout=15)
    assert len(checks) == 1 and state["generations"] == 2
    assert all(t["status"] == "succeeded" for t in rows(a, "tasks"))


def test_reservations_use_utf8_bytes_and_missing_image_rates_remain_unknown():
    evidence = {"pricing": {"rates": PRICE}}
    amount, _ = request_pricing(evidence, "chat", "\u4e2d" * 10, "system", 0)
    assert amount == 292
    assert request_pricing({}, "image", "prompt", "")[0] is None
    assert (
        request_pricing({"pricing": {"rates": {"request": "0.04"}}}, "image", "prompt", "")[0]
        == 40000
    )


def test_placeholder_allowance_is_visible_without_granting_catalog_authority(clients):
    a, _ = clients
    signup(a)
    saved = a.put(
        "/v1/connections/openrouter",
        json={
            "account_ref": "Placeholder",
            "credentials": {
                "api_key": "placeholder-key",
                "model_id": "placeholder/model",
                "max_cost_micros": "50000",
            },
        },
    )
    assert saved.status_code == 200 and saved.json()["enabled"] is False
    report = a.get("/v1/model-registry").json()
    assert report["request_allowance_micros"] == 50000 and report["models"] == []
    assert a.post("/v1/model-registry/refresh").status_code == 409


def test_model_call_renews_its_own_active_lease(clients, monkeypatch):
    a, _ = clients
    brand, state, _ = setup(a, monkeypatch)
    original = gateway.ensure_budget

    async def almost_expired(session, org_id):
        budget = await original(session, org_id)
        await session.execute(
            update(Task)
            .where(Task.organization_id == org_id, Task.status == "running")
            .values(leased_until=time.time() + 1)
        )
        await session.commit()
        return budget

    monkeypatch.setattr(gateway, "ensure_budget", almost_expired)
    runtime = a.app.state.runtime
    original_generate = runtime.gateway.generate
    leases = []

    async def observed(task, *args, **kwargs):
        result = await original_generate(task, *args, **kwargs)
        async with runtime.factory() as session:
            await tenant_scope(session, task.organization_id)
            leases.append((await session.get(Task, task.id)).leased_until)
        return result

    monkeypatch.setattr(runtime.gateway, "generate", observed)
    assert generate(a, brand)["status"] == "succeeded" and state["generations"] == 1
    assert leases and leases[0] > time.time() + 60
