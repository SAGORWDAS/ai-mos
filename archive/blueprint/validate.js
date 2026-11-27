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

for (const f of ['plan', 'outreach_draft']) {
  JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'spec', 'schemas', f + '.json'), 'utf8'));
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

// every task dependency resolves within its phase
const dangling = [];
d.phases.forEach(p => {
  const ids = new Set(p.tasks.map(t => t.id));
  p.tasks.forEach(t => (t.depends || []).forEach(dep => {
    if (!ids.has(dep) && !/^PH-/.test(dep)) dangling.push(t.id + '->' + dep);
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
