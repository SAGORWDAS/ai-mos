"use client";

import { FormEvent, useState } from "react";
import { api } from "./api";

export default function QuickStart({
  disabled,
  onStarted,
  onConnect,
}: {
  disabled: boolean;
  onStarted: () => Promise<void>;
  onConnect: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [sample, setSample] = useState(false);
  const [request, setRequest] = useState({ signature: "", key: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const supplied = {
        name: form.get("name"),
        offer: form.get("offer"),
        audience: form.get("audience"),
        objective: form.get("objective"),
        sample,
        connected_research: !sample && form.get("research") === "on",
      };
      const signature = JSON.stringify(supplied);
      const key =
        request.signature === signature ? request.key : crypto.randomUUID();
      setRequest({ signature, key });
      const result = await api<{ status: string; missing_fields?: string[] }>(
        "/v1/setup/start",
        { ...supplied, idempotency_key: key },
      );
      if (result.status === "needs_information")
        throw new Error(`Complete: ${result.missing_fields?.join(", ")}`);
      setMessage(
        "Campaign started. Follow preparation in Operations. With connected research, observed contacts are scored and drafted automatically; sending remains blocked until contactability and exact output are reviewed.",
      );
      await onStarted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Setup failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="operation-card">
      <p className="eyebrow">Your marketing team</p>
      <h2>Start with a short business brief</h2>
      <p>
        Any product, service or market. Add your offer and intended customers;
        the team prepares a campaign. You can change the details in Brand Brain
        later.
      </p>
      {message && (
        <p role="status" className="message">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      <div className="actions">
        <button
          type="button"
          className="secondary"
          disabled={busy || !!message}
          onClick={() => setSample(!sample)}
        >
          {sample ? "Use my own business" : "Fill with a fictional sample"}
        </button>
        <button type="button" className="secondary" onClick={onConnect}>
          Connect accounts
        </button>
      </div>
      <form
        key={sample ? "sample" : "own"}
        className="operation-form"
        onSubmit={start}
      >
        <fieldset disabled={disabled || busy || !!message}>
          <label>
            Business or product name
            <input
              name="name"
              required
              maxLength={120}
              defaultValue={sample ? "Fictional sample agency" : ""}
            />
          </label>
          <label>
            What do you offer? Use only facts you approve.
            <textarea
              name="offer"
              required
              minLength={10}
              maxLength={600}
              defaultValue={
                sample
                  ? "We build websites for independent shops. This is a fictional sample for testing."
                  : ""
              }
            />
            <small>
              Keep this to 80 words or fewer. Add longer background material in
              Brand Brain later.
            </small>
          </label>
          <label>
            Who should the team look for?
            <input
              name="audience"
              required
              minLength={3}
              maxLength={300}
              placeholder="Any industry, customer type or location"
              defaultValue={sample ? "Fictional independent retailers" : ""}
            />
          </label>
          <label>
            Your campaign goal
            <textarea
              name="objective"
              required
              minLength={8}
              maxLength={500}
              defaultValue="Find suitable prospects and prepare a reviewed outreach campaign."
            />
          </label>
          <label className="check">
            <input name="research" type="checkbox" disabled={sample} />
            Use my enabled search connection to find prospects
          </label>
          <p className="small muted">
            Without a connection, preparation runs in sandbox and searches make
            no external requests. Model connections can incur charges within
            your configured budget. Sample facts must be replaced before real
            use.
          </p>
          <button disabled={busy} type="submit">
            {busy
              ? "Starting…"
              : request.key && error
                ? "Retry campaign start"
                : "Start campaign preparation"}
          </button>
        </fieldset>
      </form>
    </section>
  );
}
