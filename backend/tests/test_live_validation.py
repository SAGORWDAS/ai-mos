import importlib.util
import secrets
import time
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import update
from test_foundation import signup
from test_growth import brand_and_lead, make_draft, rows

from app.config import Settings
from app.deployment import configuration_checks, enforce_configuration
from app.growth.models import ModelUsage, ValidationRecord
from app.models import Membership
from app.tenancy import tenant_scope

CODE = "Controlled-QA-access-0123456789-ABCDEFGHIJK"


def validation_settings(**overrides):
    values = dict(
        app_env="validation",
        worker_enabled=False,
        database_url=f"postgresql+asyncpg://pilot:{secrets.token_urlsafe(32)}@localhost/pilot",
        secure_cookies=True,
        public_api_url="https://pilot.example.com/api",
        allowed_origins=["https://pilot.example.com"],
        token_encryption_key=Fernet.generate_key().decode(),
        validation_access_code=CODE,
        validation_review_ref="QA-REVIEW-001",
    )
    return Settings(**{**values, **overrides})


@pytest.mark.parametrize(
    "override",
    [
        {"secure_cookies": False},
        {"allow_unverified_models": True},
        {"validation_access_code": "placeholder-code"},
        {"validation_review_ref": ""},
        {"token_encryption_key": "invalid"},
        {"allowed_origins": ["*"]},
        {"public_api_url": "http://pilot.example.com/api"},
        {"database_url": "sqlite+aiosqlite:///example.db"},
        {
            "database_url": "postgresql+asyncpg://pilot:placeholder-password-for-testing@localhost/pilot"
        },
        {"token_encryption_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="},
    ],
)
def test_validation_configuration_fails_closed(override):
    with pytest.raises(RuntimeError, match="validation_configuration_required"):
        enforce_configuration(validation_settings(**override))
    assert all(c["ready"] for c in configuration_checks(validation_settings()))


def test_validation_checks_and_sandbox_receipts_do_not_claim_live_success(clients):
    a, b = clients
    signup(a)
    signup(b, "other-validation@example.test")
    brand, lead = brand_and_lead(a)
    make_draft(a, lead)
    report = a.get("/v1/live-validation").json()
    assert report["production_approved"] is False
    assert report["ready_to_begin_core_validation"] is False
    assert report["receipts"]["model_completions"] == 0
    assert report["records"] == []
    assert {c["id"] for c in report["checks"]} >= {"gmail", "brave", "openrouter", "test_contact"}
    imported = a.get("/v1/live-validation?workflow=outreach").json()
    assert "brave" not in {c["id"] for c in imported["checks"]}
    assert a.get("/v1/live-validation?workflow=arbitrary").status_code == 422
    data = {
        "kind": "seed_delivery",
        "outcome": "failed",
        "reference": "QA-ONLY-001",
        "note": "Synthetic setup check only; no actual inbox placement was tested.",
    }
    saved = a.post("/v1/live-validation/evidence", json=data)
    assert saved.status_code == 201, saved.text
    assert "scope_hash" not in saved.json()
    assert b.get("/v1/live-validation").json()["records"] == []
    assert b.get(f"/v1/data/validation_records/{saved.json()['id']}").status_code == 404
    assert a.get("/v1/live-validation").json()["records"][0]["current"] is True
    # No outcome report may turn on a provider or promote the environment.
    assert a.get("/v1/live-validation").json()["production_approved"] is False

    async def age():
        async with a.app.state.factory() as session:
            await tenant_scope(session, brand["organization_id"])
            await session.execute(
                update(ValidationRecord).values(created_at=time.time() - 31 * 86400)
            )
            await session.commit()

    # PostgreSQL history is append-only; age is verified by controlled clocks instead there.
    if a.app.state.factory.kw["bind"].dialect.name == "sqlite":
        a.portal.call(age)
        assert a.get("/v1/live-validation").json()["records"][0]["current"] is False


def test_evidence_stales_on_setup_change_and_owner_checks_apply_while_stopped(clients):
    a, _ = clients
    identity = signup(a)
    data = {
        "kind": "opt_out",
        "outcome": "passed",
        "reference": "QA-ASSERTION-ONLY",
        "note": "Synthetic owner report used solely to test evidence storage.",
    }
    assert a.post("/v1/live-validation/evidence", json=data).status_code == 201
    brand_and_lead(a)
    assert a.get("/v1/live-validation").json()["records"][0]["current"] is False
    assert a.post("/v1/org/emergency-stop", json={"enabled": True}).status_code == 200
    assert (
        a.post("/v1/live-validation/evidence", json={**data, "outcome": "failed"}).status_code
        == 201
    )
    record_id = rows(a, "validation_records")[0]["id"]

    async def demote():
        async with a.app.state.factory() as session:
            await tenant_scope(session, identity["organization"]["id"])
            await session.execute(
                update(Membership)
                .where(Membership.user_id == identity["user"]["id"])
                .values(role="viewer")
            )
            await session.commit()

    a.portal.call(demote)
    for url in [
        "/v1/live-validation",
        "/v1/data/validation_records",
        f"/v1/data/validation_records/{record_id}",
    ]:
        assert a.get(url).status_code == 403
    assert a.post("/v1/live-validation/evidence", json=data).status_code == 403


def test_pilot_signup_code_and_validation_errors_do_not_expose_secrets(clients):
    a, _ = clients
    a.app.state.runtime.settings.validation_access_code = CODE
    # The create_app closure and runtime share the same Settings object.
    body = {
        "name": "Pilot operator",
        "organization_name": "Pilot QA",
        "email": "pilot@example.test",
        "password": "Controlled password for QA 123",
    }
    assert a.post("/v1/auth/signup", json=body).status_code == 403
    bad = a.post("/v1/auth/signup", json={**body, "access_code": CODE, "name": ""})
    assert bad.status_code == 422
    assert CODE not in bad.text and body["password"] not in bad.text
    assert a.post("/v1/auth/signup", json={**body, "access_code": CODE}).status_code == 201
    assert CODE not in a.get("/v1/live-validation").text


def test_sandbox_briefs_and_demo_contacts_do_not_qualify_for_live_drills(clients):
    a, _ = clients
    signup(a)
    result = a.post(
        "/v1/setup/start",
        json={
            "name": "Fictional QA",
            "offer": "We build websites for shops.",
            "audience": "Independent shops",
            "objective": "Prepare a synthetic QA campaign",
            "sample": True,
            "idempotency_key": "validation-demo-profile",
        },
    )
    assert result.status_code == 202, result.text
    checks = {c["id"]: c["ready"] for c in a.get("/v1/live-validation").json()["checks"]}
    assert not checks["business_brief"] and not checks["test_contact"]
    brand_and_lead(a)
    checks = {c["id"]: c["ready"] for c in a.get("/v1/live-validation").json()["checks"]}
    assert checks["business_brief"] and not checks["test_contact"]


def test_old_unresolved_model_holds_still_block_readiness_and_remain_tenant_scoped(clients):
    a, b = clients
    signup(a)
    signup(b, "hold-other@example.test")
    brand, lead = brand_and_lead(a)
    make_draft(a, lead)

    async def hold():
        async with a.app.state.factory() as session:
            await tenant_scope(session, brand["organization_id"])
            await session.execute(
                update(ModelUsage).values(
                    simulated=False,
                    settled=False,
                    created_at=time.time() - 40 * 86400,
                    status="provider_cost_unknown",
                )
            )
            await session.commit()

    a.portal.call(hold)
    report = a.get("/v1/live-validation").json()
    assert report["receipts"]["unknown_model_charges"] == 0
    assert report["outstanding_holds"]["unknown_model_charges"] == 1
    assert not next(c for c in report["checks"] if c["id"] == "receipt_reconciliation")["ready"]
    assert b.get("/v1/live-validation").json()["outstanding_holds"]["unknown_model_charges"] == 0


def test_private_validation_config_generation_does_not_overwrite_or_accept_injection(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/prepare-validation.py"
    spec = importlib.util.spec_from_file_location("prepare_validation", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / ".env.validation"
    module.prepare("pilot.example.com", "QA-REVIEW-001", path)
    settings = Settings(_env_file=path)
    assert settings.validation_access_code and settings.secure_cookies
    assert settings.public_api_url == "https://pilot.example.com/api"
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        module.prepare("pilot.example.com", "QA-REVIEW-002", path)
    assert path.read_bytes() == before
    for domain, review in [
        ("https://pilot.example.com", "QA-REVIEW-001"),
        ("pilot.example.com", "${PRIVATE_VARIABLE}"),
    ]:
        with pytest.raises(ValueError):
            module.prepare(domain, review, tmp_path / "bad")
