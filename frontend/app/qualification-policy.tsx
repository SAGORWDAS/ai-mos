"use client";
import { useEffect, useState } from "react";
import { api } from "./api";
type Policy = {
  threshold: number;
  model_version: string;
  enabled: boolean;
  note: string;
};
export default function QualificationPolicy({
  owner,
  disabled,
}: {
  owner: boolean;
  disabled: boolean;
}) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [threshold, setThreshold] = useState("65");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => {
    let active = true;
    api<Policy>("/v1/qualification-policy")
      .then((p) => {
        if (active) {
          setPolicy(p);
          setThreshold(String(p.threshold));
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  async function save() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const p = await api<Policy>(
        "/v1/qualification-policy",
        { threshold: Number(threshold) },
        "PUT",
      );
      setPolicy(p);
      setMessage(
        "Threshold saved. Existing scores keep their recorded policy until you rescore them.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save threshold.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="operation-card">
      <h3>Qualification policy</h3>
      <p>
        Score recorded company, domain, source confidence and contactability
        evidence using a versioned rubric. Scoring uses no paid model call. This
        score does not grant permission to contact a lead or predict a sale.
      </p>
      {policy && (
        <p className="small muted">
          {policy.model_version} ·{" "}
          {policy.enabled ? "Enabled" : "Agent disabled"} · {policy.note}
        </p>
      )}
      <label>
        Qualification threshold
        <input
          type="number"
          min="1"
          max="100"
          value={threshold}
          onChange={(e) => setThreshold(e.target.value)}
          disabled={!owner || disabled || busy}
        />
      </label>
      <button disabled={!owner || disabled || busy || !policy} onClick={save}>
        Save qualification threshold
      </button>
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
    </section>
  );
}
