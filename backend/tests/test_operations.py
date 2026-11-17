import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_foundation import signup
from test_growth import approve, brand_and_lead, drain, execute, key, make_draft, rows

from app.backup import backup, restore


def test_automatic_workflows_followup_stops_on_reply_and_recurring_revenue(clients, tmp_path):
    client, _ = clients
    signup(client)
    for trigger, action in [
        ("lead.created", "score_lead"),
        ("message.received", "notify_owner"),
        ("payment.succeeded", "onboarding_checklist"),
    ]:
        assert (
            client.post(
                "/v1/workflows",
                json={
                    "name": f"Test {trigger}",
                    "trigger": trigger,
                    "action": action,
                },
            ).status_code
            == 201
        )
    brand, lead = brand_and_lead(client)
    assert rows(client, "leads")[0]["score"] == 100
    assert len(rows(client, "workflow_runs")) == 1
    sequence = client.post(
        "/v1/sequences",
        json={
            "brand_id": brand["id"],
            "name": "Test follow-up",
            "delay_days": 1,
            "max_steps": 2,
        },
    ).json()
    assert (
        client.post(
            f"/v1/sequences/{sequence['id']}/enroll", json={"lead_id": lead["id"]}
        ).status_code
        == 201
    )
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute("UPDATE sequence_enrollments SET next_at=0")
    drain(client)
    assert len(rows(client, "outreach_drafts")) == 1
    assert rows(client, "messages") == []
    client.post(
        "/v1/inbox/simulate",
        json={
            "lead_id": lead["id"],
            "body": "Tell me more",
            "idempotency_key": key(),
        },
    )
    assert rows(client, "sequence_enrollments")[0]["status"] == "stopped"
    assert len(rows(client, "notifications")) == 1
    checkout = client.post(
        "/v1/checkouts",
        json={
            "lead_id": lead["id"],
            "description": "Monthly maintenance test",
            "amount_minor": 1000,
            "currency": "USD",
            "recurring": True,
        },
    ).json()
    assert (
        client.post(
            f"/v1/checkouts/{checkout['id']}/simulate-payment", json={"event_id": key()}
        ).status_code
        == 200
    )
    assert len(rows(client, "subscriptions")) == 1
    assert len(rows(client, "workflow_runs")) == 3


def test_bulk_campaign_rolls_back_every_message_on_suppression_and_daily_cap(clients):
    client, _ = clients
    signup(client)
    brand, lead = brand_and_lead(client)
    make_draft(client, lead)
    lead2 = client.post(
        "/v1/leads/import",
        json={
            "leads": [
                {
                    "brand_id": brand["id"],
                    "name": "Second test",
                    "email": "second@example.test",
                    "source": "Synthetic QA",
                    "lawful_basis": "consent",
                    "basis_evidence": "Test only",
                }
            ]
        },
    ).json()["created"][0]
    make_draft(client, lead2)
    campaign = client.post(
        "/v1/campaigns",
        json={
            "brand_id": brand["id"],
            "name": "Test reviewed batch",
            "lead_ids": [lead["id"], lead2["id"]],
        },
    ).json()
    approval = client.post(f"/v1/campaigns/{campaign['id']}/request-approval").json()
    client.post(f"/v1/approvals/{approval['id']}/decision", json={"decision": "approved"})
    client.put("/v1/budgets/current", json={"limit_micros": 2000000, "daily_send_cap": 1})
    assert execute(client, approval).status_code == 429
    assert rows(client, "messages") == []
    client.put("/v1/budgets/current", json={"limit_micros": 2000000, "daily_send_cap": 20})
    client.post("/v1/suppressions", json={"email": lead2["email"], "reason": "manual"})
    assert execute(client, approval).status_code == 403
    assert rows(client, "messages") == []
    assert rows(client, "approvals")[0]["status"] == "approved"


def test_budget_reservations_race_without_overspend(clients):
    client, _ = clients
    client.app.state.runtime.settings.model_cache_seconds = 0
    signup(client)
    _, lead = brand_and_lead(client)
    client.app.state.runtime.settings.sandbox_model_cost_micros = 10
    client.put("/v1/budgets/current", json={"limit_micros": 10, "daily_send_cap": 20})
    for _ in range(2):
        client.post("/v1/drafts", json={"lead_id": lead["id"], "idempotency_key": key()})
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: client.portal.call(client.app.state.runtime.tick), range(2)))
    drain(client)
    budget = client.get("/v1/budgets/current").json()
    assert budget["spent_micros"] == 10
    assert budget["reserved_micros"] == 0
    assert len(rows(client, "outreach_drafts")) == 1


def test_unrelated_approval_survives_draft_revision_and_expenses_have_evidence(clients):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    first = make_draft(client, lead)
    approval = approve(client, first)
    second = make_draft(client, lead)
    client.put(
        f"/v1/drafts/{second['id']}",
        json={
            "expected_version": second["version"],
            "subject": "Following up from Test agency",
            "body": second["body"],
        },
    )
    assert execute(client, approval).status_code == 200
    assert (
        client.post(
            "/v1/expenses",
            json={
                "category": "human_review",
                "amount_micros": 10000,
                "evidence": "Synthetic review cost for test",
            },
        ).status_code
        == 201
    )
    assert client.get("/v1/analytics").json()["recorded_total_cost_micros"] == 10000


def test_AC13_verified_backup_and_restore_preserves_audit_and_refuses_overwrite(clients, tmp_path):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    make_draft(client, lead)
    target = tmp_path / "backup.db"
    manifest = backup(tmp_path / "test.db", target)
    restored = tmp_path / "restored.db"
    assert restore(target, restored) == manifest["counts"]
    assert manifest["counts"]["audit_logs"] > 0
    with sqlite3.connect(tmp_path / "test.db") as original, sqlite3.connect(restored) as result:
        assert (
            original.execute("SELECT id,action FROM audit_logs ORDER BY id").fetchall()
            == result.execute("SELECT id,action FROM audit_logs ORDER BY id").fetchall()
        )
    with pytest.raises(FileExistsError):
        restore(target, restored)
    with target.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ValueError, match="checksum"):
        restore(target, tmp_path / "bad.db")


def test_uncited_body_assertion_is_rejected_and_exports_exclude_credentials(clients):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    draft = make_draft(client, lead)
    result = client.put(
        f"/v1/drafts/{draft['id']}",
        json={
            "expected_version": draft["version"],
            "subject": draft["subject"],
            "body": draft["body"] + " We have ten thousand clients.",
        },
    )
    assert result.status_code == 422
    export = client.get("/v1/exports/workspace")
    assert export.status_code == 200
    assert "sessions" not in export.json()["data"]
    assert "password_hash" not in export.text
    assert "token_hash" not in export.text
    assert len(export.json()["data"]["leads"]) == 1


def test_stale_draft_revision_cannot_overwrite_new_copy(clients):
    client, _ = clients
    signup(client)
    _, lead = brand_and_lead(client)
    draft = make_draft(client, lead)
    payload = {
        "expected_version": draft["version"],
        "subject": draft["subject"],
        "body": draft["body"],
    }
    assert client.put(f"/v1/drafts/{draft['id']}", json=payload).status_code == 200
    assert client.put(f"/v1/drafts/{draft['id']}", json=payload).status_code == 409
    assert rows(client, "outreach_drafts")[0]["version"] == draft["version"] + 1


def test_plain_language_optouts_are_recognized_before_drafting():
    from app.growth.knowledge import classify

    for phrase in [
        "Take me off this list",
        "Stop",
        "Don't email me",
        "No more messages please",
        "Leave me alone",
    ]:
        assert classify(phrase)["label"] == "unsubscribe"
