from test_foundation import signup
from test_growth import drain, key, rows


def test_one_brief_setup_is_atomic_scoped_and_replay_safe(clients):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    body = {
        "name": "Sample agency",
        "offer": "We build websites for independent shops.",
        "audience": "Independent shops",
        "objective": "Prepare my first outreach campaign",
        "sample": True,
        "idempotency_key": key(),
    }
    first = a.post("/v1/setup/start", json=body)
    assert first.status_code == 202, first.text
    assert a.post("/v1/setup/start", json=body).json()["task"]["id"] == first.json()["task"]["id"]
    assert (
        a.post(
            "/v1/setup/start", json={**body, "offer": "A different approved sample offer"}
        ).status_code
        == 409
    )
    assert len(a.get("/v1/brands").json()) == 1
    assert len(rows(a, "leads")) == 1
    assert len(rows(a, "campaigns")) == 1
    assert a.get("/v1/brands").json()[0]["voice"]["sandbox_only"] is True
    assert rows(a, "leads")[0]["email"].endswith("@example.invalid")
    assert rows(b, "campaigns") == []
    drain(a)
    assert rows(a, "plans")[0]["status"] == "completed"
    assert rows(a, "outreach_drafts")[0]["status"] == "pending_approval"
    assert not rows(a, "messages")


def test_missing_search_connection_rolls_back_new_business(clients):
    a, _ = clients
    signup(a)
    body = {
        "name": "No partial setup",
        "offer": "We build websites for shops.",
        "audience": "Independent shops",
        "objective": "Find suitable prospects for the offer",
        "connected_research": True,
        "idempotency_key": key(),
    }
    response = a.post("/v1/setup/start", json=body)
    assert response.status_code == 409
    assert not a.get("/v1/brands").json()
    assert not rows(a, "tasks")
    assert not rows(a, "campaigns")
