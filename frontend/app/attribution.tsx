"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";
import { displayMoney } from "./money";

type Entity = { id: string; name: string };
type Revenue = {
  campaign_id: string | null;
  currency: string;
  simulated: boolean;
  amount_minor: number;
};
type Report = {
  model: string;
  touches: number;
  note: string;
  net_revenue: Revenue[];
  unresolved_refunds: number;
  ad_spend: {
    campaign_id: string;
    spend: string;
    currency: string;
    clicks: number;
    impressions: number;
  }[];
  outcomes: {
    campaign_id: string | null;
    simulated: boolean;
    contact_credit: number;
    qualified_credit: number;
    meeting_credit: number;
    customer_credit: number;
    recorded_cpl_micros: number | null;
    recorded_cac_micros: number | null;
  }[];
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
    model_micros: number;
    expense_micros: number;
    held_micros: number;
  }[];
};
export default function Attribution({
  writable,
  revision = 0,
}: {
  writable: boolean;
  revision?: number;
}) {
  const [campaigns, setCampaigns] = useState<Entity[]>([]);
  const [leads, setLeads] = useState<Entity[]>([]);
  const [pages, setPages] = useState<
    { id: string; title: string; status: string }[]
  >([]);
  const [trackingLink, setTrackingLink] = useState("");
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
      api<{ items: { id: string; title: string; status: string }[] }>(
        "/v1/data/content_items",
      ),
    ])
      .then(([c, l, r, p]) => {
        if (active) {
          setCampaigns(c.items);
          setLeads(l.items);
          setReport(r);
          setPages(p.items.filter((item) => item.status === "published_local"));
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [model, revision]);
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
              <th>Attributed net revenue</th>
            </tr>
          </thead>
          <tbody>
            {report?.net_revenue.map((r, i) => (
              <tr key={i}>
                <td>{name(r.campaign_id)}</td>
                <td>{r.simulated ? "Sandbox" : "Live"}</td>
                <td>{r.currency}</td>
                <td>{displayMoney(r.amount_minor, r.currency)}</td>
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
          known cost · ${(c.amount_micros / 1000000).toFixed(6)} USD
          {` (models $${(c.model_micros / 1000000).toFixed(6)}, expenses $${(c.expense_micros / 1000000).toFixed(6)}, held $${(c.held_micros / 1000000).toFixed(6)})`}
        </p>
      ))}
      {!!report?.unresolved_refunds && (
        <p role="status">
          {report.unresolved_refunds} legacy refund receipts need review; their
          value is shown as unassigned.
        </p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Campaign / mode</th>
              <th>Contact credit</th>
              <th>Qualified</th>
              <th>Meetings</th>
              <th>Customers</th>
              <th>Recorded CPL / CAC (USD)</th>
            </tr>
          </thead>
          <tbody>
            {report?.outcomes.map((r, i) => (
              <tr key={i}>
                <td>
                  {name(r.campaign_id)} · {r.simulated ? "Sandbox" : "Live"}
                </td>
                <td>{r.contact_credit.toFixed(2)}</td>
                <td>{r.qualified_credit.toFixed(2)}</td>
                <td>{r.meeting_credit.toFixed(2)}</td>
                <td>{r.customer_credit.toFixed(2)}</td>
                <td>
                  {r.recorded_cpl_micros === null
                    ? "—"
                    : `$${(r.recorded_cpl_micros / 1000000).toFixed(2)}`}{" "}
                  /{" "}
                  {r.recorded_cac_micros === null
                    ? "—"
                    : `$${(r.recorded_cac_micros / 1000000).toFixed(2)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted">{report?.note}</p>
      {report?.ad_spend.map((row, i) => (
        <p key={i}>
          {name(row.campaign_id)} · Provider ad spend: {row.spend}{" "}
          {row.currency} · {row.clicks} clicks / {row.impressions} impressions
          {row.currency !== "USD"
            ? " (not converted into USD cost ratios)"
            : ""}
        </p>
      ))}
      <details className="form-disclosure">
        <summary>Create a campaign enquiry link</summary>
        <p>
          Use a published owned page. Enquiries keep the signed campaign source;
          the link does not set tracking cookies or grant marketing permission.
        </p>
        <form
          className="operation-form"
          onSubmit={async (event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            setBusy(true);
            setError("");
            try {
              const result = await api<{ url: string }>(
                `/v1/campaigns/${data.get("campaign")}/tracking-link`,
                { content_id: data.get("page"), channel: data.get("channel") },
              );
              setTrackingLink(result.url);
            } catch (e) {
              setError(
                e instanceof Error ? e.message : "Could not create link",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
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
              Published page
              <select name="page" required>
                <option value="">Choose a published page</option>
                {pages.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Source
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
            <button>Create 30-day campaign link</button>
          </fieldset>
        </form>
        {trackingLink && (
          <label>
            Campaign link
            <input
              readOnly
              value={trackingLink}
              onClick={(e) => e.currentTarget.select()}
            />
          </label>
        )}
      </details>
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
