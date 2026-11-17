const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const mod = { exports: {} };
vm.runInNewContext(
  ts.transpileModule(
    fs.readFileSync(
      path.join(__dirname, "../app/connection-values.ts"),
      "utf8",
    ),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    },
  ).outputText,
  { module: mod, exports: mod.exports },
);
const { credentialPayload } = mod.exports;
test("search prices accept normal dollars while preserving unknown versus explicit free", () => {
  assert.equal(
    credentialPayload("brave", {
      api_key: "fixture",
      search_price_micros: "0.005",
    }).search_price_micros,
    "5000",
  );
  assert.equal(
    credentialPayload("brave", { search_price_micros: "0" })
      .search_price_micros,
    "0",
  );
  assert.equal(
    credentialPayload("brave", { search_price_micros: "" }).search_price_micros,
    undefined,
  );
  assert.equal(
    credentialPayload("openrouter", { model_id: "fixture/model" }).model_id,
    "fixture/model",
  );
});
test("invalid or fractional-micro prices cannot silently change recorded campaign costs", () => {
  for (const value of ["-1", "Infinity", "text", "0.0000005", "1001"])
    assert.throws(() =>
      credentialPayload("brave", { search_price_micros: value }),
    );
});
