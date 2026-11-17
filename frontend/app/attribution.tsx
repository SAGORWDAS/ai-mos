"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";

type Entity = { id: string; name: string };
type Report = {
  model: string;
  touches: number;
  note: string;
  revenue: {
    campaign_id: string | null;
    currency: string;
    simulated: boolean;
    payments: number;
    amount_minor: number;
  }[];
  costs: {
    campaign_id: string | null;
    simulated: boolean;
    amount_micros: number;
  }[];
};
export default function Attribution({ writable }: { writable: boolean }) {
  const [campaigns, setCampaigns] = useState<Entity[]>([]);
  const [leads, setLeads] = useState<Entity[]>([]);
  const [model, setModel] = useState("last_touch");
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  async function refresh() {
    setReport(await api<Report>(`/v1/attribution/report?model=${model}`));
  }
  useEffect(() => {
    let active = true;
    Promise.all([
      api<{ items: Entity[] }>("/v1/data/campaigns"),
      api<{ items: Entity[] }>("/v1/data/leads"),
      api<Report>(`/v1/attribution/report?model=${model}`),
    ])
      .then(([c, l, r]) => {
        if (active) {
          setCampaigns(c.items);
          setLeads(l.items);
          setReport(r);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [model]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api("/v1/attribution/touches", {
        campaign_id: f.get("campaign"),
        lead_id: f.get("lead"),
        channel: f.get("channel"),
        evidence: f.get("evidence"),
        occurred_at: new Date(String(f.get("time"))).getTime() / 1000,
        simulated: f.get("mode") === "sandbox",
        idempotency_key: crypto.randomUUID(),
      });
      await refresh();
      setNotice(
        "Touchpoint recorded. Reports use the recorded evidence and payment timestamps.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }
  const name = (id: string | null) =>
    campaigns.find((c) => c.id === id)?.name ||
    (id ? "Campaign outside loaded page" : "Unassigned");
  return (
    <section className="operation-card">
      <h2>Campaign attribution</h2>
      <p>
        Compare first touch, last touch or equal credit across distinct
        campaigns. Test outcomes stay separate from live outcomes; currencies
        are never combined.
      </p>
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="message">
          {notice}
        </p>
      )}
      <label>
        Attribution model
        <select value={model} onChange={(e) => setModel(e.target.value)}>
          <option value="last_touch">Last touch</option>
          <option value="first_touch">First touch</option>
          <option value="linear">Equal credit by campaign</option>
        </select>
      </label>
      <p>
        {report?.touches || 0} recorded touchpoints · 90-day window before each
        payment
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Campaign</th>
              <th>Mode</th>
              <th>Currency</th>
              <th>Attributed gross revenue (minor units)</th>
            </tr>
          </thead>
          <tbody>
            {report?.revenue.map((r, i) => (
              <tr key={i}>
                <td>{name(r.campaign_id)}</td>
                <td>{r.simulated ? "Sandbox" : "Live"}</td>
                <td>{r.currency}</td>
                <td>{r.amount_minor}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!report?.revenue.length && (
        <p className="muted">No succeeded payments to attribute yet.</p>
      )}
      {report?.costs.map((c, i) => (
        <p key={i}>
          {name(c.campaign_id)} · {c.simulated ? "Sandbox" : "Live"} recorded
          expense · ${(c.amount_micros / 1000000).toFixed(6)} USD
        </p>
      ))}
      <p className="small muted">{report?.note}</p>
      <details className="form-disclosure">
        <summary>Record an evidenced touchpoint</summary>
        <p>
          Use an actual receipt or CRM observation for live records. A
          touchpoint is evidence of an interaction, not proof it caused a sale.
        </p>
        <form className="operation-form" onSubmit={save}>
          <fieldset disabled={!writable || busy}>
            <label>
              Campaign
              <select name="campaign" required>
                <option value="">Choose campaign</option>
                {campaigns.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Contact
              <select name="lead" required>
                <option value="">Choose contact</option>
                {leads.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Channel
              <select name="channel">
                {[
                  "email",
                  "website",
                  "social",
                  "paid_ad",
                  "referral",
                  "other",
                ].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <label>
              When did it happen?
              <input type="datetime-local" name="time" required />
            </label>
            <label>
              Mode
              <select name="mode">
                <option value="sandbox">Sandbox test</option>
                <option value="live">Live evidence</option>
              </select>
            </label>
            <label>
              Receipt or source evidence
              <textarea
                name="evidence"
                required
                minLength={10}
                maxLength={1000}
              />
            </label>
            <button type="submit">
              {busy ? "Saving…" : "Record touchpoint"}
            </button>
          </fieldset>
        </form>
      </details>
    </section>
  );
}
