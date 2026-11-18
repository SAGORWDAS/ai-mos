def signup(client, email="owner@example.com"):
    response = client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "password": "a secure passphrase 123",
            "name": "Owner",
            "organization_name": "Growth studio",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_auth_session_logout_and_bad_password(db_clients):
    a, _ = db_clients
    signup(a)
    assert a.get("/v1/auth/me").json()["role"] == "owner"
    assert a.post("/v1/auth/logout").status_code == 204
    assert a.get("/v1/auth/me").status_code == 401
    assert (
        a.post(
            "/v1/auth/login",
            json={
                "email": "owner@example.com",
                "password": "incorrect",
            },
        ).status_code
        == 401
    )
    assert (
        a.post(
            "/v1/auth/login",
            json={
                "email": "owner@example.com",
                "password": "a secure passphrase 123",
            },
        ).status_code
        == 200
    )


def test_AC02_tenant_isolation_and_forged_org(db_clients):
    a, b = db_clients
    owner = signup(a)
    signup(b, "other@example.com")
    brand = a.post(
        "/v1/brands",
        json={
            "name": "Private brand",
            "positioning": "Human supplied facts",
        },
    ).json()
    assert b.get("/v1/brands").json() == []
    assert b.get(f"/v1/brands/{brand['id']}").status_code == 404
    assert (
        b.post(
            "/v1/brands",
            json={
                "name": "Forged",
                "organization_id": owner["organization"]["id"],
            },
        ).status_code
        == 422
    )
    assert all(row["action"] != "brand.created" for row in b.get("/v1/audit").json())


def test_auth_roles_and_invitation_acceptance(db_clients):
    a, b = db_clients
    signup(a)
    signup(b, "viewer@example.com")
    invite = a.post(
        "/v1/org/invitations",
        json={
            "email": "viewer@example.com",
            "role": "viewer",
        },
    )
    assert invite.status_code == 201
    token = invite.json()["token"]
    assert b.post("/v1/org/invitations/accept", json={"token": token}).status_code == 200
    assert b.get("/v1/auth/me").json()["role"] == "viewer"
    assert b.post("/v1/brands", json={"name": "Forbidden"}).status_code == 403
    assert b.post("/v1/org/emergency-stop", json={"enabled": True}).status_code == 403
    assert b.post("/v1/org/invitations/accept", json={"token": token}).status_code == 409


def test_AC12_emergency_stop_and_audit(db_clients):
    a, _ = db_clients
    signup(a)
    assert a.post("/v1/org/emergency-stop", json={"enabled": True}).status_code == 200
    assert a.post("/v1/brands", json={"name": "Stopped"}).status_code == 423
    assert a.get("/v1/brands").status_code == 200
    actions = [row["action"] for row in a.get("/v1/audit").json()]
    assert "emergency_stop.set" in actions
    assert "action.refused" in actions
    assert a.post("/v1/org/emergency-stop", json={"enabled": False}).status_code == 200
    assert a.post("/v1/brands", json={"name": "Resumed"}).status_code == 201


def test_csrf_cross_origin_is_rejected(db_clients):
    a, _ = db_clients
    signup(a)
    assert a.post("/v1/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403


def test_brand_persistence_update_and_review(db_clients):
    a, _ = db_clients
    signup(a)
    brand = a.post("/v1/brands", json={"name": "My product"}).json()
    result = a.post(f"/v1/brands/{brand['id']}/review").json()
    assert result["status"] == "needs_information"
    assert "positioning" in result["missing_fields"]
    changed = a.put(
        f"/v1/brands/{brand['id']}",
        json={
            "name": "My product",
            "positioning": "Reporting for independent retailers",
            "icp": {"segments": ["Independent retailers"]},
            "approved_claims": ["Exports weekly reports"],
        },
    )
    assert changed.status_code == 200
    assert a.get("/v1/brands").json()[0]["positioning"] == changed.json()["positioning"]
    assert a.get("/v1/metrics/overview").json()["brands"] == 1
    assert a.get("/v1/integrations").json()["external_effects_enabled"] is False
