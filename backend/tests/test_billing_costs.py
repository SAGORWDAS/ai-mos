import httpx
from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows


def paid_recurring(client):
    signup(client)
    _, lead = brand_and_lead(client)
    checkout = client.post(
        "/v1/checkouts",
        json={
            "lead_id": lead["id"],
            "description": "Recurring test service",
            "amount_minor": 10000,
            "currency": "USD",
            "recurring": True,
        },
    ).json()
    assert (
        client.post(
            f"/v1/checkouts/{checkout['id']}/simulate-payment", json={"event_id": key()}
        ).status_code
        == 200
    )
    return checkout


def test_billing_renewal_failure_cancellation_refunds_and_replay(clients):
    a, b = clients
    checkout = paid_recurring(a)
    signup(b, "other@example.test")
    path = f"/v1/checkouts/{checkout['id']}/simulate-lifecycle"
    payload = {"idempotency_key": key(), "kind": "renewal"}
    assert b.post(path, json=payload).status_code == 404
    assert a.post(path, json=payload).status_code == 200
    assert a.post(path, json=payload).json()["status"] == "duplicate"
    assert len(rows(a, "payments")) == 2
    assert (
        a.post(path, json={"idempotency_key": key(), "kind": "payment_failed"}).status_code == 200
    )
    assert rows(a, "subscriptions")[0]["status"] == "past_due"
    assert rows(a, "customers")[0]["status"] == "at_risk"
    assert a.post(path, json={"idempotency_key": key(), "kind": "renewal"}).status_code == 200
    assert rows(a, "subscriptions")[0]["status"] == "active"
    assert a.post(path, json={"idempotency_key": key(), "kind": "cancel"}).status_code == 200
    assert rows(a, "subscriptions")[0]["status"] == "canceled"
    assert rows(a, "customers")[0]["status"] == "churned"
    assert (
        a.post(
            path, json={"idempotency_key": key(), "kind": "refund", "amount_minor": 4000}
        ).status_code
        == 200
    )
    assert (
        a.post(
            path, json={"idempotency_key": key(), "kind": "refund", "amount_minor": 10000}
        ).status_code
        == 200
    )
    assert (
        a.post(
            path, json={"idempotency_key": key(), "kind": "refund", "amount_minor": 4000}
        ).status_code
        == 200
    )
    analytics = a.get("/v1/analytics").json()
    assert analytics["refunds_minor"]["sandbox"] == {"USD": 10000}
    assert analytics["net_simulated_revenue_minor"] == {"USD": 20000}
    assert (
        a.post(
            path, json={"idempotency_key": key(), "kind": "refund", "amount_minor": 20000}
        ).status_code
        == 422
    )


def unknown_model(client):
    signup(client)
    _, lead = brand_and_lead(client)
    runtime = client.app.state.runtime
    runtime.settings.provider_mode = "openrouter"
    runtime.settings.openrouter_api_key = "unit-key"
    runtime.settings.model_id = "unit/model"
    runtime.gateway.transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"id": "gen-unit", "choices": [{"message": {"content": "{}"}}]}
        )
    )
    client.post("/v1/drafts", json={"lead_id": lead["id"], "idempotency_key": key()})
    drain(client)
    usage = rows(client, "model_usage")[0]
    assert usage["settled"] is False
    assert client.get("/v1/budgets/current").json()["reserved_micros"] == 20000
    return usage


def test_unknown_cost_can_be_reconciled_once_with_owner_receipt(clients):
    a, b = clients
    usage = unknown_model(a)
    signup(b, "other@example.test")
    path = f"/v1/model-usage/{usage['id']}/reconcile"
    assert (
        b.post(
            path, json={"cost_micros": 1000, "evidence": "Provider account receipt test"}
        ).status_code
        == 404
    )
    assert a.post(path, json={"cost_micros": 1000}).status_code == 422
    assert (
        a.post(
            path, json={"cost_micros": 1000, "evidence": "Provider account receipt test"}
        ).status_code
        == 200
    )
    assert (
        a.post(
            path, json={"cost_micros": 5000, "evidence": "Duplicate receipt should not charge"}
        ).json()["status"]
        == "already_settled"
    )
    budget = a.get("/v1/budgets/current").json()
    assert budget["reserved_micros"] == 0 and budget["spent_micros"] == 1000
    assert rows(a, "model_usage")[0]["settled"] is True


def test_two_subscriptions_for_same_customer_cancel_independently(clients):
    a, _ = clients
    first = paid_recurring(a)
    lead = rows(a, "leads")[0]
    second = a.post(
        "/v1/checkouts",
        json={
            "lead_id": lead["id"],
            "description": "Second recurring service",
            "amount_minor": 5000,
            "currency": "USD",
            "recurring": True,
        },
    ).json()
    assert (
        a.post(
            f"/v1/checkouts/{second['id']}/simulate-payment", json={"event_id": key()}
        ).status_code
        == 200
    )
    assert len(rows(a, "customers")) == 1 and len(rows(a, "subscriptions")) == 2
    assert (
        a.post(
            f"/v1/checkouts/{first['id']}/simulate-lifecycle",
            json={"idempotency_key": key(), "kind": "cancel"},
        ).status_code
        == 200
    )
    assert rows(a, "customers")[0]["status"] == "active"
    assert (
        a.post(
            f"/v1/checkouts/{second['id']}/simulate-lifecycle",
            json={"idempotency_key": key(), "kind": "cancel"},
        ).status_code
        == 200
    )
    assert rows(a, "customers")[0]["status"] == "churned"
