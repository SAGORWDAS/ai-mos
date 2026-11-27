// AI Marketing Team — single-file UI, no framework, no build step.
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let S = null; // app state from /api/state

async function api(path, body, method) {
  const res = await fetch('/api' + path, {
    method: method || (body ? 'POST' : 'GET'),
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Something went wrong');
  return data;
}
function toast(msg, err) {
  const d = document.createElement('div');
  d.textContent = msg; if (err) d.className = 'err';
  $('#toast').append(d); setTimeout(() => d.remove(), err ? 7000 : 3500);
}
// Wrap a button click: spinner + error toast.
async function act(btn, fn) {
  btn.classList.add('busy'); btn.disabled = true;
  try { return await fn(); } catch (e) { toast(e.message, true); } finally { btn.classList.remove('busy'); btn.disabled = false; }
}
function md(src) {
  const lines = esc(src).split('\n'); let html = '', list = false;
  for (let l of lines) {
    l = l.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|\s)\*(.+?)\*/g, '$1<i>$2</i>');
    const li = l.match(/^\s*(?:[-*]|\d+\.)\s+(.*)/);
    if (li) { if (!list) { html += '<ul>'; list = true; } html += `<li>${li[1]}</li>`; continue; }
    if (list) { html += '</ul>'; list = false; }
    const hd = l.match(/^(#{1,3})\s+(.*)/);
    html += hd ? `<h${hd[1].length + 1}>${hd[2]}</h${hd[1].length + 1}>` : l.trim() ? `<p>${l}</p>` : '';
  }
  return html + (list ? '</ul>' : '');
}
const ago = (t) => { if (!t) return ''; const d = new Date(t.includes('T') ? t : t.replace(' ', 'T') + 'Z'); return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); };
const copy = (text) => navigator.clipboard.writeText(text).then(() => toast('Copied'));
const STATUS_PILL = { new: '', contacted: 'acc', replied: 'warn', interested: 'ok', won: 'ok', lost: 'bad', unsubscribed: 'bad' };
const INTENT_PILL = { interested: 'ok', question: 'ok', not_now: 'warn', not_interested: 'bad', unsubscribe: 'bad', out_of_office: '', other: '' };

async function refresh() {
  S = await api('/state');
  $('#b-drafts').textContent = S.stats.drafts || '';
  $('#b-unread').textContent = S.stats.unread || '';
  $('#spend').innerHTML = `AI spend (30 days)<br><b style="color:var(--ink);font-size:15px">$${S.usage.month.toFixed(3)}</b> · ${S.usage.calls} calls`;
}

// ---------------- pages ----------------
const pages = {};

pages.home = () => {
  const r = S.ready, st = S.stats;
  const steps = [
    [r.openai && r.gmail, 'Connect OpenAI and Gmail', '#/settings', 'Settings'],
    [r.brand, 'Tell the team about your business', '#/brand', 'Brand'],
    [st.plans > 0, 'Get a 30-day marketing plan', '#/strategy', 'Strategy'],
    [st.leads > 0, 'Add people you want to reach', '#/leads', 'Leads'],
    [st.contacted > 0, 'Review and send your first emails', '#/outreach', 'Outreach'],
  ];
  const done = steps.filter((s) => s[0]).length;
  return `
  <h1>Good to see you${S.settings.sender_name ? ', ' + esc(S.settings.sender_name.split(' ')[0]) : ''}</h1>
  <p class="sub">Your AI marketing team writes, sends and follows up. You approve every email before it goes out.</p>
  <div class="grid g4">
    ${[['Leads', st.leads], ['Contacted', st.contacted], ['Replied', st.replied], ['Interested', st.interested]].map(([k, v]) => `<div class="card stat"><b>${v}</b><span>${k}</span></div>`).join('')}
  </div>
  <div class="grid g2">
    <div class="card">
      <div class="row"><h2 class="sp">Getting started</h2><span class="pill ${done === 5 ? 'ok' : 'acc'}">${done}/5</span></div>
      <ol class="steps">${steps.map(([ok, t, href, b]) => `<li class="${ok ? 'done' : ''}"><span class="sp">${t}</span><a class="btn s" href="${href}">${b}</a></li>`).join('')}</ol>
    </div>
    <div class="card">
      <h2>Today</h2>
      <ol class="steps">
        <li class="${st.drafts ? '' : 'done'}"><span class="sp">${st.drafts} email draft${st.drafts === 1 ? '' : 's'} waiting for approval</span><a class="btn s" href="#/outreach">Review</a></li>
        <li class="${st.unread ? '' : 'done'}"><span class="sp">${st.unread} new repl${st.unread === 1 ? 'y' : 'ies'}</span><a class="btn s" href="#/inbox">Open</a></li>
        <li class="done"><span class="sp">${st.sentToday}/${st.cap} emails sent today</span></li>
      </ol>
      <div class="row" style="margin-top:12px">
        <button class="btn" id="fu">Draft due follow-ups</button>
        <button class="btn" id="ck">Check Gmail for replies</button>
      </div>
      <p class="mute">${S.lastInboxCheck ? 'Last checked ' + ago(S.lastInboxCheck) : 'Replies are checked every 10 minutes while the app is open.'}</p>
    </div>
  </div>`;
};
pages.home.on = () => {
  $('#fu').onclick = (e) => act(e.target, async () => { const r = await api('/outreach/followups', {}); toast(`${r.drafted} follow-up${r.drafted === 1 ? '' : 's'} drafted`); go(); });
  $('#ck').onclick = (e) => act(e.target, async () => { const r = await api('/inbox/check', {}); toast(r.busy ? 'Already checking…' : `${r.found} new repl${r.found === 1 ? 'y' : 'ies'}`); go(); });
};

const BRAND_FIELDS = [
  ['name', 'Business name', 'Acme Bakery'],
  ['website', 'Website', 'https://…'],
  ['offer', 'What do you sell?', 'Custom cakes delivered same day in Dhaka'],
  ['audience', 'Who is your ideal customer?', 'Office managers planning team celebrations; parents planning birthdays'],
  ['usp', 'Why should they pick you?', 'Same-day delivery, 4.9★ on Google, free tasting box'],
  ['pricing', 'Pricing (optional)', 'From $25; corporate plans from $200/month'],
  ['proof', 'Proof: clients, results, reviews (only real ones)', '300+ office orders in 2025'],
  ['tone', 'Voice / tone', 'Warm, friendly, simple English'],
  ['avoid', 'Words or claims to never use', 'cheapest, guaranteed'],
  ['cta', 'Main call to action', 'Reply to book a free tasting / 15-min call'],
];
pages.brand = () => `
  <h1>Brand</h1><p class="sub">Everything the team writes comes from this. Be specific and honest — the AI never invents claims beyond it.</p>
  <div class="card"><label>Fast start: fill from your website</label>
    <div class="row"><input id="url" placeholder="yourbusiness.com" value="${esc(S.brand.website || '')}" style="flex:1"><button class="btn" id="auto">Auto-fill</button></div>
    <div class="hint">Reads your homepage and drafts the fields below. Check them before saving.</div></div>
  <div class="card"><form id="bf" class="grid g2">
    ${BRAND_FIELDS.map(([k, l, ph]) => `<div class="f" ${['offer', 'audience', 'usp', 'proof'].includes(k) ? 'style="grid-column:1/-1"' : ''}><label>${l}</label>
      ${['offer', 'audience', 'usp', 'proof'].includes(k) ? `<textarea name="${k}" placeholder="${ph}" style="min-height:64px">${esc(S.brand[k] || '')}</textarea>` : `<input name="${k}" placeholder="${ph}" value="${esc(S.brand[k] || '')}">`}</div>`).join('')}
    <div><button class="btn p">Save brand</button></div></form></div>`;
pages.brand.on = () => {
  $('#auto').onclick = (e) => act(e.target, async () => {
    const r = await api('/brand/autofill', { url: $('#url').value });
    for (const [k, v] of Object.entries(r)) { const el = $(`[name=${k}]`); if (el && v) el.value = v; }
    toast('Filled from website — review and save');
  });
  $('#bf').onsubmit = (e) => { e.preventDefault(); act(e.submitter, async () => { await api('/brand', Object.fromEntries(new FormData(e.target))); await refresh(); toast('Brand saved'); }); };
};

pages.strategy = async () => {
  const plans = await api('/plans');
  return `<h1>Strategy</h1><p class="sub">Your AI CMO writes a practical 30-day plan for your goal and budget.</p>
  <div class="card"><label>What do you want in the next 30 days?</label>
    <div class="row"><input id="goal" placeholder="e.g. 10 new corporate clients with $0 ad budget" style="flex:1"><button class="btn p" id="gen">Create plan</button></div></div>
  ${plans.length ? plans.map((p) => `<div class="card"><div class="row"><div class="sp"><b>${esc(p.goal || 'Plan')}</b><div class="mute">${ago(p.created)}</div></div>
    <button class="btn s" data-copy="${p.id}">Copy</button><button class="btn s ghost danger" data-del="${p.id}">Delete</button></div><div class="md">${md(p.body)}</div></div>`).join('')
    : '<div class="card empty">No plan yet. Describe a goal above.</div>'}`;
};
pages.strategy.on = (plans) => {
  $('#gen').onclick = (e) => act(e.target, async () => { await api('/plans', { goal: $('#goal').value }); toast('Plan ready'); go(); });
  bindRows('/plans', async (id) => (await api('/plans')).find((p) => p.id == id).body);
};

pages.content = async () => {
  const items = await api('/content');
  return `<h1>Content</h1><p class="sub">Posts, blogs, newsletters and ad copy in your brand voice. Copy and publish where you like.</p>
  <div class="card"><div class="grid" style="grid-template-columns:200px 1fr 90px auto;align-items:end">
    <div><label>Channel</label><select id="ch">${S.channels.map((c) => `<option>${c}</option>`).join('')}</select></div>
    <div><label>Topic or angle</label><input id="topic" placeholder="e.g. Behind the scenes of our busiest week"></div>
    <div><label>Variants</label><select id="n"><option>1</option><option>2</option><option selected>3</option></select></div>
    <button class="btn p" id="gen">Write</button></div></div>
  ${items.length ? `<div class="grid g2">${items.map((c) => `<div class="card"><div class="row" style="margin-bottom:8px"><span class="pill acc">${esc(c.channel)}</span><span class="mute sp">${esc(c.topic)}</span>
    <button class="btn s" data-copy="${c.id}">Copy</button><button class="btn s ghost danger" data-del="${c.id}">✕</button></div><div class="pre">${esc(c.body)}</div></div>`).join('')}</div>`
    : '<div class="card empty">Nothing yet. Pick a channel and press Write.</div>'}`;
};
pages.content.on = () => {
  $('#gen').onclick = (e) => act(e.target, async () => { await api('/content', { channel: $('#ch').value, topic: $('#topic').value, count: $('#n').value }); go(); });
  bindRows('/content', async (id) => (await api('/content')).find((c) => c.id == id).body);
};

function bindRows(base, getText) {
  document.querySelectorAll('[data-copy]').forEach((b) => (b.onclick = async () => copy(await getText(b.dataset.copy))));
  document.querySelectorAll('[data-del]').forEach((b) => (b.onclick = () => act(b, async () => { await api(`${base}/${b.dataset.del}`, null, 'DELETE'); go(); })));
}

// ---- leads ----
function parseCSV(text) {
  const rows = []; let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (c === '"') q = false; else cell += c; }
    else if (c === '"') q = true;
    else if (c === ',' || c === ';' || c === '\t') { row.push(cell); cell = ''; }
    else if (c === '\n' || c === '\r') { if (c === '\r' && text[i + 1] === '\n') i++; row.push(cell); rows.push(row); row = []; cell = ''; }
    else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const head = rows.shift()?.map((h) => h.trim().toLowerCase()) || [];
  const find = (...keys) => head.findIndex((h) => keys.some((k) => h.includes(k)));
  const ix = { email: find('email', 'e-mail'), first: find('first'), last: find('last'), name: find('name'), company: find('company', 'organi', 'business'), role: find('title', 'role', 'position', 'job'), website: find('website', 'url', 'domain', 'site'), notes: find('note', 'about', 'description') };
  if (ix.email < 0) throw new Error('CSV needs an "email" column.');
  return rows.filter((r) => r[ix.email]).map((r) => ({
    email: r[ix.email], company: r[ix.company] || '', role: r[ix.role] || '', website: r[ix.website] || '', notes: r[ix.notes] || '',
    name: ix.first >= 0 ? `${r[ix.first] || ''} ${ix.last >= 0 ? r[ix.last] || '' : ''}`.trim() : r[ix.name] || '',
  }));
}

let leadFilter = 'all';
pages.leads = async () => {
  const leads = await api('/leads');
  const shown = leads.filter((l) => leadFilter === 'all' || l.status === leadFilter);
  const counts = leads.reduce((a, l) => ((a[l.status] = (a[l.status] || 0) + 1), a), {});
  return `<div class="row"><div class="sp"><h1>Leads</h1><p class="sub">People you want to reach. Import a CSV or add them one by one.</p></div>
    <button class="btn" id="add">+ Add lead</button><label class="btn" style="margin:0;color:var(--ink)">Import CSV<input type="file" id="csv" accept=".csv,.txt" hidden></label></div>
  <div class="tabs">${['all', 'new', 'contacted', 'replied', 'interested', 'won', 'lost', 'unsubscribed'].map((s) => `<button class="btn s ${leadFilter === s ? 'on' : ''}" data-f="${s}">${s} ${s === 'all' ? leads.length : counts[s] || 0}</button>`).join('')}</div>
  <div class="card">
    <div class="row" style="margin-bottom:10px"><span class="mute sp"><span id="selc">0</span> selected</span>
      <button class="btn s" id="score">AI score fit</button><button class="btn s p" id="draft">Write emails for selected</button></div>
    ${shown.length ? `<table><thead><tr><th><input type="checkbox" id="all"></th><th>Person</th><th>Company</th><th>Fit</th><th>Status</th><th></th></tr></thead><tbody>
    ${shown.map((l) => `<tr><td><input type="checkbox" class="sel" value="${l.id}" ${l.status !== 'new' ? 'data-c="1"' : ''}></td>
      <td><b>${esc(l.name || '—')}</b><div class="mute">${esc(l.email)}</div></td>
      <td>${esc(l.company)}<div class="mute">${esc(l.role)}</div></td>
      <td>${l.score == null ? '<span class="mute">—</span>' : `<span class="pill ${l.score >= 70 ? 'ok' : l.score >= 40 ? 'warn' : 'bad'}" title="${esc(l.score_reason)}">${l.score}</span>`}</td>
      <td><select class="st" data-id="${l.id}" style="padding:4px 8px;width:auto">${Object.keys(STATUS_PILL).map((s) => `<option ${s === l.status ? 'selected' : ''}>${s}</option>`).join('')}</select></td>
      <td style="white-space:nowrap"><button class="btn s ghost" data-th="${l.id}">Thread</button><button class="btn s ghost danger" data-del="${l.id}">✕</button></td></tr>`).join('')}
    </tbody></table>` : `<div class="empty">No leads here.<br><span class="mute">Tip: export contacts from LinkedIn Sales Navigator, Apollo, Google Sheets or your CRM as CSV with columns like name, email, company, title, website.</span></div>`}
  </div>`;
};
pages.leads.on = () => {
  const sel = () => [...document.querySelectorAll('.sel:checked')].map((c) => +c.value);
  const upd = () => ($('#selc').textContent = sel().length);
  document.querySelectorAll('.sel').forEach((c) => (c.onchange = upd));
  $('#all') && ($('#all').onchange = (e) => { document.querySelectorAll('.sel').forEach((c) => (c.checked = e.target.checked)); upd(); });
  document.querySelectorAll('[data-f]').forEach((b) => (b.onclick = () => { leadFilter = b.dataset.f; go(); }));
  document.querySelectorAll('.st').forEach((s) => (s.onchange = async () => { await api('/leads/' + s.dataset.id, { status: s.value }, 'PATCH'); toast('Status updated'); refresh(); }));
  document.querySelectorAll('[data-th]').forEach((b) => (b.onclick = () => showThread(b.dataset.th)));
  bindRows('/leads', () => '');
  $('#csv').onchange = async (e) => {
    try {
      const leads = parseCSV(await e.target.files[0].text());
      const r = await api('/leads', { leads }); toast(`${r.added} added, ${r.skipped} skipped (duplicates or invalid)`); go();
    } catch (err) { toast(err.message, true); }
  };
  $('#add').onclick = () => modal('Add lead', `<form id="lf" class="grid g2">
    ${[['name', 'Name'], ['email', 'Email *'], ['company', 'Company'], ['role', 'Job title'], ['website', 'Website']].map(([k, l]) => `<div><label>${l}</label><input name="${k}" ${k === 'email' ? 'required type="email"' : ''}></div>`).join('')}
    <div style="grid-column:1/-1"><label>Notes (helps personalise: recent news, how you found them)</label><textarea name="notes"></textarea></div>
    <div><button class="btn p">Add</button></div></form>`, (d) => {
    $('#lf', d).onsubmit = async (e) => { e.preventDefault(); const r = await api('/leads', { leads: [Object.fromEntries(new FormData(e.target))] }); toast(r.added ? 'Lead added' : 'Already exists or invalid email', !r.added); d.close(); go(); };
  });
  $('#score').onclick = (e) => act(e.target, async () => { const r = await api('/leads/score', { ids: sel() }); toast(`Scored ${r.scored} leads`); go(); });
  $('#draft').onclick = (e) => act(e.target, async () => {
    const ids = sel(); if (!ids.length) throw new Error('Select at least one new lead.');
    const r = await api('/outreach/draft', { ids }); toast(`${r.drafted} draft${r.drafted === 1 ? '' : 's'} ready for review`); location.hash = '#/outreach';
  });
};

async function showThread(id) {
  const t = await api(`/leads/${id}/thread`);
  modal(esc(t.lead.name || t.lead.email), t.messages.length ? t.messages.map((m) => `<div class="bubble ${m.direction}"><div class="mute">${m.direction === 'in' ? 'Them' : 'You'} · ${m.status} · ${ago(m.sent_at || m.created)}</div><b>${esc(m.subject)}</b><div class="pre">${esc(m.body)}</div></div>`).join('') : '<div class="empty">No emails yet.</div>');
}

// ---- outreach (approval queue) ----
pages.outreach = async () => {
  const drafts = await api('/messages?status=draft');
  const sent = await api('/messages?status=sent');
  return `<div class="row"><div class="sp"><h1>Outreach</h1><p class="sub">Every email waits here for your OK. Edit anything, then send. ${S.stats.sentToday}/${S.stats.cap} sent today.</p></div>
    <button class="btn" id="fu">Draft due follow-ups</button>${drafts.length ? `<button class="btn p" id="sendall">Send all ${drafts.length}</button>` : ''}</div>
  ${drafts.length ? drafts.map((m) => `<div class="mail" data-id="${m.id}"><div class="to row"><span class="sp">To <b>${esc(m.name || '')}</b> &lt;${esc(m.email)}&gt; · ${esc(m.company || '')}</span><span class="pill ${m.kind === 'reply' ? 'ok' : m.kind === 'followup' ? 'warn' : 'acc'}">${m.kind === 'first' ? 'first email' : m.kind}</span></div>
    <input class="subj" value="${esc(m.subject)}" style="margin-bottom:8px;font-weight:600"><textarea class="body">${esc(m.body)}</textarea>
    ${m.error ? `<div class="pill bad" style="margin-top:8px">Last error: ${esc(m.error)}</div>` : ''}
    <div class="row" style="margin-top:10px"><span class="mute sp">${m.kind !== 'reply' ? 'Unsubscribe line is added automatically.' : ''}</span><button class="btn s ghost danger del">Discard</button><button class="btn s p send">Send</button></div></div>`).join('')
    : `<div class="card empty">No drafts waiting. Select leads on the <a href="#/leads">Leads</a> page and press “Write emails”.</div>`}
  <h2 style="margin-top:28px">Recently sent</h2>
  <div class="card">${sent.length ? `<table><tbody>${sent.slice(0, 30).map((m) => `<tr><td><b>${esc(m.name || m.email)}</b><div class="mute">${esc(m.email)}</div></td><td>${esc(m.subject)}<div class="mute">${m.kind}</div></td><td class="mute">${ago(m.sent_at)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">Nothing sent yet.</div>'}</div>`;
};
pages.outreach.on = () => {
  const save = (card) => api('/messages/' + card.dataset.id, { subject: $('.subj', card).value, body: $('.body', card).value }, 'PATCH');
  document.querySelectorAll('.mail').forEach((card) => {
    $('.subj', card).onchange = $('.body', card).onchange = () => save(card);
    $('.del', card).onclick = (e) => act(e.target, async () => { await api('/messages/' + card.dataset.id, null, 'DELETE'); go(); });
    $('.send', card).onclick = (e) => act(e.target, async () => {
      await save(card); const r = await api('/messages/send', { ids: [+card.dataset.id] });
      if (r.errors.length) throw new Error(r.errors[0]); toast('Sent ✓'); go();
    });
  });
  $('#fu').onclick = (e) => act(e.target, async () => { const r = await api('/outreach/followups', {}); toast(`${r.drafted} follow-up${r.drafted === 1 ? '' : 's'} drafted`); go(); });
  $('#sendall') && ($('#sendall').onclick = (e) => act(e.target, async () => {
    const cards = [...document.querySelectorAll('.mail')];
    if (!confirm(`Send ${cards.length} emails now? They go out a few seconds apart.`)) return;
    for (const c of cards) await save(c);
    const r = await api('/messages/send', { ids: cards.map((c) => +c.dataset.id) });
    toast(`Sent ${r.sent}`); if (r.errors.length) toast(r.errors[0], true); go();
  }));
};

// ---- inbox ----
pages.inbox = async () => {
  const msgs = await api('/messages?status=received,handled');
  return `<div class="row"><div class="sp"><h1>Replies</h1><p class="sub">The team reads replies, tags the intent and drafts your answer (in Outreach). Follow-ups stop automatically when someone replies.</p></div>
    <button class="btn p" id="ck">Check Gmail now</button></div>
  ${msgs.length ? msgs.map((m) => `<div class="card" style="${m.status === 'handled' ? 'opacity:.6' : ''}"><div class="row"><b class="sp">${esc(m.name || m.email)} <span class="mute">${esc(m.company || '')}</span></b>
    <span class="pill ${INTENT_PILL[m.intent] || ''}">${esc((m.intent || '').replace('_', ' '))}</span><span class="mute">${ago(m.created)}</span></div>
    <p style="margin:8px 0"><b>${esc(m.summary || '')}</b></p><div class="pre mute" style="max-height:140px;overflow:auto">${esc(m.body)}</div>
    <div class="row" style="margin-top:10px"><button class="btn s ghost" data-th="${m.lead_id}">Full thread</button><span class="sp"></span>
    ${m.status === 'received' ? `<button class="btn s" data-done="${m.id}">Mark done</button>` : ''}<a class="btn s p" href="#/outreach">See drafted reply</a></div></div>`).join('')
    : '<div class="card empty">No replies yet. They show up here automatically.</div>'}`;
};
pages.inbox.on = () => {
  $('#ck').onclick = (e) => act(e.target, async () => { const r = await api('/inbox/check', {}); toast(`${r.found || 0} new repl${r.found === 1 ? 'y' : 'ies'}`); go(); });
  document.querySelectorAll('[data-th]').forEach((b) => (b.onclick = () => showThread(b.dataset.th)));
  document.querySelectorAll('[data-done]').forEach((b) => (b.onclick = async () => { await api('/messages/' + b.dataset.done, { status: 'handled' }, 'PATCH'); go(); }));
};

// ---- settings ----
pages.settings = () => {
  const s = S.settings;
  const f = (k, l, hint = '', type = 'text', ph = '') => `<div class="f"><label>${l}</label><input name="${k}" type="${type}" value="${esc(s[k])}" placeholder="${ph}">${hint ? `<div class="hint">${hint}</div>` : ''}</div>`;
  return `<h1>Settings</h1><p class="sub">Keys stay on this computer (in the <code>data</code> folder). Nothing is sent anywhere except OpenAI and Gmail.</p>
  <form id="sf">
  <div class="grid g2">
    <div class="card"><div class="row"><h2 class="sp">OpenAI</h2><span class="pill ${S.ready.openai ? 'ok' : 'warn'}">${S.ready.openai ? 'saved' : 'needed'}</span></div>
      ${f('openai_key', 'API key', 'Get one at platform.openai.com → API keys. Add $5 credit — that covers thousands of emails.', 'password', 'sk-…')}
      ${f('model', 'Model', 'A small “mini” model keeps costs very low. “Test” lists models your key can use.')}
      <div class="grid g2">${f('price_in', 'Price / 1M input tokens ($)')}${f('price_out', 'Price / 1M output tokens ($)')}</div>
      <button type="button" class="btn s" id="to">Test OpenAI</button></div>
    <div class="card"><div class="row"><h2 class="sp">Gmail</h2><span class="pill ${S.ready.gmail ? 'ok' : 'warn'}">${S.ready.gmail ? 'saved' : 'needed'}</span></div>
      ${f('gmail_user', 'Gmail address', '', 'email', 'you@gmail.com')}
      ${f('gmail_pass', 'App Password (16 letters)', 'Google Account → Security → turn on 2-Step Verification → search “App passwords” → create one named “Marketing”. Not your normal password.', 'password')}
      ${f('sender_name', 'Your name (shown as sender)', '', 'text', 'Jane Doe')}
      <button type="button" class="btn s" id="tg">Test Gmail</button></div>
  </div>
  <div class="card"><h2>Sending rules</h2><div class="grid g3">
    ${f('daily_cap', 'Max emails per day', 'Keep 20–40 for a normal Gmail account to avoid spam flags.', 'number')}
    ${f('followup_days', 'Follow up after (days)', '', 'number')}
    ${f('max_followups', 'Max follow-ups per lead', '', 'number')}</div>
    ${f('footer', 'Footer added to outreach emails', 'Keep an opt-out line — it is required by anti-spam laws in most countries.')}
    <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="ai" ${s.auto_inbox === '1' ? 'checked' : ''}> Check Gmail for replies every 10 minutes while the app is open</label>
  </div>
  <button class="btn p">Save settings</button></form>
  <p class="mute" style="margin-top:20px">Total AI spend so far: $${S.usage.total.toFixed(4)} over ${S.usage.calls} calls.</p>`;
};
pages.settings.on = () => {
  const save = async () => { const d = Object.fromEntries(new FormData($('#sf'))); d.auto_inbox = $('#ai').checked ? '1' : '0'; S = await api('/settings', d); };
  $('#sf').onsubmit = (e) => { e.preventDefault(); act(e.submitter, async () => { await save(); toast('Saved'); go(); }); };
  $('#to').onclick = (e) => act(e.target, async () => { await save(); await api('/test/openai', {}); toast('OpenAI works ✓'); });
  $('#tg').onclick = (e) => act(e.target, async () => { await save(); await api('/test/gmail', {}); toast('Gmail works ✓ (send + read)'); });
};

// ---------------- modal + router ----------------
function modal(title, html, on) {
  const d = document.createElement('dialog');
  d.innerHTML = `<div class="hd"><b class="sp">${title}</b><button class="btn s ghost" value="x">✕</button></div><div class="bd">${html}</div>`;
  document.body.append(d); d.showModal();
  $('.hd button', d).onclick = () => d.close(); d.onclose = () => d.remove();
  on && on(d);
}

async function go() {
  const p = (location.hash.replace(/^#\/?/, '') || 'home').split('?')[0];
  const page = pages[p] || pages.home;
  document.querySelectorAll('#nav a').forEach((a) => a.classList.toggle('on', a.dataset.p === (pages[p] ? p : 'home')));
  try {
    await refresh();
    $('#view').innerHTML = await page();
    page.on && page.on();
  } catch (e) { $('#view').innerHTML = `<div class="card empty">${esc(e.message)}</div>`; }
}
addEventListener('hashchange', go);
go();
