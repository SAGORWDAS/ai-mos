const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const ts = require("typescript");
const moduleUnderTest = { exports: {} };
vm.runInNewContext(
  ts.transpileModule(
    fs.readFileSync(
      require("node:path").join(__dirname, "../app/cost-forecast.ts"),
      "utf8",
    ),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    },
  ).outputText,
  { module: moduleUnderTest, exports: moduleUnderTest.exports },
);
const { costForecast } = moduleUnderTest.exports;
const baseline = {
  prospects: 1000,
  variablePer100: [1, 2, 3, 4, 5],
  fixedMonthly: 50,
  rates: [50, 90, 10, 20, 50],
  firstYearRevenue: 1000,
};
test("forecast scales acquisition costs through the funnel and preserves fixed costs", () => {
  const r = costForecast(baseline);
  assert.equal(r.total, 200);
  assert.equal(r.variableCost, 150);
  assert.equal(r.counts[4], 4.5);
  assert.equal(r.cpl, 0.4);
  assert.equal(r.cac, 200 / 4.5);
  assert.equal(r.expectedRevenue, 4500);
});
test("zero conversion has no finite CAC and invalid assumptions cannot show a misleading result", () => {
  const r = costForecast({ ...baseline, rates: [50, 90, 0, 20, 50] });
  assert.equal(r.cac, null);
  assert.equal(r.costPerReply, null);
  for (const input of [
    { ...baseline, prospects: NaN },
    { ...baseline, rates: [101, 1, 1, 1, 1] },
    { ...baseline, fixedMonthly: -1 },
    { ...baseline, rates: [] },
  ])
    assert.throws(() => costForecast(input));
});
