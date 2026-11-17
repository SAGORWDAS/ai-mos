"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";

type Business = { id: string; name: string };
type Contact = {
  id: string;
  name: string;
  brand_id: string;
  lawful_basis: string;
  status: string;
};
export default function Autopilot({
  owner,
  paused,
  refresh,
}: {
  owner: boolean;
  paused: boolean;
  refresh: () => Promise<void>;
}) {
  const [brands, setBrands] = useState<Business[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [brand, setBrand] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  async function load() {
    const [businesses, people] = await Promise.all([
      api<Business[]>("/v1/brands"),
      api<{ items: Contact[] }>("/v1/data/leads"),
    ]);
    setBrands(businesses);
    setContacts(people.items);
  }
  useEffect(() => {
    void load().catch((e) => setError(e.message));
  }, []);
  async function saveBusiness(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    const form = new FormData(event.currentTarget);
    try {
      const item = await api<Business>("/v1/brands", {
        name: form.get("name"),
        website: form.get("website") || "",
        positioning: form.get("offer") || "",
        icp: {
          segments: String(form.get("audience") || "")
            .split("\n")
            .filter(Boolean),
        },
        approved_claims: String(form.get("claims") || "")
          .split("\n")
          .map((v) => v.trim())
          .filter(Boolean),
      });
      setBrand(item.id);
      setSelected([]);
      await load();
      await refresh();
      setNotice(
        "Business saved. You can complete or change its facts in Brand Brain whenever needed.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save business");
    } finally {
      setBusy(false);
    }
  }
  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    const form = new FormData(event.currentTarget);
    try {
      const result = await api<{ status: string; missing_fields?: string[] }>(
        "/v1/autopilot/start",
        {
          brand_id: brand,
          objective: form.get("objective"),
          lead_ids: selected,
          search_query: form.get("search_query") || "",
          connected_research: form.get("connected_research") === "on",
          target: Number(form.get("target")),
          window_days: Number(form.get("window_days")),
          campaign_budget_micros: Math.round(
            Number(form.get("campaign_budget") || 0) * 1000000,
          ),
          idempotency_key: crypto.randomUUID(),
        },
      );
      setNotice(
        result.status === "needs_information"
          ? `This campaign needs: ${result.missing_fields?.join(", ")}. Add them in Brand Brain; the platform remains available.`
          : "Autopilot started. Internal tasks run automatically; review prepared output in Approvals and progress in Plans & tasks.",
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start campaign");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="operation-card">
      <p className="eyebrow">Reusable campaign setup</p>
      <h3>Autopilot</h3>
      <p>
        No business details are needed to install or explore the platform. Add a
        business here whenever you are ready, then start automatic campaign
        preparation.
      </p>
      <p className="small muted">
        Runs planning, research, strategy, content and selected-contact drafting
        without approving each internal task. Your enabled model may charge
        within your budget. External sends and publication remain separate
        controlled actions.
      </p>
      {error && (
        <p className="message error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="message" role="status">
          {notice}
        </p>
      )}
      <details
        className="form-disclosure"
        open={brands.length === 0 ? true : undefined}
      >
        <summary>Add a business now or later</summary>
        <form className="operation-form" onSubmit={saveBusiness}>
          <fieldset disabled={!owner || paused || busy}>
            <label>
              Business or product name
              <input name="name" required maxLength={120} />
            </label>
            <label>
              Website (optional)
              <input name="website" type="url" maxLength={500} />
            </label>
            <label>
              What do you offer? (can be added later)
              <textarea name="offer" maxLength={5000} />
            </label>
            <label>
              Ideal customers (one group per line; can be added later)
              <textarea name="audience" maxLength={500} />
            </label>
            <label>
              Approved factual statements (one per line; can be added later)
              <textarea
                name="claims"
                placeholder="Only facts you can support"
                maxLength={5000}
              />
            </label>
            <button>Save business profile</button>
          </fieldset>
        </form>
      </details>
      <form className="operation-form" onSubmit={start}>
        <fieldset disabled={!owner || paused || busy}>
          <label>
            Business for this campaign
            <select
              value={brand}
              required
              onChange={(e) => {
                setBrand(e.target.value);
                setSelected([]);
              }}
            >
              <option value="">Choose when ready</option>
              {brands.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Campaign objective
            <textarea
              name="objective"
              required
              minLength={8}
              maxLength={500}
              placeholder="Describe the result you want for this business"
            />
          </label>
          <div className="form-grid">
            <label>
              Target outcome count
              <input
                name="target"
                type="number"
                min={1}
                max={10000}
                defaultValue={10}
              />
            </label>
            <label>
              Window in days
              <input
                name="window_days"
                type="number"
                min={1}
                max={365}
                defaultValue={30}
              />
            </label>
            <label>
              Campaign spending allowance (USD)
              <input
                name="campaign_budget"
                type="number"
                min="0"
                max="1000000"
                step="0.01"
                defaultValue="0"
              />
              <span className="small muted">
                Planning bounds only; zero grants no campaign spending. Model
                costs use your separate monthly model budget.
              </span>
            </label>
          </div>
          <details className="evidence">
            <summary>Optional prospect research and existing contacts</summary>
            <label>
              Website research query
              <input name="search_query" maxLength={300} />
            </label>
            <label className="check">
              <input name="connected_research" type="checkbox" />
              Use enabled Brave connection for this search (provider credits
              apply)
            </label>
            <p className="small muted">
              Research reads up to three suggested business pages and imports
              observed contacts for review. It does not establish marketing
              permission. Select up to twenty reviewed existing contacts below
              for automatic drafts.
            </p>
            {contacts
              .filter(
                (c) =>
                  c.brand_id === brand &&
                  c.status !== "suppressed" &&
                  c.lawful_basis !== "not_established",
              )
              .map((c) => (
                <label className="check" key={c.id}>
                  <input
                    type="checkbox"
                    checked={selected.includes(c.id)}
                    disabled={!selected.includes(c.id) && selected.length >= 20}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...selected, c.id]
                          : selected.filter((id) => id !== c.id),
                      )
                    }
                  />
                  {c.name}
                </label>
              ))}
          </details>
          <button>{busy ? "Working…" : "Start automatic preparation"}</button>
        </fieldset>
      </form>
      {!owner && (
        <p className="small muted">A workspace owner starts Autopilot.</p>
      )}
    </section>
  );
}
