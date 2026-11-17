import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows


def test_cancel_during_model_call_cannot_persist_draft_or_overwrite_cancel(clients, monkeypatch):
    a, _ = clients
    signup(a)
    _, lead = brand_and_lead(a)
    runtime = a.app.state.runtime
    original = runtime.gateway.generate
    entered, release = Event(), Event()

    async def delayed(*args, **kwargs):
        result = await original(*args, **kwargs)
        entered.set()
        await asyncio.to_thread(release.wait, 10)
        return result

    monkeypatch.setattr(runtime.gateway, "generate", delayed)
    response = a.post("/v1/drafts", json={"lead_id": lead["id"], "idempotency_key": key()})
    task_id = response.json()["id"]
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(drain, a)
        try:
            assert entered.wait(5)
            assert a.post(f"/v1/tasks/{task_id}/cancel").status_code == 200
        finally:
            release.set()
        pending.result(timeout=10)
    assert rows(a, "outreach_drafts") == []
    assert rows(a, "tasks")[0]["status"] == "cancelled"
    assert len(rows(a, "model_usage")) == 1
