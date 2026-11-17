from test_foundation import signup
from test_growth import brand_and_lead


def test_workspace_snapshot_has_one_tenant_and_no_credentials(clients):
    a, b = clients
    first = signup(a)
    second = signup(b, "second@example.test")
    brand, _ = brand_and_lead(a)
    response = a.get("/v1/workspace")
    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot["identity"]["organization"]["id"] == first["organization"]["id"]
    assert [item["id"] for item in snapshot["brands"]] == [brand["id"]]
    assert snapshot["metrics"]["brands"] == 1
    other = b.get("/v1/workspace").json()
    assert other["identity"]["organization"]["id"] == second["organization"]["id"]
    assert other["brands"] == [] and other["metrics"]["brands"] == 0
    for name in ["password_hash", "token_ciphertext", "totp_secret", "recovery_hash"]:
        assert name not in response.text


def test_stale_workspace_or_user_context_is_rejected_before_writes(clients):
    a, b = clients
    first = signup(a)
    second = signup(b, "second@example.test")
    org_id, user_id = first["organization"]["id"], first["user"]["id"]
    assert (
        a.get("/v1/workspace", headers={"X-Workspace-ID": org_id, "X-User-ID": user_id}).status_code
        == 200
    )
    stale = {"X-Workspace-ID": second["organization"]["id"], "X-User-ID": user_id}
    assert a.post("/v1/brands", json={"name": "Must not create"}, headers=stale).status_code == 409
    assert a.get("/v1/brands").json() == []
    assert (
        a.get(
            "/v1/data/leads", headers={"X-Workspace-ID": org_id, "X-User-ID": second["user"]["id"]}
        ).status_code
        == 409
    )
