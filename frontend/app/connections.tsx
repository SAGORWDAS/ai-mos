"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "./api";
import SetupReadiness from "./setup-readiness";
import { credentialPayload } from "./connection-values";

type Connection = {
  id: string;
  provider: string;
  account_ref: string;
  status: string;
  enabled: boolean;
  version: number;
  sync_enabled: boolean;
  auto_draft_replies: boolean;
  sync_interval_minutes: number;
  sync_last_at: number;
  sync_error: string;
};
const providers = {
  meta_ads: "Meta paid advertising",
  wordpress: "WordPress.com publishing",
  linkedin: "LinkedIn member publishing",
  openrouter: "OpenRouter",
  gmail: "Gmail",
  calendar: "Google Calendar",
  stripe: "Stripe",
  resend: "Resend opt-in campaigns",
  brave: "Brave prospect research",
};
type Provider = keyof typeof providers;
const fields: Record<Provider, [string, string, boolean][]> = {
  meta_ads: [
    ["access_token", "Meta ads access token", true],
    ["ad_account_id", "Numeric ad account ID", false],
    ["page_id", "Numeric Facebook page ID", false],
  ],
  wordpress: [
    ["access_token", "WordPress.com OAuth access token", true],
    ["site_id", "Numeric site ID", false],
  ],
  linkedin: [
    [
      "access_token",
      "LinkedIn access token (openid, profile, w_member_social)",
      true,
    ],
    ["author_urn", "Member URN (optional; verified from account)", false],
  ],
  resend: [
    ["api_key", "Resend API key", true],
    ["sender", "Verified sending address", false],
    ["webhook_secret", "Svix webhook signing secret", true],
  ],
  brave: [
    ["api_key", "Brave Search API key", true],
    [
      "search_price_micros",
      "Contract cost per search (USD, optional; blank means unknown)",
      false,
    ],
  ],
  openrouter: [
    ["api_key", "API key", true],
    ["model_id", "Exact model ID", false],
    ["embedding_model_id", "Embedding model ID (optional)", false],
    ["image_model_id", "Image API model ID (optional)", false],
  ],
  gmail: [
    ["access_token", "OAuth access token", true],
    ["sender", "Sending address", false],
    ["refresh_token", "OAuth refresh token (optional)", true],
    ["client_id", "OAuth client ID (optional)", false],
    ["client_secret", "OAuth client secret (optional)", true],
  ],
  calendar: [
    ["access_token", "OAuth access token", true],
    ["calendar_id", "Calendar ID", false],
    ["refresh_token", "OAuth refresh token (optional)", true],
    ["client_id", "OAuth client ID (optional)", false],
    ["client_secret", "OAuth client secret (optional)", true],
  ],
  stripe: [
    ["secret_key", "Stripe secret key", true],
    ["webhook_secret", "Webhook signing secret", true],
    ["success_url", "Success return URL (HTTPS)", false],
    ["cancel_url", "Cancel return URL (HTTPS)", false],
  ],
};
const activation: Record<Provider, string> = {
  meta_ads: "Enable owner-approved paid advertising",
  wordpress: "Enable reviewed article publishing",
  linkedin: "Enable reviewed member posts",
  openrouter: "Enable model calls",
  gmail: "Enable approved email dispatch",
  calendar: "Enable approved bookings",
  stripe: "Enable checkout creation",
  resend: "Enable approved opt-in campaigns",
  brave: "Enable requested prospect searches",
};

export default function Connections({ role }: { role: string }) {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [provider, setProvider] = useState<Provider>("openrouter");
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [account, setAccount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [oauth, setOauth] = useState<{
    authorization_url: string;
    redirect_uri: string;
  } | null>(null);
  const owner = role === "owner";
  const [configureOpen, setConfigureOpen] = useState(false);
  const refresh = useCallback(
    async () => setConnections(await api<Connection[]>("/v1/connections")),
    [],
  );
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
  }, [refresh]);
  async function act(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      await refresh();
      setNotice(message);
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connection failed");
      return false;
    } finally {
      setBusy(false);
    }
  }
  function placeholders() {
    const values: Record<string, string> = {};
    for (const [name, , secret] of fields[provider])
      values[name] = secret ? `placeholder-${name}` : "";
    if (provider === "openrouter") values.model_id = "placeholder/model";
    if (provider === "gmail") values.sender = "sandbox@example.test";
    if (provider === "resend") values.sender = "sandbox@example.test";
    if (provider === "calendar") values.calendar_id = "primary";
    if (provider === "wordpress") values.site_id = "123456";
    if (provider === "stripe") {
      values.success_url = "https://example.test/success";
      values.cancel_url = "https://example.test/cancel";
    }
    setCredentials(values);
    setAccount("Placeholder setup - no live account");
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const saved = await act(
      () =>
        api(
          `/v1/connections/${provider}`,
          {
            account_ref: account,
            credentials: credentialPayload(provider, credentials),
          },
          "PUT",
        ),
      "Configuration saved. It remains disabled until credentials are verified and you explicitly enable it.",
    );
    if (saved) setCredentials({});
  }
  return (
    <section>
      <SetupReadiness
        configure={(id) => {
          setProvider(id as Provider);
          setCredentials({});
          setAccount("");
          setConfigureOpen(true);
        }}
      />
      <p className="lede narrow">
        Sandbox is available immediately. Each real provider needs verified
        credentials and a separate owner activation. Saving a configuration does
        not enable it.
      </p>
      <div className="sandbox-note">
        <b>Placeholder credentials stay local.</b> They can be saved for setup
        testing, but cannot enable provider calls. Email and bookings also
        require an exact human approval and an explicit connected-provider
        execution.
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
      {oauth && (
        <div className="message">
          <p>Register this exact redirect URI in your Google OAuth client:</p>
          <p className="preserve">{oauth.redirect_uri}</p>
          <a
            href={oauth.authorization_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Continue to Google
          </a>
          <p className="small muted">
            The request expires in ten minutes. After returning, refresh this
            page and explicitly enable the verified connection.
          </p>
        </div>
      )}
      <div className="provider-list">
        {Object.entries(providers).map(([id, name]) => {
          const connection = connections.find((item) => item.provider === id);
          return (
            <article className="operation-card" key={id}>
              <div className="row-between">
                <h3>{name}</h3>
                <span className="badge">
                  {connection?.enabled
                    ? "Enabled"
                    : connection?.status || "Sandbox default"}
                </span>
              </div>
              {connection && (
                <p className="small muted">
                  {connection.account_ref} · Revision {connection.version}
                </p>
              )}
              <div className="actions">
                {connection &&
                  ["gmail", "calendar"].includes(id) &&
                  connection.status !== "revoked" && (
                    <button
                      className="secondary"
                      disabled={!owner || busy}
                      onClick={() =>
                        act(async () => {
                          setOauth(
                            await api<{
                              authorization_url: string;
                              redirect_uri: string;
                            }>(`/v1/connections/${id}/oauth/start`, {}),
                          );
                        }, "Google connection request prepared. Review the redirect URI and continue below.")
                      }
                    >
                      Connect Google account
                    </button>
                  )}
                {connection && connection.status !== "revoked" && (
                  <button
                    className="secondary"
                    disabled={!owner || busy}
                    onClick={() =>
                      act(
                        () => api(`/v1/connections/${id}/verify`, {}),
                        "Credential check completed. Placeholder configurations remain disabled.",
                      )
                    }
                  >
                    Verify credentials
                  </button>
                )}
                {connection?.status === "verified" && !connection.enabled && (
                  <button
                    className="primary"
                    disabled={!owner || busy}
                    onClick={() =>
                      act(
                        () => api(`/v1/connections/${id}/activate`, {}),
                        `${name} enabled for this workspace. Sandbox execution remains a separate option.`,
                      )
                    }
                  >
                    {activation[id as Provider]}
                  </button>
                )}
                {connection && connection.status !== "revoked" && (
                  <button
                    className="text-button"
                    disabled={!owner || busy}
                    onClick={() =>
                      act(
                        () => api(`/v1/connections/${id}/disconnect`, {}),
                        "Disconnected. Stored credentials were removed; provider accounts and subscriptions were not cancelled.",
                      )
                    }
                  >
                    Disconnect
                  </button>
                )}
              </div>
              {id === "gmail" && connection?.enabled && (
                <div>
                  <p className="small muted">
                    Scheduled inbox checks:{" "}
                    {connection.sync_enabled
                      ? `every ${connection.sync_interval_minutes} minutes`
                      : "disabled"}
                    {connection.sync_last_at
                      ? ` · Last check ${new Date(connection.sync_last_at * 1000).toLocaleString()}`
                      : ""}
                  </p>
                  {connection.sync_error && (
                    <p role="status">
                      {connection.sync_error.replaceAll("_", " ")}
                    </p>
                  )}
                  <button
                    className="secondary"
                    disabled={!owner || busy}
                    onClick={() =>
                      act(
                        () =>
                          api("/v1/connections/gmail/sync-schedule", {
                            enabled: !connection.sync_enabled,
                            interval_minutes: 10,
                            auto_draft_replies: connection.auto_draft_replies,
                          }),
                        connection.sync_enabled
                          ? "Scheduled inbox checks disabled."
                          : "Scheduled inbox checks enabled every ten minutes. Replies are imported for review; nothing is sent automatically.",
                      )
                    }
                  >
                    {connection.sync_enabled
                      ? "Disable scheduled inbox checks"
                      : "Enable scheduled inbox checks"}
                  </button>
                  <p className="small muted">
                    Automatic reply drafts:{" "}
                    {connection.auto_draft_replies ? "enabled" : "disabled"}.
                    Clear interest and meeting requests can be drafted into
                    Approvals. Pricing, complaints and unclear replies need your
                    attention. Connected AI may charge within your budget.
                  </p>
                  <button
                    className="secondary"
                    disabled={!owner || busy}
                    onClick={() =>
                      act(
                        () =>
                          api("/v1/connections/gmail/sync-schedule", {
                            enabled: connection.sync_enabled,
                            interval_minutes:
                              connection.sync_interval_minutes || 10,
                            auto_draft_replies: !connection.auto_draft_replies,
                          }),
                        connection.auto_draft_replies
                          ? "Automatic reply drafting disabled."
                          : "Automatic reply drafting enabled. Nothing is sent without approval.",
                      )
                    }
                  >
                    {connection.auto_draft_replies
                      ? "Disable automatic reply drafts"
                      : "Enable automatic reply drafts"}
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </div>
      <details
        id="provider-configuration"
        className="form-disclosure"
        open={configureOpen}
        onToggle={(event) => setConfigureOpen(event.currentTarget.open)}
      >
        <summary>Configure a provider</summary>
        <p className="small muted">
          Saving replaces its previous credentials and disables the connection.
          Stored secrets are never returned to this form.
        </p>
        <form className="operation-form" onSubmit={save}>
          <fieldset disabled={!owner || busy}>
            <label>
              Provider
              <select
                value={provider}
                onChange={(e) => {
                  setProvider(e.target.value as Provider);
                  setCredentials({});
                }}
              >
                {Object.entries(providers).map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Account reference
              <input
                value={account}
                onChange={(e) => setAccount(e.target.value)}
                maxLength={254}
                required
              />
            </label>
            <div className="actions">
              <button
                type="button"
                className="secondary"
                onClick={placeholders}
              >
                Use placeholder values
              </button>
            </div>
            <div className="form-grid">
              {fields[provider].map(([key, label, secret]) => (
                <label key={key}>
                  {label}
                  <input
                    type={
                      secret
                        ? "password"
                        : key === "search_price_micros"
                          ? "number"
                          : "text"
                    }
                    min={key === "search_price_micros" ? 0 : undefined}
                    max={key === "search_price_micros" ? 1000 : undefined}
                    step={
                      key === "search_price_micros" ? "0.000001" : undefined
                    }
                    autoComplete="off"
                    value={credentials[key] || ""}
                    onChange={(e) =>
                      setCredentials({ ...credentials, [key]: e.target.value })
                    }
                    maxLength={10000}
                  />
                </label>
              ))}
            </div>
            <button className="primary">
              {busy ? "Saving…" : "Save disabled configuration"}
            </button>
          </fieldset>
        </form>
      </details>
      <p className="small muted">
        Google requires your own OAuth app and grants. Stripe requires an
        eligible merchant account, HTTPS return URLs and a reachable signed
        webhook endpoint. No account is created on your behalf.
      </p>
    </section>
  );
}
