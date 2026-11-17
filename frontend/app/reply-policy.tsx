"use client";

import { useEffect, useState } from "react";
import { api } from "./api";
import ReplyDigest from "./reply-digest";

type Brand = { id: string; name: string };
type Policy = {
  enabled: boolean;
  execution_mode: string;
  daily_cap: number;
  counter_used: number;
  expires_at: number;
};
type Preview = {
  policy: Policy | null;
  template_preview: string;
  template_hash: string;
  requires_reapproval: boolean;
};

export default function ReplyPolicy({
  owner,
  disabled,
}: {
  owner: boolean;
  disabled: boolean;
}) {
  const [brands, setBrands] = useState<Brand[]>([]);
  const [brand, setBrand] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mode, setMode] = useState("sandbox");
  const [cap, setCap] = useState("5");
  const [days, setDays] = useState("7");
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<Brand[]>("/v1/brands")
      .then((rows) => {
        if (active) {
          setBrands(rows);
          setBrand(rows[0]?.id || "");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    setPreview(null);
    setReviewed(false);
    setMessage("");
    setError("");
    if (brand)
      api<Preview>(`/v1/brands/${brand}/reply-policy`)
        .then((row) => {
          if (active) {
            setPreview(row);
            setMode(row.policy?.execution_mode || "sandbox");
            setCap(String(row.policy?.daily_cap || 5));
          }
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    return () => {
      active = false;
    };
  }, [brand]);
  async function save(enabled: boolean) {
    if (!preview || busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api(
        `/v1/brands/${brand}/reply-policy`,
        {
          enabled,
          execution_mode: mode,
          daily_cap: Number(cap),
          expires_days: Number(days),
          reviewed_template_hash: enabled ? preview.template_hash : "",
        },
        "PUT",
      );
      setPreview(await api<Preview>(`/v1/brands/${brand}/reply-policy`));
      setReviewed(false);
      setMessage(
        enabled
          ? "Exact-template reply policy enabled."
          : "Automatic replies disabled. Queued replies will recheck this policy before delivery.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save policy.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="operation-card">
      <h3>Automatic replies with standing approval</h3>
      <p>
        Review one fixed reply and set a daily attempt limit. Only clear,
        non-escalated replies from known contacts qualify. Ambiguous replies and
        changed business facts return to review. Connected delivery also
        requires current contactability, suppression and spending checks.
      </p>
      <label>
        Business
        <select
          value={brand}
          onChange={(e) => setBrand(e.target.value)}
          disabled={busy}
        >
          <option value="">Choose a business</option>
          {brands.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </label>
      {preview && (
        <>
          <p className="small">
            {preview.policy?.enabled
              ? `Enabled until ${new Date(preview.policy.expires_at * 1000).toLocaleString()} · ${preview.policy.execution_mode}`
              : "Disabled"}
            {preview.requires_reapproval
              ? " · Business facts changed: review again."
              : ""}
          </p>
          <pre className="payload-preview">
            {preview.template_preview ||
              "Add an approved business claim before enabling replies."}
          </pre>
          <div className="form-grid">
            <label>
              Delivery
              <select
                value={mode}
                onChange={(e) => {
                  setMode(e.target.value);
                  setReviewed(false);
                }}
                disabled={busy}
              >
                <option value="sandbox">Sandbox simulation</option>
                <option value="live">Connected Gmail</option>
              </select>
            </label>
            <label>
              Daily attempts
              <input
                type="number"
                min="1"
                max="20"
                value={cap}
                onChange={(e) => setCap(e.target.value)}
              />
            </label>
            <label>
              Expires after days
              <input
                type="number"
                min="1"
                max="30"
                value={days}
                onChange={(e) => setDays(e.target.value)}
              />
            </label>
          </div>
          <label className="check">
            <input
              type="checkbox"
              checked={reviewed}
              onChange={(e) => setReviewed(e.target.checked)}
            />
            I approve this exact template, delivery mode and limits.
          </label>
          <div className="actions">
            <button
              className="primary"
              disabled={
                !owner ||
                disabled ||
                busy ||
                !reviewed ||
                !preview.template_preview
              }
              onClick={() => save(true)}
            >
              Enable reviewed policy
            </button>
            <button
              className="secondary"
              disabled={!owner || busy || !preview.policy?.enabled}
              onClick={() => save(false)}
            >
              Disable automatic replies
            </button>
          </div>
          <p className="small muted">
            Maximum 20 attempts per day and 30 days per approval. Attempts count
            even when a later guard blocks sending. Prices, disputes, refunds
            and uncertain replies need review. The owner can disable this policy
            while the workspace is paused.
          </p>
        </>
      )}
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
      {owner && brand && <ReplyDigest brand={brand} />}
    </section>
  );
}
