from test_foundation import signup


def test_bulk_connection_cannot_activate_without_signed_receipts(clients):
    a, _ = clients
    signup(a)
    assert (
        a.put(
            "/v1/connections/resend",
            json={
                "account_ref": "Synthetic ESP setup",
                "credentials": {"api_key": "unit-esp-key", "sender": "sender@example.test"},
            },
        ).status_code
        == 200
    )
    result = a.post("/v1/connections/resend/verify")
    assert result.status_code == 409
    assert a.post("/v1/connections/resend/activate").status_code == 409
