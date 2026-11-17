import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from test_foundation import signup


def key():
    return str(uuid4())


def rows(client, resource):
    response = client.get(f"/v1/data/{resource}")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def drain(client):
    for _ in range(50):
        if not client.portal.call(client.app.state.runtime.tick):
            return
    raise AssertionError("Queue did not drain")


def brand_and_lead(client, email="contact@example.test"):
    brand = client.post(
        "/v1/brands",
        json={
            "name": "Test agency",
            "positioning": "Website development for independent retailers",
            "website": "https://example.test",
            "icp": {"segments": ["Independent retailers"]},
            "voice": {"tone": "Direct"},
            "approved_claims": ["We build websites for retailers."],
            "prohibited_claims": ["guaranteed revenue"],
        },
    ).json()
    response = client.post(
        "/v1/leads/import",
        json={
            "leads": [
                {
                    "brand_id": brand["id"],
                    "name": "Test contact",
                    "email": email,
                    "company": "Test retail",
                    "domain": "example.test",
                    "source": "First-party enquiry",
                    "lawful_basis": "consent",
                    "basis_evidence": "Synthetic QA contact; local test only",
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    return brand, response.json()["created"][0]


def make_draft(client, lead):
    response = client.post("/v1/drafts", json={"lead_id": lead["id"], "idempotency_key": key()})
    assert response.status_code == 202, response.text
    drain(client)
    drafts = rows(client, "outreach_drafts")
    assert drafts, rows(client, "tasks")
    return drafts[0]


def approve(client, draft):
    response = client.post(f"/v1/drafts/{draft['id']}/request-approval")
    assert response.status_code == 201, response.text
    approval = response.json()
    response = client.post(
        f"/v1/approvals/{approval['id']}/decision", json={"decision": "approved"}
    )
    assert response.status_code == 200, response.text
    return approval


def execute(client, approval, action_key=None):
    return client.post(
        "/v1/effects/execute",
        json={
            "approval_id": approval["id"],
            "idempotency_key": action_key or key(),
        },
    )


def test_complete_sandbox_growth_to_revenue(clients):
    client, _ = clients
    signup(client)
    brand, lead = brand_and_lead(client)
    result = client.post(
        "/v1/commands",
        json={
            "brand_id": brand["id"],
            "objective": "Acquire ten qualified agency prospects",
            "idempotency_key": key(),
        },
    )
    assert result.status_code == 202, result.text
    drain(client)
    plan = rows(client, "plans")[0]
    assert plan["status"] == "draft"
    assert client.post(f"/v1/plans/{plan['id']}/approve").status_code == 200
    drain(client)
    assert rows(client, "plans")[0]["status"] == "completed"
    assert len(rows(client, "content_items")) == 1
    assert len(rows(client, "model_usage")) == 5
    assert client.post(f"/v1/leads/{lead['id']}/score").json()["score"] == 100
    draft = make_draft(client, lead)
    approval = approve(client, draft)
    delivered = execute(client, approval)
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["simulated"] is True
    inbound = client.post(
        "/v1/inbox/simulate",
        json={
            "lead_id": lead["id"],
            "body": "I am interested",
            "idempotency_key": key(),
        },
    )
    assert inbound.status_code == 201
    assert inbound.json()["classification"]["label"] == "interested"
    booking = client.post(
        "/v1/meetings/propose",
        json={
            "lead_id": lead["id"],
            "title": "Agency discovery",
            "starts_at": time.time() + 86400,
        },
    ).json()
    client.post(
        f"/v1/approvals/{booking['approval']['id']}/decision", json={"decision": "approved"}
    )
    assert execute(client, booking["approval"]).json()["status"] == "booked"
    checkout = client.post(
        "/v1/checkouts",
        json={
            "lead_id": lead["id"],
            "description": "Test website project",
            "amount_minor": 10000,
            "currency": "USD",
        },
    ).json()
    event = {"event_id": key()}
    paid = client.post(f"/v1/checkouts/{checkout['id']}/simulate-payment", json=event)
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "processed"
    assert (
        client.post(f"/v1/checkouts/{checkout['id']}/simulate-payment", json=event).json()["status"]
        == "duplicate"
    )
    assert len(rows(client, "payments")) == 1
    customer = rows(client, "customers")[0]
    assert (
        client.put(
            f"/v1/customers/{customer['id']}/onboarding", json={"completed": ["Welcome"]}
        ).status_code
        == 200
    )
    support = client.post(
        "/v1/support",
        json={
            "customer_id": customer["id"],
            "subject": "Refund request",
            "body": "Please refund this test",
        },
    ).json()
    assert support["status"] == "escalated"
    assert len(rows(client, "payments")) == 1
    analytics = client.get("/v1/analytics").json()
    assert analytics["simulated_revenue_minor"] == {"USD": 10000}
    assert analytics["verified_revenue_minor"] == {}
    assert (
        client.post(
            "/v1/learning",
            json={
                "lesson": "Test evidence demonstrates a completed local workflow.",
                "evidence": [plan["id"]],
                "effect_size": 5,
            },
        ).status_code
        == 201
    )


def test_AC03_suppression_precedes_reply_and_blocks_approved_send(clients):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    approval = approve(client, make_draft(client, lead))
    inbound = client.post(
        "/v1/inbox/simulate",
        json={
            "lead_id": lead["id"],
            "body": "Unsubscribe but I am interested in pricing",
            "idempotency_key": key(),
        },
    ).json()
    assert inbound["classification"]["label"] == "unsubscribe"
    result = execute(client, approval)
    assert result.status_code == 403, result.text
    assert rows(client, "messages")[0]["direction"] == "inbound"
    assert len(rows(client, "messages")) == 1
    assert (
        client.post(
            f"/v1/messages/{inbound['id']}/draft-reply", json={"idempotency_key": key()}
        ).status_code
        == 409
    )


def test_AC04_duplicate_worker_and_send_are_single_effect(clients):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    request = {"lead_id": lead["id"], "idempotency_key": key()}
    assert client.post("/v1/drafts", json=request).status_code == 202
    assert client.post("/v1/drafts", json=request).status_code == 202
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: client.portal.call(client.app.state.runtime.tick), range(2)))
    assert len(rows(client, "outreach_drafts")) == 1
    assert len(rows(client, "model_usage")) == 1
    approval = approve(client, rows(client, "outreach_drafts")[0])
    request_key = key()
    assert execute(client, approval, request_key).status_code == 200
    assert execute(client, approval, request_key).status_code == 200
    assert execute(client, approval).status_code == 409
    assert len(rows(client, "messages")) == 1


def test_AC05_edit_revokes_and_expiry_rejects(clients, tmp_path):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    draft = make_draft(client, lead)
    approval = approve(client, draft)
    assert (
        client.put(
            f"/v1/drafts/{draft['id']}",
            json={
                "expected_version": draft["version"],
                "subject": "Following up from Test agency",
                "body": draft["body"],
            },
        ).status_code
        == 200
    )
    assert execute(client, approval).status_code == 409
    approval = approve(client, draft)
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute("UPDATE approvals SET expires_at=0 WHERE id=?", (approval["id"],))
    assert execute(client, approval).status_code == 409
    assert rows(client, "messages") == []


def test_AC07_budget_reservation_and_AC08_timeout_ledger(clients):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    client.app.state.runtime.settings.sandbox_model_cost_micros = 10
    assert (
        client.put(
            "/v1/budgets/current", json={"limit_micros": 0, "daily_send_cap": 20}
        ).status_code
        == 200
    )
    client.post("/v1/drafts", json={"lead_id": lead["id"], "idempotency_key": key()})
    drain(client)
    assert rows(client, "tasks")[0]["error_code"] == "budget_exhausted"
    assert rows(client, "model_usage")[0]["status"] == "budget_refused"
    client.put("/v1/budgets/current", json={"limit_micros": 100, "daily_send_cap": 20})
    client.app.state.runtime.settings.sandbox_failure = "timeout"
    client.post("/v1/drafts", json={"lead_id": lead["id"], "idempotency_key": key()})
    drain(client)
    assert rows(client, "model_usage")[0]["status"] == "timeout"
    assert client.get("/v1/budgets/current").json()["reserved_micros"] == 0


def test_AC09_competing_booking_and_AC10_forged_webhook(clients):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    approvals = []
    for _ in range(2):
        item = client.post(
            "/v1/meetings/propose",
            json={
                "lead_id": lead["id"],
                "title": "Discovery call",
                "starts_at": time.time() + 86400,
            },
        ).json()
        approval = item["approval"]
        client.post(f"/v1/approvals/{approval['id']}/decision", json={"decision": "approved"})
        approvals.append(approval)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda approval: execute(client, approval).status_code, approvals)
        )
    assert sorted(results) == [200, 409]
    result = client.post(
        "/v1/webhooks/payments",
        content=json.dumps({"type": "payment.succeeded"}),
        headers={"x-webhook-signature": "forged", "x-webhook-timestamp": str(int(time.time()))},
    )
    assert result.status_code == 401
    assert rows(client, "payments") == []


def test_AC11_agent_permission_ceiling_AC12_stop_AC14_grounding(clients):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    assert client.post("/v1/tools/TLS-14/invoke", json={"agent_id": "AGT-01"}).status_code == 403
    draft = make_draft(client, lead)
    assert (
        client.put(
            f"/v1/drafts/{draft['id']}",
            json={
                "expected_version": draft["version"],
                "subject": draft["subject"],
                "body": "This is guaranteed revenue for everyone, unsubscribe.",
            },
        ).status_code
        == 422
    )
    approval = approve(client, draft)
    client.post("/v1/org/emergency-stop", json={"enabled": True})
    assert execute(client, approval).status_code == 423
    assert rows(client, "messages") == []


def test_tenant_boundaries_on_every_growth_read_and_foreign_key_input(clients):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    brand, lead = brand_and_lead(a)
    draft = make_draft(a, lead)
    approval = approve(a, draft)
    execute(a, approval)
    for resource in [
        "leads",
        "outreach_drafts",
        "tasks",
        "model_usage",
        "approvals",
        "messages",
        "effects",
        "activities",
        "brand_documents",
        "brand_chunks",
    ]:
        assert rows(a, resource)
        assert rows(b, resource) == []
    assert (
        b.post("/v1/drafts", json={"lead_id": lead["id"], "idempotency_key": key()}).status_code
        == 404
    )
    assert (
        b.post(f"/v1/brands/{brand['id']}/search", json={"query": "retailers"}).status_code == 404
    )
    assert b.get(f"/v1/data/outreach_drafts/{draft['id']}").status_code == 404
