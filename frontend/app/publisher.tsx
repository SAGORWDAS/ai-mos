"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "./api";

type Approval = {
  id: string;
  status: string;
  payload: { title: string; body: string; channel: string };
};
type Effect = {
  id?: string;
  effect_id?: string;
  status: string;
  result?: { receipt?: { url?: string; provider_id?: string } };
};
type Connection = {
  provider: string;
  enabled: boolean;
  status: string;
  account_ref: string;
};
export default function Publisher({
  contentId,
  disabled,
  connections,
}: {
  contentId: string;
  disabled: boolean;
  connections: Connection[];
}) {
  const [channel, setChannel] = useState("linkedin");
  const [approval, setApproval] = useState<Approval | null>(null);
  const [effect, setEffect] = useState<Effect | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = useRef("");
  const connection = connections.find(
    (c) => c.provider === channel && c.enabled && c.status === "verified",
  );
  useEffect(() => {
    if (!effect?.effect_id || effect.status !== "queued") return;
    let active = true;
    const id = effect.effect_id;
    const timer = setInterval(() => {
      void api<Effect>(`/v1/data/effects/${id}`)
        .then((row) => {
          if (active) setEffect({ ...row, effect_id: id });
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    }, 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [effect?.effect_id, effect?.status]);
  async function act(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publishing failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="form-disclosure">
      <summary>Publish to LinkedIn or WordPress</summary>
      <p>
        Publishing means posting this reviewed text to your selected account.
        Sandbox makes no external post. LinkedIn currently supports member text
        posts; WordPress uses a WordPress.com or connected Jetpack site ID.
      </p>
      {error && (
        <p className="message error" role="alert">
          {error}
        </p>
      )}
      <label>
        Destination
        <select
          disabled={busy}
          value={channel}
          onChange={(e) => {
            setChannel(e.target.value);
            setApproval(null);
            setEffect(null);
            key.current = "";
          }}
        >
          <option value="linkedin">LinkedIn member profile</option>
          <option value="wordpress">WordPress.com website</option>
        </select>
      </label>
      <p className="small muted">
        {connection
          ? `Connected account: ${connection.account_ref}`
          : "No enabled account for this destination. You can test in sandbox or connect it in Integrations."}
      </p>
      <div className="actions">
        <button
          type="button"
          className="secondary"
          disabled={disabled || busy}
          onClick={() =>
            void act(async () => {
              setApproval(
                await api<Approval>(
                  `/v1/content/${contentId}/channel-approval`,
                  { channel },
                ),
              );
              setEffect(null);
              key.current = crypto.randomUUID();
            })
          }
        >
          Prepare publication review
        </button>
      </div>
      {approval && (
        <section aria-label="Publication review">
          <h4>{approval.payload.title}</h4>
          <p className="preserve">{approval.payload.body}</p>
          <p>
            Destination: {approval.payload.channel} · Approval:{" "}
            {approval.status}
          </p>
          {approval.status === "pending" && (
            <button
              type="button"
              disabled={disabled || busy}
              onClick={() =>
                void act(async () => {
                  setApproval(
                    await api<Approval>(
                      `/v1/approvals/${approval.id}/decision`,
                      { decision: "approved" },
                    ),
                  );
                })
              }
            >
              Approve this exact publication
            </button>
          )}
          {approval.status === "approved" && !effect && (
            <div className="actions">
              <button
                type="button"
                disabled={disabled || busy}
                onClick={() =>
                  void act(async () => {
                    setEffect(
                      await api<Effect>("/v1/effects/execute", {
                        approval_id: approval.id,
                        idempotency_key: key.current,
                        execution_mode: "sandbox",
                      }),
                    );
                  })
                }
              >
                Simulate publication
              </button>
              <button
                type="button"
                disabled={disabled || busy || !connection}
                onClick={() =>
                  void act(async () => {
                    setEffect(
                      await api<Effect>("/v1/effects/execute", {
                        approval_id: approval.id,
                        idempotency_key: key.current,
                        execution_mode: "live",
                      }),
                    );
                  })
                }
              >
                Publish to connected account
              </button>
            </div>
          )}
          {effect && (
            <p role="status">
              Publication: {effect.status}
              {effect.result?.receipt?.provider_id
                ? ` · Receipt: ${effect.result.receipt.provider_id}`
                : ""}
              .{" "}
              {effect.status === "uncertain"
                ? "Review the provider console before taking any further action. Automatic retry is blocked."
                : ""}
            </p>
          )}
        </section>
      )}
    </details>
  );
}
