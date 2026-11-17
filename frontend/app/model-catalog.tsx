"use client";
import { useEffect, useState } from "react";
import { api } from "./api";
type Model = {
  id: string;
  operation: string;
  model_id: string;
  status: string;
  eligible: boolean;
  current: boolean;
  verified_at: number | null;
  verification_error: string;
  price_snapshot: { rates?: Record<string, unknown> };
};
type Catalog = {
  models: Model[];
  verification_required: boolean;
  freshness_days: number;
  request_allowance_micros: number;
  truncated: boolean;
  note: string;
};
const price = (value: unknown) => {
  const amount = Number(value) * 1000000;
  return Number.isFinite(amount)
    ? new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 6,
      }).format(amount)
    : "Not available";
};
export default function ModelCatalog({
  owner,
  canRefresh,
  revision,
}: {
  owner: boolean;
  canRefresh: boolean;
  revision: number;
}) {
  const [data, setData] = useState<Catalog | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<Catalog>("/v1/model-registry")
      .then((r) => {
        if (active) setData(r);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [revision]);
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      setData(await api<Catalog>("/v1/model-registry/refresh", {}));
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not refresh model prices.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="form-disclosure">
      <summary>AI models and prices</summary>
      <p>
        Account verification checks your selected models and saves advertised
        provider rates. The gateway refreshes aging catalog evidence
        automatically when needed. Missing or expired verification blocks
        connected generation; sandbox remains available.
      </p>
      <button disabled={!owner || !canRefresh || busy} onClick={refresh}>
        {busy ? "Checking catalog…" : "Refresh model prices"}
      </button>
      {!canRefresh && (
        <p className="small muted">
          Save and verify your OpenRouter account to check its selected models.
          No business details are needed for this setup.
        </p>
      )}
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      {data && (
        <>
          <p className="small muted">
            {data.verification_required
              ? "Catalog verification required for connected generation."
              : "Development override enabled; unverified models are permitted outside production."}
          </p>
          <p className="small muted">
            Per-request allowance:{" "}
            {new Intl.NumberFormat(undefined, {
              style: "currency",
              currency: "USD",
              maximumFractionDigits: 6,
            }).format(data.request_allowance_micros / 1000000)}
            . Known estimates above this allowance are refused before
            generation. Image tiers and final provider charges can differ;
            unknown costs remain held for reconciliation. Change the allowance
            in your OpenRouter configuration.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Model / use</th>
                  <th>Catalog status</th>
                  <th>Verified</th>
                  <th>Advertised USD rates</th>
                </tr>
              </thead>
              <tbody>
                {data.models.map((m) => (
                  <tr key={m.id}>
                    <td>
                      {m.model_id}
                      <br />
                      {m.operation}
                      {m.current
                        ? " · current selection"
                        : " · earlier selection"}
                    </td>
                    <td>
                      {m.eligible
                        ? "Catalog verified"
                        : "Verification required"}
                      {m.verification_error && (
                        <p className="small muted">
                          {m.verification_error.replaceAll("_", " ")}
                        </p>
                      )}
                    </td>
                    <td>
                      {m.verified_at
                        ? new Date(m.verified_at * 1000).toLocaleString()
                        : "Not verified"}
                    </td>
                    <td>
                      {m.operation !== "image" &&
                      m.price_snapshot.rates?.prompt !== undefined ? (
                        <span>
                          {price(m.price_snapshot.rates.prompt)} / 1M input
                          tokens
                          {m.operation === "chat" &&
                          m.price_snapshot.rates.completion !== undefined
                            ? ` · ${price(m.price_snapshot.rates.completion)} / 1M output tokens`
                            : ""}
                        </span>
                      ) : (
                        "See provider rate details"
                      )}
                      <details>
                        <summary>Provider rate details</summary>
                        <pre className="payload-preview">
                          {JSON.stringify(m.price_snapshot, null, 2)}
                        </pre>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!data.models.length && (
            <p>
              No verified model selections yet. Your sandbox does not need an
              API key.
            </p>
          )}
          {data.truncated && (
            <p>
              Showing the most recent 100 selections; workspace export includes
              the full registry.
            </p>
          )}
          <p className="small muted">{data.note}</p>
        </>
      )}
    </details>
  );
}
