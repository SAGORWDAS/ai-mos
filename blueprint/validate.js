const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');

const specPath = path.join(__dirname, '..', 'spec', 'ai-mos.spec.yaml');
const d = yaml.load(fs.readFileSync(specPath, 'utf8'));
const tasks = d.phases.reduce((a, p) => a + p.tasks.length, 0);
console.log('YAML OK');
console.log('  modules=' + d.modules.length + ' agents=' + d.agents.length +
  ' tools=' + d.tools.length + ' phases=' + d.phases.length + ' tasks=' + tasks +
  ' acs=' + d.acceptance_tests.length);

const schemaDir = path.join(__dirname, '..', 'spec', 'schemas');
for (const f of fs.readdirSync(schemaDir).filter(name => name.endsWith('.json'))) {
  JSON.parse(fs.readFileSync(path.join(schemaDir, f), 'utf8'));
  console.log('JSON OK ' + f);
}

// referential sanity: every agent tool exists; every module service exists
const toolIds = new Set(d.tools.map(t => t.id));
const svcIds = new Set(d.services.map(s => s.id));
const badTools = [];
d.agents.forEach(a => (a.tools || []).forEach(t => { if (!toolIds.has(t)) badTools.push(a.id + '->' + t); }));
const badSvc = d.modules.filter(m => !svcIds.has(m.service)).map(m => m.id);
console.log('broken tool refs: ' + (badTools.length ? badTools.join(',') : 'none'));
console.log('broken service refs: ' + (badSvc.length ? badSvc.join(',') : 'none'));

// Dependencies may point to earlier phases as well as tasks in this phase.
const dangling = [];
const allTasks = d.phases.flatMap(p => p.tasks);
const taskIds = new Set(allTasks.map(t => t.id));
const phaseIds = new Set(d.phases.map(p => p.id));
d.phases.forEach(p => {
  p.tasks.forEach(t => (t.depends || []).forEach(dep => {
    if (!taskIds.has(dep) && !phaseIds.has(dep)) dangling.push(t.id + '->' + dep);
  }));
});
console.log('dangling deps: ' + (dangling.length ? dangling.join(',') : 'none'));

// ---- task capsules must exist one-for-one ---------------------------------
const TASKS = require('./tasks');
const capsuleDir = path.join(__dirname, '..', 'spec', 'tasks');
const specIds = new Set(d.phases.flatMap(p => p.tasks.map(t => t.id)));
const cardIds = new Set(TASKS.map(t => t.id));
const capsuleIds = fs.existsSync(capsuleDir)
  ? new Set(fs.readdirSync(capsuleDir).filter(f => f.endsWith('.yaml')).map(f => f.replace('.yaml', '')))
  : new Set();

const missing = [...specIds].filter(id => !cardIds.has(id));
const extra = [...cardIds].filter(id => !specIds.has(id));
const noCapsule = [...cardIds].filter(id => !capsuleIds.has(id));

console.log('cards: ' + cardIds.size + ' · spec tasks: ' + specIds.size + ' · capsules: ' + capsuleIds.size);
console.log('spec tasks without a card: ' + (missing.length ? missing.join(',') : 'none'));
console.log('cards without a spec task: ' + (extra.length ? extra.join(',') : 'none'));
console.log('cards without a capsule: ' + (noCapsule.length ? noCapsule.join(',') : 'none'));

// Report failures to CI rather than printing errors and exiting successfully.
const duplicateTaskIds = taskIds.size !== allTasks.length;
const extraCapsules = [...capsuleIds].filter(id => !specIds.has(id));
const badCapsuleIds = [...capsuleIds].filter(id => {
  const capsule = yaml.load(fs.readFileSync(path.join(capsuleDir, id + '.yaml'), 'utf8'));
  return capsule.id !== id;
});
const visiting = new Set();
const visited = new Set();
const cycles = [];
const graph = new Map(allTasks.map(t => [t.id, (t.depends || []).flatMap(dep => {
  if (phaseIds.has(dep)) return d.phases.find(p => p.id === dep).tasks.map(t => t.id);
  return [dep];
})]));
function visit(id) {
  if (visiting.has(id)) { cycles.push(id); return; }
  if (visited.has(id)) return;
  visiting.add(id);
  for (const dependency of graph.get(id) || []) visit(dependency);
  visiting.delete(id);
  visited.add(id);
}
for (const id of taskIds) visit(id);
console.log('dependency cycles: ' + (cycles.length ? cycles.join(',') : 'none'));
console.log('extra capsules: ' + (extraCapsules.length ? extraCapsules.join(',') : 'none'));
console.log('capsule id mismatches: ' + (badCapsuleIds.length ? badCapsuleIds.join(',') : 'none'));
if (duplicateTaskIds || [badTools, badSvc, dangling, missing, extra, noCapsule,
    extraCapsules, badCapsuleIds, cycles].some(errors => errors.length)) process.exitCode = 1;
