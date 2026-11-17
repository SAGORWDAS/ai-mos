import time

import httpx
import pytest
from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows

from app.growth.providers import GoogleProvider


def test_registered_tools_use_workflows_and_permission_ceilings(clients):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    brand, lead = brand_and_lead(a)

    def invoke(tool, agent, args):
        return a.post(f"/v1/tools/{tool}/invoke", json={"agent_id": agent, "args": args})

    assert invoke("TLS-04", "AGT-05", {"lead_id": lead["id"]}).json()["score"] >= 0
    assert invoke("TLS-04", "AGT-05", {}).status_code == 422
    assert (
        b.post(
            "/v1/tools/TLS-04/invoke", json={"agent_id": "AGT-05", "args": {"lead_id": lead["id"]}}
        ).status_code
        == 404
    )
    result = invoke(
        "TLS-06",
        "AGT-06",
        {
            "brand_id": brand["id"],
            "type": "article",
            "topic": "Approved service",
            "idempotency_key": key(),
        },
    )
    assert result.status_code == 200, result.text
    drain(a)
    content = rows(a, "content_items")[0]
    approval = invoke("TLS-13", "AGT-14", {"subject_type": "content", "subject_id": content["id"]})
    assert approval.status_code == 200
    assert approval.json()["status"] == "pending"
    assert (
        invoke(
            "TLS-14", "AGT-07", {"approval_id": approval.json()["id"], "idempotency_key": key()}
        ).status_code
        == 403
    )
    assert (
        invoke("TLS-11", "AGT-08", {"body": "Please unsubscribe me"}).json()["label"]
        == "unsubscribe"
    )
    assert invoke("TLS-11", "AGT-08", {"body": "x" * 5001}).status_code == 422
    assert (
        invoke(
            "TLS-07",
            "AGT-07",
            {"lead_id": lead["id"], "status": "qualified", "reason": "Reviewed sample evidence"},
        ).status_code
        == 200
    )
    assert (
        invoke(
            "TLS-07",
            "AGT-07",
            {
                "lead_id": lead["id"],
                "status": "qualified",
                "reason": "Reviewed sample evidence",
                "paid": True,
            },
        ).status_code
        == 422
    )
    now = time.time() + 3600
    assert (
        invoke("TLS-08", "AGT-11", {"starts_at": now, "ends_at": now + 1800}).json()["simulated"]
        is True
    )
    assert (
        invoke(
            "TLS-01",
            "AGT-02",
            {"brand_id": brand["id"], "query": "sample prospect search", "idempotency_key": key()},
        ).status_code
        == 200
    )
    drain(a)


@pytest.mark.asyncio
async def test_calendar_read_cache_is_bounded_and_booking_rechecks():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/freeBusy"):
            return httpx.Response(200, json={"calendars": {"primary": {"busy": []}}})
        return httpx.Response(503)

    provider = GoogleProvider("test-cache-token", transport=httpx.MockTransport(handler))
    GoogleProvider._availability_cache.clear()
    assert await provider.availability(1, 1000, use_cache=True)
    assert await provider.availability(1, 1000, use_cache=True)
    assert len(calls) == 1
    assert await provider.availability(1, 1000)
    assert len(calls) == 2
