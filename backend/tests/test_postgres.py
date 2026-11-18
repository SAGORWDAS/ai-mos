"""Native integration tests. Set AI_MOS_TEST_ADMIN_URL for a disposable PostgreSQL instance."""

import asyncio
import json
import os
import time
from uuid import uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient
from test_foundation import signup
from test_growth import brand_and_lead, drain, make_draft, rows
from test_growth import test_complete_sandbox_growth_to_revenue as complete_workflow

from app.growth.effects import signature
from app.main import create_app

ADMIN = os.environ.get("AI_MOS_TEST_ADMIN_URL")
pytestmark = pytest.mark.skipif(not ADMIN, reason="Native PostgreSQL integration URL not supplied")


def test_native_validation_environment_startup_and_secure_signup(pg_clients):
    from test_live_validation import CODE, validation_settings

    from app.deployment import database_checks

    a, _ = pg_clients
    api_engine = a.app.state.factory.kw["bind"]
    worker_engine = a.app.state.runtime.factory.kw["bind"]

    async def inspect():
        assert all(c["ready"] for c in await database_checks(api_engine))
        assert all(c["ready"] for c in await database_checks(worker_engine, worker=True))
        assert not all(c["ready"] for c in await database_checks(api_engine, worker=True))

    a.portal.call(inspect)
    app = create_app(validation_settings(database_url=a.app.state.runtime.settings.database_url))
    with TestClient(app, base_url="https://pilot.example.com") as pilot:
        assert pilot.get("/healthz").json()["mode"] == "validation"
        body = {
            "name": "Pilot owner",
            "organization_name": "Controlled QA",
            "email": "pilot-native@example.test",
            "password": "Secure controlled pilot QA 123",
        }
        assert pilot.post("/v1/auth/signup", json=body).status_code == 403
        created = pilot.post("/v1/auth/signup", json={**body, "access_code": CODE})
        assert created.status_code == 201, created.text
        cookie = created.headers["set-cookie"]
        assert "Secure" in cookie and "HttpOnly" in cookie
        report = pilot.get("/v1/live-validation")
        assert report.status_code == 200, report.text
        assert report.json()["production_approved"] is False
        assert report.json()["ready_to_begin_core_validation"] is False
        assert all(
            c["ready"]
            for c in report.json()["checks"]
            if c["id"]
            in {"validation_environment", "runtime_role", "schema", "tenant_rls", "grants"}
        )


def test_native_validation_startup_rejects_missing_forced_rls(pg_clients):
    from sqlalchemy.engine import make_url
    from test_live_validation import validation_settings

    a, _ = pg_clients
    url = a.app.state.runtime.settings.database_url
    admin_url = ADMIN.rsplit("/", 1)[0] + "/" + make_url(url).database

    async def alter(force):
        conn = await asyncpg.connect(admin_url)
        try:
            await conn.execute("ALTER TABLE validation_records " + force + " ROW LEVEL SECURITY")
        finally:
            await conn.close()

    a.portal.call(alter, "NO FORCE")
    try:
        app = create_app(validation_settings(database_url=url))
        with pytest.raises(RuntimeError, match="tenant_rls"):
            with TestClient(app):
                pass
    finally:
        a.portal.call(alter, "FORCE")


@pytest.mark.parametrize(
    "scenario",
    [
        "test_validation_checks_and_sandbox_receipts_do_not_claim_live_success",
        "test_evidence_stales_on_setup_change_and_owner_checks_apply_while_stopped",
    ],
)
def test_native_validation_evidence_isolation(pg_clients, scenario):
    import test_live_validation

    getattr(test_live_validation, scenario)(pg_clients)


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


def test_native_standing_reply_caps(pg_clients):
    from test_reply_policy import test_explicit_template_standing_policy_caps_safe_sandbox_replies

    test_explicit_template_standing_policy_caps_safe_sandbox_replies(pg_clients)


def test_native_standing_reply_contactability(pg_clients):
    from test_reply_policy import (
        test_contactability_guard_holds_automatic_reply_without_failing_task,
    )

    test_contactability_guard_holds_automatic_reply_without_failing_task(pg_clients)


def test_native_image_asset_scope(pg_clients):
    from test_creative_ads import (
        test_private_raster_generation_is_costed_scoped_and_not_in_task_lists,
    )

    test_private_raster_generation_is_costed_scoped_and_not_in_task_lists(pg_clients)


def test_native_standing_reply_revocation(pg_clients, monkeypatch):
    from test_reply_policy import test_disabling_standing_policy_blocks_queued_live_dispatch

    test_disabling_standing_policy_blocks_queued_live_dispatch(pg_clients, monkeypatch)


def test_native_usage_breakdown(pg_clients):
    from test_reply_policy import test_usage_day_agent_type_filters_are_scoped

    test_usage_day_agent_type_filters_are_scoped(pg_clients)


@pytest.mark.parametrize("fail_partial", [False, True])
def test_native_meta_receipts_and_cap(pg_clients, monkeypatch, fail_partial):
    from test_creative_ads import test_meta_full_contract_cap_approval_partial_receipts_and_replay

    test_meta_full_contract_cap_approval_partial_receipts_and_replay(
        pg_clients, monkeypatch, fail_partial
    )


def test_native_measurement_net_and_cost_lineage(pg_clients):
    from test_measurement_tracking import (
        test_model_costs_customer_credit_and_refund_net_preserve_lineage,
    )

    test_model_costs_customer_credit_and_refund_net_preserve_lineage(pg_clients)


def test_native_signed_campaign_enquiry(pg_clients):
    from test_measurement_tracking import test_signed_enquiry_source_is_scoped_and_replay_safe

    test_signed_enquiry_source_is_scoped_and_replay_safe(pg_clients)


def test_native_tenfold_worker_burst(pg_clients, monkeypatch):
    from test_burst_acceptance import test_tenfold_draft_burst_under_four_workers_preserves_jobs

    test_tenfold_draft_burst_under_four_workers_preserves_jobs(pg_clients, monkeypatch)


def test_native_structured_tool_refusals(pg_clients, caplog):
    from test_observability import (
        test_tool_rejections_have_structured_logs_and_durable_audit_without_arguments,
    )

    test_tool_rejections_have_structured_logs_and_durable_audit_without_arguments(
        pg_clients, caplog
    )


def test_native_command_workflow_trace(pg_clients, caplog):
    from test_observability import test_command_task_events_share_one_workflow_trace

    test_command_task_events_share_one_workflow_trace(pg_clients, caplog)


def test_native_qualification_policy(pg_clients):
    from test_qualification_policy import (
        test_scoring_is_versioned_scoped_and_keeps_pipeline_and_contactability,
    )

    test_scoring_is_versioned_scoped_and_keeps_pipeline_and_contactability(pg_clients)


def test_native_search_price_and_cache(pg_clients, monkeypatch):
    from test_research_cache import test_search_cache_price_accrual_and_account_scope

    test_search_cache_price_accrual_and_account_scope(pg_clients, monkeypatch)


def test_native_observation_cache_age(pg_clients, monkeypatch):
    from test_research_cache import (
        test_contact_cache_preserves_observation_age_scope_and_force_refresh,
    )

    test_contact_cache_preserves_observation_age_scope_and_force_refresh(pg_clients, monkeypatch)


@pytest.mark.parametrize("kind", ["research", "strategy"])
def test_native_research_strategy_grounding(pg_clients, kind):
    from test_planning_evidence import (
        test_uncited_research_and_invented_strategy_are_costed_rejected_and_not_cached,
    )

    test_uncited_research_and_invented_strategy_are_costed_rejected_and_not_cached(pg_clients, kind)


def test_native_automatic_reply_ambiguity(pg_clients):
    from test_reply_policy import (
        test_keyword_confidence_cannot_authorize_ambiguous_or_quoted_reply,
    )

    test_keyword_confidence_cannot_authorize_ambiguous_or_quoted_reply(pg_clients)




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


@pytest.mark.parametrize(
    "scenario",
    [
        "test_verified_catalog_and_usage_price_snapshots_are_scoped_and_historical",
        "test_concurrent_jobs_share_one_expired_catalog_refresh",
        "test_request_allowance_refuses_without_a_charge_and_sends_price_ceiling",
        "test_verified_rates_bound_chat_routing_and_oversized_estimates_are_refused",
        "test_budget_policy_carries_to_next_month_without_carrying_spend",
    ],
)
def test_native_postgres_model_registry(pg_clients, monkeypatch, scenario):
    import test_model_registry

    getattr(test_model_registry, scenario)(pg_clients, monkeypatch)


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
