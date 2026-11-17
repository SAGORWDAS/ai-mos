"use client";

import { useEffect, useState } from "react";
import { api } from "./api";

type Report = {
  providers: {
    provider: string;
    purpose: string;
    needs: string;
    status: string;
    enabled: boolean;
    callback_url: string;
  }[];
  hosting: Record<string, boolean>;
  live_checks: string[];
  production_gate: string;
  seo: { public_indexing_active: boolean; sitemap_url: string; note: string };
};
export default function SetupReadiness({
  configure,
}: {
  configure: (provider: string) => void;
}) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  async function load() {
    try {
      setReport(await api<Report>("/v1/setup/readiness"));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not check setup");
    }
  }
  useEffect(() => {
    void load();
  }, []);
  return (
    <section className="operation-card">
      <h2>Connect when you are ready</h2>
      <p>
        Business details belong to campaign setup inside the app. They are not
        required to install the platform. Connect only the services you want to
        use; sandbox stays available without them.
      </p>
      <button className="secondary" onClick={() => void load()}>
        Refresh setup checks
      </button>
      {error && <p role="alert">{error}</p>}
      {report && (
        <>
          <ol>
            {report.providers.map((p) => (
              <li key={p.provider}>
                <p>
                  <b>{p.purpose}</b> ·{" "}
                  {p.enabled ? "Enabled" : p.status.replaceAll("_", " ")}
                </p>
                <p className="small muted">
                  {p.needs}. Save, verify, then explicitly enable.
                </p>
                {p.callback_url && (
                  <details className="evidence">
                    <summary>Callback address to register</summary>
                    <p className="preserve">{p.callback_url}</p>
                  </details>
                )}
                <a
                  href="#provider-configuration"
                  className="text-button"
                  onClick={() => configure(p.provider)}
                >
                  Configure {p.provider}
                </a>
              </li>
            ))}
          </ol>
          <details className="evidence">
            <summary>Public page SEO</summary>
            <p>{report.seo.note}</p>
            <p>
              Search indexing:{" "}
              {report.seo.public_indexing_active
                ? "Enabled for approved public pages"
                : "Off for this instance"}
            </p>
            {report.seo.public_indexing_active && (
              <p>
                <a
                  href={report.seo.sitemap_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open this workspace's public sitemap
                </a>
              </p>
            )}
            <p className="small muted">
              When hosting is ready, configure the public HTTPS API base and
              PUBLIC_INDEXING_ENABLED. Submit the displayed sitemap in your own
              Search Console account.
            </p>
          </details>
          <details className="evidence">
            <summary>Deployment and live validation</summary>
            <p>
              {report.production_gate}. Connecting an account does not certify
              production readiness.
            </p>
            {Object.entries(report.hosting).map(([key, ready]) => (
              <p key={key}>
                {key.replaceAll("_", " ")}:{" "}
                {ready
                  ? "Configured"
                  : "Not configured for this local instance"}
              </p>
            ))}
            <ul>
              {report.live_checks.map((check) => (
                <li key={check}>{check}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
