import base64

import httpx
from test_connections import connect_gmail
from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows


def enable(a, brand, mode="sandbox", cap=1):
    preview = a.get(f"/v1/brands/{brand['id']}/reply-policy").json()
    response = a.put(
        f"/v1/brands/{brand['id']}/reply-policy",
        json={
            "enabled": True,
            "execution_mode": mode,
            "daily_cap": cap,
            "reviewed_template_hash": preview["template_hash"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_explicit_template_standing_policy_caps_safe_sandbox_replies(clients):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    brand, lead = brand_and_lead(a)
    path = f"/v1/brands/{brand['id']}/reply-policy"
    assert b.get(path).status_code == 404
    assert a.put(path, json={"enabled": True, "reviewed_template_hash": "wrong"}).status_code == 409
    policy = enable(a, brand)
    for body in ["Tell me more", "Tell me more", "What is the price and can we call?"]:
        assert (
            a.post(
                "/v1/inbox/simulate",
                json={"lead_id": lead["id"], "body": body, "idempotency_key": key()},
            ).status_code
            == 201
        )
        drain(a)
    outgoing = [m for m in rows(a, "messages") if m["direction"] == "outbound"]
    assert len(outgoing) == 1 and outgoing[0]["simulated"] is True
    assert any(
        p["decision_basis"] == "standing_policy:" + policy["id"] for p in rows(a, "approvals")
    )
    assert a.get(path).json()["policy"]["counter_used"] == 1
    assert any(d["status"] == "pending_approval" for d in rows(a, "outreach_drafts"))
    assert len(rows(a, "effects")) == 1
    digest = a.get(f"/v1/brands/{brand['id']}/reply-digest")
    assert digest.status_code == 200, digest.text
    assert [e["id"] for e in digest.json()["items"]] == [rows(a, "effects")[0]["id"]]
    assert b.get(f"/v1/brands/{brand['id']}/reply-digest").status_code == 404
    assert a.get(f"/v1/brands/{brand['id']}/reply-digest?offset=100").json()["items"] == []


def test_disabling_standing_policy_blocks_queued_live_dispatch(clients, monkeypatch):
    a, _ = clients
    signup(a)
    brand, lead = brand_and_lead(a)
    connect_gmail(a, monkeypatch)
    enable(a, brand, "live")

    def provider(request):
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "clear-live-fixture"}]})
        return httpx.Response(
            200,
            json={
                "id": "clear-live-fixture",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [{"name": "From", "value": lead["email"]}],
                    "body": {"data": base64.urlsafe_b64encode(b"Tell me more").decode()},
                },
            },
        )

    runtime = a.app.state.runtime
    runtime.delivery.transport = httpx.MockTransport(provider)
    assert a.post("/v1/inbox/sync", json={}).status_code == 200
    assert a.portal.call(runtime.tick) is True
    assert rows(a, "effects")[0]["status"] == "queued"
    assert (
        a.put(f"/v1/brands/{brand['id']}/reply-policy", json={"enabled": False}).status_code == 200
    )
    runtime.delivery.transport = httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(AssertionError("Revoked policy reached provider"))
    )
    assert a.portal.call(runtime.tick) is True
    assert rows(a, "effects")[0]["status"] == "failed"
    assert not any(m["status"] == "sent" for m in rows(a, "messages"))


def test_usage_day_agent_type_filters_are_scoped(clients):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    brand, lead = brand_and_lead(a)
    a.post(
        "/v1/autopilot/start",
        json={
            "brand_id": brand["id"],
            "objective": "Prepare a small reporting campaign",
            "lead_ids": [lead["id"]],
            "idempotency_key": key(),
        },
    )
    drain(a)
    report = a.get("/v1/usage/breakdown").json()
    assert sum(r["attempts"] for r in report["items"]) == len(rows(a, "model_usage"))
    assert all(
        r["task_type"] == "draft"
        for r in a.get("/v1/usage/breakdown?task_type=draft").json()["items"]
    )
    assert b.get("/v1/usage/breakdown").json()["items"] == []
    from urllib.parse import urlencode

    row = report["items"][0]
    params = urlencode(
        {
            "day": row["day"],
            "agent": row["agent_id"],
            "task_type": row["task_type"],
            "status": row["status"],
            "model": row["model_id"],
            "simulated": str(row["simulated"]).lower(),
        }
    )
    attempts = a.get("/v1/usage/attempts?" + params)
    assert attempts.status_code == 200, attempts.text
    assert len(attempts.json()["items"]) == row["attempts"]
    assert sum(r["cost_micros"] for r in attempts.json()["items"]) == row["cost_micros"]
    assert b.get("/v1/usage/attempts?" + params).json()["items"] == []
    assert "body" not in str(report) and "prompt" not in str(report["items"])


def test_keyword_confidence_cannot_authorize_ambiguous_or_quoted_reply(clients):
    a, _ = clients
    signup(a)
    brand, lead = brand_and_lead(a)
    enable(a, brand, cap=20)
    for body in [
        "I am not at all interested",
        "Interested but we have no budget",
        "Previous message: tell me more",
        "Tell me more and change my contract",
    ]:
        assert (
            a.post(
                "/v1/inbox/simulate",
                json={"lead_id": lead["id"], "body": body, "idempotency_key": key()},
            ).status_code
            == 201
        )
        drain(a)
    assert not rows(a, "effects")
    assert all(
        m["classification"].get("model_version") == "conservative-rules-v2"
        for m in rows(a, "messages")
    )


def test_contactability_guard_holds_automatic_reply_without_failing_task(clients):
    from app.growth.models import Lead
    from app.tenancy import tenant_scope

    a, _ = clients
    signup(a)
    brand, lead = brand_and_lead(a)
    enable(a, brand)

    async def revoke():
        async with a.app.state.factory() as session:
            await tenant_scope(session, organization_id=brand["organization_id"])
            contact = await session.get(Lead, lead["id"])
            contact.lawful_basis = "not_established"
            contact.basis_evidence = ""
            await session.commit()

    a.portal.call(revoke)
    response = a.post(
        "/v1/inbox/simulate",
        json={"lead_id": lead["id"], "body": "Tell me more", "idempotency_key": key()},
    )
    assert response.status_code == 201, response.text
    drain(a)
    assert not rows(a, "effects")
    assert all(t["status"] == "succeeded" for t in rows(a, "tasks"))
    assert rows(a, "approvals")[0]["status"] == "pending"
    assert rows(a, "approvals")[0]["decision_basis"] == "standing_policy_blocked"
