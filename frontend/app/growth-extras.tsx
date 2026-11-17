"use client";

import { FormEvent, useState } from "react";
import { api } from "./api";
import { currencies, currencyFactor, displayMoney } from "./money";

type Row = { id: string; [key: string]: unknown };
const obj = (v: unknown): Record<string, unknown> =>
  v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
const label = (row: Row) => String(row.name || row.title || row.id);
const options = (rows: Row[]) =>
  rows.map((row) => (
    <option key={row.id} value={row.id}>
      {label(row)}
    </option>
  ));

export function CreativeAssets({
  brands,
  tasks,
  disabled,
  refresh,
}: {
  brands: Row[];
  tasks: Row[];
  disabled: boolean;
  refresh: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api("/v1/creative/images", {
        brand_id: f.get("brand"),
        brief: f.get("brief"),
        connected_provider: f.get("connected") === "on",
        idempotency_key: crypto.randomUUID(),
      });
      setMessage(
        "Image work queued. Completed assets appear here and stay private until you choose to use them.",
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not generate image");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="operation-card">
      <h3>Creative images</h3>
      <p>
        Create a private illustration from a short visual brief. Sandbox
        produces a labelled checkerboard fixture; connected generation uses your
        selected image model and budget. Review every asset before publication
        or advertising.
      </p>
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="message">
          {message}
        </p>
      )}
      <form className="operation-form" onSubmit={create}>
        <fieldset disabled={disabled || busy}>
          <label>
            Business
            <select name="brand" required>
              <option value="">Choose business</option>
              {options(brands)}
            </select>
          </label>
          <label>
            What should the image show?
            <textarea
              name="brief"
              required
              minLength={10}
              maxLength={1000}
              placeholder="A clean black-and-white illustration of an independent shop"
            />
          </label>
          <label className="check">
            <input name="connected" type="checkbox" />
            Use my enabled image model (may incur charges)
          </label>
          <button>{busy ? "Queuing…" : "Prepare creative image"}</button>
        </fieldset>
      </form>
      {tasks
        .filter((t) => t.type === "creative_image")
        .slice(0, 10)
        .map((task) => (
          <article className="operation-card compact" key={task.id}>
            <p>
              {String(obj(task.input).brief || "Creative image")} ·{" "}
              {String(task.status)}
            </p>
            {task.status === "failed" && (
              <p role="status">
                {String(task.error_code).replaceAll("_", " ")}
              </p>
            )}
            {task.status === "succeeded" && (
              <>
                <p className="small muted">{String(obj(task.output).label)}</p>
                <img
                  src={`/api/v1/creative/images/${task.id}`}
                  alt={String(obj(task.output).label)}
                  width={Number(obj(task.output).width)}
                  height={Number(obj(task.output).height)}
                  style={{ maxWidth: "100%", height: "auto" }}
                />
                <p>
                  <a href={`/api/v1/creative/images/${task.id}?download=true`}>
                    Download private image
                  </a>
                </p>
              </>
            )}
          </article>
        ))}
    </section>
  );
}

type Approval = {
  id: string;
  status: string;
  payload: Record<string, unknown>;
};
export function Advertising({
  data,
  disabled,
  connected,
  canPause,
  refresh,
}: {
  data: Record<string, Row[]>;
  disabled: boolean;
  connected: boolean;
  canPause: boolean;
  refresh: () => Promise<void>;
}) {
  const [campaign, setCampaign] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [approval, setApproval] = useState<Approval | null>(null);
  const [message, setMessage] = useState("");
  const campaigns = data.campaigns || [];
  const selected = campaigns.find((c) => c.id === campaign);
  const content = (data.content_items || []).filter(
    (c) => c.brand_id === selected?.brand_id,
  );
  const images = (data.tasks || []).filter(
    (t) =>
      t.type === "creative_image" &&
      t.status === "succeeded" &&
      obj(t.input).brand_id === selected?.brand_id,
  );
  async function act(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await work();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Advertising action failed");
    } finally {
      setBusy(false);
    }
  }
  async function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    await act(async () => {
      setApproval(
        await api<Approval>("/v1/advertising/request-approval", {
          campaign_id: campaign,
          content_id: f.get("content"),
          image_task_id: f.get("image"),
          landing_url: f.get("url"),
          country: f.get("country"),
          currency,
          lifetime_budget_minor: Math.round(
            Number(f.get("budget")) * currencyFactor(currency),
          ),
          duration_days: Number(f.get("days")),
          ordinary_commercial_confirmed: f.get("ordinary") === "on",
          activate: f.get("activate") === "on",
          idempotency_key: crypto.randomUUID(),
        }),
      );
      setMessage("");
    });
  }
  return (
    <>
      <section className="operation-card">
        <h2>Paid campaign</h2>
        <p>
          Prepare a Meta link-ad campaign with a lifetime budget and an end
          date. Start in sandbox. Live execution requires a verified ad account,
          billing, an approved image and an owner decision. This workflow
          supports ordinary commercial ads; special-category campaigns need
          specialist setup in Meta.
        </p>
        {error && (
          <p role="alert" className="message error">
            {error}
          </p>
        )}
        {message && (
          <p role="status" className="message">
            {message}
          </p>
        )}
        <form className="operation-form" onSubmit={review}>
          <fieldset disabled={disabled || busy}>
            <label>
              Campaign
              <select
                required
                value={campaign}
                onChange={(e) => {
                  setCampaign(e.target.value);
                  setApproval(null);
                }}
              >
                <option value="">Choose campaign</option>
                {options(campaigns)}
              </select>
            </label>
            <label>
              Reviewed copy
              <select name="content" required>
                <option value="">Choose content from this business</option>
                {options(content)}
              </select>
            </label>
            <label>
              Reviewed image
              <select name="image" required>
                <option value="">Choose a completed image</option>
                {images.map((t) => (
                  <option key={t.id} value={t.id}>
                    {String(obj(t.input).brief || t.id)}
                    {obj(t.output).simulated ? " (sandbox)" : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Public landing page
              <input
                name="url"
                type="url"
                required
                placeholder="https://your-business.com/offer"
              />
            </label>
            <div className="form-grid">
              <label>
                Country code
                <input
                  name="country"
                  required
                  pattern="[A-Z]{2}"
                  maxLength={2}
                  placeholder="US"
                />
              </label>
              <label>
                Currency
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                >
                  {currencies.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
              <label>
                Total lifetime budget
                <input
                  name="budget"
                  type="number"
                  required
                  min={1 / currencyFactor(currency)}
                  max={1000000 / currencyFactor(currency)}
                  step={1 / currencyFactor(currency)}
                />
              </label>
              <label>
                Duration (days)
                <input
                  name="days"
                  type="number"
                  min={1}
                  max={7}
                  defaultValue={3}
                  required
                />
              </label>
            </div>
            <label className="check">
              <input name="ordinary" type="checkbox" required />I reviewed the
              offer and confirm it is an ordinary commercial campaign, not a
              special-category ad.
            </label>
            <label className="check">
              <input name="activate" type="checkbox" />
              Activate after creation (live execution can spend the approved
              budget)
            </label>
            <button>Prepare exact campaign review</button>
          </fieldset>
        </form>
        {approval && (
          <section className="operation-card">
            <h3>{String(approval.payload.title)}</h3>
            <p className="preserve">{String(approval.payload.body)}</p>
            <img
              src={`/api/v1/creative/images/${approval.payload.image_task_id}`}
              alt="Image frozen in this campaign review"
              style={{ maxWidth: "100%", height: "auto" }}
            />
            <p>
              {displayMoney(
                Number(approval.payload.lifetime_budget_minor),
                String(approval.payload.currency),
              )}{" "}
              lifetime · {String(approval.payload.duration_days)} days ·{" "}
              {approval.payload.activate
                ? "Activation authorized if live execution is selected"
                : "Create paused resources"}
            </p>
            <p>Landing page: {String(approval.payload.landing_url)}</p>
            <div className="actions">
              {approval.status === "pending" && (
                <button
                  disabled={disabled || busy}
                  onClick={() =>
                    act(async () => {
                      setApproval(
                        await api<Approval>(
                          `/v1/approvals/${approval.id}/decision`,
                          { decision: "approved" },
                        ),
                      );
                    })
                  }
                >
                  Approve this exact budget and creative
                </button>
              )}
              {approval.status === "approved" && (
                <>
                  <button
                    disabled={disabled || busy}
                    onClick={() =>
                      act(async () => {
                        await api("/v1/effects/execute", {
                          approval_id: approval.id,
                          idempotency_key: `ads-${approval.id}-sandbox`,
                          execution_mode: "sandbox",
                        });
                        setApproval(null);
                        setMessage(
                          "Sandbox campaign simulated. No ad purchase or publication occurred.",
                        );
                      })
                    }
                  >
                    Simulate campaign
                  </button>
                  <button
                    disabled={disabled || busy || !connected}
                    onClick={() =>
                      act(async () => {
                        await api("/v1/effects/execute", {
                          approval_id: approval.id,
                          idempotency_key: `ads-${approval.id}-live`,
                          execution_mode: "live",
                        });
                        setApproval(null);
                        setMessage(
                          "Approved campaign queued. Follow its receipt below.",
                        );
                      })
                    }
                  >
                    Execute on connected ad account
                  </button>
                </>
              )}
            </div>
          </section>
        )}
      </section>
      <section className="operation-card">
        <h3>Campaign execution receipts</h3>
        <p className="small muted">
          Workspace pause stops new work. Existing provider ads need a separate
          pause here or in Meta. Lifetime budgets and end dates remain in
          effect.
        </p>
        {(data.effects || [])
          .filter((e) => e.action === "launch_paid_ads")
          .map((effect) => (
            <article key={effect.id} className="operation-card compact">
              <p>
                {String(obj(effect.payload).title)} · {String(effect.status)}
                {obj(effect.result).paused_at ? " · Paused" : ""}
              </p>
              <p>
                {obj(effect.result).simulated
                  ? "Sandbox receipt"
                  : "Provider execution"}{" "}
                ·{" "}
                {displayMoney(
                  Number(obj(effect.payload).lifetime_budget_minor),
                  String(obj(effect.payload).currency),
                )}{" "}
                lifetime
              </p>
              {effect.status === "uncertain" && (
                <p role="status">
                  The provider outcome needs review. Do not create another
                  campaign until its console and saved receipts have been
                  checked.
                </p>
              )}
              <button
                className="secondary"
                disabled={busy || !canPause}
                onClick={() =>
                  act(async () => {
                    await api(`/v1/advertising/${effect.id}/pause`, {
                      idempotency_key: crypto.randomUUID(),
                    });
                    setMessage("Pause request confirmed.");
                  })
                }
              >
                Pause this campaign
              </button>
              <button
                className="secondary"
                disabled={busy || !canPause}
                onClick={() =>
                  act(async () => {
                    const result = await api<{
                      spend: string;
                      currency: string;
                      clicks: number;
                      impressions: number;
                    }>(`/v1/advertising/${effect.id}/metrics`, {
                      idempotency_key: crypto.randomUUID(),
                    });
                    setMessage(
                      `Provider results: ${result.spend} ${result.currency} spent, ${result.clicks} clicks, ${result.impressions} impressions. USD spend is recorded once in campaign costs; other currencies remain separate.`,
                    );
                  })
                }
              >
                Refresh results and recorded spend
              </button>
            </article>
          ))}
      </section>
    </>
  );
}
