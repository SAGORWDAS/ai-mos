"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import GrowthWorkspace from "./growth-workspace";
import Connections from "./connections";
import AccountSecurity, { RecoveryForm } from "./account-security";
import { currencyFactor } from "./money";

type Identity = {
  user: { name: string; email: string };
  organization: { id: string; name: string; emergency_stop: boolean };
  role: string;
};
type Brand = {
  id: string;
  name: string;
  website: string;
  positioning: string;
  icp: Record<string, unknown>;
  voice: Record<string, unknown>;
  pricing: Record<string, unknown>;
  approved_claims: string[];
  prohibited_claims: string[];
};
type Audit = {
  id: string;
  action: string;
  decision: string;
  created_at: number;
  trace_id: string;
};
type Member = { name: string; email: string; role: string };
type Org = { id: string; name: string; role: string };
type Metrics = {
  brands: number;
  audit_events: number;
  model_calls: number;
  external_effects: number;
  cost_minor: number;
};
type Review = { status: string; missing_fields: string[] };
function PricingFields({ pricing }: { pricing?: Record<string, unknown> }) {
  const initial = Array.isArray(pricing?.plans)
    ? (pricing.plans as Record<string, unknown>[])
    : [];
  const [plans, setPlans] = useState(initial.length ? initial : [{}]);
  return (
    <details className="evidence">
      <summary>Pricing and packages (optional)</summary>
      <p className="small muted">
        Enter your own approved prices. Unknown prices can stay blank.
      </p>
      <label>
        Currency
        <input
          name="pricing_currency"
          pattern="[A-Z]{3}"
          maxLength={3}
          defaultValue={String(pricing?.currency || "USD")}
        />
      </label>
      {plans.map((plan, index) => (
        <div className="form-grid" key={index}>
          <label>
            Package name
            <input name="plan_name" defaultValue={String(plan.name || "")} />
          </label>
          <label>
            Monthly price (selected currency)
            <input
              name="plan_price"
              type="number"
              step="0.01"
              min={0}
              defaultValue={
                plan.price_monthly_minor === undefined
                  ? ""
                  : Number(plan.price_monthly_minor) /
                    currencyFactor(String(pricing?.currency || "USD"))
              }
            />
          </label>
          <label>
            What is included?
            <input
              name="plan_limits"
              defaultValue={String(plan.limits || "")}
            />
          </label>
        </div>
      ))}
      <button
        type="button"
        className="secondary"
        disabled={plans.length >= 20}
        onClick={() => setPlans([...plans, {}])}
      >
        Add package
      </button>
    </details>
  );
}
const navigation = [
  "Overview",
  "Operations",
  "Brand Brain",
  "Activity",
  "Integrations",
  "Team & settings",
  "Build roadmap",
] as const;
type View = (typeof navigation)[number];

async function api<T>(
  path: string,
  body?: unknown,
  method = "POST",
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: body === undefined ? "GET" : method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail = data.detail;
    const message = Array.isArray(detail)
      ? detail.map((x: { msg: string }) => x.msg).join(". ")
      : detail;
    throw new Error(
      message
        ? String(message).replaceAll("_", " ")
        : `Request failed (${response.status})`,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export default function Workspace() {
  const [me, setMe] = useState<Identity | null>(null);
  const [boot, setBoot] = useState(true);
  const [signup, setSignup] = useState(true);
  const [view, setView] = useState<View>("Overview");
  const [brands, setBrands] = useState<Brand[]>([]);
  const [logs, setLogs] = useState<Audit[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [editing, setEditing] = useState<Brand | null | undefined>(undefined);
  const [review, setReview] = useState<Review | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [inviteToken, setInviteToken] = useState("");
  const [connections, setConnections] = useState<
    { provider: string; enabled: boolean; status: string }[]
  >([]);

  const refresh = useCallback(async () => {
    const identity = await api<Identity>("/v1/auth/me");
    setMe(identity);
    const [b, l, m, o, counts] = await Promise.all([
      api<Brand[]>("/v1/brands"),
      api<Audit[]>("/v1/audit"),
      api<Member[]>("/v1/org/members"),
      api<Org[]>("/v1/orgs"),
      api<Metrics>("/v1/metrics/overview"),
    ]);
    setBrands(b);
    setLogs(l);
    setMembers(m);
    setOrgs(o);
    setMetrics(counts);
    setConnections(
      await api<{ provider: string; enabled: boolean; status: string }[]>(
        "/v1/connections",
      ),
    );
  }, []);

  useEffect(() => {
    api<Identity>("/v1/auth/me")
      .then(() => refresh())
      .catch((e: Error) => {
        if (e.message !== "unauthenticated")
          setError(
            "Cannot reach the local API. Start the backend, then reload.",
          );
      })
      .finally(() => setBoot(false));
  }, [refresh]);

  async function perform(action: () => Promise<void>) {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  function go(next: View) {
    setView(next);
    setEditing(undefined);
    setReview(null);
    setError("");
    setNotice("");
  }

  async function authenticate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await perform(async () => {
      await api(
        signup ? "/v1/auth/signup" : "/v1/auth/login",
        Object.fromEntries(form.entries()),
      );
      await refresh();
    });
  }

  async function saveBrand(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const value = (key: string) => String(form.get(key) || "");
    const lines = (key: string) =>
      value(key)
        .split("\n")
        .map((x) => x.trim())
        .filter(Boolean);
    await perform(async () => {
      const prices = form.getAll("plan_price");
      if (
        form
          .getAll("plan_name")
          .some(
            (name, index) =>
              String(name).trim() && !String(prices[index] || "").trim(),
          )
      )
        throw new Error(
          "Enter a price for each named package, or leave the package name blank.",
        );
      const payload = {
        name: value("name"),
        website: value("website"),
        positioning: value("positioning"),
        icp: {
          ...editing?.icp,
          segments: lines("segments"),
          geographies: lines("geographies"),
        },
        voice: {
          ...editing?.voice,
          tone: value("tone"),
          banned_phrases: lines("banned_phrases"),
        },
        pricing: {
          currency: value("pricing_currency") || "USD",
          plans: form
            .getAll("plan_name")
            .map((name, index) => ({
              name: String(name).trim(),
              price_monthly_minor: Math.round(
                Number(form.getAll("plan_price")[index]) *
                  currencyFactor(value("pricing_currency") || "USD"),
              ),
              limits: String(form.getAll("plan_limits")[index] || ""),
            }))
            .filter((plan) => plan.name),
          discounts_allowed: !!editing?.pricing.discounts_allowed,
          discount_ceiling_pct: Number(
            editing?.pricing.discount_ceiling_pct || 0,
          ),
        },
        approved_claims: lines("approved_claims"),
        prohibited_claims: lines("prohibited_claims"),
      };
      await api(
        editing ? `/v1/brands/${editing.id}` : "/v1/brands",
        payload,
        editing ? "PUT" : "POST",
      );
      await refresh();
      setEditing(undefined);
      setNotice("Brand facts saved to your workspace.");
    });
  }

  const writable =
    me && me.role !== "viewer" && !me.organization.emergency_stop;
  const admin = me && ["owner", "admin"].includes(me.role);

  return (
    <>
      <a href="#main" className="skip">
        Skip to content
      </a>
      <header className="masthead">
        <div className="mast-inner">
          <a className="wordmark" href="/" aria-label="AI MOS home">
            <span>AI</span>
            <span>M</span>
            <span>O</span>
            <span>S</span>
          </a>
          <p className="mast-caption">THE MARKETING OPERATING SYSTEM</p>
          <div className="mast-account">
            {me ? (
              <>
                <span>{me.user.name}</span>
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() =>
                    perform(async () => {
                      await api("/v1/auth/logout", {});
                      setMe(null);
                      setBrands([]);
                      setLogs([]);
                    })
                  }
                >
                  Sign out
                </button>
              </>
            ) : (
              <span>Independent thinking. Measurable growth.</span>
            )}
          </div>
        </div>
      </header>
      {me && (
        <nav className="nav" aria-label="Main navigation">
          <div>
            {navigation.map((item) => (
              <button
                key={item}
                onClick={() => go(item)}
                aria-current={view === item ? "page" : undefined}
              >
                {item}
              </button>
            ))}
          </div>
        </nav>
      )}
      <main id="main" className={me ? "container" : "auth-container"}>
        {error && (
          <div className="message error" role="alert">
            {error}
          </div>
        )}
        {notice && (
          <div className="message" role="status">
            {notice}
          </div>
        )}
        {boot ? (
          <p role="status">Opening your workspace…</p>
        ) : !me ? (
          <div className="auth-grid">
            <section className="intro">
              <p className="eyebrow">A clearer way to grow</p>
              <h1>
                Your business.
                <br />
                Your direction.
                <br />
                One workspace.
              </h1>
              <p className="lede">
                Bring your brand, your team and your marketing decisions
                together. Keep control of what goes out, and understand what it
                costs.
              </p>
              <div className="intro-notes">
                <p>
                  <b>01</b> Start with the facts about your business.
                </p>
                <p>
                  <b>02</b> Review the work before it reaches a customer.
                </p>
                <p>
                  <b>03</b> Measure the outcome, and improve.
                </p>
              </div>
              <p className="muted small">
                Local sandbox edition · No API keys needed
              </p>
            </section>
            <section className="auth-panel">
              <p className="eyebrow">Your workspace</p>
              <h2>{signup ? "Make room for better work." : "Welcome back."}</h2>
              <p className="muted">
                {signup
                  ? "Create your account to begin. Your business details stay yours to define."
                  : "Sign in to continue where you left off."}
              </p>
              <form onSubmit={authenticate}>
                {signup && (
                  <>
                    <label>
                      Your name
                      <input
                        name="name"
                        autoComplete="name"
                        required
                        maxLength={120}
                      />
                    </label>
                    <label>
                      Workspace name
                      <input
                        name="organization_name"
                        placeholder="Your agency or business"
                        required
                        maxLength={120}
                      />
                    </label>
                  </>
                )}
                <label>
                  Email address
                  <input
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    maxLength={254}
                  />
                </label>
                <label>
                  Password
                  <input
                    name="password"
                    type="password"
                    autoComplete={signup ? "new-password" : "current-password"}
                    required
                    minLength={signup ? 12 : 1}
                    maxLength={256}
                  />
                  {signup && <small>Use at least 12 characters.</small>}
                </label>
                {!signup && (
                  <label>
                    Authenticator code (if enabled)
                    <input
                      name="otp"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={6}
                    />
                  </label>
                )}
                <button className="primary full" disabled={busy}>
                  {busy
                    ? "Please wait…"
                    : signup
                      ? "Create workspace →"
                      : "Sign in →"}
                </button>
              </form>
              <p className="small">
                {signup ? "Already have an account?" : "New to AI-MOS?"}{" "}
                <button
                  className="text-button"
                  onClick={() => {
                    setSignup(!signup);
                    setError("");
                  }}
                >
                  {signup ? "Sign in" : "Create a workspace"}
                </button>
              </p>
              {!signup && <RecoveryForm />}
              <p className="small muted">
                This build runs on your computer. Outreach, bookings and
                payments use local sandbox adapters.
              </p>
            </section>
          </div>
        ) : (
          <>
            <div className="edition">
              <span>
                {me.organization.name}{" "}
                <span className="muted">/ {me.role}</span>
              </span>
              <span>LOCAL DEVELOPMENT · SANDBOX DEFAULT</span>
            </div>
            {me.organization.emergency_stop && (
              <div className="stop-banner" role="status">
                <strong>Workspace paused.</strong> Changes are stopped. Reading
                remains available. An owner can resume in settings.
              </div>
            )}
            <div className="page-heading">
              <div>
                <p className="eyebrow">
                  {view === "Overview"
                    ? "Your workspace, at a glance"
                    : "Workspace / " + view}
                </p>
                <h1>
                  {view === "Overview" ? "A foundation for growth." : view}
                </h1>
              </div>
              {view === "Overview" && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => perform(refresh)}
                >
                  Refresh ↻
                </button>
              )}
              {view === "Brand Brain" && editing === undefined && (
                <button
                  className="primary"
                  disabled={!writable || busy}
                  onClick={() => {
                    setEditing(null);
                    setReview(null);
                  }}
                >
                  Add a brand +
                </button>
              )}
            </div>
            {view === "Overview" && (
              <>
                <div className="overview-grid">
                  <section className="lead-story">
                    <p className="eyebrow">Start here</p>
                    <h2>
                      Good marketing begins
                      <br />
                      with knowing your business.
                    </h2>
                    <p className="lede">
                      Define what you offer, who you serve, and what you can
                      honestly promise. Your Brand Brain gives future work a
                      reliable source of truth.
                    </p>
                    <button
                      className="primary"
                      onClick={() => go("Brand Brain")}
                    >
                      {brands.length
                        ? "Open Brand Brain →"
                        : "Set up your first brand →"}
                    </button>
                    <p className="small muted">
                      Works for a service business, an agency, a SaaS product,
                      or your next idea.
                    </p>
                  </section>
                  <aside className="briefing">
                    <h3>The current brief</h3>
                    <p>
                      Planning, CRM, approvals and the customer workflow are
                      available with sandbox providers.
                    </p>
                    <div className="rule-row">
                      <span>External actions</span>
                      <b>
                        {me.organization.emergency_stop
                          ? "Paused"
                          : connections.some((item) => item.enabled)
                            ? "Approval required"
                            : "Sandbox only"}
                      </b>
                    </div>
                    <div className="rule-row">
                      <span>Connected providers</span>
                      <b>{connections.filter((item) => item.enabled).length}</b>
                    </div>
                    <div className="rule-row">
                      <span>Business facts</span>
                      <b>{brands.length ? "In progress" : "Awaiting you"}</b>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => go("Build roadmap")}
                    >
                      See what comes next →
                    </button>
                  </aside>
                </div>
                <div className="stats" aria-label="Workspace statistics">
                  {[
                    ["Brands", metrics?.brands],
                    ["Audit events", metrics?.audit_events],
                    ["Model calls", metrics?.model_calls],
                    [
                      "Recorded spend",
                      `$${((metrics?.cost_minor || 0) / 100).toFixed(2)}`,
                    ],
                  ].map(([label, value]) => (
                    <div key={String(label)}>
                      <span className="eyebrow">{label}</span>
                      <strong>{value ?? "—"}</strong>
                    </div>
                  ))}
                </div>
                <section className="section">
                  <div className="section-title">
                    <h2>In your workspace</h2>
                    <button
                      className="text-button"
                      onClick={() => go("Activity")}
                    >
                      View activity →
                    </button>
                  </div>
                  <div className="three-col">
                    <article>
                      <span className="article-number">01 / KNOWLEDGE</span>
                      <h3>One source of truth</h3>
                      <p>
                        Save your positioning, ideal customers, voice and
                        approved claims. Keep the message consistent across
                        every future campaign.
                      </p>
                      <button
                        className="text-button"
                        onClick={() => go("Brand Brain")}
                      >
                        Manage brands →
                      </button>
                    </article>
                    <article>
                      <span className="article-number">02 / PEOPLE</span>
                      <h3>Clear responsibilities</h3>
                      <p>
                        Give colleagues the access they need. Owners, admins,
                        members and viewers each have a defined role.
                      </p>
                      <button
                        className="text-button"
                        onClick={() => go("Team & settings")}
                      >
                        Manage your team →
                      </button>
                    </article>
                    <article>
                      <span className="article-number">03 / CONTROL</span>
                      <h3>A record of the work</h3>
                      <p>
                        See recorded workspace changes and refused actions, with
                        a trace reference for investigation.
                      </p>
                      <button
                        className="text-button"
                        onClick={() => go("Activity")}
                      >
                        Read the activity log →
                      </button>
                    </article>
                  </div>
                </section>
              </>
            )}
            {view === "Operations" && (
              <GrowthWorkspace key={me.organization.id} identity={me} />
            )}
            {view === "Brand Brain" && (
              <>
                {editing !== undefined ? (
                  <section className="editor">
                    <h2>
                      {editing
                        ? "Edit your brand"
                        : "Tell us about your business"}
                    </h2>
                    <p className="muted">
                      Enter facts you stand behind. Leave unknown details blank.
                      One item per line in list fields.
                    </p>
                    <form onSubmit={saveBrand} key={editing?.id || "new"}>
                      <div className="form-grid">
                        <label>
                          Brand or service name
                          <input
                            name="name"
                            defaultValue={editing?.name}
                            required
                            maxLength={120}
                          />
                        </label>
                        <label>
                          Website
                          <input
                            name="website"
                            type="url"
                            defaultValue={editing?.website}
                            placeholder="https://your-business.com"
                            maxLength={500}
                          />
                        </label>
                      </div>
                      <label>
                        Positioning
                        <textarea
                          name="positioning"
                          defaultValue={editing?.positioning}
                          placeholder="What do you offer, who is it for, and why should they choose you?"
                          maxLength={5000}
                        />
                      </label>
                      <div className="form-grid">
                        <label>
                          Ideal customer segments
                          <textarea
                            name="segments"
                            defaultValue={(
                              (editing?.icp.segments as string[]) || []
                            ).join("\n")}
                            placeholder="One customer segment per line"
                          />
                        </label>
                        <label>
                          Target locations
                          <textarea
                            name="geographies"
                            defaultValue={(
                              (editing?.icp.geographies as string[]) || []
                            ).join("\n")}
                            placeholder="Countries, cities, or remote"
                          />
                        </label>
                      </div>
                      <label>
                        Brand voice
                        <input
                          name="tone"
                          defaultValue={String(editing?.voice.tone || "")}
                          placeholder="Describe how your business should sound"
                        />
                      </label>
                      <div className="form-grid">
                        <label>
                          Approved claims
                          <textarea
                            name="approved_claims"
                            defaultValue={editing?.approved_claims.join("\n")}
                            placeholder="Only facts you can support"
                          />
                        </label>
                        <label>
                          Prohibited claims
                          <textarea
                            name="prohibited_claims"
                            defaultValue={editing?.prohibited_claims.join("\n")}
                            placeholder="Statements your marketing must never make"
                          />
                        </label>
                      </div>
                      <label>
                        Banned phrases
                        <textarea
                          name="banned_phrases"
                          defaultValue={(
                            (editing?.voice.banned_phrases as string[]) || []
                          ).join("\n")}
                        />
                      </label>
                      <PricingFields
                        key={editing?.id || "new-pricing"}
                        pricing={editing?.pricing}
                      />
                      <div className="actions">
                        <button
                          className="primary"
                          disabled={busy || !writable}
                        >
                          {busy ? "Saving…" : "Save brand facts"}
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          disabled={busy}
                          onClick={() => setEditing(undefined)}
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  </section>
                ) : brands.length === 0 ? (
                  <div className="empty">
                    <span className="eyebrow">An open page</span>
                    <h2>Your first brand belongs here.</h2>
                    <p>
                      Add the facts about your agency, service or product.
                      Nothing is filled in on your behalf.
                    </p>
                    <button
                      className="primary"
                      disabled={!writable}
                      onClick={() => setEditing(null)}
                    >
                      Add your first brand →
                    </button>
                  </div>
                ) : (
                  <div className="brand-list">
                    {brands.map((b) => (
                      <article key={b.id} className="brand-card">
                        <div>
                          <p className="eyebrow">Brand profile</p>
                          <h2>{b.name}</h2>
                          <p>
                            {b.positioning ||
                              "Positioning has not been added yet."}
                          </p>
                          {b.website && (
                            <a
                              href={b.website}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              {b.website}
                            </a>
                          )}
                          <p className="muted small">
                            {b.approved_claims.length} approved claims ·{" "}
                            {((b.icp.segments as string[]) || []).length}{" "}
                            customer segments
                          </p>
                        </div>
                        <div className="actions">
                          <button
                            className="secondary"
                            disabled={!writable || busy}
                            onClick={() => {
                              setEditing(b);
                              setReview(null);
                            }}
                          >
                            Edit profile
                          </button>
                          <button
                            className="text-button"
                            disabled={busy}
                            onClick={() =>
                              perform(async () => {
                                setReview(
                                  await api<Review>(
                                    `/v1/brands/${b.id}/review`,
                                    {},
                                  ),
                                );
                                setNotice(`Review of ${b.name}`);
                              })
                            }
                          >
                            Check readiness →
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
                {review && (
                  <div className="review" role="status">
                    <h3>
                      {review.missing_fields.length
                        ? "A few facts are still needed."
                        : "The core facts are present."}
                    </h3>
                    <p>
                      {review.missing_fields.length
                        ? `Add: ${review.missing_fields.join(", ")}.`
                        : "Your profile is ready for planning and grounded drafting in Operations."}
                    </p>
                    <p className="small muted">
                      This checks for required fields. It does not verify your
                      claims or call an AI model.
                    </p>
                  </div>
                )}
              </>
            )}
            {view === "Activity" && (
              <section>
                <p className="muted">
                  Workspace changes and permission decisions. Most recent first.
                </p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Action</th>
                        <th>Decision</th>
                        <th>Time</th>
                        <th>Trace reference</th>
                      </tr>
                    </thead>
                    <tbody>
                      {logs.map((log) => (
                        <tr key={log.id}>
                          <td>
                            <b>{log.action.replaceAll(".", " / ")}</b>
                          </td>
                          <td>{log.decision.replaceAll("_", " ")}</td>
                          <td>
                            {new Date(log.created_at * 1000).toLocaleString()}
                          </td>
                          <td>
                            <code>{log.trace_id.slice(0, 8)}</code>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {logs.length === 100 && (
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      perform(async () => {
                        const more = await api<Audit[]>(
                          `/v1/audit?before=${logs[logs.length - 1].created_at}`,
                        );
                        setLogs([...logs, ...more]);
                      })
                    }
                  >
                    Load older activity
                  </button>
                )}
              </section>
            )}
            {view === "Integrations" && <Connections role={me.role} />}
            {view === "Team & settings" && (
              <>
                <section className="section">
                  <h2>Workspace & access</h2>
                  <label className="narrow">
                    Active workspace
                    <select
                      value={me.organization.id}
                      disabled={busy}
                      onChange={(e) =>
                        perform(async () => {
                          await api(`/v1/orgs/${e.target.value}/switch`, {});
                          setEditing(undefined);
                          await refresh();
                        })
                      }
                    >
                      {orgs.map((org) => (
                        <option value={org.id} key={org.id}>
                          {org.name} ({org.role})
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Name</th>
                          <th>Email</th>
                          <th>Role</th>
                        </tr>
                      </thead>
                      <tbody>
                        {members.map((member) => (
                          <tr key={member.email}>
                            <td>{member.name}</td>
                            <td>{member.email}</td>
                            <td>{member.role}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
                <div className="two-col">
                  <section>
                    <h2>Invite a colleague</h2>
                    <p className="muted">
                      Invitations expire after 24 hours. Share the token
                      privately; email delivery is not connected.
                    </p>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        const form = new FormData(e.currentTarget);
                        perform(async () => {
                          const result = await api<{ token: string }>(
                            "/v1/org/invitations",
                            Object.fromEntries(form.entries()),
                          );
                          setInviteToken(result.token);
                          await refresh();
                        });
                      }}
                    >
                      <label>
                        Email
                        <input
                          type="email"
                          name="email"
                          required
                          disabled={!admin}
                        />
                      </label>
                      <label>
                        Role
                        <select name="role" disabled={!admin}>
                          <option value="viewer">Viewer — read only</option>
                          <option value="member">Member — edit brands</option>
                          {me.role === "owner" && (
                            <option value="admin">
                              Admin — manage invitations
                            </option>
                          )}
                        </select>
                      </label>
                      <button
                        className="primary"
                        disabled={busy || !admin || !writable}
                      >
                        Create invitation
                      </button>
                    </form>
                    {inviteToken && (
                      <label>
                        Invitation token
                        <input
                          readOnly
                          value={inviteToken}
                          onFocus={(e) => e.currentTarget.select()}
                        />
                      </label>
                    )}
                  </section>
                  <section>
                    <h2>Join a workspace</h2>
                    <p className="muted">
                      Sign in using the invited email, then paste your token
                      here. Your existing workspace remains available.
                    </p>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        const form = new FormData(e.currentTarget);
                        perform(async () => {
                          await api("/v1/org/invitations/accept", {
                            token: form.get("token"),
                          });
                          await refresh();
                          setNotice("You have joined the workspace.");
                        });
                      }}
                    >
                      <label>
                        Invitation token
                        <input name="token" required minLength={20} />
                      </label>
                      <button className="secondary" disabled={busy}>
                        Accept invitation
                      </button>
                    </form>
                  </section>
                </div>
                <AccountSecurity
                  owner={me.role === "owner"}
                  onChange={refresh}
                />
                <section className="stop-section">
                  <div>
                    <h2>Emergency stop</h2>
                    <p>
                      Pause workspace changes immediately. Reading and account
                      access remain available. Only an owner can change this
                      setting.
                    </p>
                  </div>
                  <button
                    className={
                      me.organization.emergency_stop ? "primary" : "secondary"
                    }
                    disabled={busy || me.role !== "owner"}
                    onClick={() =>
                      perform(async () => {
                        await api("/v1/org/emergency-stop", {
                          enabled: !me.organization.emergency_stop,
                        });
                        await refresh();
                      })
                    }
                  >
                    {me.organization.emergency_stop
                      ? "Resume workspace"
                      : "Pause workspace"}
                  </button>
                </section>
              </>
            )}
            {view === "Build roadmap" && (
              <section>
                <p className="lede narrow">
                  A practical route from business facts to approved outreach,
                  then measurable revenue. Each stage needs evidence before it
                  is considered complete.
                </p>
                <div className="roadmap">
                  {[
                    [
                      "01",
                      "Workspace foundation",
                      "Available locally",
                      "Accounts, roles, brand profiles, audit history and emergency stop. PostgreSQL migrations, restricted database roles and tenant isolation have been tested locally.",
                    ],
                    [
                      "02",
                      "Marketing intelligence",
                      "Available in sandbox",
                      "A goal becomes a structured plan. Grounded drafts, usage ledger, budgets and single-use approvals.",
                    ],
                    [
                      "03",
                      "Acquisition",
                      "Available in sandbox",
                      "Sourced leads, CRM, consent and suppression checks, approved sending and reply classification.",
                    ],
                    [
                      "04",
                      "Conversation & revenue",
                      "Available in sandbox",
                      "Calendar coordination, checkout, signed payment webhooks and customer onboarding.",
                    ],
                    [
                      "05",
                      "Learning & operations",
                      "Available in sandbox",
                      "Attribution, experiments, support, retention, restore drills and deployment hardening.",
                    ],
                  ].map(([num, title, status, detail]) => (
                    <article key={num}>
                      <span className="road-number">{num}</span>
                      <div>
                        <p className="eyebrow">{status}</p>
                        <h2>{title}</h2>
                        <p>{detail}</p>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </main>
      <footer>
        <span>AI-MOS</span>
        <p>Clarity in the work. Accountability in the outcome.</p>
        <small>Development edition · Sandbox default</small>
      </footer>
    </>
  );
}
