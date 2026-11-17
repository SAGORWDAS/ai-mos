import copy
import json

import httpx
import pytest
from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows

from app.growth.planning_evidence import validate_strategy
from app.tenancy import tenant_scope


@pytest.mark.parametrize("kind", ["research", "strategy"])
def test_uncited_research_and_invented_strategy_are_costed_rejected_and_not_cached(clients, kind):
    a, _ = clients
    identity = signup(a)
    brand, _ = brand_and_lead(a)
    assert (
        a.post(
            "/v1/autopilot/start",
            json={
                "brand_id": brand["id"],
                "objective": "Prepare a small sourced campaign",
                "campaign_budget_micros": 2500000,
                "idempotency_key": key(),
            },
        ).status_code
        == 202
    )
    drain(a)
    plan = rows(a, "plans")[0]
    initial = next(t["output"] for t in rows(a, "tasks") if t["type"] == "strategy")
    assert initial["campaign_budget_micros"] == 2500000
    assert sum(p["max_budget_micros"] for p in initial["channel_plan"]) <= 2500000
    assert initial["pricing_evidence"] == brand["pricing"]
    runtime = a.app.state.runtime
    runtime.settings.provider_mode = "openrouter"
    runtime.settings.openrouter_api_key = "unit-model-key"
    runtime.settings.model_id = "fixture/research-strategy"
    valid = False

    def provider(request):
        payload = json.loads(request.content)
        seed = json.loads(payload["messages"][-1]["content"])["required_shape_example"]
        output = copy.deepcopy(seed)
        if not valid:
            if kind == "research":
                output["findings"] = [{"chunk_id": "invented-source", "content": "Invented fact"}]
            else:
                output["pricing_evidence"] = {"invented_price": 99999}
        return httpx.Response(
            200,
            json={
                "id": "unit-generation",
                "usage": {"cost": 0.001},
                "choices": [{"message": {"content": json.dumps(output)}}],
            },
        )

    runtime.gateway.transport = httpx.MockTransport(provider)

    async def enqueue():
        async with a.app.state.factory() as session:
            await tenant_scope(session, brand["organization_id"], identity["user"]["id"])
            task = await runtime.enqueue(
                session,
                brand["organization_id"],
                identity["user"]["id"],
                kind,
                "AGT-02" if kind == "research" else "AGT-03",
                key(),
                {"brand_id": brand["id"]},
                plan_id=plan["id"],
            )
            return task.id

    rejected_id = a.portal.call(enqueue)
    drain(a)
    rejected = next(t for t in rows(a, "tasks") if t["id"] == rejected_id)
    assert rejected["status"] == "failed", rejected
    usage = next(u for u in rows(a, "model_usage") if u["task_id"] == rejected_id)
    assert usage["status"] == "invalid_output" and usage["cost_micros"] == 1000
    valid = True
    accepted_id = a.portal.call(enqueue)
    drain(a)
    accepted = next(t for t in rows(a, "tasks") if t["id"] == accepted_id)
    assert accepted["status"] == "succeeded", accepted
    assert "invented" not in str(accepted["output"])


def test_strategy_channel_caps_cannot_exceed_owner_allowance():
    seed = {
        "audience": ["Recorded audience"],
        "positioning": "Recorded offer",
        "pricing_evidence": {},
        "approval_required": True,
        "autonomous_spend": False,
        "campaign_budget_micros": 100,
        "currency": "USD",
        "guidance": "validate_one_offer",
        "channel_plan": [
            {"channel": "approved_email", "min_budget_micros": 0, "max_budget_micros": 100}
        ],
    }
    validate_strategy(seed, seed)
    for plan in [
        [{"channel": "approved_email", "min_budget_micros": -1, "max_budget_micros": 100}],
        [{"channel": "paid_social", "min_budget_micros": 0, "max_budget_micros": 101}],
        [{"channel": "unknown", "min_budget_micros": 0, "max_budget_micros": 0}],
    ]:
        with pytest.raises(ValueError):
            validate_strategy({**seed, "channel_plan": plan}, seed)
