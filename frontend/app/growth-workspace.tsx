"use client";

import {
  FormEvent,
  ReactNode,
  createContext,
  useContext,
  useCallback,
  useEffect,
  useState,
} from "react";
import { api } from "./api";
import { currencies, currencyFactor, displayMoney } from "./money";

type Item = { id: string; created_at: number; [key: string]: unknown };
type Page = { items: Item[]; next_cursor: number | null };
type Identity = {
  organization: { id: string; emergency_stop: boolean };
  role: string;
};
const sections = [
  "Command Center",
  "Plans & tasks",
  "Leads & CRM",
  "Outreach",
  "Inbox",
  "Content",
  "Campaigns",
  "Approvals",
  "Meetings",
  "Revenue",
  "Customers",
  "Support",
  "Automation",
  "Learning",
  "Analytics",
  "Agents",
  "Usage & cost",
  "Knowledge",
  "Sequences",
  "Notifications",
  "Expenses",
] as const;
type Section = (typeof sections)[number];
const resources: Record<Section, string[]> = {
  "Command Center": ["commands", "plans", "tasks"],
  "Plans & tasks": ["plans", "tasks"],
  "Leads & CRM": ["leads", "activities", "suppressions", "tasks"],
  Outreach: ["outreach_drafts", "tasks"],
  Inbox: ["messages"],
  Content: ["content_items", "tasks"],
  Campaigns: ["campaigns", "outreach_drafts"],
  Approvals: ["approvals", "effects"],
  Meetings: ["meetings"],
  Revenue: ["checkouts", "payments", "subscriptions", "provider_events"],
  Customers: ["customers"],
  Support: ["support_threads"],
  Automation: ["workflows", "workflow_runs"],
  Learning: ["learning_records"],
  Analytics: [],
  Agents: [],
  "Usage & cost": ["model_usage"],
  Knowledge: ["brand_documents", "tasks"],
  Sequences: ["sequences", "sequence_enrollments"],
  Notifications: ["notifications"],
  Expenses: ["expenses"],
};
const descriptions: Record<Section, string> = {
  Sequences:
    "Schedule bounded follow-up drafting. Every message still needs a separate human approval; human replies and opt-outs stop the sequence.",
  Notifications:
    "Read internal notifications produced by your automation rules.",
  Expenses:
    "Record attributable data, sending, review and infrastructure expenses with an evidence reference. Sandbox expenses stay labelled as test data.",
  "Command Center":
    "Turn an objective into a structured plan. Sandbox uses a deterministic template; an enabled model connection uses your configured provider.",
  "Plans & tasks":
    "Review plans, approve internal work, and follow the dependency graph through durable jobs.",
  "Leads & CRM":
    "Import sourced contacts, record your contactability evidence, qualify leads and track their stage.",
  Outreach:
    "Prepare grounded drafts, edit the copy and request approval. Every message needs its own valid authorization.",
  Inbox:
    "Import known-contact replies from connected Gmail or simulate a test message. Opt-outs suppress the contact before other work.",
  Content:
    "Prepare a landing page, article, social draft, SEO outline or creative brief from your approved brand facts.",
  Campaigns:
    "Group up to twenty contacts into a reviewed batch. Every draft and recipient is frozen in its approval.",
  Approvals:
    "Read the exact payload before deciding. Edits invalidate authorization; approvals expire after 24 hours and execute once.",
  Meetings:
    "Propose a time and request approval. Choose sandbox execution or an enabled calendar; connected bookings recheck availability.",
  Revenue:
    "Create a sandbox or connected Stripe checkout. Signed payment receipts confirm revenue; test revenue stays separate.",
  Customers:
    "Track onboarding after a verified payment event. A checkout alone does not create a paid customer.",
  Support:
    "Record customer requests and responses. Refunds, disputes and contract questions escalate to a human.",
  Automation:
    "Create bounded trigger/action rules. Rules perform internal work and cannot recursively invoke one another.",
  Learning:
    "Record lessons with an evidence reference and a measured effect size. Evidence must belong to this workspace.",
  Analytics:
    "Inspect recorded results. Sandbox deliveries and revenue are labelled separately from real outcomes.",
  Agents:
    "One shared runtime with twenty role manifests. Permissions come from the registry; disabling a role blocks its jobs.",
  "Usage & cost":
    "Inspect every model attempt, including refusals and failures, and control the monthly budget and daily send cap.",
  Knowledge:
    "Import text, PDFs or public webpages. Retrieve cited passages with keyword search or explicitly selected sandbox/connected embedding search.",
};

const text = (row: Item, key: string) => String(row[key] ?? "");
const number = (row: Item, key: string) => Number(row[key] || 0);
const object = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
const date = (value: unknown) =>
  value ? new Date(Number(value) * 1000).toLocaleString() : "—";
const money = (value: unknown) =>
  `$${(Number(value || 0) / 1_000_000).toFixed(6)}`;
const clean = (value: unknown) => String(value ?? "").replaceAll("_", " ");
function Evidence({ value }: { value: unknown }) {
  return (
    <details className="evidence">
      <summary>Details & evidence</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
function Status({ value }: { value: unknown }) {
  return <span className="badge">{clean(value)}</span>;
}

const WorkContext = createContext<{
  busy: boolean;
  writable: boolean;
  brands: Item[];
  leads: Item[];
  customers: Item[];
  data: Record<string, Item[]>;
} | null>(null);
function useWork() {
  const state = useContext(WorkContext);
  if (!state) throw new Error("Missing workspace context");
  return state;
}
function Form({
  children,
  submit,
  label = "Save",
  disabled,
}: {
  children: ReactNode;
  submit: (fields: FormData) => Promise<unknown>;
  label?: string;
  disabled?: boolean;
}) {
  const { busy, writable } = useWork();
  const blocked = disabled ?? !writable;
  return (
    <form
      className="operation-form"
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        void submit(new FormData(event.currentTarget));
      }}
    >
      <fieldset disabled={busy || blocked}>
        {children}
        <button className="primary" disabled={busy || blocked}>
          {busy ? "Working…" : label}
        </button>
      </fieldset>
    </form>
  );
}
function BrandSelect() {
  const { brands } = useWork();
  return (
    <label>
      Brand
      <select name="brand_id" required>
        <option value="">Choose a brand</option>
        {brands.map((b) => (
          <option key={b.id} value={b.id}>
            {text(b, "name")}
          </option>
        ))}
      </select>
    </label>
  );
}
function LeadSelect() {
  const { leads } = useWork();
  return (
    <label>
      Contact
      <select name="lead_id" required>
        <option value="">Choose a contact</option>
        {leads
          .filter((l) => l.status !== "suppressed")
          .map((l) => (
            <option key={l.id} value={l.id}>
              {text(l, "name")} — {text(l, "email")}
            </option>
          ))}
      </select>
    </label>
  );
}
function CustomerSelect() {
  const { customers, leads } = useWork();
  return (
    <label>
      Customer
      <select name="customer_id" required>
        <option value="">Choose a customer</option>
        {customers.map((c) => (
          <option key={c.id} value={c.id}>
            {text(leads.find((l) => l.id === c.lead_id) || c, "name") ||
              c.id.slice(0, 8)}
          </option>
        ))}
      </select>
    </label>
  );
}
function Empty({ resource }: { resource: string }) {
  const { data } = useWork();
  return data[resource]?.length ? null : (
    <p className="empty-note">
      No {resource.replaceAll("_", " ")} recorded yet.
    </p>
  );
}

function DraftEditor({
  draft,
  brandName,
  save,
}: {
  draft: Item;
  brandName: string;
  save: (fields: Record<string, FormDataEntryValue>) => Promise<unknown>;
}) {
  const [snapshot, setSnapshot] = useState<Item | null>(null);
  const { busy, writable } = useWork();
  return (
    <div className="evidence">
      <button
        className="text-button"
        disabled={busy || !writable}
        onClick={() => setSnapshot(snapshot ? null : { ...draft })}
      >
        {snapshot ? "Cancel revision" : "Edit draft"}
      </button>
      {snapshot && (
        <Form
          label="Save revision"
          submit={async (form) => {
            const result = await save(Object.fromEntries(form.entries()));
            if (result) setSnapshot(null);
          }}
        >
          <input
            type="hidden"
            name="expected_version"
            value={number(snapshot, "version")}
          />
          <p className="small muted">
            Keep cited claims and the opt-out. Add new facts to Brand Brain
            first. Concurrent edits require refreshing before saving.
          </p>
          <label>
            Subject
            <select name="subject" defaultValue={text(snapshot, "subject")}>
              {["A question from", "Following up from", "A question about"].map(
                (prefix) => {
                  const subject = `${prefix} ${brandName}`.slice(0, 90);
                  return (
                    <option key={prefix} value={subject}>
                      {subject}
                    </option>
                  );
                },
              )}
            </select>
          </label>
          <label>
            Body
            <textarea
              className="large-textarea"
              name="body"
              defaultValue={text(snapshot, "body")}
              minLength={30}
              maxLength={1200}
              required
            />
          </label>
        </Form>
      )}
    </div>
  );
}

function ContactEditor({
  lead,
  save,
}: {
  lead: Item;
  save: (body: Record<string, unknown>) => Promise<unknown>;
}) {
  const [snapshot, setSnapshot] = useState<Item | null>(null);
  const { busy, writable } = useWork();
  return (
    <details
      className="evidence"
      onToggle={(event) => {
        if (event.currentTarget.open && !snapshot) setSnapshot({ ...lead });
        if (!event.currentTarget.open) setSnapshot(null);
      }}
    >
      <summary>Edit contact and approved personalisation</summary>
      {snapshot && (
        <Form
          label="Save contact"
          disabled={busy || !writable || lead.status === "suppressed"}
          submit={async (form) => {
            const result = await save({
              ...Object.fromEntries(form.entries()),
              expected_version: number(snapshot, "version"),
            });
            if (result) setSnapshot(null);
          }}
        >
          <p className="small muted">
            Record the source for contact permission and any observation used in
            outreach. Saving invalidates existing approvals for this contact.
          </p>
          {["name", "company", "domain"].map((field) => (
            <label key={field}>
              {clean(field)}
              <input
                name={field}
                defaultValue={text(snapshot, field)}
                required={field === "name"}
              />
            </label>
          ))}
          <label>
            Contactability basis
            <select
              name="lawful_basis"
              defaultValue={text(snapshot, "lawful_basis")}
            >
              <option value="not_established">Not established</option>
              <option value="consent">Consent</option>
              <option value="legitimate_interest">Legitimate interest</option>
            </select>
          </label>
          <label>
            Evidence for this basis
            <textarea
              name="basis_evidence"
              maxLength={2000}
              defaultValue={text(snapshot, "basis_evidence")}
            />
          </label>
          <label>
            Approved observation for outreach
            <textarea
              name="personalisation"
              maxLength={400}
              defaultValue={text(snapshot, "personalisation")}
            />
          </label>
          <label>
            Private source evidence for the observation
            <textarea
              name="personalisation_evidence"
              maxLength={2000}
              defaultValue={text(snapshot, "personalisation_evidence")}
            />
          </label>
        </Form>
      )}
    </details>
  );
}

export default function GrowthWorkspace({
  identity,
  initial = "Command Center",
}: {
  identity: Identity;
  initial?: Section;
}) {
  const [section, setSection] = useState<Section>(initial);
  const [data, setData] = useState<Record<string, Item[]>>({});
  const [brands, setBrands] = useState<Item[]>([]);
  const [connections, setConnections] = useState<
    { provider: string; enabled: boolean; status: string }[]
  >([]);
  const [analytics, setAnalytics] = useState<Record<string, unknown>>({});
  const [budget, setBudget] = useState<Item | null>(null);
  const [cacheStats, setCacheStats] = useState<Record<string, number>>({});
  const [agents, setAgents] = useState<Record<string, unknown>[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [searchResult, setSearchResult] = useState<unknown>(null);
  const [selectedLeads, setSelectedLeads] = useState<string[]>([]);
  const [checkoutCurrency, setCheckoutCurrency] = useState("USD");
  const [csvText, setCsvText] = useState("");
  const [inboxCursor, setInboxCursor] = useState<string | null>(null);
  const [pageBefore, setPageBefore] = useState<Record<string, number[]>>({});
  const [nextPages, setNextPages] = useState<Record<string, number | null>>({});
  const writable =
    identity.role !== "viewer" && !identity.organization.emergency_stop;
  const owner = identity.role === "owner";
  const admin = ["owner", "admin"].includes(identity.role);

  const refresh = useCallback(async () => {
    const names = [...new Set([...resources[section], "leads", "customers"])];
    const [brandRows, entries] = await Promise.all([
      api<Item[]>("/v1/brands"),
      Promise.all(
        names.map(
          async (name) =>
            [
              name,
              await api<Page>(
                `/v1/data/${name}${pageBefore[name]?.length ? "?before=" + pageBefore[name].at(-1) : ""}`,
              ),
            ] as const,
        ),
      ),
    ]);
    setBrands(brandRows);
    setConnections(
      await api<{ provider: string; enabled: boolean; status: string }[]>(
        "/v1/connections",
      ),
    );
    setData(
      Object.fromEntries(entries.map(([name, page]) => [name, page.items])),
    );
    setNextPages(
      Object.fromEntries(
        entries.map(([name, page]) => [name, page.next_cursor]),
      ),
    );
    if (section === "Analytics")
      setAnalytics(await api<Record<string, unknown>>("/v1/analytics"));
    if (section === "Usage & cost") {
      setBudget(await api<Item>("/v1/budgets/current"));
      setCacheStats(await api<Record<string, number>>("/v1/model-cache"));
    }
    if (section === "Agents")
      setAgents(await api<Record<string, unknown>[]>("/v1/agents"));
  }, [section, pageBefore]);

  useEffect(() => {
    let current = true;
    const load = () =>
      refresh().catch((e) => {
        if (current) setError(e.message);
      });
    load();
    const timer = setInterval(load, 4000);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [refresh]);

  const rows = (resource: string) => data[resource] || [];
  const connected = (provider: string) =>
    connections.some(
      (item) =>
        item.provider === provider &&
        item.enabled &&
        item.status === "verified",
    );
  const leadName = (leadId: unknown) =>
    text(
      rows("leads").find((lead) => lead.id === leadId) || {
        id: "",
        created_at: 0,
      },
      "name",
    ) || String(leadId).slice(0, 8);
  async function act(action: () => Promise<unknown>, message = "Saved.") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await action();
      await refresh();
      setNotice(message);
      return result;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  const post = (
    path: string,
    body: unknown = {},
    message = "Saved.",
    method = "POST",
  ) => act(() => api(path, body, method), message);
  const keyed = (body: Record<string, unknown>) => ({
    ...body,
    idempotency_key: crypto.randomUUID(),
  });

  const fields = (form: FormData) => Object.fromEntries(form.entries());

  return (
    <WorkContext.Provider
      value={{
        busy,
        writable,
        brands,
        leads: rows("leads"),
        customers: rows("customers"),
        data,
      }}
    >
      <div className="operations">
        <aside className="operations-nav" aria-label="Operations navigation">
          {sections.map((name) => (
            <button
              key={name}
              aria-current={section === name ? "page" : undefined}
              onClick={() => {
                setSection(name);
                setError("");
                setNotice("");
                setSearchResult(null);
              }}
            >
              {name}
            </button>
          ))}
        </aside>
        <div className="operations-body">
          <div className="operations-heading">
            <div>
              <p className="eyebrow">
                {connections.some((item) => item.enabled)
                  ? "Workspace"
                  : "Sandbox workspace"}{" "}
                / {section}
              </p>
              <h2>{section}</h2>
            </div>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => act(refresh, "Updated.")}
            >
              Refresh
            </button>
          </div>
          <p className="muted">{descriptions[section]}</p>
          <div className="sandbox-note">
            {connections.some((item) => item.enabled) ? (
              <>
                <b>Connected providers are enabled.</b> Sandbox buttons still
                simulate. A connected-provider execution is a separate explicit
                action and may contact recipients or create bookings.
              </>
            ) : (
              <>
                <b>Sandbox is the default.</b> Sandbox actions contact no
                recipients. Publishing on this server creates a public page;
                connected actions require an enabled provider and an explicit
                execution choice.
              </>
            )}
          </div>
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
          {!writable && (
            <p className="small muted">
              {identity.organization.emergency_stop
                ? "Workspace paused. Reading is available."
                : "Your role has read-only access."}
            </p>
          )}

          {section === "Command Center" && (
            <>
              <Form
                label="Create plan →"
                submit={(form) =>
                  act(async () => {
                    const result = await api<{
                      status: string;
                      missing_fields?: string[];
                    }>(
                      "/v1/commands",
                      keyed({
                        ...fields(form),
                        target: Number(form.get("target")),
                        window_days: Number(form.get("window_days")),
                      }),
                    );
                    if (result.status === "needs_information")
                      throw new Error(
                        `Add these business facts first: ${result.missing_fields?.join(", ")}`,
                      );
                    return result;
                  }, "Planning job queued. Follow its progress in Plans & tasks.")
                }
              >
                <BrandSelect />
                <label>
                  What do you want to achieve?
                  <textarea
                    name="objective"
                    minLength={8}
                    maxLength={500}
                    required
                    placeholder="Describe your business objective and constraints"
                  />
                </label>
                <div className="form-grid">
                  <label>
                    Business goal
                    <select name="goal">
                      <option value="leads">Qualified leads</option>
                      <option value="sales">Sales</option>
                      <option value="cac">Acquisition cost</option>
                      <option value="retention">Retention</option>
                      <option value="efficiency">Efficiency</option>
                    </select>
                  </label>
                  <label>
                    Audience
                    <input
                      name="audience"
                      placeholder="Uses your brand's customer segments if blank"
                    />
                  </label>
                  <label>
                    Target outcome count
                    <input
                      type="number"
                      name="target"
                      defaultValue={10}
                      min={1}
                      max={10000}
                      required
                    />
                  </label>
                  <label>
                    Window in days
                    <input
                      type="number"
                      name="window_days"
                      defaultValue={30}
                      min={1}
                      max={365}
                      required
                    />
                  </label>
                </div>
              </Form>
              <h3>Recent commands</h3>
              {rows("commands").map((row) => (
                <article className="operation-card" key={row.id}>
                  <Status value={row.status} />
                  <h3>{text(row, "raw")}</h3>
                  <Evidence value={row.parsed} />
                </article>
              ))}
              <Empty resource="commands" />
            </>
          )}

          {section === "Plans & tasks" && (
            <>
              <h3>Plans awaiting your direction</h3>
              {rows("plans").map((plan) => (
                <article key={plan.id} className="operation-card">
                  <Status value={plan.status} />
                  <h3>{text(plan, "objective")}</h3>
                  <p>{String(object(plan.payload).execution_plan || "")}</p>
                  <Evidence value={plan.payload} />
                  {plan.status === "draft" && (
                    <button
                      className="primary"
                      disabled={!writable || busy}
                      onClick={() =>
                        post(
                          `/v1/plans/${plan.id}/approve`,
                          {},
                          "Plan approved. Internal tasks are running.",
                        )
                      }
                    >
                      Approve internal plan
                    </button>
                  )}
                </article>
              ))}
              <Empty resource="plans" />
              <h3 className="subheading">Task queue</h3>
              {rows("tasks").map((task) => (
                <article key={task.id} className="operation-card compact">
                  <div className="row-between">
                    <b>
                      {clean(task.type)} / {text(task, "agent_id")}
                    </b>
                    <Status value={task.status} />
                  </div>
                  <p className="small muted">
                    Attempt {number(task, "attempt")} · {date(task.created_at)}{" "}
                    · {task.id.slice(0, 8)}
                  </p>
                  {!!task.error_code && (
                    <p className="error-text">{clean(task.error_code)}</p>
                  )}
                  <Evidence
                    value={{ input: task.input, output: task.output }}
                  />
                  <div className="actions">
                    {["failed", "blocked"].includes(text(task, "status")) && (
                      <button
                        className="secondary"
                        disabled={
                          !writable || busy || number(task, "attempt") >= 3
                        }
                        onClick={() =>
                          post(
                            `/v1/tasks/${task.id}/retry`,
                            {},
                            "Task queued for retry.",
                          )
                        }
                      >
                        Retry
                      </button>
                    )}
                    {(["created", "ready", "blocked"].includes(
                      text(task, "status"),
                    ) ||
                      (task.status === "running" &&
                        task.type !== "checkout")) && (
                      <button
                        className="text-button"
                        disabled={!writable || busy}
                        onClick={() =>
                          post(
                            `/v1/tasks/${task.id}/cancel`,
                            {},
                            "Task cancelled.",
                          )
                        }
                      >
                        Cancel task
                      </button>
                    )}
                  </div>
                </article>
              ))}
              <Empty resource="tasks" />
            </>
          )}

          {section === "Leads & CRM" && (
            <>
              <details className="form-disclosure">
                <summary>Read a public business contact page</summary>
                <p className="small muted">
                  Imports only addresses observed on the same business domain.
                  Review contactability evidence before creating outreach.
                </p>
                <Form
                  label="Read contact page"
                  submit={(form) =>
                    post(
                      "/v1/prospects/enrich",
                      keyed(fields(form)),
                      "Website research queued.",
                    )
                  }
                >
                  <BrandSelect />
                  <label>
                    Business contact page URL
                    <input
                      name="url"
                      type="url"
                      required
                      placeholder="https://business.example/contact"
                    />
                  </label>
                  <label>
                    Company name
                    <input name="company" maxLength={200} />
                  </label>
                </Form>
              </details>
              <details className="form-disclosure">
                <summary>Research prospect websites</summary>
                <p className="small muted">
                  Search returns source suggestions, not verified contacts. No
                  email address or marketing permission is inferred. Connected
                  searches use provider credits and are capped at 100 attempts
                  per workspace per day.
                </p>
                <Form
                  label="Research prospects"
                  submit={(form) =>
                    post(
                      "/v1/prospects/search",
                      keyed({
                        brand_id: form.get("brand_id"),
                        query: form.get("query"),
                        connected_provider:
                          form.get("connected_provider") === "true",
                      }),
                      "Prospect research queued. Results appear below.",
                    )
                  }
                >
                  <BrandSelect />
                  <label>
                    Search query
                    <input
                      name="query"
                      required
                      minLength={3}
                      maxLength={300}
                    />
                  </label>
                  <label>
                    Search mode
                    <select name="connected_provider">
                      <option value="false">Sandbox, no external lookup</option>
                      {connected("brave") && (
                        <option value="true">Connected Brave Search</option>
                      )}
                    </select>
                  </label>
                </Form>
                {rows("tasks")
                  .filter((item) => item.type === "prospect_search")
                  .map((task) => (
                    <article className="operation-card" key={task.id}>
                      <Status value={task.status} />
                      <p>{String(object(task.input).query || "")}</p>
                      <Evidence value={task.output} />
                      {(Array.isArray(object(task.output).results)
                        ? (object(task.output).results as Item[])
                        : []
                      ).map((result) => (
                        <p key={text(result, "url")}>
                          <a
                            href={text(result, "url")}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {text(result, "title")}
                          </a>
                          <br />
                          <small>{text(result, "description")}</small>
                        </p>
                      ))}
                      {!!task.error_code && (
                        <p role="status">{clean(task.error_code)}</p>
                      )}
                    </article>
                  ))}
              </details>
              <details
                className="form-disclosure"
                open={rows("leads").length === 0}
              >
                <summary>Add a sourced contact</summary>
                <Form
                  label="Import contact"
                  submit={(form) =>
                    post(
                      "/v1/leads/import",
                      {
                        leads: [
                          {
                            ...fields(form),
                            source_confidence: Number(
                              form.get("source_confidence"),
                            ),
                          },
                        ],
                      },
                      "Contact imported; duplicates are left unchanged.",
                    )
                  }
                >
                  <BrandSelect />
                  <div className="form-grid">
                    <label>
                      Contact name
                      <input name="name" required maxLength={120} />
                    </label>
                    <label>
                      Email
                      <input
                        name="email"
                        type="email"
                        required
                        maxLength={254}
                      />
                    </label>
                    <label>
                      Company
                      <input name="company" maxLength={200} />
                    </label>
                    <label>
                      Domain
                      <input name="domain" maxLength={250} />
                    </label>
                    <label>
                      Source
                      <input
                        name="source"
                        required
                        minLength={3}
                        placeholder="Where this contact came from"
                      />
                    </label>
                    <label>
                      Source confidence (0–100)
                      <input
                        name="source_confidence"
                        type="number"
                        min={0}
                        max={100}
                        defaultValue={100}
                        required
                      />
                    </label>
                  </div>
                  <label>
                    Contactability basis
                    <select name="lawful_basis">
                      <option value="not_established">
                        Not established — sending blocked
                      </option>
                      <option value="consent">Consent</option>
                      <option value="legitimate_interest">
                        Legitimate interest
                      </option>
                      <option value="existing_customer">
                        Existing customer
                      </option>
                    </select>
                  </label>
                  <label>
                    Evidence for the basis
                    <textarea
                      name="basis_evidence"
                      required
                      minLength={3}
                      placeholder="Record the evidence; selecting an option does not establish legal compliance"
                    />
                  </label>
                </Form>
              </details>
              <div className="pipeline-summary">
                {[
                  "discovered",
                  "qualified",
                  "contacted",
                  "replied",
                  "meeting_set",
                  "converted",
                  "suppressed",
                ].map((stage) => (
                  <div key={stage}>
                    <b>
                      {rows("leads").filter((l) => l.status === stage).length}
                    </b>
                    <small>{clean(stage)}</small>
                  </div>
                ))}
              </div>
              {rows("leads").map((lead) => (
                <article className="operation-card" key={lead.id}>
                  <div className="row-between">
                    <h3>{text(lead, "name")}</h3>
                    <Status value={lead.status} />
                  </div>
                  <p>
                    {text(lead, "company")} · {text(lead, "email")} · Score{" "}
                    {number(lead, "score")}
                  </p>
                  <p className="small muted">
                    Source: {text(lead, "source")} · Basis:{" "}
                    {clean(lead.lawful_basis)}
                  </p>
                  <Evidence value={lead} />
                  <ContactEditor
                    lead={lead}
                    save={(body) =>
                      post(
                        `/v1/leads/${lead.id}`,
                        body,
                        "Contact updated; previous approvals invalidated.",
                        "PUT",
                      )
                    }
                  />
                  <div className="actions">
                    <button
                      className="secondary"
                      disabled={
                        !writable || busy || lead.status === "suppressed"
                      }
                      onClick={() =>
                        post(
                          `/v1/leads/${lead.id}/score`,
                          {},
                          "Qualification score updated.",
                        )
                      }
                    >
                      Score contact
                    </button>
                    <button
                      className="text-button"
                      disabled={
                        !writable || busy || lead.status === "suppressed"
                      }
                      onClick={() =>
                        post(
                          "/v1/drafts",
                          keyed({ lead_id: lead.id }),
                          "Drafting job queued. See Outreach.",
                        )
                      }
                    >
                      Create draft →
                    </button>
                    <button
                      className="text-button"
                      disabled={
                        !writable || busy || lead.status === "suppressed"
                      }
                      onClick={() =>
                        post(
                          "/v1/suppressions",
                          { email: lead.email, reason: "manual" },
                          "Contact suppressed.",
                        )
                      }
                    >
                      Suppress contact
                    </button>
                  </div>
                  <details className="evidence">
                    <summary>Change pipeline stage</summary>
                    <Form
                      label="Update stage"
                      submit={(form) =>
                        post(
                          `/v1/leads/${lead.id}/stage`,
                          fields(form),
                          "Stage updated with activity record.",
                        )
                      }
                    >
                      <label>
                        Stage
                        <select
                          name="status"
                          defaultValue={text(lead, "status")}
                        >
                          <option value="discovered">Discovered</option>
                          <option value="enriched">Enriched</option>
                          <option value="qualified">Qualified</option>
                          <option value="disqualified">Disqualified</option>
                          <option value="contacted">Contacted</option>
                          <option value="replied">Replied</option>
                          <option value="meeting_set">Meeting set</option>
                          <option value="dormant">Dormant</option>
                        </select>
                      </label>
                      <label>
                        Reason
                        <input name="reason" minLength={3} required />
                      </label>
                    </Form>
                  </details>
                </article>
              ))}
              <Empty resource="leads" />
            </>
          )}

          {section === "Outreach" && (
            <>
              <Form
                label="Queue draft"
                submit={(form) =>
                  post(
                    "/v1/drafts",
                    keyed(fields(form)),
                    "Drafting job queued.",
                  )
                }
              >
                <LeadSelect />
              </Form>
              {rows("outreach_drafts").map((draft) => (
                <article key={draft.id} className="operation-card">
                  <div className="row-between">
                    <p className="eyebrow">
                      {leadName(draft.lead_id)} / Version{" "}
                      {number(draft, "version")}
                    </p>
                    <Status value={draft.status} />
                  </div>
                  <h3>{text(draft, "subject")}</h3>
                  <p className="preserve">{text(draft, "body")}</p>
                  <Evidence value={draft.claims} />
                  {draft.status !== "sent" && (
                    <>
                      <button
                        className="primary"
                        disabled={!writable || busy}
                        onClick={() =>
                          post(
                            `/v1/drafts/${draft.id}/request-approval`,
                            {},
                            "Approval requested. Review it in Approvals.",
                          )
                        }
                      >
                        Request send approval →
                      </button>
                      <DraftEditor
                        draft={draft}
                        brandName={text(
                          brands.find(
                            (b) =>
                              b.id ===
                              rows("leads").find((l) => l.id === draft.lead_id)
                                ?.brand_id,
                          ) || { id: "", created_at: 0 },
                          "name",
                        )}
                        save={(body) =>
                          post(
                            `/v1/drafts/${draft.id}`,
                            body,
                            "Revision saved and affected approvals revoked.",
                            "PUT",
                          )
                        }
                      />
                    </>
                  )}
                </article>
              ))}
              <Empty resource="outreach_drafts" />
            </>
          )}

          {section === "Approvals" && (
            <>
              {rows("approvals").map((approval) => (
                <article key={approval.id} className="operation-card">
                  <div className="row-between">
                    <h3>{clean(approval.action_class)}</h3>
                    <Status
                      value={
                        number(approval, "expires_at") < Date.now() / 1000 &&
                        approval.status === "pending"
                          ? "expired"
                          : approval.status
                      }
                    />
                  </div>
                  <p className="small muted">
                    Expires {date(approval.expires_at)} · Payload hash{" "}
                    {text(approval, "payload_hash").slice(0, 16)}
                  </p>
                  <pre className="payload-preview">
                    {JSON.stringify(approval.payload, null, 2)}
                  </pre>
                  <div className="actions">
                    {approval.status === "approved" &&
                      ((approval.action_class === "send_email" &&
                        connected("gmail")) ||
                        (approval.action_class === "send_bulk_campaign" &&
                          connected("resend")) ||
                        (approval.action_class === "book_meeting" &&
                          connected("calendar"))) && (
                        <button
                          className="primary"
                          disabled={!writable || busy}
                          onClick={() =>
                            post(
                              "/v1/effects/execute",
                              {
                                approval_id: approval.id,
                                idempotency_key: `execute-live:${approval.id}`,
                                execution_mode: "live",
                              },
                              "Provider dispatch queued. Check its receipt in the execution log below.",
                            )
                          }
                        >
                          Execute with connected provider
                        </button>
                      )}
                    {approval.status === "pending" && (
                      <>
                        <button
                          className="primary"
                          disabled={
                            !writable ||
                            !admin ||
                            busy ||
                            (approval.action_class === "send_bulk_campaign" &&
                              !owner)
                          }
                          onClick={() =>
                            post(
                              `/v1/approvals/${approval.id}/decision`,
                              { decision: "approved" },
                              "Approved. Execution is a separate action.",
                            )
                          }
                        >
                          Approve exact payload
                        </button>
                        <button
                          className="secondary"
                          disabled={!writable || !admin || busy}
                          onClick={() =>
                            post(
                              `/v1/approvals/${approval.id}/decision`,
                              { decision: "rejected" },
                              "Rejected.",
                            )
                          }
                        >
                          Reject
                        </button>
                      </>
                    )}
                    {approval.status === "approved" &&
                      approval.action_class === "publish_content" &&
                      admin && (
                        <button
                          className="secondary"
                          disabled={!writable || busy}
                          onClick={() =>
                            post(
                              "/v1/effects/execute",
                              {
                                approval_id: approval.id,
                                idempotency_key: `publish-local:${approval.id}`,
                                execution_mode: "local",
                              },
                              "Published on this server. The public link is in Execution receipts.",
                            )
                          }
                        >
                          Publish on this server
                        </button>
                      )}
                    {approval.status === "approved" && (
                      <button
                        className="primary"
                        disabled={!writable || busy}
                        onClick={() =>
                          post(
                            "/v1/effects/execute",
                            {
                              approval_id: approval.id,
                              idempotency_key: `execute:${approval.id}`,
                            },
                            "Sandbox action completed. No real external action occurred.",
                          )
                        }
                      >
                        Execute in sandbox
                      </button>
                    )}
                  </div>
                </article>
              ))}
              <Empty resource="approvals" />
              <h3 className="subheading">Execution receipts</h3>
              {rows("effects").map((effect) => (
                <article className="operation-card compact" key={effect.id}>
                  <Status value={effect.status} />
                  <p>{clean(effect.action)}</p>
                  <Evidence value={effect.result} />
                  {effect.status === "uncertain" && owner && (
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        post(
                          `/v1/effects/${effect.id}/reconcile`,
                          {},
                          "Provider receipt check completed. An unconfirmed result is not retried automatically.",
                        )
                      }
                    >
                      Check provider receipt
                    </button>
                  )}
                </article>
              ))}
            </>
          )}

          {section === "Inbox" && (
            <>
              {connected("gmail") && (
                <div className="operation-card">
                  <h3>Connected Gmail inbox</h3>
                  <p className="small muted">
                    Import up to 20 messages per page from known CRM contacts.
                    Unknown senders, attachments and messages without plain text
                    are skipped. No reply is sent automatically.
                  </p>
                  <div className="actions">
                    <button
                      className="primary"
                      disabled={busy || !writable}
                      onClick={async () => {
                        const result = await post(
                          "/v1/inbox/sync",
                          { cursor: inboxCursor },
                          "Inbox page checked. See counts below.",
                        );
                        if (result) {
                          const page = result as { next_cursor: string | null };
                          setInboxCursor(page.next_cursor);
                          setSearchResult(result);
                        }
                      }}
                    >
                      {inboxCursor
                        ? "Import next inbox page"
                        : "Check connected inbox"}
                    </button>
                    {inboxCursor && (
                      <button
                        className="secondary"
                        onClick={() => setInboxCursor(null)}
                      >
                        Start from latest
                      </button>
                    )}
                  </div>
                  {searchResult != null && <Evidence value={searchResult} />}
                </div>
              )}
              <details className="form-disclosure">
                <summary>Simulate an inbound reply</summary>
                <Form
                  label="Receive test reply"
                  submit={(form) =>
                    post(
                      "/v1/inbox/simulate",
                      keyed(fields(form)),
                      "Reply received and classified.",
                    )
                  }
                >
                  <LeadSelect />
                  <label>
                    Subject
                    <input
                      name="subject"
                      defaultValue="Reply"
                      maxLength={200}
                    />
                  </label>
                  <label>
                    Message
                    <textarea
                      name="body"
                      required
                      maxLength={5000}
                      placeholder="Try an interested reply, a pricing question, or an unsubscribe"
                    />
                  </label>
                </Form>
              </details>
              {rows("messages").map((message) => (
                <article key={message.id} className="operation-card">
                  <div className="row-between">
                    <p className="eyebrow">
                      {clean(message.direction)} / {leadName(message.lead_id)}
                    </p>
                    <Status value={message.status} />
                  </div>
                  <h3>{text(message, "subject")}</h3>
                  <p className="preserve">{text(message, "body")}</p>
                  {message.direction === "inbound" && (
                    <>
                      <p className="small">
                        Intent:{" "}
                        <b>{clean(object(message.classification).label)}</b> ·
                        Confidence{" "}
                        {Number(
                          object(message.classification).confidence || 0,
                        ).toFixed(2)}
                        {object(message.classification).escalate
                          ? " · Human review required"
                          : ""}
                      </p>
                      {["interested", "meeting_request"].includes(
                        String(object(message.classification).label),
                      ) && (
                        <button
                          className="secondary"
                          disabled={!writable || busy}
                          onClick={() =>
                            post(
                              `/v1/messages/${message.id}/draft-reply`,
                              keyed({}),
                              "Reply drafting queued. It still needs send approval.",
                            )
                          }
                        >
                          Draft a reply
                        </button>
                      )}
                    </>
                  )}
                  <p className="small muted">
                    {message.simulated ? "Sandbox message" : "Provider message"}{" "}
                    · {date(message.created_at)}
                  </p>
                </article>
              ))}
              <Empty resource="messages" />
            </>
          )}

          {section === "Content" && (
            <>
              <Form
                label="Generate grounded draft"
                submit={(form) =>
                  post(
                    "/v1/content/generate",
                    keyed(fields(form)),
                    "Content job queued.",
                  )
                }
              >
                <BrandSelect />
                <div className="form-grid">
                  <label>
                    Format
                    <select name="type">
                      <option value="landing_page">Landing page</option>
                      <option value="article">Article</option>
                      <option value="seo">SEO outline</option>
                      <option value="social">Social draft</option>
                      <option value="creative_brief">Creative brief</option>
                    </select>
                  </label>
                  <label>
                    Topic
                    <input
                      name="topic"
                      required
                      minLength={3}
                      maxLength={200}
                    />
                  </label>
                </div>
              </Form>
              {rows("content_items").map((item) => (
                <article className="operation-card" key={item.id}>
                  <Status value={item.status} />
                  <p className="eyebrow">{clean(item.type)}</p>
                  <h3>{text(item, "title")}</h3>
                  <p className="preserve">{text(item, "body")}</p>
                  <Evidence value={item.citations} />
                  {item.status === "published_local" && (
                    <div className="actions">
                      <a
                        href={`/api/v1/public/${identity.organization.id}/${item.id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Open published page
                      </a>
                      <button
                        className="secondary"
                        disabled={!writable || busy || !admin}
                        onClick={() =>
                          post(
                            `/v1/content/${item.id}/unpublish`,
                            {},
                            "Public page removed. A new approval is required before publishing again.",
                          )
                        }
                      >
                        Unpublish
                      </button>
                    </div>
                  )}
                  {item.status === "draft" && (
                    <button
                      className="secondary"
                      disabled={!writable || busy}
                      onClick={() =>
                        post(
                          `/v1/content/${item.id}/request-approval`,
                          {},
                          "Publishing approval requested.",
                        )
                      }
                    >
                      Request publish approval
                    </button>
                  )}
                </article>
              ))}
              <Empty resource="content_items" />
            </>
          )}

          {section === "Campaigns" && (
            <>
              <Form
                label="Create reviewed batch"
                submit={(form) =>
                  post(
                    "/v1/campaigns",
                    {
                      ...fields(form),
                      lead_ids: selectedLeads,
                      budget_micros: Math.round(
                        Number(form.get("budget_micros")) * 1_000_000,
                      ),
                    },
                    "Campaign created. Prepare each contact's draft before requesting approval.",
                  )
                }
              >
                <BrandSelect />
                <label>
                  Campaign name
                  <input name="name" required minLength={3} maxLength={160} />
                </label>
                <label>
                  Campaign budget (USD)
                  <input
                    name="budget_micros"
                    type="number"
                    step="0.01"
                    min={0}
                    defaultValue={0}
                    required
                  />
                </label>
                <div className="contact-picker">
                  <p className="small">
                    Select up to 20 contacts from the same brand.
                  </p>
                  {rows("leads")
                    .filter((l) => l.status !== "suppressed")
                    .map((lead) => (
                      <label className="check-label" key={lead.id}>
                        <input
                          type="checkbox"
                          checked={selectedLeads.includes(lead.id)}
                          onChange={(e) =>
                            setSelectedLeads(
                              e.target.checked
                                ? [...selectedLeads, lead.id]
                                : selectedLeads.filter((id) => id !== lead.id),
                            )
                          }
                        />
                        {text(lead, "name")} — {text(lead, "email")}
                      </label>
                    ))}
                </div>
              </Form>
              {rows("campaigns").map((campaign) => (
                <article className="operation-card" key={campaign.id}>
                  <div className="row-between">
                    <h3>{text(campaign, "name")}</h3>
                    <Status value={campaign.status} />
                  </div>
                  <p>
                    {Array.isArray(campaign.lead_ids)
                      ? campaign.lead_ids.length
                      : 0}{" "}
                    contacts · Budget {money(campaign.budget_micros)}
                  </p>
                  <div className="actions">
                    <button
                      className="primary"
                      disabled={
                        !writable || busy || campaign.status === "completed"
                      }
                      onClick={() =>
                        post(
                          `/v1/campaigns/${campaign.id}/request-approval`,
                          {},
                          "Batch approval requested from an owner.",
                        )
                      }
                    >
                      Request batch approval
                    </button>
                    <button
                      className="secondary"
                      disabled={
                        !writable || busy || campaign.status === "completed"
                      }
                      onClick={() =>
                        post(
                          `/v1/campaigns/${campaign.id}/pause`,
                          {},
                          "Campaign paused.",
                        )
                      }
                    >
                      Pause campaign
                    </button>
                  </div>
                </article>
              ))}
              <Empty resource="campaigns" />
            </>
          )}

          {section === "Meetings" && (
            <>
              <Form
                label="Propose & request approval"
                submit={(form) =>
                  post(
                    "/v1/meetings/propose",
                    {
                      lead_id: form.get("lead_id"),
                      title: form.get("title"),
                      starts_at:
                        new Date(String(form.get("start"))).getTime() / 1000,
                      duration_minutes: Number(form.get("duration_minutes")),
                      timezone:
                        Intl.DateTimeFormat().resolvedOptions().timeZone,
                    },
                    "Meeting proposed. Review the booking in Approvals.",
                  )
                }
              >
                <LeadSelect />
                <label>
                  Meeting title
                  <input name="title" minLength={3} maxLength={200} required />
                </label>
                <div className="form-grid">
                  <label>
                    Start time — your local timezone
                    <input name="start" type="datetime-local" required />
                  </label>
                  <label>
                    Duration
                    <select name="duration_minutes">
                      <option value="30">30 minutes</option>
                      <option value="45">45 minutes</option>
                      <option value="60">60 minutes</option>
                    </select>
                  </label>
                </div>
              </Form>
              {rows("meetings").map((meeting) => (
                <article className="operation-card" key={meeting.id}>
                  <Status value={meeting.status} />
                  <h3>{text(meeting, "title")}</h3>
                  <p>
                    {leadName(meeting.lead_id)} · {date(meeting.starts_at)}
                  </p>
                  <p className="small muted">
                    {text(meeting, "timezone")} ·{" "}
                    {text(meeting, "provider_id") ||
                      "Awaiting approved booking"}
                  </p>
                </article>
              ))}
              <Empty resource="meetings" />
            </>
          )}

          {section === "Revenue" && (
            <>
              <Form
                label="Create checkout"
                disabled={!writable || !owner}
                submit={(form) =>
                  post(
                    "/v1/checkouts",
                    {
                      ...fields(form),
                      amount_minor: Math.round(
                        Number(form.get("amount_minor")) *
                          currencyFactor(String(form.get("currency"))),
                      ),
                      recurring: form.get("recurring") === "on",
                    },
                    form.get("execution_mode") === "live"
                      ? "Checkout creation queued with your connected Stripe account. Its URL will appear after the provider responds."
                      : "Sandbox checkout created. Simulate a signed test payment to exercise onboarding.",
                  )
                }
              >
                <LeadSelect />
                <label>
                  Description
                  <input
                    name="description"
                    required
                    minLength={3}
                    maxLength={200}
                  />
                </label>
                <label>
                  Execution
                  <select name="execution_mode">
                    <option value="sandbox">Sandbox checkout</option>
                    {connected("stripe") && (
                      <option value="live">Connected Stripe account</option>
                    )}
                  </select>
                </label>
                <div className="form-grid">
                  <label>
                    Amount ({checkoutCurrency})
                    <input
                      name="amount_minor"
                      type="number"
                      min={1 / currencyFactor(checkoutCurrency)}
                      step={1 / currencyFactor(checkoutCurrency)}
                      required
                      placeholder="Enter the actual price"
                    />
                  </label>
                  <label>
                    Currency
                    <select
                      name="currency"
                      value={checkoutCurrency}
                      onChange={(e) => setCheckoutCurrency(e.target.value)}
                    >
                      {currencies.map((code) => (
                        <option key={code}>{code}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <label className="check-label">
                  <input type="checkbox" name="recurring" />
                  Monthly recurring service
                </label>
              </Form>
              {rows("checkouts").map((checkout) => (
                <article key={checkout.id} className="operation-card">
                  <Status value={checkout.status} />
                  <h3>{text(checkout, "description")}</h3>
                  <p>
                    {leadName(checkout.lead_id)} · {text(checkout, "currency")}{" "}
                    {displayMoney(
                      number(checkout, "amount_minor"),
                      text(checkout, "currency"),
                    )}
                  </p>
                  {!!checkout.url && (
                    <p>
                      <a
                        href={text(checkout, "url")}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Open provider checkout →
                      </a>
                    </p>
                  )}
                  {checkout.status === "pending" &&
                    text(checkout, "provider_ref").startsWith("sandbox:") && (
                      <button
                        className="primary"
                        disabled={!writable || !owner || busy}
                        onClick={() =>
                          post(
                            `/v1/checkouts/${checkout.id}/simulate-payment`,
                            { event_id: `sandbox-event:${checkout.id}` },
                            "Signed sandbox payment event processed. No real money moved.",
                          )
                        }
                      >
                        Simulate successful payment
                      </button>
                    )}
                  <Evidence value={checkout} />
                </article>
              ))}
              <Empty resource="checkouts" />
              <h3 className="subheading">Payment ledger</h3>
              {rows("payments").map((payment) => (
                <article key={payment.id} className="operation-card compact">
                  <b>
                    {text(payment, "currency")} ·{" "}
                    {displayMoney(
                      number(payment, "amount_minor"),
                      text(payment, "currency"),
                    )}
                  </b>
                  <p className="small">
                    {text(payment, "provider_event_id")} ·{" "}
                    {payment.simulated
                      ? "Simulated"
                      : "Verified provider event"}
                  </p>
                </article>
              ))}
              <h3 className="subheading">Subscriptions</h3>
              {rows("subscriptions").map((subscription) => (
                <article
                  className="operation-card compact"
                  key={subscription.id}
                >
                  <Status value={subscription.status} />
                  <p>
                    {displayMoney(
                      number(subscription, "amount_minor"),
                      text(subscription, "currency"),
                    )}{" "}
                    / month
                  </p>
                  <p className="small muted">
                    Period ends {date(subscription.current_period_end)}
                  </p>
                </article>
              ))}
              <details className="form-disclosure">
                <summary>Test subscription and refund receipts</summary>
                <p className="small muted">
                  Only paid sandbox checkouts appear. These controls record
                  simulated receipts; they do not change a provider account or
                  transfer money.
                </p>
                <Form
                  label="Simulate lifecycle event"
                  disabled={!owner || !writable}
                  submit={(form) =>
                    post(
                      `/v1/checkouts/${form.get("checkout_id")}/simulate-lifecycle`,
                      keyed({ kind: form.get("kind") }),
                      "Sandbox lifecycle receipt processed.",
                    )
                  }
                >
                  <label>
                    Paid test checkout
                    <select name="checkout_id" required>
                      <option value="">Choose a paid test checkout</option>
                      {rows("checkouts")
                        .filter(
                          (item) =>
                            item.status === "paid" &&
                            text(item, "provider_ref").startsWith("sandbox:"),
                        )
                        .map((item) => (
                          <option key={item.id} value={item.id}>
                            {text(item, "description")}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Receipt
                    <select name="kind">
                      <option value="renewal">Subscription renewal</option>
                      <option value="payment_failed">
                        Subscription payment failure
                      </option>
                      <option value="cancel">Subscription cancellation</option>
                      <option value="refund">Full checkout refund</option>
                    </select>
                  </label>
                </Form>
              </details>
              <h3 className="subheading">Provider lifecycle receipts</h3>
              {rows("provider_events")
                .filter((item) => item.provider !== "brave")
                .map((item) => (
                  <article className="operation-card compact" key={item.id}>
                    <Status
                      value={
                        item.simulated ? "Test receipt" : "Verified receipt"
                      }
                    />
                    <h3>{clean(item.kind)}</h3>
                    <Evidence value={item} />
                  </article>
                ))}
            </>
          )}

          {section === "Customers" && (
            <>
              {rows("customers").map((customer) => (
                <article className="operation-card" key={customer.id}>
                  <Status value={customer.status} />
                  <h3>{leadName(customer.lead_id)}</h3>
                  <p>Health score: {number(customer, "health_score")}/100</p>
                  <Form
                    label="Save onboarding progress"
                    submit={(form) =>
                      post(
                        `/v1/customers/${customer.id}/onboarding`,
                        { completed: form.getAll("completed") },
                        "Onboarding updated.",
                        "PUT",
                      )
                    }
                  >
                    {(Array.isArray(customer.onboarding)
                      ? customer.onboarding
                      : []
                    ).map((entry, index) => {
                      const step = object(entry);
                      return (
                        <label className="check-label" key={index}>
                          <input
                            name="completed"
                            type="checkbox"
                            value={String(step.step)}
                            defaultChecked={!!step.done}
                          />
                          {String(step.step)}
                        </label>
                      );
                    })}
                  </Form>
                </article>
              ))}
              <Empty resource="customers" />
            </>
          )}

          {section === "Support" && (
            <>
              <Form
                label="Open support request"
                submit={(form) =>
                  post("/v1/support", fields(form), "Support request recorded.")
                }
              >
                <CustomerSelect />
                <label>
                  Subject
                  <input
                    name="subject"
                    minLength={3}
                    maxLength={200}
                    required
                  />
                </label>
                <label>
                  Request
                  <textarea
                    name="body"
                    minLength={3}
                    maxLength={5000}
                    required
                  />
                </label>
              </Form>
              {rows("support_threads").map((thread) => (
                <article className="operation-card" key={thread.id}>
                  <Status value={thread.status} />
                  <h3>{text(thread, "subject")}</h3>
                  <p className="preserve">{text(thread, "body")}</p>
                  {!!thread.response && (
                    <blockquote>{text(thread, "response")}</blockquote>
                  )}
                  <Form
                    label="Save human response"
                    disabled={
                      !writable || (thread.status === "escalated" && !admin)
                    }
                    submit={(form) =>
                      post(
                        `/v1/support/${thread.id}`,
                        fields(form),
                        "Response recorded internally; no email was sent.",
                        "PUT",
                      )
                    }
                  >
                    <label>
                      Response
                      <textarea
                        name="response"
                        minLength={3}
                        maxLength={5000}
                        required
                        defaultValue={text(thread, "response")}
                      />
                    </label>
                    <label>
                      Status
                      <select
                        name="status"
                        defaultValue={text(thread, "status")}
                      >
                        <option value="open">Open</option>
                        <option value="resolved">Resolved</option>
                        <option value="escalated">Escalated</option>
                      </select>
                    </label>
                  </Form>
                </article>
              ))}
            </>
          )}

          {section === "Automation" && (
            <>
              <Form
                label="Create automation rule"
                submit={(form) =>
                  post(
                    "/v1/workflows",
                    { ...fields(form), enabled: true },
                    "Rule created.",
                  )
                }
              >
                <label>
                  Name
                  <input name="name" minLength={3} maxLength={160} required />
                </label>
                <div className="form-grid">
                  <label>
                    Event
                    <select name="trigger">
                      <option value="lead.created">Lead created</option>
                      <option value="message.received">Message received</option>
                      <option value="payment.succeeded">
                        Payment succeeded
                      </option>
                    </select>
                  </label>
                  <label>
                    Action
                    <select name="action">
                      <option value="notify_owner">
                        Notify owner internally
                      </option>
                      <option value="score_lead">
                        Score lead (lead created only)
                      </option>
                      <option value="onboarding_checklist">
                        Onboarding checklist (payment only)
                      </option>
                    </select>
                  </label>
                </div>
              </Form>
              {rows("workflows").map((workflow) => (
                <article key={workflow.id} className="operation-card">
                  <Status value={workflow.enabled ? "enabled" : "disabled"} />
                  <h3>{text(workflow, "name")}</h3>
                  <p>
                    {text(workflow, "trigger")} → {clean(workflow.action)}
                  </p>
                  <Form
                    label="Run against recorded event"
                    submit={(form) =>
                      post(
                        `/v1/workflows/${workflow.id}/run`,
                        keyed(fields(form)),
                        "Automation ran once for this event.",
                      )
                    }
                  >
                    <label>
                      Recorded subject ID
                      <input
                        name="subject_id"
                        required
                        placeholder="Lead, inbound message or payment ID for this trigger"
                      />
                    </label>
                  </Form>
                </article>
              ))}
              <Empty resource="workflows" />
              {rows("workflow_runs").map((run) => (
                <article className="operation-card compact" key={run.id}>
                  <Status value={run.status} />
                  <Evidence value={run.output} />
                </article>
              ))}
            </>
          )}

          {section === "Learning" && (
            <>
              <Form
                label="Save evidence-based lesson"
                submit={(form) =>
                  post(
                    "/v1/learning",
                    {
                      lesson: form.get("lesson"),
                      effect_size: Number(form.get("effect_size")),
                      evidence: String(form.get("evidence"))
                        .split("\n")
                        .map((x) => x.trim())
                        .filter(Boolean),
                    },
                    "Lesson saved with its evidence.",
                  )
                }
              >
                <label>
                  Lesson
                  <textarea
                    name="lesson"
                    required
                    minLength={10}
                    maxLength={3000}
                  />
                </label>
                <label>
                  Evidence IDs — one per line
                  <textarea
                    name="evidence"
                    required
                    placeholder="Use task, message, plan, campaign or payment IDs from Details & evidence"
                  />
                </label>
                <label>
                  Measured effect size (%)
                  <input
                    name="effect_size"
                    type="number"
                    min={-100}
                    max={100}
                    required
                  />
                </label>
              </Form>
              {rows("learning_records").map((lesson) => (
                <article className="operation-card" key={lesson.id}>
                  <h3>{text(lesson, "lesson")}</h3>
                  <p>Effect size: {number(lesson, "effect_size")}%</p>
                  <Evidence value={lesson.evidence} />
                </article>
              ))}
              <Empty resource="learning_records" />
            </>
          )}

          {section === "Analytics" && (
            <>
              <div className="analytics-grid">
                {[
                  "leads",
                  "sent",
                  "human_replies",
                  "meetings",
                  "customers",
                  "tasks",
                ].map((name) => (
                  <div key={name}>
                    <span className="eyebrow">{clean(name)}</span>
                    <strong>{String(analytics[name] ?? "—")}</strong>
                  </div>
                ))}
              </div>
              <div className="two-col">
                <section>
                  <h3>Sandbox net revenue</h3>
                  {Object.entries(
                    object(analytics.net_simulated_revenue_minor),
                  ).map(([currency, amount]) => (
                    <p key={currency}>
                      {displayMoney(Number(amount), currency)}
                    </p>
                  ))}
                  <p className="small muted">
                    Test receipts only. These amounts are not real revenue.
                  </p>
                </section>
                <section>
                  <h3>Real net verified revenue</h3>
                  {Object.entries(
                    object(analytics.net_verified_revenue_minor),
                  ).map(([currency, amount]) => (
                    <p key={currency}>
                      {displayMoney(Number(amount), currency)}
                    </p>
                  ))}
                  <p className="small muted">
                    Signed live payment receipts less recorded refunds. Disputes
                    require review; fees and taxes are not deducted.
                  </p>
                </section>
              </div>
              <p>
                Model usage cost: <b>{money(analytics.cost_micros)}</b>
              </p>
              <p className="muted">{String(analytics.cost_note || "")}</p>
              <Evidence value={analytics} />
            </>
          )}

          {section === "Agents" && (
            <div className="agent-grid">
              {agents.map((agent) => (
                <article className="operation-card" key={String(agent.id)}>
                  <p className="eyebrow">
                    {String(agent.id)} / {String(agent.tier)} /{" "}
                    {String(agent.ceiling)}
                  </p>
                  <h3>{String(agent.name)}</h3>
                  <p className="small muted">
                    Tools:{" "}
                    {Array.isArray(agent.tools) ? agent.tools.join(", ") : ""}
                  </p>
                  <Status value={agent.enabled ? "enabled" : "disabled"} />
                  <button
                    className="secondary"
                    disabled={!owner || !writable || busy}
                    onClick={() =>
                      post(
                        `/v1/agents/${agent.id}`,
                        { enabled: !agent.enabled },
                        "Role configuration updated.",
                        "PUT",
                      )
                    }
                  >
                    {agent.enabled ? "Disable role" : "Enable role"}
                  </button>
                </article>
              ))}
            </div>
          )}

          {section === "Usage & cost" && (
            <>
              <article className="operation-card">
                <h3>Reuse validated responses</h3>
                <p>
                  {cacheStats.cache_hits || 0} cache hits ·{" "}
                  {cacheStats.provider_calls_avoided || 0} paid provider calls
                  avoided · {cacheStats.validated_responses || 0} current cached
                  responses.
                </p>
                <p className="small muted">
                  Identical requests reuse validated output for{" "}
                  {cacheStats.expiry_hours || 0} hours. Changes to source claims
                  or approved observations create a new request. Cache hits cost
                  zero in the model ledger.
                </p>
                <button
                  className="secondary"
                  disabled={!owner || !writable || busy}
                  onClick={() =>
                    post("/v1/model-cache/clear", {}, "Response cache cleared.")
                  }
                >
                  Clear response cache
                </button>
              </article>
              {budget && (
                <>
                  <div className="stats">
                    <div>
                      <span className="eyebrow">Monthly limit</span>
                      <strong>{money(budget.limit_micros)}</strong>
                    </div>
                    <div>
                      <span className="eyebrow">Spent</span>
                      <strong>{money(budget.spent_micros)}</strong>
                    </div>
                    <div>
                      <span className="eyebrow">Reserved</span>
                      <strong>{money(budget.reserved_micros)}</strong>
                    </div>
                  </div>
                  <Form
                    label="Update budget & cap"
                    disabled={!writable || !owner}
                    submit={(form) =>
                      post(
                        "/v1/budgets/current",
                        {
                          limit_micros: Math.round(
                            Number(form.get("limit_micros")) * 1_000_000,
                          ),
                          daily_send_cap: Number(form.get("daily_send_cap")),
                        },
                        "Budget updated.",
                        "PUT",
                      )
                    }
                  >
                    <div className="form-grid">
                      <label>
                        Monthly model budget (USD)
                        <input
                          name="limit_micros"
                          type="number"
                          min={0}
                          max={1000}
                          step="0.000001"
                          defaultValue={
                            number(budget, "limit_micros") / 1_000_000
                          }
                          required
                        />
                        <small>Set zero to block model work.</small>
                      </label>
                      <label>
                        Daily send cap
                        <input
                          name="daily_send_cap"
                          type="number"
                          min={0}
                          max={1000}
                          defaultValue={number(budget, "daily_send_cap")}
                          required
                        />
                      </label>
                    </div>
                  </Form>
                </>
              )}
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Role / model</th>
                      <th>Status</th>
                      <th>Cost</th>
                      <th>Mode</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows("model_usage").map((usage) => (
                      <tr key={usage.id}>
                        <td>
                          {text(usage, "agent_id")}
                          <br />
                          <small>{text(usage, "model_id")}</small>
                        </td>
                        <td>{clean(usage.status)}</td>
                        <td>
                          {usage.settled === false && !usage.simulated
                            ? "Unknown (reserved)"
                            : money(usage.cost_micros)}
                        </td>
                        <td>{usage.simulated ? "Sandbox" : "Live"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {owner &&
                rows("model_usage")
                  .filter(
                    (usage) =>
                      usage.settled === false && usage.status !== "reserved",
                  )
                  .map((usage) => (
                    <details className="form-disclosure" key={usage.id}>
                      <summary>
                        Reconcile held cost ·{" "}
                        {text(usage, "request_id").slice(0, 8)}
                      </summary>
                      <p>
                        Unknown cost holds {money(usage.reserved_micros)}. Use a
                        provider receipt to settle once; actual costs can exceed
                        the reservation.
                      </p>
                      <button
                        className="secondary"
                        disabled={busy || !writable || !usage.provider_ref}
                        onClick={() =>
                          post(
                            `/v1/model-usage/${usage.id}/reconcile`,
                            {},
                            "Provider cost receipt reconciled.",
                          )
                        }
                      >
                        Retrieve provider cost
                      </button>
                      <Form
                        label="Record receipt cost"
                        submit={(form) =>
                          post(
                            `/v1/model-usage/${usage.id}/reconcile`,
                            {
                              cost_micros: Math.round(
                                Number(form.get("amount")) * 1000000,
                              ),
                              evidence: form.get("evidence"),
                            },
                            "Receipt cost recorded and reservation released.",
                          )
                        }
                      >
                        <label>
                          Actual cost (USD)
                          <input
                            name="amount"
                            type="number"
                            min={0}
                            max={1000}
                            step="0.000001"
                            required
                          />
                        </label>
                        <label>
                          Receipt evidence
                          <input
                            name="evidence"
                            minLength={10}
                            maxLength={1000}
                            required
                          />
                        </label>
                      </Form>
                    </details>
                  ))}
            </>
          )}

          {section === "Knowledge" && (
            <>
              <details className="form-disclosure">
                <summary>Import a PDF or website</summary>
                <p className="small muted">
                  Source material is untrusted evidence. Importing does not
                  approve new marketing claims. PDFs: 5 MB, 100 pages; scanned
                  documents need OCR first. Websites: public HTTPS only, no
                  sign-in.
                </p>
                <Form
                  label="Import PDF"
                  submit={(form) =>
                    act(async () => {
                      const file = form.get("file") as File;
                      if (!file || file.size > 5000000)
                        throw new Error("Choose a PDF up to 5 MB.");
                      const response = await fetch(
                        `/api/v1/brands/${form.get("brand_id")}/ingest-pdf?title=${encodeURIComponent(String(form.get("title")))}`,
                        {
                          method: "POST",
                          credentials: "same-origin",
                          headers: { "Content-Type": "application/pdf" },
                          body: file,
                        },
                      );
                      if (!response.ok) {
                        const error = await response.json();
                        throw new Error(
                          String(error.detail).replaceAll("_", " "),
                        );
                      }
                      return response.json();
                    }, "PDF text indexed with source references.")
                  }
                >
                  <BrandSelect />
                  <label>
                    Document title
                    <input name="title" required maxLength={200} />
                  </label>
                  <label>
                    PDF file
                    <input
                      name="file"
                      type="file"
                      accept="application/pdf"
                      required
                    />
                  </label>
                </Form>
                <Form
                  label="Import website"
                  submit={(form) =>
                    post(
                      `/v1/brands/${form.get("brand_id")}/ingest-website`,
                      { url: form.get("url"), title: form.get("title") },
                      "Public website text indexed.",
                    )
                  }
                >
                  <BrandSelect />
                  <label>
                    Document title
                    <input name="title" required maxLength={200} />
                  </label>
                  <label>
                    Public HTTPS URL
                    <input
                      name="url"
                      type="url"
                      pattern="https://.*"
                      required
                      maxLength={2000}
                    />
                  </label>
                </Form>
              </details>
              <details className="form-disclosure">
                <summary>Download a brand card</summary>
                <p className="small muted">
                  A simple monochrome SVG using your supplied brand facts. This
                  is a layout asset, not an AI-generated photograph.
                </p>
                {brands.map((brand) => (
                  <p key={brand.id}>
                    <a href={`/api/v1/brands/${brand.id}/creative.svg`}>
                      Download {text(brand, "name")} card
                    </a>
                  </p>
                ))}
              </details>
              <Form
                label="Index supplied document"
                submit={(form) => {
                  const brandId = String(form.get("brand_id"));
                  const body = fields(form);
                  delete body.brand_id;
                  return post(
                    `/v1/brands/${brandId}/documents`,
                    body,
                    "Document indexed with source references.",
                  );
                }}
              >
                <BrandSelect />
                <label>
                  Document title
                  <input name="title" required maxLength={200} />
                </label>
                <label>
                  Source reference
                  <input
                    name="source_uri"
                    defaultValue="human-entry"
                    maxLength={500}
                  />
                </label>
                <label>
                  Source text
                  <textarea
                    className="large-textarea"
                    name="content"
                    required
                    minLength={10}
                    maxLength={30000}
                  />
                </label>
              </Form>
              <Form
                label="Retrieve cited passages"
                disabled={false}
                submit={(form) =>
                  act(async () => {
                    const result = await api(
                      `/v1/brands/${form.get("brand_id")}/search`,
                      { query: form.get("query") },
                    );
                    setSearchResult(result);
                    return result;
                  }, "Search completed.")
                }
              >
                <BrandSelect />
                <label>
                  Search question
                  <input name="query" required maxLength={500} />
                </label>
              </Form>
              {searchResult !== null && (
                <pre className="payload-preview">
                  {JSON.stringify(searchResult, null, 2)}
                </pre>
              )}
              <details className="form-disclosure">
                <summary>Search document vectors</summary>
                <p className="small muted">
                  Index source documents below first. Sandbox uses deterministic
                  hash vectors to test the workflow. Connected mode uses your
                  configured embedding model and may incur provider costs.
                </p>
                <Form
                  label="Search indexed documents"
                  submit={(form) =>
                    post(
                      `/v1/brands/${form.get("brand_id")}/semantic-search`,
                      keyed({
                        query: form.get("query"),
                        connected_provider:
                          form.get("connected_provider") === "true",
                      }),
                      "Vector search queued. Results appear below.",
                    )
                  }
                >
                  <BrandSelect />
                  <label>
                    Question
                    <input
                      name="query"
                      required
                      minLength={3}
                      maxLength={500}
                    />
                  </label>
                  <label>
                    Mode
                    <select name="connected_provider">
                      <option value="false">Sandbox vectors</option>
                      {connected("openrouter") && (
                        <option value="true">Connected embedding model</option>
                      )}
                    </select>
                  </label>
                </Form>
                {rows("tasks")
                  .filter((task) =>
                    ["semantic_search", "embed_document"].includes(
                      text(task, "type"),
                    ),
                  )
                  .map((task) => (
                    <article className="operation-card compact" key={task.id}>
                      <Status value={task.status} />
                      <p>{clean(task.type)}</p>
                      {!!task.error_code && <p>{clean(task.error_code)}</p>}
                      <Evidence value={task.output} />
                    </article>
                  ))}
              </details>
              {rows("brand_documents").map((document) => (
                <article className="operation-card compact" key={document.id}>
                  <Status value={document.status} />
                  <h3>{text(document, "title")}</h3>
                  <p className="small muted">{text(document, "source_uri")}</p>
                  <div className="actions">
                    <button
                      className="secondary"
                      disabled={!writable || busy}
                      onClick={() =>
                        post(
                          `/v1/brands/${document.brand_id}/documents/${document.id}/embed`,
                          keyed({ connected_provider: false }),
                          "Sandbox vector indexing queued in bounded batches.",
                        )
                      }
                    >
                      Index sandbox vectors
                    </button>
                    {connected("openrouter") && (
                      <button
                        className="secondary"
                        disabled={!writable || busy}
                        onClick={() =>
                          post(
                            `/v1/brands/${document.brand_id}/documents/${document.id}/embed`,
                            keyed({ connected_provider: true }),
                            "Connected embedding jobs queued. Check model costs and document status.",
                          )
                        }
                      >
                        Index with connected model
                      </button>
                    )}
                  </div>
                  <Evidence value={document} />
                </article>
              ))}
            </>
          )}

          {section === "Sequences" && (
            <>
              <Form
                label="Create follow-up sequence"
                submit={(form) =>
                  post(
                    "/v1/sequences",
                    {
                      ...fields(form),
                      delay_days: Number(form.get("delay_days")),
                      max_steps: Number(form.get("max_steps")),
                    },
                    "Sequence created. Enrol a contact to schedule its first draft.",
                  )
                }
              >
                <BrandSelect />
                <label>
                  Name
                  <input name="name" required minLength={3} maxLength={160} />
                </label>
                <div className="form-grid">
                  <label>
                    Days between drafts
                    <input
                      name="delay_days"
                      type="number"
                      defaultValue={3}
                      min={1}
                      max={90}
                      required
                    />
                  </label>
                  <label>
                    Maximum follow-ups
                    <input
                      name="max_steps"
                      type="number"
                      defaultValue={2}
                      min={1}
                      max={5}
                      required
                    />
                  </label>
                </div>
              </Form>
              {rows("sequences").map((sequence) => (
                <article className="operation-card" key={sequence.id}>
                  <h3>{text(sequence, "name")}</h3>
                  <p>
                    {number(sequence, "max_steps")} steps ?{" "}
                    {number(sequence, "delay_days")} days between drafts
                  </p>
                  <Form
                    label="Enrol contact"
                    submit={(form) =>
                      post(
                        `/v1/sequences/${sequence.id}/enroll`,
                        fields(form),
                        "Contact enrolled. No automatic sending is enabled.",
                      )
                    }
                  >
                    <LeadSelect />
                  </Form>
                </article>
              ))}
              {rows("sequence_enrollments").map((enrollment) => (
                <article className="operation-card compact" key={enrollment.id}>
                  <Status value={enrollment.status} />
                  <p>
                    {leadName(enrollment.lead_id)} · Step{" "}
                    {number(enrollment, "step")} · Next draft{" "}
                    {date(enrollment.next_at)}
                  </p>
                </article>
              ))}
            </>
          )}
          {section === "Notifications" && (
            <>
              {rows("notifications").map((notification) => (
                <article className="operation-card" key={notification.id}>
                  <Status value={notification.read ? "read" : "unread"} />
                  <h3>{text(notification, "title")}</h3>
                  <p className="small muted">
                    Subject {text(notification, "subject_id")} ?{" "}
                    {date(notification.created_at)}
                  </p>
                  {!notification.read && (
                    <button
                      className="secondary"
                      disabled={!writable || busy}
                      onClick={() =>
                        post(
                          `/v1/notifications/${notification.id}/read`,
                          {},
                          "Marked as read.",
                        )
                      }
                    >
                      Mark as read
                    </button>
                  )}
                </article>
              ))}
              <Empty resource="notifications" />
            </>
          )}
          {section === "Expenses" && (
            <>
              <Form
                label="Record expense"
                disabled={!writable || !owner}
                submit={(form) =>
                  post(
                    "/v1/expenses",
                    {
                      ...fields(form),
                      amount_micros: Math.round(
                        Number(form.get("amount_micros")) * 1_000_000,
                      ),
                      simulated: form.get("simulated") !== "false",
                    },
                    "Expense recorded with evidence.",
                  )
                }
              >
                <div className="form-grid">
                  <label>
                    Cost category
                    <select name="category">
                      <option value="data">Prospect data</option>
                      <option value="sending">Sending infrastructure</option>
                      <option value="human_review">Human review</option>
                      <option value="infrastructure">
                        Application infrastructure
                      </option>
                    </select>
                  </label>
                  <label>
                    Record type
                    <select name="simulated">
                      <option value="true">Sandbox expense</option>
                      <option value="false">Real expense with evidence</option>
                    </select>
                  </label>
                  <label>
                    Amount (USD)
                    <input
                      name="amount_micros"
                      type="number"
                      step="0.000001"
                      min={0}
                      max={1000}
                      required
                    />
                    <small>
                      Record the full amount attributable to this workspace.
                    </small>
                  </label>
                </div>
                <label>
                  Invoice, timesheet or other evidence
                  <input
                    name="evidence"
                    required
                    minLength={3}
                    maxLength={1000}
                  />
                </label>
              </Form>
              {rows("expenses").map((expense) => (
                <article className="operation-card compact" key={expense.id}>
                  <Status
                    value={
                      expense.simulated ? "sandbox expense" : "recorded expense"
                    }
                  />
                  <h3>
                    {clean(expense.category)} · {money(expense.amount_micros)}
                  </h3>
                  <p>{text(expense, "evidence")}</p>
                </article>
              ))}
              <Empty resource="expenses" />
            </>
          )}
          {section === "Leads & CRM" && (
            <details className="form-disclosure">
              <summary>Import a CSV contact file</summary>
              <p className="small muted">
                Up to 100 rows. Required columns: name, email, source,
                lawful_basis, basis_evidence. Optional: company, domain,
                source_confidence. Contacts without an established basis remain
                blocked from sending.
              </p>
              <Form
                label="Import CSV"
                submit={(form) =>
                  post(
                    "/v1/leads/import-csv",
                    { brand_id: form.get("brand_id"), content: csvText },
                    "CSV imported. Duplicate contacts were left unchanged.",
                  )
                }
              >
                <BrandSelect />
                <label>
                  Choose a CSV file
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    onChange={(e) => {
                      const file = e.currentTarget.files?.[0];
                      if (file) void file.text().then(setCsvText);
                    }}
                  />
                </label>
                <label>
                  CSV contents
                  <textarea
                    className="large-textarea"
                    value={csvText}
                    onChange={(e) => setCsvText(e.target.value)}
                    required
                  />
                </label>
              </Form>
            </details>
          )}
          {Object.keys(nextPages)
            .filter(
              (name) => nextPages[name] != null || pageBefore[name]?.length,
            )
            .map((name) => (
              <div className="record-pagination" key={name}>
                <span>
                  {clean(name)} · Page {(pageBefore[name]?.length || 0) + 1}
                </span>
                <div className="actions">
                  <button
                    className="secondary"
                    disabled={busy || !pageBefore[name]?.length}
                    onClick={() =>
                      setPageBefore((current) => ({
                        ...current,
                        [name]: (current[name] || []).slice(0, -1),
                      }))
                    }
                  >
                    Newer {clean(name)}
                  </button>
                  <button
                    className="secondary"
                    disabled={busy || nextPages[name] == null}
                    onClick={() =>
                      setPageBefore((current) => ({
                        ...current,
                        [name]: [
                          ...(current[name] || []),
                          nextPages[name] as number,
                        ],
                      }))
                    }
                  >
                    Older {clean(name)}
                  </button>
                </div>
              </div>
            ))}
          {owner && (
            <div className="workspace-export">
              <button
                className="text-button"
                disabled={busy}
                onClick={() =>
                  act(async () => {
                    const exported = await api("/v1/exports/workspace");
                    const link = document.createElement("a");
                    const url = URL.createObjectURL(
                      new Blob([JSON.stringify(exported, null, 2)], {
                        type: "application/json",
                      }),
                    );
                    link.href = url;
                    link.download = "ai-mos-workspace.json";
                    link.click();
                    setTimeout(() => URL.revokeObjectURL(url), 1000);
                  }, "Workspace export prepared. It contains workspace data, without account passwords or session tokens.")
                }
              >
                Export workspace data
              </button>
            </div>
          )}
        </div>
      </div>
    </WorkContext.Provider>
  );
}
