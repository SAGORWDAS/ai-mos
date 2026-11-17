import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows
from test_knowledge_publication import publish

from app.growth.attribution import allocate
from app.growth.measurement import refund_events


def test_signed_enquiry_source_is_scoped_and_replay_safe(clients):
    a, b = clients
    owner = signup(a)
    brand, lead = brand_and_lead(a)
    page = publish(a, brand)
    campaign = a.post(
        "/v1/campaigns",
        json={"brand_id": brand["id"], "name": "Owned page campaign", "lead_ids": [lead["id"]]},
    ).json()
    response = a.post(
        f"/v1/campaigns/{campaign['id']}/tracking-link",
        json={"content_id": page["id"], "channel": "social"},
    )
    assert response.status_code == 200, response.text
    url = urlsplit(response.json()["url"])
    token = parse_qs(url.query)["campaign_token"][0]
    path = f"/v1/public/{owner['organization']['id']}/{page['id']}"
    assert 'name="campaign_token"' in b.get(path + "?" + url.query).text
    data = {
        "name": "Fixture enquiry",
        "email": "enquiry@example.invalid",
        "message": "Please tell me about this service.",
        "request_reply": True,
        "campaign_token": token,
    }
    assert b.post(path + "/enquire", json=data).status_code == 200
    assert b.post(path + "/enquire", json=data).status_code == 200
    touches = rows(a, "attribution_touches")
    assert len(touches) == 1 and touches[0]["campaign_id"] == campaign["id"]
    assert touches[0]["channel"] == "social"
    assert (
        b.post(
            path + "/enquire",
            json={**data, "campaign_token": token[:-1] + ("0" if token[-1] != "0" else "1")},
        ).status_code
        == 422
    )
    new = next(lead for lead in rows(a, "leads") if lead["email"] == data["email"])
    assert new["lawful_basis"] == "not_established"


def test_model_costs_customer_credit_and_refund_net_preserve_lineage(clients):
    a, _ = clients
    signup(a)
    setup = a.post(
        "/v1/setup/start",
        json={
            "name": "Fictional reporting",
            "offer": "We build websites for shops.",
            "audience": "Shops",
            "objective": "Prepare an evidence-backed sample campaign",
            "sample": True,
            "idempotency_key": key(),
        },
    ).json()
    drain(a)
    lead = rows(a, "leads")[0]
    campaign = rows(a, "campaigns")[0]
    a.post(
        "/v1/attribution/touches",
        json={
            "lead_id": lead["id"],
            "campaign_id": campaign["id"],
            "channel": "email",
            "evidence": "Synthetic test receipt",
            "occurred_at": time.time() - 5,
            "simulated": True,
            "idempotency_key": key(),
        },
    )
    checkout = a.post(
        "/v1/checkouts",
        json={
            "lead_id": lead["id"],
            "description": "Sample service",
            "amount_minor": 101,
            "currency": "USD",
        },
    ).json()
    a.post(f"/v1/checkouts/{checkout['id']}/simulate-payment", json={"event_id": key()})
    refunded = a.post(
        f"/v1/checkouts/{checkout['id']}/simulate-lifecycle",
        json={"kind": "refund", "amount_minor": 31, "idempotency_key": key()},
    )
    assert refunded.status_code == 200, refunded.text
    report = a.get("/v1/attribution/report").json()
    assert sum(r["amount_minor"] for r in report["net_revenue"]) == 70
    assert report["unresolved_refunds"] == 0
    bucket = next(c for c in report["costs"] if c["campaign_id"] == campaign["id"])
    usage = rows(a, "model_usage")
    assert bucket["model_micros"] == sum(u["cost_micros"] for u in usage)
    assert (
        next(o for o in report["outcomes"] if o["campaign_id"] == campaign["id"])["customer_credit"]
        == 1
    )
    assert setup["task"]["id"]


def test_refund_rounding_is_symmetric_and_ambiguous_legacy_credit_is_unassigned():
    payment = SimpleNamespace(
        lead_id="x", created_at=100, amount_minor=101, currency="USD", simulated=False
    )
    touches = [
        SimpleNamespace(
            id=str(i), lead_id="x", campaign_id=str(i), occurred_at=50 + i, simulated=False
        )
        for i in range(2)
    ]
    positive = allocate([payment], touches, "linear", 90)
    payment.amount_minor = -101
    negative = allocate([payment], touches, "linear", 90)
    assert all(
        p["amount_minor"] == -n["amount_minor"] for p, n in zip(positive, negative, strict=True)
    )
    payments = [
        SimpleNamespace(checkout_id="c", simulated=False, currency="USD", provider_event_id=str(i))
        for i in range(2)
    ]
    receipt = SimpleNamespace(
        kind="charge.refunded",
        amount_minor=-10,
        evidence={"checkout_id": "c"},
        simulated=False,
        currency="USD",
        created_at=100,
    )
    refunds, unknown = refund_events([receipt], payments, {}, "org")
    assert unknown == 1
    assert allocate(refunds, touches, "last_touch", 90)[0]["campaign_id"] is None
