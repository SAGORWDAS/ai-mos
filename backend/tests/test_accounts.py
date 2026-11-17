import time

from app.accounts import totp

PASSWORD = "A strong test password 2026!"


def register(client, email="owner@example.test"):
    return client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "name": "Test user",
            "organization_name": "Test account workspace",
            "password": PASSWORD,
        },
    ).json()


def test_totp_rfc6238_vector():
    assert totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 1) == "287082"


def test_private_recovery_consumed_once_and_all_sessions_revoked(clients):
    a, b = clients
    register(a)
    b.post("/v1/auth/login", json={"email": "owner@example.test", "password": PASSWORD})
    assert a.post("/v1/auth/recovery-code", json={"password": "wrong"}).status_code == 401
    code = a.post("/v1/auth/recovery-code", json={"password": PASSWORD}).json()["code"]
    assert code not in a.get("/v1/exports/workspace").text
    newpass = "A replacement test password!"
    assert (
        b.post(
            "/v1/auth/recover",
            json={"email": "owner@example.test", "code": code, "password": newpass},
        ).status_code
        == 200
    )
    assert a.get("/v1/auth/me").status_code == 401
    assert (
        a.post(
            "/v1/auth/recover",
            json={"email": "owner@example.test", "code": code, "password": newpass},
        ).status_code
        == 401
    )
    assert (
        a.post(
            "/v1/auth/login", json={"email": "owner@example.test", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        a.post(
            "/v1/auth/login", json={"email": "owner@example.test", "password": newpass}
        ).status_code
        == 200
    )


def test_authenticator_confirmation_login_replay_and_recovery(clients):
    a, b = clients
    register(a)
    recovery = a.post("/v1/auth/recovery-code", json={"password": PASSWORD}).json()["code"]
    b.post("/v1/auth/login", json={"email": "owner@example.test", "password": PASSWORD})
    secret = a.post("/v1/auth/mfa/setup", json={"password": PASSWORD}).json()["secret"]
    assert a.get("/v1/auth/security").json()["mfa_enabled"] is False
    assert (
        a.post(
            "/v1/auth/mfa/confirm", json={"otp": totp(secret, int(time.time() // 30))}
        ).status_code
        == 200
    )
    assert b.get("/v1/auth/me").status_code == 401
    assert (
        b.post(
            "/v1/auth/login", json={"email": "owner@example.test", "password": PASSWORD}
        ).status_code
        == 401
    )
    otp = totp(secret, int(time.time() // 30) + 1)
    assert (
        b.post(
            "/v1/auth/login", json={"email": "owner@example.test", "password": PASSWORD, "otp": otp}
        ).status_code
        == 200
    )
    assert (
        a.post(
            "/v1/auth/login", json={"email": "owner@example.test", "password": PASSWORD, "otp": otp}
        ).status_code
        == 401
    )
    assert (
        a.post(
            "/v1/auth/recover",
            json={"email": "owner@example.test", "code": recovery, "password": PASSWORD},
        ).status_code
        == 200
    )
    assert b.get("/v1/auth/me").status_code == 401
    assert (
        a.post(
            "/v1/auth/login", json={"email": "owner@example.test", "password": PASSWORD}
        ).status_code
        == 200
    )
    assert a.get("/v1/auth/security").json() == {"mfa_enabled": False, "recovery_configured": False}


def join(a, b):
    owner = register(a)
    member = register(b, "member@example.test")
    token = a.post(
        "/v1/org/invitations", json={"email": "member@example.test", "role": "member"}
    ).json()["token"]
    assert b.post("/v1/org/invitations/accept", json={"token": token}).status_code == 200
    return owner, member


def test_member_lifecycle_and_last_owner_safeguards(clients):
    a, b = clients
    owner, member = join(a, b)
    member_id = next(
        item["id"]
        for item in a.get("/v1/org/members").json()
        if item["email"] == "member@example.test"
    )
    owner_id = next(
        item["id"] for item in a.get("/v1/org/members").json() if item["role"] == "owner"
    )
    assert b.put("/v1/org/members/" + owner_id, json={"role": "viewer"}).status_code == 403
    assert a.put("/v1/org/members/" + owner_id, json={"role": "viewer"}).status_code == 409
    assert a.put("/v1/org/members/" + member_id, json={"role": "viewer"}).status_code == 200
    assert b.post("/v1/brands", json={"name": "Refused"}).status_code == 403
    assert a.post("/v1/org/members/" + owner_id + "/remove").status_code == 409
    assert a.post("/v1/org/members/" + member_id + "/remove").status_code == 200
    assert b.get("/v1/auth/me").status_code == 401
    assert (
        b.post(
            "/v1/auth/login", json={"email": "member@example.test", "password": PASSWORD}
        ).status_code
        == 200
    )
    assert b.get("/v1/auth/me").json()["organization"]["id"] == member["organization"]["id"]


def test_ownership_transfer_requires_existing_member_and_password(clients):
    a, b = clients
    join(a, b)
    member_id = next(
        item["id"] for item in a.get("/v1/org/members").json() if item["role"] == "member"
    )
    assert (
        a.post("/v1/org/transfer", json={"user_id": member_id, "password": "wrong"}).status_code
        == 401
    )
    assert (
        a.post("/v1/org/transfer", json={"user_id": member_id, "password": PASSWORD}).status_code
        == 200
    )
    assert a.get("/v1/auth/me").json()["role"] == "admin"
    assert b.get("/v1/auth/me").json()["role"] == "owner"
    assert a.post("/v1/org/emergency-stop", json={"enabled": True}).status_code == 403
