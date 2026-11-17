from test_foundation import signup
from test_growth import approve, brand_and_lead, drain, key, make_draft, rows


def test_validated_cache_cost_lineage_and_clear(clients):
    a, b = clients
    signup(a)
    signup(b, "second@example.test")
    _, lead = brand_and_lead(a)
    a.app.state.runtime.settings.sandbox_model_cost_micros = 10
    make_draft(a, lead)
    make_draft(a, lead)
    usage = rows(a, "model_usage")
    hit = next(item for item in usage if item["status"] == "cache_hit")
    original = next(item for item in usage if item["status"] == "succeeded")
    assert hit["cost_micros"] == 0
    assert hit["cache_source_id"] == original["id"]
    assert a.get("/v1/budgets/current").json()["spent_micros"] == 10
    assert a.get("/v1/model-cache").json()["cache_hits"] == 1
    assert b.get("/v1/model-cache").json()["validated_responses"] == 0
    assert a.post("/v1/model-cache/clear").status_code == 200
    make_draft(a, lead)
    assert a.get("/v1/budgets/current").json()["spent_micros"] == 20


def test_contact_provenance_stale_edit_and_approval_invalidation(clients):
    a, b = clients
    signup(a)
    signup(b, "second@example.test")
    _, lead = brand_and_lead(a)
    draft = make_draft(a, lead)
    approval = approve(a, draft)
    path = f"/v1/leads/{lead['id']}"
    body = {
        "expected_version": 1,
        "name": "Retail team",
        "company": "Sample retail",
        "domain": "example.test",
        "lawful_basis": "consent",
        "basis_evidence": "Synthetic first-party request for contact",
        "personalisation": "Your shop lists a seasonal collection.",
        "personalisation_evidence": "Synthetic fixture; human-reviewed observation",
    }
    assert b.put(path, json=body).status_code == 404
    assert a.put(path, json={**body, "personalisation_evidence": ""}).status_code == 422
    assert a.put(path, json=body).status_code == 200
    assert a.put(path, json=body).status_code == 409
    assert (
        next(x for x in rows(a, "approvals") if x["id"] == approval["id"])["status"]
        == "invalidated"
    )
    previous = {x["id"] for x in rows(a, "outreach_drafts")}
    make_draft(a, lead)
    new = next((x for x in rows(a, "outreach_drafts") if x["id"] not in previous), None)
    assert new, [(x["status"], x.get("error"), x.get("output")) for x in rows(a, "tasks")]
    assert body["personalisation"] in new["body"]
    assert body["personalisation_evidence"] not in new["body"]
    assert not any(x["status"] == "cache_hit" for x in rows(a, "model_usage"))


def test_public_enrichment_observed_addresses_only(clients, monkeypatch):
    from app.growth import discovery

    a, _ = clients
    signup(a)
    brand, _ = brand_and_lead(a)

    async def fake_fetch(url):
        return "Contact hello@retailer.example or outsider@elsewhere.example", url

    monkeypatch.setattr(discovery, "fetch_text", fake_fetch)
    response = a.post(
        "/v1/prospects/enrich",
        json={
            "brand_id": brand["id"],
            "url": "https://retailer.example/contact",
            "company": "Retailer",
            "idempotency_key": key(),
        },
    )
    assert response.status_code == 202, response.text
    drain(a)
    observed = next(x for x in rows(a, "leads") if x["email"] == "hello@retailer.example")
    assert observed["lawful_basis"] == "not_established"
    assert not any(x["email"] == "outsider@elsewhere.example" for x in rows(a, "leads"))
    assert (
        a.post("/v1/drafts", json={"lead_id": observed["id"], "idempotency_key": key()}).status_code
        == 202
    )
    drain(a)
    draft = next(x for x in rows(a, "outreach_drafts") if x["lead_id"] == observed["id"])
    approval = approve(a, draft)
    response = a.post(
        "/v1/effects/execute", json={"approval_id": approval["id"], "idempotency_key": key()}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "contactability_not_established"
