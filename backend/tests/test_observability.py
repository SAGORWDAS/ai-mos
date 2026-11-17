import json
import logging

from test_foundation import signup
from test_growth import brand_and_lead, drain, key, rows


def test_tool_rejections_have_structured_logs_and_durable_audit_without_arguments(clients, caplog):
    a, _ = clients
    signup(a)
    caplog.set_level(logging.INFO, logger="ai_mos.events")
    marker = "private-prompt-marker-never-log"
    assert (
        a.post(
            "/v1/tools/TLS-04/invoke", json={"agent_id": "AGT-05", "args": {"private_note": marker}}
        ).status_code
        == 422
    )
    assert (
        a.post(
            "/v1/tools/UNREGISTERED/invoke",
            json={"agent_id": "AGT-05", "args": {"private_note": marker}},
        ).status_code
        == 403
    )
    assert (
        a.post(
            "/v1/tools/TLS-04/invoke", json={"agent_id": "AGT-05", "args": {}, "unexpected": marker}
        ).status_code
        == 422
    )
    audit = a.get("/v1/audit").json()
    assert any(r["action"] == "tool.refused" for r in audit)
    assert any(r["action"] == "tool.schema_refused" for r in audit)
    logs = [json.loads(r.message) for r in caplog.records if r.name == "ai_mos.events"]
    refusal = next(r for r in logs if r["action"] == "tool.refused")
    assert refusal["tool_id"] == "TLS-04" and refusal["agent_id"] == "AGT-05"
    assert refusal["org_id"] and refusal["trace_id"]
    assert marker not in caplog.text


def test_command_task_events_share_one_workflow_trace(clients, caplog):
    a, _ = clients
    signup(a)
    brand, _ = brand_and_lead(a)
    caplog.set_level(logging.INFO, logger="ai_mos.events")
    response = a.post(
        "/v1/autopilot/start",
        json={
            "brand_id": brand["id"],
            "objective": "Prepare a controlled evidence-backed campaign",
            "idempotency_key": key(),
        },
    )
    assert response.status_code == 202, response.text
    drain(a)
    commands = rows(a, "commands")
    traces = {
        json.loads(r.message)["trace_id"]
        for r in caplog.records
        if r.name == "ai_mos.events" and json.loads(r.message)["action"] == "task.started"
    }
    assert traces == {commands[0]["id"]}


def test_task_failure_logs_exclude_raw_exception_content(clients, monkeypatch, caplog):
    a, _ = clients
    signup(a)
    _, lead = brand_and_lead(a)
    caplog.set_level(logging.INFO, logger="ai_mos.events")
    marker = "private generated customer message must not enter logs"

    async def fail(task):
        raise ValueError(marker)

    monkeypatch.setattr(a.app.state.runtime, "execute", fail)
    assert (
        a.post("/v1/drafts", json={"lead_id": lead["id"], "idempotency_key": key()}).status_code
        == 202
    )
    drain(a)
    assert rows(a, "tasks")[0]["status"] == "failed"
    assert marker not in caplog.text
