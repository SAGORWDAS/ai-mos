const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');

const WS = path.join(__dirname, '..');
let bad = 0;
const ok = m => console.log('  ok    ' + m);
const fail = m => { console.log('  FAIL  ' + m); bad++; };

for (const f of ['infra/docker-compose.yml', '.github/workflows/ci.yml']) {
  try { yaml.load(fs.readFileSync(path.join(WS, f), 'utf8')); ok(f + ' parses'); }
  catch (e) { fail(f + ' → ' + e.message.split('\n')[0]); }
}

for (const f of ['frontend/package.json', 'frontend/tsconfig.json']) {
  try { JSON.parse(fs.readFileSync(path.join(WS, f), 'utf8')); ok(f + ' parses'); }
  catch (e) { fail(f + ' → ' + e.message); }
}

// Makefile: recipe lines must start with a TAB
const mk = fs.readFileSync(path.join(WS, 'Makefile'), 'utf8').split('\n');
const recipes = mk.filter(l => /^\t/.test(l)).length;
const badIndent = mk.filter(l => /^ {2,}(\$\(COMPOSE\)|@echo|powershell|cp |test -f)/.test(l));
badIndent.length ? fail('Makefile has space-indented recipes: ' + badIndent.slice(0, 2).join(' | ')) : ok('Makefile: ' + recipes + ' tab-indented recipe lines');

// compose: every service has a build or image
const compose = yaml.load(fs.readFileSync(path.join(WS, 'infra/docker-compose.yml'), 'utf8'));
const svc = Object.keys(compose.services);
const missing = svc.filter(s => !compose.services[s].build && !compose.services[s].image);
console.log('  services: ' + svc.join(', '));
missing.length ? fail('services without build/image: ' + missing) : ok('all services resolve');

// required env keys present in the example
const envEx = fs.readFileSync(path.join(WS, '.env.example'), 'utf8');
const required = ['DATABASE_URL', 'REDIS_URL', 'OPENROUTER_API_KEY', 'TOKEN_ENCRYPTION_KEY'];
const absent = required.filter(k => !new RegExp('^' + k + '=', 'm').test(envEx));
absent.length ? fail('.env.example missing: ' + absent) : ok('.env.example lists provider configuration (optional locally)');

process.exit(bad ? 1 : 0);
