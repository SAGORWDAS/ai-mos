import time
from types import SimpleNamespace

from test_foundation import signup
from test_growth import brand_and_lead, key

from app.growth.attribution import allocate


def test_integer_multitouch_attribution_conserves_currency_and_mode():
    payment = SimpleNamespace(
        lead_id="lead", created_at=1000, amount_minor=101, currency="USD", simulated=True
    )
    touches = [
        SimpleNamespace(
            id=str(i), lead_id="lead", campaign_id=campaign, occurred_at=when, simulated=mode
        )
        for i, (campaign, when, mode) in enumerate(
            [
                ("a", 100, True),
                ("a", 200, True),
                ("b", 300, True),
                ("future", 2000, True),
                ("live", 400, False),
            ]
        )
    ]
    result = allocate([payment], touches, "linear", 90)
    assert {r["campaign_id"]: r["amount_minor"] for r in result} == {"a": 51, "b": 50}
    assert allocate([payment], touches, "first_touch", 90)[0]["campaign_id"] == "a"
    assert allocate([payment], touches, "last_touch", 90)[0]["campaign_id"] == "b"
    payment.created_at = 10_000_000
    assert allocate([payment], touches, "last_touch", 1)[0]["campaign_id"] is None


def test_attribution_tenant_scope_replay_and_paid_outcome(clients):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    brand, lead = brand_and_lead(a)
    campaign = a.post(
        "/v1/campaigns",
        json={"brand_id": brand["id"], "name": "Test campaign", "lead_ids": [lead["id"]]},
    ).json()
    payload = {
        "lead_id": lead["id"],
        "campaign_id": campaign["id"],
        "channel": "email",
        "evidence": "Synthetic approved outreach receipt",
        "occurred_at": time.time() - 10,
        "idempotency_key": key(),
    }
    first = a.post("/v1/attribution/touches", json=payload)
    assert first.status_code == 201, first.text
    assert a.post("/v1/attribution/touches", json=payload).json()["id"] == first.json()["id"]
    assert (
        a.post("/v1/attribution/touches", json={**payload, "channel": "social"}).status_code == 409
    )
    assert b.post("/v1/attribution/touches", json=payload).status_code == 404
    assert b.get("/v1/attribution/report").json()["touches"] == 0
    checkout = a.post(
        "/v1/checkouts",
        json={
            "lead_id": lead["id"],
            "description": "Sample service",
            "amount_minor": 12345,
            "currency": "USD",
        },
    ).json()
    assert (
        a.post(
            f"/v1/checkouts/{checkout['id']}/simulate-payment", json={"event_id": key()}
        ).status_code
        == 200
    )
    report = a.get("/v1/attribution/report").json()
    assert report["revenue"] == [
        {
            "campaign_id": campaign["id"],
            "currency": "USD",
            "simulated": True,
            "payments": 1,
            "amount_minor": 12345,
        }
    ]
    assert (
        b.post(
            "/v1/expenses",
            json={
                "category": "data",
                "amount_micros": 10,
                "evidence": "Synthetic cost",
                "campaign_id": campaign["id"],
            },
        ).status_code
        == 404
    )
    assert (
        a.post(
            "/v1/expenses",
            json={
                "category": "data",
                "amount_micros": 10,
                "evidence": "Synthetic cost",
                "campaign_id": campaign["id"],
            },
        ).status_code
        == 201
    )
    assert a.get("/v1/attribution/report").json()["costs"][0]["amount_micros"] == 10
