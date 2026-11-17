const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

function client(fetch) {
  const module = { exports: {} };
  let reloads = 0;
  const notifications = [];
  const code = ts.transpileModule(
    fs.readFileSync(path.join(__dirname, "../app/api.ts"), "utf8"),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    },
  ).outputText;
  vm.runInNewContext(code, {
    module,
    exports: module.exports,
    fetch,
    crypto: { randomUUID: () => "synthetic-session-event" },
    window: {
      localStorage: {
        setItem(key, value) {
          notifications.push({ key, value });
        },
      },
      location: {
        reload() {
          reloads++;
        },
      },
    },
  });
  return { ...module.exports, reloads: () => reloads, notifications };
}
const response = (status, detail) => ({
  ok: status < 400,
  status,
  json: async () => ({ detail }),
});

test("private calls bind workspace/user; auth and bootstrap remain unbound", async () => {
  const calls = [];
  const c = client(async (url, options) => {
    calls.push({ url, options });
    return response(200, "ok");
  });
  c.setWorkspaceContext("workspace-a", "user-a");
  await c.api("/v1/brands");
  assert.equal(calls[0].options.headers["X-Workspace-ID"], "workspace-a");
  assert.equal(calls[0].options.headers["X-User-ID"], "user-a");
  await c.api("/v1/workspace");
  await c.api("/v1/auth/login", { email: "synthetic@example.test" });
  assert.equal(calls[1].options.headers["X-Workspace-ID"], undefined);
  assert.equal(calls[2].options.headers["X-User-ID"], undefined);
  assert.equal(c.notifications.length, 1);
  assert.equal(c.notifications[0].key, c.SESSION_EVENT_KEY);
  assert.equal(c.notifications[0].value, "synthetic-session-event");
  c.setWorkspaceContext(null);
  await c.api("/v1/brands");
  assert.equal(calls[3].options.headers["X-Workspace-ID"], undefined);
});

test("a session context mismatch rejects data and reloads only once", async () => {
  const c = client(async () => response(409, "session_context_changed"));
  c.setWorkspaceContext("a", "user");
  await assert.rejects(c.api("/v1/data/leads"), /session context changed/);
  await assert.rejects(c.api("/v1/data/leads"), /session context changed/);
  assert.equal(c.reloads(), 1);
});

test("a stale request cannot reload a newly selected workspace", async () => {
  let finish;
  const c = client(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  c.setWorkspaceContext("a", "user");
  const pending = c.api("/v1/data/leads");
  c.setWorkspaceContext("b", "user");
  finish(response(409, "session_context_changed"));
  await assert.rejects(pending, /session context changed/);
  assert.equal(c.reloads(), 0);
});

test("an expired session reloads while password-proof rejection preserves the page", async () => {
  const expired = client(async () => response(401, "unauthenticated"));
  expired.setWorkspaceContext("a", "user");
  await assert.rejects(expired.api("/v1/brands"), /unauthenticated/);
  assert.equal(expired.reloads(), 1);
  const proof = client(async () => response(401, "invalid_credentials"));
  proof.setWorkspaceContext("a", "user");
  await assert.rejects(
    proof.api("/v1/auth/mfa/setup", { password: "synthetic wrong proof" }),
    /invalid credentials/,
  );
  assert.equal(proof.reloads(), 0);
});
