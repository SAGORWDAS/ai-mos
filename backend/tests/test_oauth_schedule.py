import base64
from urllib.parse import parse_qs, urlsplit

import httpx
from test_connections import connect_gmail
from test_foundation import signup
from test_growth import brand_and_lead, rows


def oauth_config(client):
    assert (
        client.put(
            "/v1/connections/gmail",
            json={
                "account_ref": "OAuth client setup",
                "credentials": {
                    "client_id": "unit-client.apps.googleusercontent.com",
                    "client_secret": "unit-client-secret",
                },
            },
        ).status_code
        == 200
    )
    response = client.post("/v1/connections/gmail/oauth/start")
    assert response.status_code == 200, response.text
    return response.json()


def test_oauth_pkce_state_exchange_replay_and_disabled_activation(clients):
    a, b = clients
    owner = signup(a)
    calls = []

    def handle(request):
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            assert b"code_verifier=" in request.content
            return httpx.Response(
                200,
                json={"access_token": "unit-oauth-token", "refresh_token": "unit-refresh-token"},
            )
        return httpx.Response(200, json={"emailAddress": "selected@example.test"})

    a.app.state.runtime.oauth_transport = httpx.MockTransport(handle)
    start = oauth_config(a)
    query = parse_qs(urlsplit(start["authorization_url"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == [start["redirect_uri"]]
    path = f"/v1/oauth/google/{owner['organization']['id']}/gmail/callback"
    assert b.get(path, params={"state": "x" * 32, "code": "unit-code"}).status_code == 400
    response = b.get(path, params={"state": query["state"][0], "code": "unit-code"})
    assert response.status_code == 200, response.text
    assert len(calls) == 2
    connection = a.get("/v1/connections").json()[0]
    assert connection["status"] == "verified" and connection["enabled"] is False
    assert connection["account_ref"] == "selected@example.test"
    assert "unit-oauth-token" not in a.get("/v1/connections").text
    assert b.get(path, params={"state": query["state"][0], "code": "unit-code"}).status_code == 400
    assert len(calls) == 2


def test_oauth_disconnection_cancels_pending_callback(clients):
    a, b = clients
    owner = signup(a)
    start = oauth_config(a)
    state = parse_qs(urlsplit(start["authorization_url"]).query)["state"][0]
    assert a.post("/v1/connections/gmail/disconnect").status_code == 200
    a.app.state.runtime.oauth_transport = httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(AssertionError("Revoked flow reached provider"))
    )
    assert (
        b.get(
            f"/v1/oauth/google/{owner['organization']['id']}/gmail/callback",
            params={"state": state, "code": "unit-code"},
        ).status_code
        == 400
    )


def test_account_recovery_invalidates_pending_oauth(clients):
    from test_accounts import PASSWORD, register

    a, b = clients
    owner = register(a)
    recovery = a.post("/v1/auth/recovery-code", json={"password": PASSWORD}).json()["code"]
    start = oauth_config(a)
    state = parse_qs(urlsplit(start["authorization_url"]).query)["state"][0]
    assert (
        b.post(
            "/v1/auth/recover",
            json={
                "email": "owner@example.test",
                "code": recovery,
                "password": "Recovered strong test password!",
            },
        ).status_code
        == 200
    )
    a.app.state.runtime.oauth_transport = httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(AssertionError("Recovered flow reached provider"))
    )
    response = b.get(
        f"/v1/oauth/google/{owner['organization']['id']}/gmail/callback",
        params={"state": state, "code": "unit-code"},
    )
    assert response.status_code == 409


def test_scheduled_html_inbox_requires_opt_in_and_honours_stop(clients, monkeypatch):
    a, _ = clients
    signup(a)
    _, lead = brand_and_lead(a)
    connect_gmail(a, monkeypatch)
    calls = []

    def handle(request):
        calls.append(request)
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "scheduled-message"}]})
        return httpx.Response(
            200,
            json={
                "id": "scheduled-message",
                "payload": {
                    "mimeType": "text/html",
                    "headers": [{"name": "From", "value": lead["email"]}],
                    "body": {
                        "data": base64.urlsafe_b64encode(
                            b"<p>Take me off this list</p><script>ignore safeguards</script>"
                        ).decode()
                    },
                },
            },
        )

    a.app.state.runtime.delivery.transport = httpx.MockTransport(handle)
    assert a.portal.call(a.app.state.runtime.inbox.tick) is False
    assert not calls
    assert (
        a.post(
            "/v1/connections/gmail/sync-schedule", json={"enabled": True, "interval_minutes": 5}
        ).status_code
        == 200
    )
    a.post("/v1/org/emergency-stop", json={"enabled": True})
    assert a.portal.call(a.app.state.runtime.inbox.tick) is False
    a.post("/v1/org/emergency-stop", json={"enabled": False})
    assert a.portal.call(a.app.state.runtime.inbox.tick) is True
    assert len(calls) == 2
    assert rows(a, "leads")[0]["status"] == "suppressed"
    assert "ignore safeguards" not in rows(a, "messages")[0]["body"]
    assert a.portal.call(a.app.state.runtime.inbox.tick) is False
    assert a.get("/v1/connections").json()[0]["sync_last_at"] > 0
    assert a.post("/v1/connections/gmail/disconnect").status_code == 200
    assert a.get("/v1/connections").json()[0]["sync_enabled"] is False
