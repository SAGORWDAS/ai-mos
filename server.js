// AI Marketing Team — local server. Run: node server.js  →  http://localhost:3000
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { all, get, run, getSetting, setSetting, allSettings, getJSON, setJSON } = require('./lib/db');
const ai = require('./lib/ai');
const mail = require('./lib/mail');
const team = require('./lib/agents');

const PORT = +process.env.PORT || 3000;
const HOST = process.env.HOST || '127.0.0.1';
const PUB = path.join(__dirname, 'public');
const SECRETS = ['openai_key', 'gmail_pass'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const firstName = () => (getSetting('sender_name') || '').split(' ')[0];

// ---------- helpers ----------
const mask = (v) => (v ? '•'.repeat(8) + v.slice(-4) : '');
const sentToday = () => get("SELECT COUNT(*) n FROM messages WHERE direction='out' AND status='sent' AND date(sent_at,'localtime')=date('now','localtime')").n;
const thread = (leadId) => all('SELECT direction,subject,body FROM messages WHERE lead_id=? AND status IN (\'sent\',\'received\',\'handled\') ORDER BY id', leadId)
  .map((m) => `${m.direction === 'out' ? 'US' : 'THEM'}: ${m.subject ? `[${m.subject}] ` : ''}${m.body}`).join('\n---\n').slice(-3500);

function state() {
  const s = allSettings();
  for (const k of SECRETS) s[k] = mask(s[k]);
  const brand = getJSON('brand', {});
  const c = (sql) => get(sql).n;
  const usage = get("SELECT COALESCE(SUM(cost),0) total, COALESCE(SUM(CASE WHEN created>=datetime('now','-30 days') THEN cost END),0) month, COUNT(*) calls FROM usage");
  return {
    settings: s, brand, channels: team.CHANNELS,
    stats: {
      leads: c('SELECT COUNT(*) n FROM leads'),
      contacted: c("SELECT COUNT(*) n FROM leads WHERE status NOT IN ('new')"),
      replied: c("SELECT COUNT(*) n FROM leads WHERE status IN ('replied','interested','won','lost','unsubscribed')"),
      interested: c("SELECT COUNT(*) n FROM leads WHERE status IN ('interested','won')"),
      won: c("SELECT COUNT(*) n FROM leads WHERE status='won'"),
      drafts: c("SELECT COUNT(*) n FROM messages WHERE status='draft'"),
      unread: c("SELECT COUNT(*) n FROM messages WHERE status='received'"),
      sentToday: sentToday(), cap: +s.daily_cap,
      plans: c('SELECT COUNT(*) n FROM plans'), content: c('SELECT COUNT(*) n FROM content'),
    },
    usage,
    ready: { openai: !!getSetting('openai_key'), gmail: !!(getSetting('gmail_user') && getSetting('gmail_pass')), brand: !!brand.name },
    lastInboxCheck: getSetting('last_inbox_check'),
  };
}

// ---------- outreach ----------
async function draftFirst(ids) {
  const sender = firstName();
  let made = 0;
  for (const id of ids) {
    const l = get('SELECT * FROM leads WHERE id=?', id);
    if (!l || l.status !== 'new' || get("SELECT 1 FROM messages WHERE lead_id=? AND status='draft'", id)) continue;
    const r = await team.firstEmail(l, sender);
    run("INSERT INTO messages(lead_id,direction,kind,subject,body,status) VALUES(?,'out','first',?,?,'draft')", id, r.subject, r.body);
    made++;
  }
  return made;
}

async function draftFollowups() {
  const days = +getSetting('followup_days'), max = +getSetting('max_followups');
  const due = all(`SELECT * FROM leads WHERE status='contacted' AND followups < ? AND last_contacted <= datetime('now', ?)
    AND id NOT IN (SELECT lead_id FROM messages WHERE status='draft')`, max, `-${days} days`);
  for (const l of due) {
    const r = await team.followUp(l, thread(l.id), l.followups + 1, firstName());
    const first = get("SELECT subject FROM messages WHERE lead_id=? AND kind='first' ORDER BY id LIMIT 1", l.id);
    const last = get("SELECT message_id FROM messages WHERE lead_id=? AND direction='out' AND status='sent' ORDER BY id DESC LIMIT 1", l.id);
    run("INSERT INTO messages(lead_id,direction,kind,subject,body,status,in_reply_to) VALUES(?,'out','followup',?,?,'draft',?)",
      l.id, 'Re: ' + (first?.subject || '').replace(/^re:\s*/i, ''), r.body, last?.message_id || null);
  }
  return due.length;
}

async function sendOne(id) {
  const m = get("SELECT m.*, l.email, l.status lstatus FROM messages m JOIN leads l ON l.id=m.lead_id WHERE m.id=? AND m.status='draft'", id);
  if (!m) throw new Error('Draft not found.');
  if (m.lstatus === 'unsubscribed') throw new Error(`${m.email} unsubscribed — not sent.`);
  if (sentToday() >= +getSetting('daily_cap')) throw new Error(`Daily limit of ${getSetting('daily_cap')} emails reached (protects your Gmail). Change it in Settings.`);
  const footer = getSetting('footer').trim();
  const text = m.body.trim() + (footer && m.kind !== 'reply' ? `\n\n--\n${footer}` : '');
  try {
    const messageId = await mail.send({ to: m.email, subject: m.subject, text, inReplyTo: m.in_reply_to });
    run("UPDATE messages SET status='sent', sent_at=datetime('now'), message_id=?, error=NULL WHERE id=?", messageId, id);
    const lead = { first: "status='contacted'", followup: "status='contacted', followups=followups+1", reply: 'status=status' }[m.kind] || 'status=status';
    run(`UPDATE leads SET ${lead}, last_contacted=datetime('now') WHERE id=?`, m.lead_id);
  } catch (e) {
    run("UPDATE messages SET error=? WHERE id=?", e.message, id);
    throw e;
  }
}

const STATUS_BY_INTENT = { interested: 'interested', question: 'interested', not_interested: 'lost', unsubscribe: 'unsubscribed', not_now: 'replied', out_of_office: 'contacted', other: 'replied' };

let checking = false;
async function checkInbox() {
  if (checking) return { found: 0, busy: true };
  checking = true;
  try {
    const leads = all("SELECT * FROM leads WHERE status NOT IN ('new')");
    const byEmail = new Map(leads.map((l) => [l.email.toLowerCase(), l]));
    const msgs = await mail.fetchFrom(new Set(byEmail.keys()));
    let found = 0;
    for (const m of msgs) {
      if (!m.messageId || get('SELECT 1 FROM messages WHERE message_id=?', m.messageId)) continue;
      const l = byEmail.get(m.from);
      const history = thread(l.id);
      const ins = run("INSERT INTO messages(lead_id,direction,kind,subject,body,status,message_id,in_reply_to,created) VALUES(?,'in','inbound',?,?,'received',?,?,COALESCE(?,datetime('now')))",
        l.id, m.subject, m.text, m.messageId, m.inReplyTo || null, m.date ? m.date.replace('T', ' ').slice(0, 19) : null);
      found++;
      run("DELETE FROM messages WHERE lead_id=? AND status='draft' AND kind='followup'", l.id); // they replied: stop follow-ups
      let t = { intent: 'other', summary: '', reply: '' };
      try { t = await team.triage(l, history, m.text, firstName()); } catch (e) { t.summary = 'AI triage failed: ' + e.message; }
      run('UPDATE messages SET intent=?, summary=? WHERE id=?', t.intent, t.summary, ins.lastInsertRowid);
      if (l.status !== 'won') run('UPDATE leads SET status=? WHERE id=?', STATUS_BY_INTENT[t.intent] || 'replied', l.id);
      if (t.reply) run("INSERT INTO messages(lead_id,direction,kind,subject,body,status,in_reply_to) VALUES(?,'out','reply',?,?,'draft',?)",
        l.id, /^re:/i.test(m.subject) ? m.subject : 'Re: ' + m.subject, t.reply, m.messageId);
    }
    setSetting('last_inbox_check', new Date().toISOString());
    return { found };
  } finally { checking = false; }
}

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
    for (const k of ['name', 'company', 'role', 'website', 'notes', 'status']) if (k in b) run(`UPDATE leads SET ${k}=? WHERE id=?`, b[k], id);
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

const server = http.createServer(async (req, res) => {
  const host = (req.headers.host || '').split(':')[0];
  if (HOST === '127.0.0.1' && !['localhost', '127.0.0.1'].includes(host)) { res.writeHead(403); return res.end(); }
  const url = new URL(req.url, 'http://x');

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
});

if (require.main === module) {
  server.listen(PORT, HOST, () => console.log(`\n  AI Marketing Team is running → http://localhost:${PORT}\n  (keep this window open; press Ctrl+C to stop)\n`));
  // Check Gmail for replies every 10 minutes while the app is open.
  setInterval(() => {
    if (getSetting('auto_inbox') === '1' && getSetting('gmail_pass')) checkInbox().catch((e) => console.error('inbox:', e.message));
  }, 10 * 60 * 1000);
}

module.exports = { server, routes };
