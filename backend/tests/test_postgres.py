"""Native integration tests. Set AI_MOS_TEST_ADMIN_URL for a disposable PostgreSQL instance."""

import asyncio
import json
import os
import time
from uuid import uuid4

import asyncpg
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from test_foundation import signup
from test_growth import brand_and_lead, drain, make_draft, rows
from test_growth import test_complete_sandbox_growth_to_revenue as complete_workflow

from app.config import Settings
from app.growth.effects import signature
from app.main import create_app
from app.migrate import upgrade

ADMIN = os.environ.get("AI_MOS_TEST_ADMIN_URL")
pytestmark = pytest.mark.skipif(not ADMIN, reason="Native PostgreSQL integration URL not supplied")


def test_native_campaign_attribution(pg_clients):
    from test_attribution import test_attribution_tenant_scope_replay_and_paid_outcome

    test_attribution_tenant_scope_replay_and_paid_outcome(pg_clients)


def test_native_one_brief_setup(pg_clients):
    from test_quick_setup import test_one_brief_setup_is_atomic_scoped_and_replay_safe

    test_one_brief_setup_is_atomic_scoped_and_replay_safe(pg_clients)


def test_native_publishing_approval_scope(pg_clients):
    from test_publishing import test_channel_sandbox_is_scoped_approved_and_idempotent

    test_channel_sandbox_is_scoped_approved_and_idempotent(pg_clients)


def test_native_automatic_reply_policy(pg_clients, monkeypatch):
    from test_automatic_replies import (
        test_owner_opt_in_prepares_safe_reply_once_and_escalates_ambiguous,
    )

    test_owner_opt_in_prepares_safe_reply_once_and_escalates_ambiguous(pg_clients, monkeypatch)


@pytest.fixture
def pg_clients():
    name = "ai_mos_test_" + uuid4().hex
    password = uuid4().hex
    api_role, worker_role = "api_" + uuid4().hex, "worker_" + uuid4().hex

    async def setup():
        conn = await asyncpg.connect(ADMIN)
        await conn.execute(f'CREATE DATABASE "{name}"')
        await conn.close()
        database_url = ADMIN.rsplit("/", 1)[0] + "/" + name
        await upgrade(database_url)
        conn = await asyncpg.connect(database_url)
        await conn.execute(f"CREATE ROLE {api_role} LOGIN PASSWORD '{password}' IN ROLE ai_mos_app")
        await conn.execute(
            f"CREATE ROLE {worker_role} LOGIN PASSWORD '{password}' IN ROLE ai_mos_worker"
        )
        await conn.close()
        from urllib.parse import urlsplit

        parsed = urlsplit(ADMIN)
        base = f"@{parsed.hostname}:{parsed.port or 5432}/{name}"
        return (
            f"postgresql+asyncpg://{api_role}:{password}{base}",
            f"postgresql+asyncpg://{worker_role}:{password}{base}",
        )

    api_url, worker_url = asyncio.run(setup())
    app = create_app(
        Settings(
            database_url=api_url,
            worker_database_url=worker_url,
            worker_enabled=False,
            token_encryption_key=Fernet.generate_key().decode(),
        )
    )
    try:
        with TestClient(app) as a:
            b = TestClient(app)
            b.portal = a.portal
            try:
                yield a, b
            finally:
                b.close()
    finally:

        async def cleanup():
            conn = await asyncpg.connect(ADMIN)
            await conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
            await conn.execute(f'DROP ROLE "{api_role}"')
            await conn.execute(f'DROP ROLE "{worker_role}"')
            await conn.close()

        asyncio.run(cleanup())


def test_native_postgres_auth_roles_queue_and_model_ledger(pg_clients):
    a, b = pg_clients
    signup(a)
    signup(b, "other@example.test")
    brand, lead = brand_and_lead(a)
    assert rows(b, "leads") == []
    assert b.get(f"/v1/brands/{brand['id']}").status_code == 404
    draft = make_draft(a, lead)
    assert draft["claims"]
    assert len(rows(a, "model_usage")) == 1
    result = a.post(
        "/v1/commands",
        json={
            "brand_id": brand["id"],
            "objective": "Verify native database task ordering",
            "idempotency_key": str(uuid4()),
        },
    )
    assert result.status_code == 202
    drain(a)
    plan = rows(a, "plans")[0]
    assert a.post(f"/v1/plans/{plan['id']}/approve").status_code == 200
    drain(a)
    assert rows(a, "plans")[0]["status"] == "completed"


def test_native_postgres_invitation_and_workspace_switch(pg_clients):
    a, b = pg_clients
    owner = signup(a)
    other = signup(b, "invited@example.test")
    invite = a.post("/v1/org/invitations", json={"email": "invited@example.test", "role": "viewer"})
    assert invite.status_code == 201, invite.text
    accepted = b.post("/v1/org/invitations/accept", json={"token": invite.json()["token"]})
    assert accepted.status_code == 200, accepted.text
    assert b.get("/v1/auth/me").json()["organization"]["id"] == owner["organization"]["id"]
    assert b.post("/v1/brands", json={"name": "Denied"}).status_code == 403
    assert b.post(f"/v1/orgs/{other['organization']['id']}/switch").status_code == 200
    assert b.get("/v1/auth/me").json()["role"] == "owner"


def test_native_postgres_complete_growth_to_revenue(pg_clients):
    complete_workflow(pg_clients)


def test_native_postgres_recovery_and_cache(pg_clients):
    from test_cache_contacts import test_validated_cache_cost_lineage_and_clear

    test_validated_cache_cost_lineage_and_clear(pg_clients)


def test_native_postgres_autopilot(pg_clients):
    from test_autopilot import test_autopilot_runs_internal_work_and_prepares_reviews_once

    test_autopilot_runs_internal_work_and_prepares_reviews_once(pg_clients)


def test_native_postgres_brand_edit_publication_review(pg_clients):
    from test_public_seo import (
        test_brand_edit_withdraws_publication_and_invalidates_related_approvals,
    )

    test_brand_edit_withdraws_publication_and_invalidates_related_approvals(pg_clients)


def test_native_postgres_workspace_snapshot(pg_clients):
    from test_workspace_snapshot import test_workspace_snapshot_has_one_tenant_and_no_credentials

    test_workspace_snapshot_has_one_tenant_and_no_credentials(pg_clients)


def test_native_postgres_account_recovery(pg_clients):
    from test_accounts import test_private_recovery_consumed_once_and_all_sessions_revoked

    test_private_recovery_consumed_once_and_all_sessions_revoked(pg_clients)


def test_native_postgres_billing_lifecycle(pg_clients):
    from test_billing_costs import test_billing_renewal_failure_cancellation_refunds_and_replay

    test_billing_renewal_failure_cancellation_refunds_and_replay(pg_clients)


def test_native_postgres_embeddings(pg_clients):
    from test_embeddings_throttle import test_embedding_workflow_sandbox_cache_and_tenant_scope

    test_embedding_workflow_sandbox_cache_and_tenant_scope(pg_clients)


def test_native_postgres_scheduled_inbox(pg_clients, monkeypatch):
    from test_oauth_schedule import test_scheduled_html_inbox_requires_opt_in_and_honours_stop

    test_scheduled_html_inbox_requires_opt_in_and_honours_stop(pg_clients, monkeypatch)


def test_native_postgres_bulk_events(pg_clients, monkeypatch):
    from test_bulk_discovery import test_live_bulk_dispatch_and_verified_delivery_bounce_webhooks

    test_live_bulk_dispatch_and_verified_delivery_bounce_webhooks(pg_clients, monkeypatch)


def test_native_postgres_backup_restore(pg_clients, tmp_path):
    from app.pgbackup import backup, restore

    a, _ = pg_clients
    signup(a)
    _, lead = brand_and_lead(a)
    make_draft(a, lead)
    source_name = a.app.state.runtime.settings.database_url.rsplit("/", 1)[1]
    source_url = ADMIN.rsplit("/", 1)[0] + "/" + source_name
    target_name = "ai_mos_restore_" + uuid4().hex
    target_url = ADMIN.rsplit("/", 1)[0] + "/" + target_name

    async def exercise():
        admin = await asyncpg.connect(ADMIN)
        await admin.execute(f'CREATE DATABASE "{target_name}"')
        try:
            path = tmp_path / "verified.dump"
            tools = os.environ.get("AI_MOS_TEST_PG_BIN")
            manifest = await backup(source_url, path, tools)
            assert manifest["counts"]["outreach_drafts"] == 1
            result = await restore(path, target_url, tools)
            assert result["status"] == "verified"
            connection = await asyncpg.connect(target_url)
            try:
                owner = await connection.fetchval(
                    "SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE proname='claim_next_task'"
                )
                assert owner == "ai_mos_queue"
                await connection.execute("SET ROLE ai_mos_app")
                assert await connection.fetchval("SELECT count(*) FROM outreach_drafts") == 0
            finally:
                await connection.close()
        finally:
            await admin.execute(f'DROP DATABASE "{target_name}" WITH (FORCE)')
            await admin.close()

    asyncio.run(exercise())


def test_native_postgres_live_effect_queue(pg_clients, monkeypatch):
    from test_connections import test_live_dispatch_waits_for_receipt_and_sandbox_stays_explicit

    test_live_dispatch_waits_for_receipt_and_sandbox_stays_explicit(pg_clients, monkeypatch)


def test_native_postgres_provider_receipt(pg_clients, monkeypatch):
    from test_connections import (
        test_connected_checkout_only_signed_matching_receipt_converts_customer,
    )

    test_connected_checkout_only_signed_matching_receipt_converts_customer(pg_clients, monkeypatch)


def test_native_postgres_signed_webhook_without_user_session(pg_clients):
    a, b = pg_clients
    signup(a)
    _, lead = brand_and_lead(a)
    checkout = a.post(
        "/v1/checkouts",
        json={
            "lead_id": lead["id"],
            "description": "Callback test",
            "amount_minor": 12345,
            "currency": "USD",
        },
    ).json()
    body = json.dumps(
        {
            "event_id": str(uuid4()),
            "checkout_ref": checkout["provider_ref"],
            "type": "payment.succeeded",
            "amount_minor": 12345,
            "currency": "USD",
        }
    ).encode()
    stamp = int(time.time())
    headers = {
        "x-webhook-timestamp": str(stamp),
        "x-webhook-signature": signature(
            a.app.state.runtime.settings.payment_webhook_secret, stamp, body
        ),
    }
    first = b.post("/v1/webhooks/payments", content=body, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "processed"
    assert (
        b.post("/v1/webhooks/payments", content=body, headers=headers).json()["status"]
        == "duplicate"
    )
    assert len(rows(a, "payments")) == 1
