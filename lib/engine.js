// Sales engine: drafting, sending, inbox handling, and the autopilot loop.
const { all, get, run, getSetting, setSetting, log } = require('./db');
const mail = require('./mail');
const team = require('./agents');
const finder = require('./finder');
const sources = require('./sources');
const { auditSite } = require('./audit');

const signals = require('./signals');
const firstName = () => (getSetting('sender_name') || '').split(' ')[0];
const owner = () => getSetting('report_to') || getSetting('gmail_user');
const today = () => new Date().toLocaleDateString('en-CA');
const sentToday = () => get("SELECT COUNT(*) n FROM messages WHERE direction='out' AND status='sent' AND date(sent_at,'localtime')=date('now','localtime')").n;
const thread = (leadId) => all("SELECT direction,subject,body FROM messages WHERE lead_id=? AND status IN ('sent','received','handled') ORDER BY id", leadId)
  .map((m) => `${m.direction === 'out' ? 'US' : 'THEM'}: ${m.subject ? `[${m.subject}] ` : ''}${m.body}`).join('\n---\n').slice(-3500);
const ready = () => !!(getSetting('openai_key') && getSetting('gmail_user') && getSetting('gmail_pass'));

async function draftFirst(ids) {
  let made = 0;
  for (const id of ids) {
    const l = get('SELECT * FROM leads WHERE id=?', id);
    if (!l || l.status !== 'new' || get("SELECT 1 FROM messages WHERE lead_id=? AND status='draft'", id)) continue;
    if (!l.audit) { l.audit = await auditSite(l.website); run('UPDATE leads SET audit=? WHERE id=?', l.audit, id); }
    const r = await team.firstEmail(l, firstName());
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
  const m = get("SELECT m.*, l.email, l.name, l.status lstatus FROM messages m JOIN leads l ON l.id=m.lead_id WHERE m.id=? AND m.status='draft'", id);
  if (!m) throw new Error('Draft not found.');
  if (['unsubscribed', 'bounced'].includes(m.lstatus) || (m.lstatus === 'lost' && m.kind !== 'reply')) throw new Error(`${m.email} is ${m.lstatus} — not sent.`);
  if (m.kind !== 'reply' && sentToday() >= +getSetting('daily_cap')) throw new Error(`Daily limit of ${getSetting('daily_cap')} emails reached (protects your Gmail).`);
  const footer = getSetting('footer').trim();
  const text = m.body.trim() + (footer && m.kind !== 'reply' ? `\n\n--\n${footer}` : '');
  try {
    const messageId = await mail.send({ to: m.email, subject: m.subject, text, inReplyTo: m.in_reply_to });
    run("UPDATE messages SET status='sent', sent_at=datetime('now'), message_id=?, error=NULL WHERE id=?", messageId, id);
    const lead = { first: "status='contacted'", followup: "status='contacted', followups=followups+1" }[m.kind] || 'status=status';
    run(`UPDATE leads SET ${lead}, last_contacted=datetime('now') WHERE id=?`, m.lead_id);
    log('sent', `${m.kind === 'first' ? 'Emailed' : m.kind === 'followup' ? 'Followed up with' : 'Replied to'} ${m.name || m.email}`);
  } catch (e) {
    run('UPDATE messages SET error=? WHERE id=?', e.message, id);
    throw e;
  }
}

function notifyOwner(subject, text) {
  return mail.send({ to: owner(), subject, text: text + '\n\n— Your AI marketing team' })
    .catch((e) => log('error', 'Could not email you: ' + e.message));
}

const STATUS_BY_INTENT = { interested: 'meeting', question: 'replied', not_interested: 'lost', unsubscribe: 'unsubscribed', not_now: 'replied', out_of_office: 'contacted', other: 'replied' };
const BOUNCE = 'mailer-daemon@googlemail.com';

let checking = false;
async function checkInbox() {
  if (checking) return { found: 0, busy: true };
  checking = true;
  try {
    const auto = getSetting('autopilot') === '1';
    const booking = getSetting('booking_link');
    const leads = all("SELECT * FROM leads WHERE email IS NOT NULL AND status NOT IN ('new','skipped','call')");
    const byEmail = new Map(leads.map((l) => [l.email.toLowerCase(), l]));
    const msgs = await mail.fetchFrom(new Set([...byEmail.keys(), BOUNCE]));
    let found = 0;
    for (const m of msgs) {
      if (m.from === BOUNCE) { // delivery failure: stop emailing that address
        for (const [email, l] of byEmail) if (l.status !== 'bounced' && m.text.toLowerCase().includes(email)) {
          run("UPDATE leads SET status='bounced' WHERE id=?", l.id); l.status = 'bounced';
          log('bounce', `${email} bounced — removed from outreach`);
        }
        continue;
      }
      if (!m.messageId || get('SELECT 1 FROM messages WHERE message_id=?', m.messageId)) continue;
      const l = byEmail.get(m.from);
      const history = thread(l.id);
      const ins = run("INSERT INTO messages(lead_id,direction,kind,subject,body,status,message_id,in_reply_to,created) VALUES(?,'in','inbound',?,?,'received',?,?,COALESCE(?,datetime('now')))",
        l.id, m.subject, m.text, m.messageId, m.inReplyTo || null, m.date ? m.date.replace('T', ' ').slice(0, 19) : null);
      found++;
      run("DELETE FROM messages WHERE lead_id=? AND status='draft' AND kind='followup'", l.id); // they replied: stop follow-ups

      if (['meeting', 'won'].includes(l.status)) { // already handed over: you take it from here
        log('hot', `${l.name || l.email} wrote again — forwarded to you`);
        await notifyOwner(`New message from ${l.name || l.email} (${l.company})`, `They wrote:\n\n${m.text}\n\nReply to them directly: ${l.email}`);
        continue;
      }

      let t = { intent: 'other', summary: '', reply: '', needs_human: true };
      try { t = await team.triage(l, history, m.text, firstName(), booking); } catch (e) { t.summary = 'AI triage failed: ' + e.message; }
      run('UPDATE messages SET intent=?, summary=? WHERE id=?', t.intent, t.summary, ins.lastInsertRowid);
      const status = STATUS_BY_INTENT[t.intent] || 'replied';
      run('UPDATE leads SET status=? WHERE id=?', status, l.id);
      log('reply', `${l.name || l.email}: ${t.intent} — ${t.summary}`);

      let draftId = null;
      if (t.reply) draftId = run("INSERT INTO messages(lead_id,direction,kind,subject,body,status,in_reply_to) VALUES(?,'out','reply',?,?,'draft',?)",
        l.id, /^re:/i.test(m.subject) ? m.subject : 'Re: ' + m.subject, t.reply, m.messageId).lastInsertRowid;

      if (auto && draftId && !t.needs_human) {
        try { await sendOne(draftId); run("UPDATE messages SET status='handled' WHERE id=?", ins.lastInsertRowid); } catch (e) { log('error', e.message); }
      } else if (auto && t.needs_human) {
        log('human', `${l.name || l.email} needs you: ${t.summary}`);
        await notifyOwner(`Needs you: ${l.name || l.email} (${l.company})`,
          `They wrote:\n\n${m.text}\n\nSuggested reply (not sent — approve it in the app's Outreach page, or reply yourself to ${l.email}):\n\n${t.reply || '(none)'}`);
      }
      if (status === 'meeting') {
        log('hot', `Meeting-ready: ${l.name || l.email} (${l.company})`);
        await notifyOwner(`🔥 Meeting-ready lead: ${l.name || l.email} (${l.company})`,
          `${t.summary}\n\nThey wrote:\n${m.text}\n\n${booking ? 'We sent them your booking link.' : 'We asked them for times — please follow up.'}\nEmail: ${l.email}\nWebsite: ${l.website}\n\nFull thread:\n${thread(l.id)}`);
      }
    }
    setSetting('last_inbox_check', new Date().toISOString());
    return { found };
  } finally { checking = false; }
}

// ---------- autopilot ----------
function inWorkHours() {
  const d = new Date(), h = d.getHours() + d.getMinutes() / 60;
  return d.getDay() > 0 && d.getDay() < 6 && h >= +getSetting('work_start') && h < +getSetting('work_end');
}

async function prospect() {
  const want = +getSetting('daily_new_leads');
  let added = await sources.runAll(want);
  if (added < want && getSetting('web_search') !== '0') {
    const web = await finder.findLeads(want - added);
    log('find', `Found ${web} new lead${web === 1 ? '' : 's'} with web search`);
    added += web;
  }
  // Check each new lead's website first: a modern site rarely buys a redesign.
  let modern = 0;
  for (const l of all("SELECT id, website FROM leads WHERE status='new' AND audit IS NULL AND website!=''")) {
    const a = await auditSite(l.website);
    run('UPDATE leads SET audit=? WHERE id=?', a, l.id);
    if (/no obvious issues/i.test(a)) { run("UPDATE leads SET status='skipped', score=0, score_reason='Website already modern' WHERE id=?", l.id); modern++; }
  }
  if (modern) log('find', `Skipped ${modern} lead${modern === 1 ? '' : 's'} whose website already looks modern`);
  const ids = all('SELECT id FROM leads WHERE score IS NULL').map((r) => r.id);
  for (let i = 0; i < ids.length; i += 20) {
    const batch = ids.slice(i, i + 20).map((id) => get('SELECT * FROM leads WHERE id=?', id));
    for (const s of await team.scoreLeads(batch)) run('UPDATE leads SET score=?, score_reason=? WHERE id=?', Math.round(+s.score || 0), s.reason || '', s.id);
  }
  const skipped = run("UPDATE leads SET status='skipped' WHERE status='new' AND score < ?", +getSetting('min_score')).changes;
  if (skipped) log('find', `Skipped ${skipped} weak-fit lead${skipped === 1 ? '' : 's'}`);
  return added;
}

async function sendBatch(max = 2) {
  let sent = 0;
  const cap = +getSetting('daily_cap');
  while (sent < max && sentToday() < cap) {
    let d = get("SELECT m.id FROM messages m JOIN leads l ON l.id=m.lead_id WHERE m.status='draft' AND m.kind='followup' AND l.status='contacted' ORDER BY m.id LIMIT 1");
    if (!d) {
      const l = get("SELECT id FROM leads WHERE status='new' AND COALESCE(score,100) >= ? AND id NOT IN (SELECT lead_id FROM messages WHERE status='draft') ORDER BY COALESCE(score,0) DESC, id LIMIT 1", +getSetting('min_score'));
      d = get("SELECT m.id FROM messages m JOIN leads l ON l.id=m.lead_id WHERE m.status='draft' AND m.kind='first' AND l.status='new' ORDER BY m.id LIMIT 1");
      if (!d && l) { await draftFirst([l.id]); d = get("SELECT id FROM messages WHERE lead_id=? AND status='draft'", l.id); }
    }
    if (!d) break;
    try { await sendOne(d.id); sent++; } catch (e) { log('error', e.message); break; }
  }
  return sent;
}

function report() {
  const c = (sql, ...p) => get(sql, ...p).n;
  const t = "date(created,'localtime')=date('now','localtime')";
  const hot = all(`SELECT text FROM activity WHERE kind IN ('hot','human') AND ${t}`).map((r) => '• ' + r.text);
  const s = {
    found: c(`SELECT COUNT(*) n FROM leads WHERE source='ai' AND ${t}`),
    first: c("SELECT COUNT(*) n FROM messages WHERE kind='first' AND status='sent' AND date(sent_at,'localtime')=date('now','localtime')"),
    follow: c("SELECT COUNT(*) n FROM messages WHERE kind='followup' AND status='sent' AND date(sent_at,'localtime')=date('now','localtime')"),
    replies: c(`SELECT COUNT(*) n FROM messages WHERE direction='in' AND ${t}`),
    meetings: c("SELECT COUNT(*) n FROM leads WHERE status='meeting'"),
    pipeline: c("SELECT COUNT(*) n FROM leads WHERE status IN ('new','contacted','replied')"),
    spend: get(`SELECT COALESCE(SUM(cost),0) n FROM usage WHERE ${t}`).n,
  };
  return {
    subject: `Daily report: ${s.first + s.follow} emails sent, ${s.replies} replies, ${hot.filter((h) => h.includes('Meeting')).length} meeting-ready`,
    text: `Today your AI marketing team:
• Found ${s.found} new leads
• Sent ${s.first} first emails and ${s.follow} follow-ups
• Received ${s.replies} replies

Needs your attention:
${hot.length ? hot.join('\n') : '• Nothing — all handled.'}

Pipeline: ${s.pipeline} leads in progress, ${s.meetings} waiting for a meeting with you.
AI cost today: $${s.spend.toFixed(3)}`,
  };
}

let ticking = false;
async function tick() {
  if (ticking || !ready()) return;
  ticking = true;
  try {
    const auto = getSetting('autopilot') === '1';
    if (auto || getSetting('auto_inbox') === '1') await checkInbox().catch((e) => log('error', 'Inbox: ' + e.message));
    if (!auto) return;
    if (inWorkHours()) {
      if (getSetting('last_find') !== today()) {
        setSetting('last_find', today());
        await prospect().catch((e) => log('error', 'Lead search: ' + e.message));
      }
      if (getSetting('signals') !== '0' && getSetting('last_signals') !== today()) {
        setSetting('last_signals', today());
        const found = await signals.findSignals().catch((e) => { log('error', 'Website requests: ' + e.message); return []; });
        if (found.length) await notifyOwner(`${found.length} people asked for a website today`, found.map((s) =>
          `${s.need === 'new' ? 'NEW WEBSITE' : 'REDESIGN'} · ${s.platform} · ${s.location || ''}\n${s.title || s.summary}\n${s.url}\n\nSuggested reply:\n${s.reply || ''}`).join('\n\n———\n\n') + '\n\nOpen each link, paste the reply and post it yourself.');
      }
      await draftFollowups().catch((e) => log('error', 'Follow-ups: ' + e.message));
      await sendBatch(2);
    }
    const h = new Date().getHours();
    if (h >= +getSetting('work_end') && getSetting('last_report') !== today()) {
      setSetting('last_report', today());
      const r = report();
      await notifyOwner(r.subject, r.text);
      log('report', 'Sent you the daily report');
    }
  } finally { ticking = false; }
}

module.exports = { sentToday, thread, draftFirst, draftFollowups, sendOne, checkInbox, prospect, sendBatch, report, tick, inWorkHours };
