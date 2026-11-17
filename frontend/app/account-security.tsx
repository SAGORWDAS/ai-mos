"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";

type Member = { id: string; name: string; email: string; role: string };

export function RecoveryForm() {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function recover(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const form = event.currentTarget;
    try {
      await api(
        "/v1/auth/recover",
        Object.fromEntries(new FormData(form).entries()),
      );
      form.reset();
      setMessage(
        "Account recovered. Sign in with the new password, then create a new recovery code and set up your authenticator again.",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Recovery failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="evidence">
      <summary>Recover your account</summary>
      <p>
        Use the private recovery code you saved earlier. Recovery changes the
        password, disables the old authenticator and signs out every session.
        Without a saved code, this local build cannot prove account ownership.
      </p>
      <form onSubmit={recover}>
        <label>
          Email
          <input name="email" type="email" autoComplete="username" required />
        </label>
        <label>
          Private recovery code
          <input
            name="code"
            type="password"
            autoComplete="off"
            required
            minLength={20}
          />
        </label>
        <label>
          New password
          <input
            name="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
          />
        </label>
        <button className="secondary" disabled={busy}>
          Recover and revoke sessions
        </button>
      </form>
      {message && <p role="status">{message}</p>}
    </details>
  );
}

export default function AccountSecurity({
  owner,
  onChange,
}: {
  owner: boolean;
  onChange: () => Promise<void>;
}) {
  const [status, setStatus] = useState({
    mfa_enabled: false,
    recovery_configured: false,
  });
  const [members, setMembers] = useState<Member[]>([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [code, setCode] = useState(""),
    [secret, setSecret] = useState("");
  async function refresh() {
    setStatus(await api("/v1/auth/security"));
    setMembers(await api("/v1/org/members"));
  }
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
  }, []);
  async function act(
    path: string,
    body: unknown,
    message: string,
    method = "POST",
  ) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<Record<string, unknown>>(path, body, method);
      await refresh();
      await onChange();
      setNotice(message);
      return result;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
      return null;
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="section">
      <h2>Account security</h2>
      <p className="muted">
        Recovery code:{" "}
        {status.recovery_configured ? "configured" : "not configured"} ·
        Authenticator: {status.mfa_enabled ? "enabled" : "disabled"}
      </p>
      {error && (
        <p className="message error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="message" role="status">
          {notice}
        </p>
      )}
      <details className="evidence">
        <summary>Recovery and two-step login</summary>
        <p>
          Store a recovery code privately before enabling an authenticator. Each
          authenticator code can be used once; wait for the next code when
          needed.
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const values = Object.fromEntries(
              new FormData(e.currentTarget).entries(),
            );
            const action = String(values.action);
            delete values.action;
            const result = await act(
              "/v1/auth/" + action,
              values,
              "Security setting updated.",
            );
            if (result?.code) setCode(String(result.code));
            if (result?.secret) setSecret(String(result.secret));
            if (action === "mfa/disable" && result) setSecret("");
          }}
        >
          <fieldset disabled={busy}>
            <label>
              Current password
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
              />
            </label>
            {status.mfa_enabled && (
              <label>
                Current authenticator code
                <input
                  name="otp"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  required
                />
              </label>
            )}
            <label>
              Action
              <select name="action">
                <option value="recovery-code">
                  Create or replace recovery code
                </option>
                {!status.mfa_enabled && (
                  <option value="mfa/setup">Set up authenticator</option>
                )}
                {status.mfa_enabled && (
                  <option value="mfa/disable">Disable authenticator</option>
                )}
              </select>
            </label>
            <button className="secondary">Apply security change</button>
          </fieldset>
        </form>
        {code && (
          <div className="message">
            <b>Shown once. Save privately.</b>
            <p className="preserve">{code}</p>
            <button className="text-button" onClick={() => setCode("")}>
              Hide saved code
            </button>
          </div>
        )}
        {secret && (
          <div className="message">
            <p>
              Enter this setup key in your authenticator app. It is not enabled
              until you confirm a code.
            </p>
            <p className="preserve">{secret}</p>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                const result = await act(
                  "/v1/auth/mfa/confirm",
                  Object.fromEntries(new FormData(e.currentTarget).entries()),
                  "Authenticator enabled. Other sessions were signed out.",
                );
                if (result) setSecret("");
              }}
            >
              <label>
                Authenticator code
                <input
                  name="otp"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  required
                />
              </label>
              <button className="secondary" disabled={busy}>
                Confirm authenticator
              </button>
            </form>
          </div>
        )}
      </details>
      {owner && (
        <details className="evidence">
          <summary>Manage workspace access</summary>
          <p>
            Role changes apply on the next request. Removing a member revokes
            their sessions in this workspace; their account and other workspaces
            remain.
          </p>
          {members
            .filter((m) => m.role !== "owner")
            .map((member) => (
              <div className="operation-card" key={member.id}>
                <h3>{member.name}</h3>
                <p>{member.email}</p>
                <div className="actions">
                  <select
                    aria-label={`Role for ${member.name}`}
                    value={member.role}
                    disabled={busy}
                    onChange={(e) =>
                      act(
                        `/v1/org/members/${member.id}`,
                        { role: e.target.value },
                        "Member role updated.",
                        "PUT",
                      )
                    }
                  >
                    <option value="admin">Admin</option>
                    <option value="member">Member</option>
                    <option value="viewer">Viewer</option>
                  </select>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      act(
                        `/v1/org/members/${member.id}/remove`,
                        {},
                        "Member removed and workspace sessions revoked.",
                      )
                    }
                  >
                    Remove member
                  </button>
                </div>
              </div>
            ))}
          <h3>Transfer ownership</h3>
          <p>
            The chosen member becomes owner and you become an admin. This needs
            your current password and, if enabled, a fresh authenticator code.
          </p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              await act(
                "/v1/org/transfer",
                Object.fromEntries(new FormData(e.currentTarget).entries()),
                "Workspace ownership transferred.",
              );
            }}
          >
            <fieldset disabled={busy}>
              <label>
                New owner
                <select name="user_id" required>
                  <option value="">Choose an existing member</option>
                  {members
                    .filter((m) => m.role !== "owner")
                    .map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name} — {m.email}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Current password
                <input
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                />
              </label>
              {status.mfa_enabled && (
                <label>
                  Authenticator code
                  <input name="otp" pattern="[0-9]{6}" required />
                </label>
              )}
              <button className="secondary">Transfer ownership</button>
            </fieldset>
          </form>
        </details>
      )}
    </section>
  );
}
