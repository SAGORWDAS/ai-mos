// Split the canonical spec into per-concept files so a coding agent can load one at a time.
const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');

const SPEC = path.join(__dirname, '..', 'spec');
const raw = fs.readFileSync(path.join(SPEC, 'ai-mos.spec.yaml'), 'utf8');
const d = yaml.load(raw);

const header = (title, note) =>
  `# AI-MOS — ${title}\n# Extracted from spec/ai-mos.spec.yaml (normative source). Do not edit in isolation.\n# ${note}\n\n`;

const dump = obj => yaml.dump(obj, { lineWidth: 100, noRefs: true, quotingType: '"' });

const files = {
  'modules.yaml': header('modules', 'MOD-01..MOD-23. Navigation modules mapped to owning services.'),
  'agents.yaml': header('agents', 'AGT-01..AGT-20. Tier = default model tier; ceiling = max autonomy.'),
  'tool-registry.yaml': header('tools', 'TLS-01..TLS-18. The only egress to the outside world.'),
  'phase-tasks.yaml': header('phase tasks', 'Task ledger with dependencies and definitions of done.'),
  'invariants.yaml': header('invariants and acceptance', 'Rules that must hold at all times, and the tests that prove them.'),
};

fs.writeFileSync(path.join(SPEC, 'modules.yaml'), files['modules.yaml'] + dump({ spec_version: d.spec_version, modules: d.modules }), 'utf8');
fs.writeFileSync(path.join(SPEC, 'agents.yaml'), files['agents.yaml'] + dump({ spec_version: d.spec_version, agents: d.agents }), 'utf8');
fs.writeFileSync(path.join(SPEC, 'tool-registry.yaml'), files['tool-registry.yaml'] + dump({ spec_version: d.spec_version, tools: d.tools, gate_sequence: d.gate_sequence }), 'utf8');
fs.writeFileSync(path.join(SPEC, 'phase-tasks.yaml'), files['phase-tasks.yaml'] + dump({
  spec_version: d.spec_version,
  phases: d.phases.map(p => ({ id: p.id, name: p.name, objective: p.objective, gate_out: p.gate_out, tasks: p.tasks })),
}), 'utf8');
fs.writeFileSync(path.join(SPEC, 'invariants.yaml'), files['invariants.yaml'] + dump({
  spec_version: d.spec_version,
  invariants: d.invariants,
  acceptance_tests: d.acceptance_tests,
  definition_of_done: d.definition_of_done,
  autonomy: d.autonomy,
  approval_matrix: d.approval_matrix,
}), 'utf8');

console.log('wrote 5 split spec files');

// ---- per-task context capsules -------------------------------------------
const TASKS = require('./tasks');
const BUDGET = { 'PH-0': 1500, 'PH-1': 4000, 'PH-2': 5000, 'PH-3': 6000, 'PH-4': 5000, 'PH-5': 6000, 'PH-6': 6000 };
const TASKDIR = path.join(SPEC, 'tasks');
fs.mkdirSync(TASKDIR, { recursive: true });

for (const t of TASKS) {
  const capsule = {
    id: t.id,
    phase: t.phase,
    kind: t.kind,
    blocking: !!t.blocking,
    title: t.title,
    context_budget_tokens: BUDGET[t.phase] || 5000,
    load_only: t.load,
    files_create: t.files.filter(f => !f.endsWith('/')),
    steps: t.steps,
    done_when: t.done,
    do_not: [t.dont, 'do not start another task in this session', 'do not invent a table, endpoint, tool or model id'],
  };
  const body = `# ${t.id} — ${t.title}\n# Generated from spec/ai-mos.spec.yaml + blueprint/tasks.js. Do not edit alone.\n\n` +
    dump(capsule);
  fs.writeFileSync(path.join(TASKDIR, t.id + '.yaml'), body, 'utf8');
}
console.log('wrote ' + TASKS.length + ' task capsules to spec/tasks/');
