import base64

import httpx
from test_connections import connect_gmail
from test_foundation import signup
from test_growth import brand_and_lead, drain, rows


def test_owner_opt_in_prepares_safe_reply_once_and_escalates_ambiguous(clients, monkeypatch):
    a, _ = clients
    signup(a)
    _, lead = brand_and_lead(a)
    connect_gmail(a, monkeypatch)

    def provider(request):
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "clear"}, {"id": "ambiguous"}]})
        message_id = request.url.path.rsplit("/", 1)[-1]
        text = (
            "Tell me more"
            if message_id == "clear"
            else "What is the price and can we schedule a call?"
        )
        return httpx.Response(
            200,
            json={
                "id": message_id,
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [{"name": "From", "value": lead["email"]}],
                    "body": {"data": base64.urlsafe_b64encode(text.encode()).decode()},
                },
            },
        )

    a.app.state.runtime.delivery.transport = httpx.MockTransport(provider)
    assert (
        a.post(
            "/v1/connections/gmail/sync-schedule",
            json={"enabled": False, "auto_draft_replies": True},
        ).status_code
        == 200
    )
    assert a.post("/v1/inbox/sync", json={}).json()["imported"] == 2
    drain(a)
    drafts = rows(a, "outreach_drafts")
    assert len(drafts) == 1
    assert drafts[0]["status"] == "pending_approval"
    assert len(rows(a, "approvals")) == 1
    assert all(m["direction"] == "inbound" for m in rows(a, "messages"))
    assert a.post("/v1/inbox/sync", json={}).json()["duplicates"] == 2
    drain(a)
    assert len(rows(a, "outreach_drafts")) == 1
    assert a.post("/v1/connections/gmail/disconnect").status_code == 200
    assert a.get("/v1/connections").json()[0]["auto_draft_replies"] is False
