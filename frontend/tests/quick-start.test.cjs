const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");
const ts = require("typescript");
const React = require("react");

function harness(api) {
  const state = [];
  let cursor = 0;
  let started = 0;
  const mockReact = {
    ...React,
    useState(initial) {
      const i = cursor++;
      if (!(i in state)) state[i] = initial;
      return [
        state[i],
        (value) => {
          state[i] = typeof value === "function" ? value(state[i]) : value;
        },
      ];
    },
  };
  const module = { exports: {} };
  const source = ts.transpileModule(
    fs.readFileSync(path.join(__dirname, "../app/quick-start.tsx"), "utf8"),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
        target: ts.ScriptTarget.ES2022,
      },
    },
  ).outputText;
  vm.runInNewContext(source, {
    module,
    exports: module.exports,
    require(name) {
      if (name === "react") return mockReact;
      if (name === "./api") return { api };
      return require(name);
    },
    crypto: webcrypto,
    FormData: class {
      constructor(values) {
        this.values = values;
      }
      get(key) {
        return this.values[key] ?? null;
      }
    },
  });
  const render = () => {
    cursor = 0;
    return module.exports.default({
      disabled: false,
      onStarted: async () => {
        started++;
      },
      onConnect: () => {},
    });
  };
  return { render, started: () => started };
}
function elements(tree, predicate, result = []) {
  if (Array.isArray(tree)) {
    tree.forEach((child) => elements(child, predicate, result));
    return result;
  }
  if (tree && typeof tree === "object" && tree.props) {
    if (predicate(tree)) result.push(tree);
    elements(tree.props.children, predicate, result);
  }
  return result;
}
const brief = {
  name: "Independent SaaS",
  offer: "We provide booking software for studios.",
  audience: "Independent studios",
  objective: "Find suitable prospects and prepare outreach.",
};
const submit = (tree, fields) =>
  elements(tree, (node) => node.type === "form")[0].props.onSubmit({
    preventDefault() {},
    currentTarget: fields,
  });

test("a short business brief starts preparation using only supplied facts", async () => {
  const calls = [];
  const h = harness(async (route, body) => {
    calls.push({ route, body });
    return route === "/v1/brands" ? { id: "brand-one" } : { status: "queued" };
  });
  await submit(h.render(), brief);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].route, "/v1/setup/start");
  assert.equal(calls[0].body.offer, brief.offer);
  assert.equal(calls[0].body.audience, brief.audience);
  assert.equal(calls[0].body.connected_research, false);
  assert.equal(h.started(), 1);
});

test("a failed campaign start retries without duplicating the saved business", async () => {
  const calls = [];
  let failed = false;
  const h = harness(async (route, body) => {
    calls.push({ route, body });
    if (route === "/v1/brands") return { id: "saved-brand" };
    if (!failed) {
      failed = true;
      throw new Error("Temporary test failure");
    }
    return { status: "queued" };
  });
  await submit(h.render(), brief);
  assert.equal(h.started(), 0);
  await submit(h.render(), brief);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].body.idempotency_key, calls[1].body.idempotency_key);
  assert.equal(h.started(), 1);
});

test("fictional sample prepares an invalid-domain contact and sandbox-only business", async () => {
  const calls = [];
  const h = harness(async (route, body) => {
    calls.push({ route, body });
    if (route === "/v1/brands") return { id: "sample-brand" };
    if (route === "/v1/leads/import")
      return { created: [{ id: "sample-contact" }], duplicates: [] };
    return { status: "queued" };
  });
  const sampleButton = elements(
    h.render(),
    (node) =>
      node.type === "button" &&
      node.props.children === "Fill with a fictional sample",
  )[0];
  sampleButton.props.onClick();
  await submit(h.render(), { ...brief, name: "Fictional sample agency" });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].route, "/v1/setup/start");
  assert.equal(calls[0].body.sample, true);
  assert.equal(calls[0].body.connected_research, false);
});
