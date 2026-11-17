import copy

from test_bulk_discovery import connect
from test_foundation import signup
from test_growth import brand_and_lead, drain, execute, key, rows


def test_twenty_task_graph_completes_without_lost_or_duplicate_jobs(clients, monkeypatch):
    a, _ = clients
    signup(a)
    brand, _ = brand_and_lead(a)
    original = a.app.state.runtime.plan_template

    def graph(command, business):
        plan = original(command, business)
        tasks = []
        for i in range(20):
            task = copy.deepcopy(plan["tasks"][i % 4])
            task["local_id"] = "t" + str(i)
            tasks.append(task)
        plan["tasks"] = tasks
        plan["dependencies"] = [["t" + str(i), "t" + str(i - 1)] for i in range(1, 20)]
        return plan

    monkeypatch.setattr(a.app.state.runtime, "plan_template", graph)
    assert (
        a.post(
            "/v1/commands",
            json={
                "brand_id": brand["id"],
                "objective": "Verify the twenty-task acceptance graph",
                "idempotency_key": key(),
            },
        ).status_code
        == 202
    )
    drain(a)
    plan = rows(a, "plans")[0]
    assert a.post(f"/v1/plans/{plan['id']}/approve").status_code == 200
    drain(a)
    assert len(rows(a, "tasks")) == 21
    assert all(t["status"] == "succeeded" for t in rows(a, "tasks"))
    assert rows(a, "plans")[0]["status"] == "completed"
    assert len(rows(a, "content_items")) == 5
    drain(a)
    assert len(rows(a, "content_items")) == 5
    assert not rows(a, "messages")


def test_one_corrective_attempt_then_refuses_ungrounded_copy(clients, monkeypatch):
    a, _ = clients
    signup(a)
    _, lead = brand_and_lead(a)
    runtime = a.app.state.runtime
    original = runtime.gateway.generate
    calls = []

    async def invalid(task, instruction, seed, **kwargs):
        calls.append(instruction)
        output = await original(task, instruction, seed, **kwargs)
        output["body"] += " Guaranteed revenue without evidence."
        return output

    monkeypatch.setattr(runtime.gateway, "generate", invalid)
    assert (
        a.post("/v1/drafts", json={"lead_id": lead["id"], "idempotency_key": key()}).status_code
        == 202
    )
    drain(a)
    assert len(calls) == 2
    assert len(rows(a, "model_usage")) == 2
    assert not rows(a, "outreach_drafts")
    assert rows(a, "tasks")[0]["status"] == "failed"


def test_fictional_sample_uses_sandbox_even_with_connected_model(clients, monkeypatch):
    a, _ = clients
    signup(a)
    brand, lead = brand_and_lead(a)
    assert (
        a.put(
            f"/v1/brands/{brand['id']}",
            json={
                "name": brand["name"],
                "positioning": brand["positioning"],
                "icp": brand["icp"],
                "approved_claims": brand["approved_claims"],
                "voice": {"sandbox_only": True},
            },
        ).status_code
        == 200
    )
    connect(
        a,
        monkeypatch,
        "openrouter",
        {"api_key": "unit-test-model-key", "model_id": "fixture/model"},
    )

    async def no_network(*args, **kwargs):
        raise AssertionError("Sample must not reach a connected AI provider")

    # All gateway attempts must resolve to sandbox before invoking the HTTP transport.
    import httpx

    runtime = a.app.state.runtime
    runtime.gateway.transport = httpx.MockTransport(no_network)
    assert (
        a.post(
            "/v1/autopilot/start",
            json={
                "brand_id": brand["id"],
                "objective": "Run a fully fictional sample campaign",
                "lead_ids": [lead["id"]],
                "idempotency_key": key(),
            },
        ).status_code
        == 202
    )
    drain(a)
    assert all(u["simulated"] for u in rows(a, "model_usage"))
    draft = rows(a, "outreach_drafts")[0]
    pending = next(p for p in rows(a, "approvals") if p["subject_id"] == draft["id"])
    assert (
        a.post(f"/v1/approvals/{pending['id']}/decision", json={"decision": "approved"}).status_code
        == 200
    )
    assert execute(a, pending).status_code == 200
    assert len(rows(a, "attribution_touches")) == 1
    assert (
        a.post(
            "/v1/checkouts",
            json={
                "lead_id": lead["id"],
                "description": "Fictional sample",
                "amount_minor": 100,
                "currency": "USD",
                "execution_mode": "live",
            },
        ).json()["detail"]
        == "sample_business_is_sandbox_only"
    )
