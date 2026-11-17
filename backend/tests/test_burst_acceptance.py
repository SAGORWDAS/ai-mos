import asyncio

import httpx
from test_connections import connect_gmail
from test_foundation import signup
from test_growth import approve, brand_and_lead, key, rows


def test_tenfold_draft_burst_under_four_workers_preserves_jobs(clients, monkeypatch):
    a, _ = clients
    signup(a)
    brand, _ = brand_and_lead(a)
    people = a.post(
        "/v1/leads/import",
        json={
            "leads": [
                {
                    "brand_id": brand["id"],
                    "name": f"Fixture {i}",
                    "email": f"burst{i}@example.invalid",
                    "source": "Controlled burst fixture",
                    "lawful_basis": "consent",
                    "basis_evidence": "Synthetic test only; no real recipients",
                }
                for i in range(20)
            ]
        },
    ).json()["created"]
    identities = []
    for lead in people:
        payload = {"lead_id": lead["id"], "idempotency_key": key()}
        first = a.post("/v1/drafts", json=payload)
        assert first.status_code == 202, first.text
        assert a.post("/v1/drafts", json=payload).json()["id"] == first.json()["id"]
        identities.append(first.json()["id"])

    async def burst():
        async def worker():
            for _ in range(100):
                if not await a.app.state.runtime.tick():
                    return
            raise AssertionError("Burst worker did not drain")

        await asyncio.gather(*(worker() for _ in range(4)))

    a.portal.call(burst)
    tasks = rows(a, "tasks")
    assert len(tasks) == 20
    assert {t["id"] for t in tasks} == set(identities)
    assert all(t["status"] == "succeeded" for t in tasks), tasks
    assert len(rows(a, "outreach_drafts")) == 20
    assert len({d["task_id"] for d in rows(a, "outreach_drafts")}) == 20
    assert not rows(a, "messages")
    connect_gmail(a, monkeypatch)
    requests = []

    def provider(request):
        assert request.url.path.endswith("/messages/send")
        requests.append(request.content)
        return httpx.Response(200, json={"id": f"fixture-burst-{len(requests)}"})

    a.app.state.runtime.delivery.transport = httpx.MockTransport(provider)
    for draft in rows(a, "outreach_drafts"):
        approval = approve(a, draft)
        payload = {
            "approval_id": approval["id"],
            "idempotency_key": key(),
            "execution_mode": "live",
        }
        first = a.post("/v1/effects/execute", json=payload)
        assert first.status_code == 200, first.text
        assert a.post("/v1/effects/execute", json=payload).json()["id"] == first.json()["id"]
    a.portal.call(burst)
    outgoing = rows(a, "messages")
    assert len(outgoing) == 20 and all(m["status"] == "sent" for m in outgoing)
    assert len(requests) == len(set(requests)) == 20
    assert len({m["provider_id"] for m in outgoing}) == 20
    assert all(e["status"] == "succeeded" for e in rows(a, "effects"))
    a.portal.call(burst)
    assert len(requests) == 20
