"use client";

import { FormEvent, useState } from "react";
import { api } from "./api";

type Report = {
  checked_at: number;
  checks: { id: string; ready: boolean; detail: string }[];
  ready_to_begin_core_validation: boolean;
  production_approved: boolean;
  receipt_window_days: number;
  receipts: Record<string, number>;
  records: {
    id: string;
    kind: string;
    outcome: string;
    reference: string;
    note: string;
    current: boolean;
    created_at: number;
  }[];
  records_truncated: boolean;
  evidence_kinds: Record<string, string>;
  note: string;
};

export default function LiveValidation() {
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [workflow, setWorkflow] = useState("acquisition");
  async function load(selected = workflow) {
    setBusy(true);
    setError("");
    try {
      setReport(await api<Report>(`/v1/live-validation?workflow=${selected}`));
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not check validation setup.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form).entries());
    setBusy(true);
    setError("");
    setSaved("");
    try {
      await api("/v1/live-validation/evidence", values);
      setSaved(
        "Owner-reported evidence saved. It does not approve production or enable providers.",
      );
      form.reset();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save evidence.");
    } finally {
      setBusy(false);
    }
  }
  function download() {
    if (!report) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "ai-mos-validation-report.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <details
      className="operation-card"
      onToggle={(e) => {
        if (e.currentTarget.open && !report && !busy) void load();
      }}
    >
      <summary>Live validation center</summary>
      <p>
        Prepare a small controlled pilot, then use the existing reviewed
        workflows for real tests. These checks never send messages, create
        bookings or charge providers.
      </p>
      <label>
        Workflow to validate
        <select
          value={workflow}
          disabled={busy}
          onChange={(e) => {
            setWorkflow(e.target.value);
            void load(e.target.value);
          }}
        >
          <option value="acquisition">Find prospects and prepare email</option>
          <option value="outreach">Email with imported contacts</option>
        </select>
      </label>
      <div className="action-row">
        <button disabled={busy} onClick={() => void load()}>
          {busy ? "Checking…" : "Refresh validation checks"}
        </button>
        <button disabled={!report} onClick={download}>
          Download validation report
        </button>
      </div>
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      {saved && (
        <p role="status" className="message">
          {saved}
        </p>
      )}
      {report && (
        <>
          <h3>
            {report.ready_to_begin_core_validation
              ? "Prepared to begin core live drills"
              : "Setup still needed before core live drills"}
          </h3>
          <p className="small muted">
            Production acceptance remains separate. Optional Calendar, payment,
            publishing and ad accounts have their own setup and exact approvals.
          </p>
          <ol>
            {report.checks.map((c) => (
              <li key={c.id}>
                <b>
                  {c.ready ? "Configured" : "Action needed"} ·{" "}
                  {c.id.replaceAll("_", " ")}
                </b>
                <p className="small muted">{c.detail}</p>
              </li>
            ))}
          </ol>
          <details className="evidence">
            <summary>Connected receipt observations</summary>
            <p>
              Last {report.receipt_window_days} days. Sandbox rows are excluded.
              These counts do not prove delivery, writing quality or
              current-account acceptance.
            </p>
            <dl>
              {Object.entries(report.receipts).map(([name, count]) => (
                <div key={name}>
                  <dt>{name.replaceAll("_", " ")}</dt>
                  <dd>{count}</dd>
                </div>
              ))}
            </dl>
          </details>
          <details className="evidence">
            <summary>Record an external drill result</summary>
            <p>
              Record what you actually checked. Do not paste passwords, API keys
              or private message contents. A reference can be a review ticket,
              report filename or provider event ID. An owner report is not
              automated proof.
            </p>
            <form onSubmit={save}>
              <fieldset disabled={busy}>
                <div className="form-grid">
                  <label>
                    Validation drill
                    <select name="kind" required>
                      {Object.entries(report.evidence_kinds).map(
                        ([id, name]) => (
                          <option key={id} value={id}>
                            {name}
                          </option>
                        ),
                      )}
                    </select>
                  </label>
                  <label>
                    Observed result
                    <select name="outcome">
                      <option value="failed">Failed / needs work</option>
                      <option value="passed">Passed my review</option>
                    </select>
                  </label>
                  <label>
                    Evidence reference
                    <input
                      name="reference"
                      required
                      minLength={3}
                      maxLength={300}
                    />
                  </label>
                  <label>
                    What was checked and what happened?
                    <textarea
                      name="note"
                      required
                      minLength={10}
                      maxLength={2000}
                    />
                  </label>
                </div>
                <button className="primary">
                  Save owner-reported evidence
                </button>
              </fieldset>
            </form>
          </details>
          <details className="evidence">
            <summary>Recorded drill history ({report.records.length})</summary>
            {report.records.length ? (
              report.records.map((r) => (
                <article key={r.id}>
                  <h4>
                    {report.evidence_kinds[r.kind] || r.kind} · {r.outcome}
                  </h4>
                  <p className="small muted">
                    Owner-reported ·{" "}
                    {new Date(r.created_at * 1000).toLocaleString()} ·{" "}
                    {r.current
                      ? "Current setup"
                      : "Stale: repeat after setup changes or 30 days"}
                  </p>
                  <p className="preserve">{r.reference}</p>
                  <p className="preserve">{r.note}</p>
                </article>
              ))
            ) : (
              <p>No external drill results recorded yet.</p>
            )}
            {report.records_truncated && (
              <p>
                Showing the latest 100 entries. Workspace export includes
                additional history up to its stated limit.
              </p>
            )}
          </details>
          <p className="small muted">{report.note}</p>
        </>
      )}
    </details>
  );
}
