import asyncio

import httpx
import pytest
from fastapi import HTTPException
from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows


@pytest.mark.asyncio
async def test_slow_response_cannot_extend_public_fetch_forever(monkeypatch):
    from app.growth import ingestion

    monkeypatch.setattr(ingestion, "FETCH_DEADLINE_SECONDS", 0.03)
    received = []

    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            for index in range(50):
                await asyncio.sleep(0.02)
                received.append(index)
                yield b"Some public source text."

    async def resolve(host):
        return "8.8.8.8"

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"content-type": "text/plain"}, stream=Slow())
    )
    with pytest.raises(HTTPException) as error:
        await ingestion.fetch_text("https://business.example/contact", transport, resolve)
    assert error.value.detail == "public_website_timeout"
    assert len(received) < 50


def test_autopilot_deadline_fails_before_worker_lease_expiry(clients, monkeypatch):
    from app.growth import autopilot, discovery

    a, _ = clients
    signup(a)
    brand, _ = brand_and_lead(a)
    monkeypatch.setattr(autopilot, "RESEARCH_DEADLINE_SECONDS", 0.01)

    async def slow(*args, **kwargs):
        await asyncio.sleep(1)
        return {"results": []}

    monkeypatch.setattr(discovery, "discover", slow)
    response = a.post(
        "/v1/autopilot/start",
        json={
            "brand_id": brand["id"],
            "objective": "Prepare the campaign and research prospects",
            "search_query": "public business websites",
            "idempotency_key": key(),
        },
    )
    assert response.status_code == 202
    drain(a)
    research = next(task for task in rows(a, "tasks") if task["type"] == "autopilot_research")
    assert research["status"] == "failed"
    assert research["error_code"] == "prospect_research_deadline_exceeded"
    assert research["leased_until"] is None
    assert rows(a, "messages") == []
    assert rows(a, "effects") == []
