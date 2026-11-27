// App: routes, request handler and autopilot timers. Started by ../server.js
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { all, get, run, log, getSetting, setSetting, allSettings, getJSON, setJSON } = require('./db');
const ai = require('./ai');
const mail = require('./mail');
const team = require('./agents');

const PORT = process.env.PORT || 3000; // a number, or a socket path on some hosts
const HOST = process.env.HOST || '127.0.0.1';
const PUB = path.join(__dirname, '..', 'public');
const SECRETS = ['openai_key', 'gmail_pass'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- helpers ----------
const mask = (v) => (v ? '•'.repeat(8) + v.slice(-4) : '');
const thread = (leadId) => all('SELECT direction,subject,body FROM messages WHERE lead_id=? AND status IN (\'sent\',\'received\',\'handled\') ORDER BY id', leadId)
  .map((m) => `${m.direction === 'out' ? 'US' : 'THEM'}: ${m.subject ? `[${m.subject}] ` : ''}${m.body}`).join('\n---\n').slice(-3500);

function state() {
  const s = allSettings();
  for (const k of SECRETS) s[k] = mask(s[k]);
  const brand = getJSON('brand', {});
  const c = (sql) => get(sql).n;
  const usage = get("SELECT COALESCE(SUM(cost),0) total, COALESCE(SUM(CASE WHEN created>=datetime('now','-30 days') THEN cost END),0) month, COUNT(*) calls FROM usage");
  return {
    settings: s, brand, channels: team.CHANNELS, cronPath: CRON ? '/api/cron?key=' + CRON : '', sources: get('SELECT COUNT(*) n FROM sources WHERE active=1').n,
    stats: {
      leads: c('SELECT COUNT(*) n FROM leads'),
      contacted: c("SELECT COUNT(*) n FROM leads WHERE status NOT IN ('new','skipped','call')"),
      calls: c("SELECT COUNT(*) n FROM leads WHERE status='call'"),
      replied: c("SELECT COUNT(*) n FROM leads WHERE status IN ('replied','interested','meeting','won','lost','unsubscribed')"),
      interested: c("SELECT COUNT(*) n FROM leads WHERE status IN ('interested','meeting','won')"),
      won: c("SELECT COUNT(*) n FROM leads WHERE status='won'"),
      drafts: c("SELECT COUNT(*) n FROM messages WHERE status='draft'"),
      unread: c("SELECT COUNT(*) n FROM messages WHERE status='received'"),
      sentToday: engine.sentToday(), meetings: c("SELECT COUNT(*) n FROM leads WHERE status='meeting'"), cap: +s.daily_cap,
      plans: c('SELECT COUNT(*) n FROM plans'), content: c('SELECT COUNT(*) n FROM content'),
    },
    usage,
    ready: { openai: !!getSetting('openai_key'), gmail: !!(getSetting('gmail_user') && getSetting('gmail_pass')), brand: !!brand.name },
    lastInboxCheck: getSetting('last_inbox_check'), workHours: engine.inWorkHours(),
    activity: all('SELECT * FROM activity ORDER BY id DESC LIMIT 40'),
  };
}

const engine = require('./engine');
const finder = require('./finder');
const sources = require('./sources');
const { draftFirst, draftFollowups, sendOne, checkInbox } = engine;

// ---------- routes ----------
const routes = {
  'GET /api/state': () => state(),

  'POST /api/settings': async (b) => {
    for (const [k, v] of Object.entries(b)) {
      if (!(k in allSettings())) continue;
      if (SECRETS.includes(k) && (v === '' || String(v).startsWith('•'))) continue; // unchanged secret
      setSetting(k, typeof v === 'string' ? v.trim() : v);
    }
    return state();
  },
  'POST /api/test/openai': async () => { await ai.testKey(getSetting('openai_key'), getSetting('model')); return { ok: true }; },
  'POST /api/test/gmail': async () => { await mail.test(); return { ok: true }; },

  'POST /api/brand': (b) => { setJSON('brand', b); return state(); },
  'POST /api/brand/autofill': async (b) => team.brandFromWebsite(String(b.url || '').trim()),
  'POST /api/onboard': async (b) => { const brand = await team.brandFromWebsite(String(b.url || '').trim()); setJSON('brand', brand); log('setup', 'Learned your product from ' + brand.website); return state(); },
  'POST /api/leads/find': async () => ({ added: await engine.prospect() }),
  'POST /api/autopilot/run': async () => { await engine.tick(); return state(); },
  'GET /api/report': () => engine.report(),
  'GET /api/sources': () => all('SELECT * FROM sources ORDER BY id DESC'),
  'POST /api/sources/categories': async (b) => sources.listCategories(String(b.url || '').trim()),
  'POST /api/sources': (b) => {
    const url = String(b.url || '').trim();
    if (!/^https?:\/\//.test(url)) throw new Error('Paste the full directory link, starting with https://');
    run('INSERT INTO sources(url,categories) VALUES(?,?)', url, JSON.stringify(b.categories || []));
    log('setup', 'Added lead source ' + new URL(url).host + ' (' + (b.categories || []).length + ' categories)');
    return all('SELECT * FROM sources ORDER BY id DESC');
  },
  'PATCH /api/sources/:id': (b, id) => { if ('active' in b) run('UPDATE sources SET active=? WHERE id=?', b.active ? 1 : 0, id); if (b.categories) run('UPDATE sources SET categories=? WHERE id=?', JSON.stringify(b.categories), id); return { ok: true }; },
  'DELETE /api/sources/:id': (b, id) => { run('DELETE FROM sources WHERE id=?', id); return { ok: true }; },
  'POST /api/sources/:id/run': async (b, id) => sources.runSource(get('SELECT * FROM sources WHERE id=?', id), 15),

  'GET /api/plans': () => all('SELECT * FROM plans ORDER BY id DESC'),
  'POST /api/plans': async (b) => { const body = await team.plan(b.goal); run('INSERT INTO plans(goal,body) VALUES(?,?)', b.goal || '', body); return all('SELECT * FROM plans ORDER BY id DESC'); },
  'DELETE /api/plans/:id': (b, id) => { run('DELETE FROM plans WHERE id=?', id); return { ok: true }; },

  'GET /api/content': () => all('SELECT * FROM content ORDER BY id DESC LIMIT 200'),
  'POST /api/content': async (b) => {
    const items = await team.content(b.channel, b.topic, Math.min(+b.count || 3, 5));
    for (const it of items) run('INSERT INTO content(channel,topic,body) VALUES(?,?,?)', b.channel, b.topic || '', typeof it === 'string' ? it : JSON.stringify(it, null, 2));
    return all('SELECT * FROM content ORDER BY id DESC LIMIT 200');
  },
  'DELETE /api/content/:id': (b, id) => { run('DELETE FROM content WHERE id=?', id); return { ok: true }; },

  'GET /api/leads': () => all('SELECT * FROM leads ORDER BY COALESCE(score,-1) DESC, id DESC'),
  'POST /api/leads': (b) => {
    let added = 0, skipped = 0;
    for (const l of b.leads || []) {
      const email = String(l.email || '').trim().toLowerCase();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { skipped++; continue; }
      const r = run('INSERT OR IGNORE INTO leads(name,email,company,role,website,notes) VALUES(?,?,?,?,?,?)',
        l.name || '', email, l.company || '', l.role || '', l.website || '', l.notes || '');
      r.changes ? added++ : skipped++;
    }
    return { added, skipped };
  },
  'PATCH /api/leads/:id': (b, id) => {
    for (const k of ['name', 'email', 'phone', 'company', 'role', 'website', 'notes', 'status']) if (k in b) run(`UPDATE leads SET ${k}=? WHERE id=?`, b[k], id);
    return get('SELECT * FROM leads WHERE id=?', id);
  },
  'DELETE /api/leads/:id': (b, id) => { run('DELETE FROM leads WHERE id=?', id); return { ok: true }; },
  'POST /api/leads/score': async (b) => {
    const ids = (b.ids?.length ? b.ids : all('SELECT id FROM leads WHERE score IS NULL').map((r) => r.id)).slice(0, 200);
    for (let i = 0; i < ids.length; i += 20) {
      const batch = ids.slice(i, i + 20).map((id) => get('SELECT * FROM leads WHERE id=?', id)).filter(Boolean);
      for (const s of await team.scoreLeads(batch)) run('UPDATE leads SET score=?, score_reason=? WHERE id=?', Math.round(+s.score || 0), s.reason || '', s.id);
    }
    return { scored: ids.length };
  },

  'POST /api/outreach/draft': async (b) => ({ drafted: await draftFirst(b.ids || []) }),
  'POST /api/outreach/followups': async () => ({ drafted: await draftFollowups() }),
  'GET /api/messages': (b, id, q) => all(`SELECT m.*, l.name, l.email, l.company, l.status lead_status FROM messages m JOIN leads l ON l.id=m.lead_id
    ${q.get('status') ? 'WHERE m.status IN (' + q.get('status').split(',').map(() => '?').join(',') + ')' : ''} ORDER BY m.id DESC LIMIT 300`, ...(q.get('status')?.split(',') || [])),
  'GET /api/leads/:id/thread': (b, id) => ({ lead: get('SELECT * FROM leads WHERE id=?', id), messages: all('SELECT * FROM messages WHERE lead_id=? ORDER BY id', id) }),
  'PATCH /api/messages/:id': (b, id) => {
    if ('subject' in b) run('UPDATE messages SET subject=? WHERE id=?', b.subject, id);
    if ('body' in b) run('UPDATE messages SET body=? WHERE id=?', b.body, id);
    if (b.status === 'handled') run("UPDATE messages SET status='handled' WHERE id=? AND status='received'", id);
    return { ok: true };
  },
  'DELETE /api/messages/:id': (b, id) => { run("DELETE FROM messages WHERE id=? AND status IN ('draft','failed')", id); return { ok: true }; },
  'POST /api/messages/send': async (b) => {
    let sent = 0; const errors = [];
    for (const id of b.ids || []) {
      try { await sendOne(id); sent++; if ((b.ids || []).length > 1) await sleep(4000 + Math.random() * 4000); }
      catch (e) { errors.push(e.message); if (/Daily limit|App Password|Invalid login|auth/i.test(e.message)) break; }
    }
    return { sent, errors };
  },
  'POST /api/inbox/check': () => checkInbox(),
};

const table = Object.entries(routes).map(([k, fn]) => {
  const [method, pattern] = k.split(' ');
  return { method, re: new RegExp('^' + pattern.replace(/:id/, '(\\d+)') + '$'), fn };
});

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.ico': 'image/x-icon' };

// Password login: required whenever the app is reachable from outside this PC.
const LOCAL = HOST === '127.0.0.1' || HOST === 'localhost';
const PASSWORD = process.env.APP_PASSWORD || '';
const TOKEN = PASSWORD && require('node:crypto').createHmac('sha256', PASSWORD).update('mt-session-v1').digest('hex');
const CRON = TOKEN && TOKEN.slice(0, 24);
const authed = (req) => !PASSWORD || (req.headers.cookie || '').split(/;\s*/).includes('mt=' + TOKEN);

async function handler(req, res) {
  const host = (req.headers.host || '').split(':')[0];
  if (LOCAL && !['localhost', '127.0.0.1'].includes(host)) { res.writeHead(403); return res.end(); }
  const url = new URL(req.url, 'http://x');

  if (url.pathname === '/api/login' && req.method === 'POST') {
    let raw = ''; for await (const c of req) { raw += c; if (raw.length > 2000) break; }
    const ok = PASSWORD && JSON.parse(raw || '{}').password === PASSWORD;
    if (!ok) await sleep(1500); // slow down guessing
    const secure = req.headers['x-forwarded-proto'] === 'https' ? '; Secure' : '';
    res.writeHead(ok ? 200 : 401, { 'Content-Type': 'application/json', ...(ok ? { 'Set-Cookie': `mt=${TOKEN}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000${secure}` } : {}) });
    return res.end(JSON.stringify(ok ? { ok: true } : { error: 'Wrong password' }));
  }
  if (url.pathname === '/api/cron') { // for a hosting cron job: wakes the app and runs one autopilot cycle
    const ok = CRON && url.searchParams.get('key') === CRON;
    if (ok) engine.tick().catch((e) => console.error('cron:', e.message));
    res.writeHead(ok ? 200 : 403); return res.end(ok ? 'ok' : 'forbidden');
  }
  if (url.pathname.startsWith('/api/') && !authed(req)) { res.writeHead(401, { 'Content-Type': 'application/json' }); return res.end('{"error":"login"}'); }

  if (url.pathname.startsWith('/api/')) {
    const r = table.find((t) => t.method === req.method && t.re.test(url.pathname));
    if (!r) { res.writeHead(404); return res.end('{}'); }
    try {
      let body = {};
      if (req.method !== 'GET') {
        let raw = '';
        for await (const chunk of req) { raw += chunk; if (raw.length > 5e6) throw new Error('Too large'); }
        body = raw ? JSON.parse(raw) : {};
      }
      const out = await r.fn(body, +(url.pathname.match(r.re)[1] || 0), url.searchParams);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(out));
    } catch (e) {
      console.error(req.method, url.pathname, e.message);
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
    return;
  }

  const file = path.join(PUB, path.normalize(url.pathname === '/' ? '/index.html' : url.pathname));
  if (!file.startsWith(PUB) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(200, { 'Content-Type': MIME['.html'] });
    return fs.createReadStream(path.join(PUB, 'index.html')).pipe(res);
  }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-cache' });
  fs.createReadStream(file).pipe(res);
}

// Called once by server.js after the port is open.
function start() {
  if (!LOCAL && PASSWORD.length < 8) throw new Error('Set the APP_PASSWORD environment variable (8+ characters) before putting the app online.');
  // Autopilot: every 10 minutes check replies, find leads, send, follow up, report.
  setInterval(() => engine.tick().catch((e) => console.error('tick:', e.message)), 10 * 60 * 1000);
  setTimeout(() => engine.tick().catch(() => {}), 15000);
}

module.exports = { handler, start, routes };
