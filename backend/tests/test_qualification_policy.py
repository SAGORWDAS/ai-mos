from test_foundation import signup
from test_growth import approve, brand_and_lead, execute, make_draft


def test_scoring_is_versioned_scoped_and_keeps_pipeline_and_contactability(clients):
    a, b = clients
    signup(a)
    signup(b, "other@example.test")
    brand, _ = brand_and_lead(a)
    lead = a.post(
        "/v1/leads/import",
        json={
            "leads": [
                {
                    "brand_id": brand["id"],
                    "name": "Observed fixture",
                    "email": "observed@example.invalid",
                    "source": "Synthetic observed contact",
                    "source_ref": "https://example.test/contact",
                    "source_confidence": 75,
                    "lawful_basis": "not_established",
                    "basis_evidence": "No contactability determination; fixture only",
                }
            ]
        },
    ).json()["created"][0]
    assert a.put("/v1/qualification-policy", json={"threshold": 18}).status_code == 200
    assert b.get("/v1/qualification-policy").json()["threshold"] == 65
    first = a.post(f"/v1/leads/{lead['id']}/score").json()
    second = a.post(f"/v1/leads/{lead['id']}/score").json()
    assert first["score"] == second["score"] == 18
    assert first["score_features"] == second["score_features"]
    assert first["qualification_threshold"] == 18 and first["status"] == "qualified"
    assert first["score_model"] == "recorded-features-v2"
    assert first["source_ref"] == "https://example.test/contact"
    assert (
        a.put(
            f"/v1/leads/{lead['id']}/stage",
            json={"status": "contacted", "reason": "Synthetic prior pipeline event"},
        ).status_code
        == 200
    )
    assert a.put("/v1/qualification-policy", json={"threshold": 99}).status_code == 200
    scored = a.post(f"/v1/leads/{lead['id']}/score").json()
    assert scored["status"] == "contacted" and scored["qualification_threshold"] == 99
    draft = make_draft(a, lead)
    assert execute(a, approve(a, draft)).status_code == 403
    assert a.put("/v1/agents/AGT-05", json={"enabled": False}).status_code == 200
    assert a.post(f"/v1/leads/{lead['id']}/score").status_code == 409
