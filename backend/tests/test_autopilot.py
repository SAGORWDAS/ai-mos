from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows


def test_platform_needs_no_business_until_campaign_start(clients):
    a, _ = clients
    signup(a)
    report = a.get("/v1/setup/readiness").json()
    assert report["platform_available"] is True
    assert report["business_details_required_to_install"] is False
    assert report["production_ready"] is False
    assert all(not item["enabled"] for item in report["providers"])
    assert "password" not in str(report)
    brand = a.post("/v1/brands", json={"name": "A business to configure later"}).json()
    response = a.post(
        "/v1/autopilot/start",
        json={
            "brand_id": brand["id"],
            "objective": "Prepare my first campaign",
            "idempotency_key": key(),
        },
    )
    assert response.json()["status"] == "needs_information"
    assert set(response.json()["missing_fields"]) == {"offer", "audience", "approved_facts"}
    assert rows(a, "tasks") == []


def test_autopilot_runs_internal_work_and_prepares_reviews_once(clients):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    brand, lead = brand_and_lead(a)
    body = {
        "brand_id": brand["id"],
        "objective": "Prepare retailer website agency campaign",
        "lead_ids": [lead["id"]],
        "idempotency_key": key(),
    }
    assert b.post("/v1/autopilot/start", json=body).status_code == 404
    response = a.post("/v1/autopilot/start", json=body)
    assert response.status_code == 202, response.text
    assert (
        a.post("/v1/autopilot/start", json=body).json()["task"]["id"]
        == response.json()["task"]["id"]
    )
    assert (
        a.post(
            "/v1/autopilot/start", json={**body, "objective": "A changed campaign objective"}
        ).status_code
        == 409
    )
    drain(a)
    assert len(rows(a, "plans")) == 1
    assert rows(a, "plans")[0]["status"] == "completed", rows(a, "tasks")
    assert len(rows(a, "outreach_drafts")) == 1
    approvals = rows(a, "approvals")
    assert {item["action_class"] for item in approvals} == {"send_email", "publish_content"}
    assert all(item["status"] == "pending" for item in approvals)
    assert rows(a, "messages") == []
    assert rows(a, "effects") == []
    assert all(item["status"] == "succeeded" for item in rows(a, "tasks"))

    async def replay_review():
        from sqlalchemy import select

        from app.growth.models import Task
        from app.tenancy import tenant_scope

        async with a.app.state.factory() as session:
            await tenant_scope(session, organization_id=brand["organization_id"])
            task = await session.scalar(select(Task).where(Task.type == "prepare_review"))
            task.status = "ready"
            task.output = {}
            await session.commit()

    a.portal.call(replay_review)
    drain(a)
    assert len(rows(a, "approvals")) == len(approvals)


def test_autopilot_refuses_unreviewed_contacts_and_unconnected_search(clients):
    a, _ = clients
    signup(a)
    brand, lead = brand_and_lead(a)
    base = {
        "brand_id": brand["id"],
        "objective": "Prepare a small prospect campaign",
        "idempotency_key": key(),
    }
    assert (
        a.post(
            "/v1/autopilot/start",
            json={**base, "connected_research": True, "search_query": "retailer websites"},
        ).status_code
        == 409
    )
    a.post("/v1/suppressions", json={"email": lead["email"], "reason": "manual"})
    assert a.post("/v1/autopilot/start", json={**base, "lead_ids": [lead["id"]]}).status_code == 409
    assert a.post("/v1/org/emergency-stop", json={"enabled": True}).status_code == 200
    assert a.post("/v1/autopilot/start", json=base).status_code == 423


def test_autopilot_collects_observed_contacts_without_inventing_permission(clients, monkeypatch):
    import httpx
    from test_bulk_discovery import connect

    from app.growth import discovery

    a, _ = clients
    signup(a)
    brand, _ = brand_and_lead(a)
    connect(a, monkeypatch, "brave", {"api_key": "unit-search-key"})
    a.app.state.runtime.search_transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "web": {
                    "results": [{"title": "Retailer", "url": "https://retailer.example/contact"}]
                }
            },
        )
    )

    async def fetch(url):
        return "Contact hello@retailer.example for business enquiries", url

    monkeypatch.setattr(discovery, "fetch_text", fetch)
    response = a.post(
        "/v1/autopilot/start",
        json={
            "brand_id": brand["id"],
            "objective": "Research potential website clients",
            "search_query": "retailer websites",
            "connected_research": True,
            "idempotency_key": key(),
        },
    )
    assert response.status_code == 202, response.text
    drain(a)
    assert rows(a, "plans")[0]["status"] == "completed", rows(a, "tasks")
    observed = next(x for x in rows(a, "leads") if x["email"] == "hello@retailer.example")
    assert observed["lawful_basis"] == "not_established"
    assert rows(a, "outreach_drafts") == []
    assert rows(a, "messages") == []


def test_member_cannot_authorize_autopilot(clients):
    a, b = clients
    signup(a)
    signup(b, "member@example.test")
    brand, _ = brand_and_lead(a)
    invite = a.post(
        "/v1/org/invitations", json={"email": "member@example.test", "role": "member"}
    ).json()
    assert b.post("/v1/org/invitations/accept", json={"token": invite["token"]}).status_code == 200
    assert (
        b.post(
            "/v1/autopilot/start",
            json={
                "brand_id": brand["id"],
                "objective": "Prepare a campaign automatically",
                "idempotency_key": key(),
            },
        ).status_code
        == 403
    )
