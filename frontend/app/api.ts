let activeWorkspace: string | null = null;
let activeUser: string | null = null;
let reloading = false;
export const SESSION_EVENT_KEY = "ai-mos.session-change";

export function setWorkspaceContext(
  workspace: string | null,
  user: string | null = null,
) {
  activeWorkspace = workspace;
  activeUser = user;
}

export async function api<T>(
  path: string,
  body?: unknown,
  method = "POST",
): Promise<T> {
  const bind = path !== "/v1/workspace" && !path.startsWith("/v1/auth/");
  const workspace = bind ? activeWorkspace : null;
  const user = bind ? activeUser : null;
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (workspace) headers["X-Workspace-ID"] = workspace;
  if (user) headers["X-User-ID"] = user;
  const response = await fetch(`/api${path}`, {
    method: body === undefined ? "GET" : method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    const detail = result.detail;
    if (
      (detail === "session_context_changed" ||
        detail === "unauthenticated" ||
        detail === "membership_revoked") &&
      workspace &&
      workspace === activeWorkspace &&
      user === activeUser &&
      !reloading
    ) {
      reloading = true;
      window.location.reload();
    }
    const message = Array.isArray(detail)
      ? detail.map((item: { msg: string }) => item.msg).join(". ")
      : detail;
    throw new Error(
      message
        ? String(message).replaceAll("_", " ")
        : `Request failed (${response.status})`,
    );
  }
  if (
    body !== undefined &&
    ([
      "/v1/auth/login",
      "/v1/auth/signup",
      "/v1/auth/logout",
      "/v1/auth/recover",
      "/v1/org/invitations/accept",
    ].includes(path) ||
      /^\/v1\/orgs\/[^/]+\/switch$/.test(path))
  ) {
    try {
      window.localStorage.setItem(SESSION_EVENT_KEY, crypto.randomUUID());
    } catch {
      /* Request context checks still protect tabs when browser storage is unavailable. */
    }
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
