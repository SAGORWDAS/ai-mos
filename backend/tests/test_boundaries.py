import sqlite3

from test_foundation import signup


def test_validation_and_duplicate_accounts(clients):
    a, _ = clients
    signup(a)
    duplicate = a.post(
        "/v1/auth/signup",
        json={
            "email": "OWNER@example.com",
            "password": "a secure passphrase 123",
            "name": "Another owner",
            "organization_name": "Another org",
        },
    )
    assert duplicate.status_code == 409
    assert a.post("/v1/brands", json={"name": "X", "icp": {"segments": "bad"}}).status_code == 422
    assert (
        a.post("/v1/brands", json={"name": "X", "website": "javascript:alert(1)"}).status_code
        == 422
    )
    assert a.post("/v1/brands", json={"name": "Unique"}).status_code == 201
    assert a.post("/v1/brands", json={"name": "Unique"}).status_code == 409
    assert a.post("/v1/brands", json={"name": "X", "positioning": "x" * 70000}).status_code == 413


def test_session_expiry_and_password_storage(clients, tmp_path):
    a, _ = clients
    signup(a)
    with sqlite3.connect(tmp_path / "test.db") as db:
        password = db.execute("SELECT password_hash FROM users").fetchone()[0]
        assert "a secure passphrase 123" not in password
        token = db.execute("SELECT token_hash FROM sessions").fetchone()[0]
        assert token != a.cookies.get("ai_mos_session")
        db.execute("UPDATE sessions SET expires_at=0")
    assert a.get("/v1/auth/me").status_code == 401


def test_invite_cannot_be_used_by_another_email(clients, tmp_path):
    a, b = clients
    signup(a)
    signup(b, "wrong@example.com")
    token = a.post(
        "/v1/org/invitations",
        json={
            "email": "right@example.com",
            "role": "member",
        },
    ).json()["token"]
    assert b.post("/v1/org/invitations/accept", json={"token": token}).status_code == 404
    assert b.post("/v1/orgs/not-my-org/switch", json={}).status_code == 404
    with sqlite3.connect(tmp_path / "test.db") as db:
        assert db.execute("SELECT accepted FROM invitations").fetchone()[0] == 0


def test_authentication_required_every_private_surface(clients):
    a, _ = clients
    for path in [
        "/v1/auth/me",
        "/v1/orgs",
        "/v1/org/members",
        "/v1/brands",
        "/v1/audit",
        "/v1/integrations",
        "/v1/metrics/overview",
    ]:
        assert a.get(path).status_code == 401
