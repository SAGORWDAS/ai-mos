"use client";

import { useEffect, useState } from "react";
import { api } from "./api";

type Usage = {
  day: string;
  agent_id: string;
  task_type: string;
  model_id: string;
  status: string;
  simulated: boolean;
  attempts: number;
  cost_micros: number;
  held_micros: number;
};
type Attempt = {
  id: string;
  request_id: string;
  task_id: string;
  created_at: number;
  cost_micros: number;
  reserved_micros: number;
  settled: boolean;
  cache_source_id: string | null;
};
export default function UsageBreakdown({
  revision = 0,
}: {
  revision?: number;
}) {
  const [days, setDays] = useState("30");
  const [agent, setAgent] = useState("");
  const [task, setTask] = useState("");
  const [status, setStatus] = useState("");
  const [rows, setRows] = useState<Usage[]>([]);
  const [agents, setAgents] = useState<{ id: string; name: string }[]>([]);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Usage | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  async function drill(row: Usage, offset = 0) {
    setBusy(true);
    setError("");
    try {
      const q = new URLSearchParams({
        day: row.day,
        agent: row.agent_id,
        task_type: row.task_type,
        status: row.status,
        model: row.model_id,
        simulated: String(row.simulated),
        offset: String(offset),
      });
      const data = await api<{ items: Attempt[]; next_offset: number | null }>(
        `/v1/usage/attempts?${q}`,
      );
      setSelected(row);
      setAttempts((current) =>
        offset ? [...current, ...data.items] : data.items,
      );
      setNext(data.next_offset);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load attempts.");
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    let active = true;
    api<{ id: string; name: string }[]>("/v1/agents")
      .then((r) => {
        if (active) setAgents(r);
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
    setError("");
    const q = new URLSearchParams({ days, agent, task_type: task, status });
    setSelected(null);
    setAttempts([]);
    setNext(null);
    api<{ items: Usage[]; truncated: boolean; note: string }>(
      `/v1/usage/breakdown?${q}`,
    )
      .then((r) => {
        if (active) {
          setRows(r.items);
          setNote(
            r.note +
              (r.truncated
                ? " Results are truncated; narrow your filters."
                : ""),
          );
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [days, agent, task, status, revision]);
  return (
    <section className="operation-card">
      <h3>Cost by day, agent and task</h3>
      <div className="form-grid">
        <label>
          Window
          <select value={days} onChange={(e) => setDays(e.target.value)}>
            {[7, 30, 90, 365].map((d) => (
              <option key={d} value={d}>
                {d} days
              </option>
            ))}
          </select>
        </label>
        <label>
          Agent
          <select value={agent} onChange={(e) => setAgent(e.target.value)}>
            <option value="">All agents</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Task type
          <select value={task} onChange={(e) => setTask(e.target.value)}>
            <option value="">All types</option>
            {[
              "plan",
              "research",
              "strategy",
              "draft",
              "reply",
              "content",
              "creative_image",
              "prospect_search",
              "prospect_enrich",
              "embed_document",
              "semantic_search",
              "report",
            ].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          Result
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All results</option>
            {[
              "succeeded",
              "cache_hit",
              "timeout",
              "invalid_output",
              "provider_error",
              "provider_cost_unknown",
            ].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Day</th>
              <th>Agent / task</th>
              <th>Model</th>
              <th>Result / mode</th>
              <th>Attempts</th>
              <th>Known cost USD</th>
              <th>Held USD</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td>{r.day}</td>
                <td>
                  {agents.find((a) => a.id === r.agent_id)?.name || r.agent_id}{" "}
                  / {r.task_type}
                </td>
                <td>{r.model_id}</td>
                <td>
                  {r.status} / {r.simulated ? "Sandbox" : "Connected"}
                </td>
                <td>
                  <button
                    disabled={busy}
                    onClick={() => drill(r)}
                    aria-label={`Inspect ${r.attempts} attempts for ${r.day}, ${r.agent_id}, ${r.task_type}, ${r.status}`}
                  >
                    {r.attempts} · inspect
                  </button>
                </td>
                <td>${(r.cost_micros / 1000000).toFixed(6)}</td>
                <td>${(r.held_micros / 1000000).toFixed(6)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && (
        <p className="muted">No attempts match these filters.</p>
      )}
      <p className="small muted">{note}</p>
      {selected && (
        <section aria-live="polite">
          <h4>
            Recorded attempts: {selected.day} / {selected.task_type}
          </h4>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Request / task</th>
                  <th>Known USD</th>
                  <th>Held USD</th>
                  <th>Cache source</th>
                </tr>
              </thead>
              <tbody>
                {attempts.map((a) => (
                  <tr key={a.id}>
                    <td>{new Date(a.created_at * 1000).toLocaleString()}</td>
                    <td>
                      {a.request_id}
                      <br />
                      {a.task_id}
                    </td>
                    <td>${(a.cost_micros / 1000000).toFixed(6)}</td>
                    <td>
                      $
                      {((a.settled ? 0 : a.reserved_micros) / 1000000).toFixed(
                        6,
                      )}
                    </td>
                    <td>{a.cache_source_id || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {next !== null && (
            <button disabled={busy} onClick={() => drill(selected, next)}>
              Load more attempts
            </button>
          )}
        </section>
      )}
    </section>
  );
}
