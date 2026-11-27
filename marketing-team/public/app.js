// Marketing Team — single-file UI, no framework, no build step.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const plural = (n, w, p = w + 's') => `${n} ${n === 1 ? w : p}`;
let S = null; // app state

async function api(path, body, method) {
  const res = await fetch('/api' + path, {
    method: method || (body ? 'POST' : 'GET'),
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && data.error === 'login') { showLogin(); throw new Error('Please log in'); }
  if (!res.ok) throw new Error(data.error || 'Something went wrong');
  return data;
}
function showLogin() {
  if ($('#login')) return;
  $('#view').innerHTML = `<form id="login" class="card" style="max-width:380px;margin:12vh auto"><h1 style="font-size:28px">Welcome back</h1><p class="sub" style="margin-bottom:18px">Enter your app password.</p>
    <input type="password" name="password" autofocus required style="margin-bottom:14px"><button class="btn p">Log in</button></form>`;
  $('#login').onsubmit = async (e) => {
    e.preventDefault();
    const r = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.fromEntries(new FormData(e.target))) });
    r.ok ? go() : toast('Wrong password', true);
  };
}
function toast(msg, err) {
  const d = document.createElement('div');
  d.textContent = msg; if (err) d.className = 'err';
  $('#toast').append(d); setTimeout(() => d.remove(), err ? 7000 : 3500);
}
async function act(btn, fn) {
  btn.classList.add('busy'); btn.disabled = true;
  try { return await fn(); } catch (e) { toast(e.message, true); } finally { btn.classList.remove('busy'); btn.disabled = false; }
}
function md(src) {
  let html = '', list = false;
  for (let l of esc(src).split('\n')) {
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
const bgMsg = (r, what) => toast(r.started ? `${what} started. Results show on Home in a few minutes.` : `Busy: ${r.busy}. Try again shortly.`, !r.started);
const copy = (text) => navigator.clipboard.writeText(text).then(() => toast('Copied'));
const host = (u) => { try { return new URL(u).host.replace(/^www\./, ''); } catch { return u; } };
const STATUS = { new: '', call: 'gold', contacted: 'acc', replied: 'warn', interested: 'ok', meeting: 'gold', won: 'ok', lost: 'bad', unsubscribed: 'bad', bounced: 'bad', skipped: '' };
const INTENT = { interested: 'ok', question: 'ok', not_now: 'warn', not_interested: 'bad', unsubscribe: 'bad', out_of_office: '', other: '' };

async function refresh() {
  S = await api('/state');
  $('#b-drafts').textContent = S.stats.drafts || '';
  $('#b-unread').textContent = S.stats.unread || '';
  $('#b-signals').textContent = S.stats.signals || '';
  $('#spend').innerHTML = `AI spend, last 30 days<b>$${S.usage.month.toFixed(2)}</b>${plural(S.usage.calls, 'AI task')}`;
}
const pages = {};
const head = (title, sub, right = '') => `<div class="head"><div><h1>${title}</h1><p class="sub">${sub}</p></div>${right}</div>`;

// ---------------- overview ----------------
pages.home = async () => {
  const r = S.ready, st = S.stats, s = S.settings, on = s.autopilot === '1', keys = r.openai && r.gmail;
  if (!keys || !r.brand) return `
  ${head('Let’s set up your sales team', 'Two quick steps. Then it finds customers, emails them, follows up and replies on its own, and hands you the people who are ready for a meeting.')}
  <div class="card" style="max-width:760px"><ol class="steps">
    <li class="${keys ? 'done' : ''}"><div class="sp"><b>Connect OpenAI and Gmail</b><div class="mute">Your OpenAI key and a Gmail App Password. About two minutes.</div></div><a class="btn ${keys ? 's' : 'p'}" href="#/settings">${keys ? 'Edit' : 'Open settings'}</a></li>
    <li class="${r.brand ? 'done' : ''}"><div class="sp"><b>Paste your website or SaaS link</b><div class="mute">The team reads it to learn what you sell, who buys it, and what free offer gets a first yes.</div>
      <div class="row" style="margin-top:14px"><input id="url" placeholder="https://yourproduct.com" style="flex:1" ${keys ? '' : 'disabled'}><button class="btn p" id="ob" ${keys ? '' : 'disabled'}>Learn my product</button></div></div></li>
  </ol></div>`;

  const hot = (await api('/leads')).filter((l) => l.status === 'meeting');
  return `
  ${head(on ? 'Your team is working' : 'Your team is paused',
    on ? `Finds ${s.daily_new_leads} leads a day, emails Mon–Fri ${s.work_start}:00–${s.work_end}:00 (up to ${s.daily_cap} a day), replies any time, and sends you a report at ${s.work_end}:00.` : 'Switch Autopilot on and it will find leads, send emails, follow up and reply on its own.',
    `<label class="switch"><input type="checkbox" id="ap" ${on ? 'checked' : ''}><span></span>Autopilot</label>`)}
  ${!s.booking_link ? `<div class="banner"><span class="sp"><b>Add your booking link.</b> Interested leads get it automatically, so meetings land in your calendar.</span><a class="btn s" href="#/settings">Add link</a></div>` : ''}
  ${!S.sources ? `<div class="banner"><span class="sp"><b>Add a lead source.</b> Paste a business directory and pick categories for more genuine local leads.</span><a class="btn s" href="#/sources">Add source</a></div>` : ''}
  <div class="grid g4">
    <div class="card stat"><b>${st.leads}</b><span>Leads found</span></div>
    <div class="card stat"><b>${st.contacted}</b><span>Emailed</span></div>
    <div class="card stat"><b>${st.replied}</b><span>Replied</span></div>
    <div class="card stat hl"><b>${st.meetings}</b><span>Ready for a meeting</span></div>
  </div>
  <div class="grid g2">
    <div class="card"><h2>Meetings to take over</h2>
      ${hot.length ? `<table><tbody>${hot.map((l) => `<tr><td><b>${esc(l.name || l.company)}</b><div class="mute">${esc(l.company)} · ${esc(l.email)}</div></td>
        <td style="text-align:right;white-space:nowrap"><button class="btn s ghost" data-th="${l.id}">Thread</button><button class="btn s p" data-won="${l.id}">Won</button></td></tr>`).join('')}</tbody></table>`
        : '<div class="empty">No one yet. When a lead wants to talk, you’ll get an email and they’ll appear here.</div>'}
      ${st.calls ? `<p class="mute" style="margin:14px 0 0">Also: <a href="#/leads?call">${plural(st.calls, 'business')} with no website or email</a> to call, which are good prospects for website services.</p>` : ''}
    </div>
    <div class="card"><div class="row" style="margin-bottom:10px"><h2 class="sp" style="margin:0">Activity</h2><button class="btn s ghost" id="rep">Today’s report</button><button class="btn s" id="run">Run now</button></div>
      <div class="feed">${S.activity.length ? S.activity.map((a) => `<div><span class="dot ${a.kind}"></span><span class="sp">${esc(a.text)}</span><span class="mute">${ago(a.created)}</span></div>`).join('') : '<div class="empty">Nothing yet.</div>'}</div>
      <p class="mute" style="margin:12px 0 0">${st.sentToday}/${st.cap} emails today · ${S.lastInboxCheck ? 'inbox checked ' + ago(S.lastInboxCheck) : 'inbox checked every 10 minutes'}</p>
    </div>
  </div>`;
};
pages.home.on = () => {
  $('#ob') && ($('#ob').onclick = (e) => act(e.target, async () => { S = await api('/onboard', { url: $('#url').value }); toast('Got it. Review your Brand page, then add a lead source.'); location.hash = '#/brand'; }));
  if (!$('#ap')) return;
  $('#ap').onchange = async (e) => {
    await api('/settings', { autopilot: e.target.checked ? '1' : '0' });
    toast(e.target.checked ? 'Autopilot is on. The first run starts now.' : 'Autopilot paused');
    if (e.target.checked) api('/autopilot/run', {}).catch((x) => toast(x.message, true));
    go();
  };
  $('#run').onclick = (e) => act(e.target, async () => bgMsg(await api('/autopilot/run', {}), 'Autopilot run'));
  $('#rep').onclick = async () => { const r = await api('/report'); modal(esc(r.subject), `<div class="pre">${esc(r.text)}</div>`); };
  bindThreads();
  $$('[data-won]').forEach((b) => (b.onclick = async () => { await api('/leads/' + b.dataset.won, { status: 'won' }, 'PATCH'); toast('Marked as won 🎉'); go(); }));
};

// ---------------- lead sources ----------------
let catCache = { url: '', list: [] };
pages.sources = async () => {
  const list = await api('/sources'), s = S.settings;
  return `${head('Lead sources', 'Where the team looks for genuine, well-paying buyers. Target markets are the main source; directories are optional extras.')}
  <div class="card"><h2>Target markets</h2>
    <div class="hint" style="margin-top:0">Each search takes the next business type and city, so leads stay fresh and varied. Businesses whose customers are worth a lot (clinics, law, finance, building, real estate) pay most for a better website. Sites that already look modern are skipped.</div>
    <div class="grid g2" style="margin-top:14px"><div><label>Business types (one per line)</label><textarea id="ni" style="min-height:220px">${esc(s.niches || '')}</textarea></div>
    <div><label>Cities or regions (one per line)</label><textarea id="pl" style="min-height:220px">${esc(s.places || '')}</textarea></div></div>
    <div class="row" style="margin-top:12px"><span class="mute sp">Leave business types empty to use “Who should it find?” below.</span><button class="btn p" id="mk">Save markets</button></div></div>
  <div class="card"><h2>Add a business directory <span class="mute" style="font-size:14px;font-weight:400">optional</span></h2>
    <div class="row"><input id="dir" placeholder="https://riverlandlink.com.au/" value="${esc(catCache.url)}" style="flex:1"><button class="btn" id="load">Load categories</button></div>
    <div class="hint">Any site where businesses list themselves, such as a local business directory, chamber of commerce or industry association. The team opens each listing, then the business’s own website, and uses the email they publish. Businesses with no website or email go on your call list.</div>
    <div id="cats"></div></div>
  ${list.map((src) => { const cats = JSON.parse(src.categories || '[]'); return `<div class="card"><div class="row">
      <div class="sp"><b style="font-size:16px">${esc(host(src.url))}</b><div class="mute">${plural(src.found, 'lead')} found · ${src.last_run ? 'last run ' + ago(src.last_run) : 'not run yet'}</div></div>
      <label class="switch" title="Use in autopilot"><input type="checkbox" data-act="${src.id}" ${src.active ? 'checked' : ''}><span></span></label>
      <button class="btn s" data-run="${src.id}">Run now</button><button class="btn s ghost danger" data-del="${src.id}">Remove</button></div>
      <div class="chips" style="margin-top:14px">${cats.slice(0, 14).map((c) => `<span class="pill">${esc(c.name)}</span>`).join('')}${cats.length > 14 ? `<span class="pill">+${cats.length - 14} more</span>` : ''}</div></div>`; }).join('')}
  <div class="card"><div class="row"><div class="sp"><h2 style="margin:0">Web search</h2><div class="mute">When directories run dry, OpenAI web search finds more. Each search costs about $0.03.</div></div>
    <label class="switch"><input type="checkbox" id="ws" ${s.web_search !== '0' ? 'checked' : ''}><span></span></label></div>
    <div class="grid g2" style="margin-top:16px"><div><label>Who should it find?</label><select id="tg">${[['both', 'Both: people and companies'], ['people', 'People: freelancers, consultants, coaches…'], ['companies', 'Companies only']].map(([v, l]) => `<option value="${v}" ${s.target === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
    <div><label>Where should it look?</label><input id="sh" value="${esc(S.brand.search_hint || '')}" placeholder="e.g. trades and cafés in South Australia"></div></div></div>`;
};
function renderCats(filter = '') {
  const f = filter.toLowerCase(), list = catCache.list.filter((c) => c.name.toLowerCase().includes(f));
  $('#cats').innerHTML = `<div class="row" style="margin:18px 0 10px"><input id="cf" placeholder="Filter ${catCache.list.length} categories…" value="${esc(filter)}" style="flex:1"><button class="btn s ghost" id="sugg">Suggest for my product</button></div>
    <div class="catlist">${list.map((c) => `<label><input type="checkbox" value="${esc(c.url)}" data-name="${esc(c.name)}" ${catCache.picked?.has(c.url) ? 'checked' : ''}>${esc(c.name)}</label>`).join('') || '<div class="empty">No match.</div>'}</div>
    <div class="row" style="margin-top:14px"><span class="mute sp"><span id="pc">${catCache.picked.size}</span> selected</span><button class="btn p" id="save">Save source</button></div>`;
  $('#cf').oninput = (e) => { const pos = e.target.selectionStart; renderCats(e.target.value); $('#cf').focus(); $('#cf').setSelectionRange(pos, pos); };
  $$('.catlist input').forEach((c) => (c.onchange = () => { c.checked ? catCache.picked.set(c.value, c.dataset.name) : catCache.picked.delete(c.value); $('#pc').textContent = catCache.picked.size; }));
  $('#sugg').onclick = () => { // simple keyword match against the brand's audience
    const words = `${S.brand.audience || ''} ${S.brand.search_hint || ''}`.toLowerCase().match(/[a-z]{4,}/g) || [];
    const stem = (w) => w.replace(/(ies|es|s|ing|ers|er)$/, '');
    const keys = new Set(words.map(stem));
    let n = 0;
    for (const c of catCache.list) if (c.name.toLowerCase().match(/[a-z]{4,}/g)?.some((w) => keys.has(stem(w)))) { catCache.picked.set(c.url, c.name); n++; }
    toast(n ? `Selected ${plural(n, 'category', 'categories')} that match your audience` : 'No obvious matches. Pick them by hand.', !n);
    renderCats($('#cf').value);
  };
  $('#save').onclick = (e) => act(e.target, async () => {
    if (!catCache.picked.size) throw new Error('Pick at least one category.');
    await api('/sources', { url: catCache.url, categories: [...catCache.picked].map(([url, name]) => ({ url, name })) });
    toast('Source saved. Autopilot will use it daily.'); catCache = { url: '', list: [], picked: new Map() }; go();
  });
}
pages.sources.on = () => {
  catCache.picked ||= new Map();
  if (catCache.list.length) renderCats();
  $('#load').onclick = (e) => act(e.target, async () => {
    const url = $('#dir').value.trim();
    const list = await api('/sources/categories', { url });
    if (!list.length) throw new Error('No category pages found on that site. Try pasting a category page link instead.');
    catCache = { url: /^https?:/.test(url) ? url : 'https://' + url, list, picked: new Map() }; renderCats();
  });
  $$('[data-run]').forEach((b) => (b.onclick = () => act(b, async () => { bgMsg(await api(`/sources/${b.dataset.run}/run`, {}), 'Directory run'); })));
  $$('[data-act]').forEach((c) => (c.onchange = () => api('/sources/' + c.dataset.act, { active: c.checked }, 'PATCH')));
  $$('[data-del]').forEach((b) => (b.onclick = () => act(b, async () => { await api('/sources/' + b.dataset.del, null, 'DELETE'); go(); })));
  $('#mk').onclick = (e) => act(e.target, async () => { await api('/settings', { niches: $('#ni').value.trim(), places: $('#pl').value.trim() }); await refresh(); toast('Target markets saved'); });
  $('#ws').onchange = (e) => api('/settings', { web_search: e.target.checked ? '1' : '0' });
  $('#tg').onchange = (e) => api('/settings', { target: e.target.value });
  $('#sh').onchange = (e) => api('/brand', { ...S.brand, search_hint: e.target.value });
};

// ---------------- leads ----------------
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
  const hd = rows.shift()?.map((h) => h.trim().toLowerCase()) || [];
  const find = (...k) => hd.findIndex((h) => k.some((x) => h.includes(x)));
  const ix = { email: find('email', 'e-mail'), first: find('first'), last: find('last'), name: find('name'), company: find('company', 'organi', 'business'), role: find('title', 'role', 'position', 'job'), website: find('website', 'url', 'domain', 'site'), notes: find('note', 'about', 'description') };
  if (ix.email < 0) throw new Error('The CSV needs an "email" column.');
  return rows.filter((r) => r[ix.email]).map((r) => ({
    email: r[ix.email], company: r[ix.company] || '', role: r[ix.role] || '', website: r[ix.website] || '', notes: r[ix.notes] || '',
    name: ix.first >= 0 ? `${r[ix.first] || ''} ${ix.last >= 0 ? r[ix.last] || '' : ''}`.trim() : r[ix.name] || '',
  }));
}
let leadFilter = 'all';
pages.leads = async () => {
  if (location.hash.includes('?call')) leadFilter = 'call';
  const leads = await api('/leads');
  const shown = leads.filter((l) => leadFilter === 'all' ? l.status !== 'call' : l.status === leadFilter);
  const counts = leads.reduce((a, l) => ((a[l.status] = (a[l.status] || 0) + 1), a), {});
  const callView = leadFilter === 'call';
  return `${head('Leads', 'Everyone the team has found or you have added. Each email is written from what is on their website.',
    `<div class="row"><label class="btn" style="margin:0">Import CSV<input type="file" id="csv" accept=".csv,.txt" hidden></label><button class="btn" id="add">Add lead</button><button class="btn p" id="find">Find leads now</button></div>`)}
  <div class="tabs">${['all', 'new', 'contacted', 'replied', 'meeting', 'won', 'call', 'lost', 'unsubscribed', 'bounced', 'skipped'].filter((t) => t === 'all' || counts[t] || ['new', 'contacted', 'meeting'].includes(t))
    .map((t) => `<button class="btn s ${leadFilter === t ? 'on' : ''}" data-f="${t}">${t === 'call' ? 'to call' : t} ${t === 'all' ? leads.length - (counts.call || 0) : counts[t] || 0}</button>`).join('')}</div>
  <div class="card">
    ${callView ? '<p class="mute" style="margin-top:0">These businesses list a phone number but no website or email. If you sell websites, call them, or add an email you find and the team will take over.</p>'
      : `<div class="row" style="margin-bottom:12px"><span class="mute sp"><span id="selc">0</span> selected</span><button class="btn s" id="score">Score fit</button><button class="btn s p" id="draft">Write emails</button></div>`}
    ${shown.length ? `<table><thead><tr>${callView ? '' : '<th style="width:28px"><input type="checkbox" id="all"></th>'}<th>Who</th><th>${callView ? 'Phone' : 'Fit'}</th><th>Status</th><th></th></tr></thead><tbody>
    ${shown.map((l) => `<tr>${callView ? '' : `<td><input type="checkbox" class="sel" value="${l.id}"></td>`}
      <td><b>${esc(l.name || l.company || '—')}</b>${l.name && l.company ? ` <span class="mute">· ${esc(l.company)}</span>` : ''}
        <div class="mute">${esc(l.email || '')}${l.website ? ` · <a href="${esc(l.website)}" target="_blank" rel="noopener">${esc(host(l.website))}</a>` : ''}</div>
        ${l.notes ? `<div class="mute" style="margin-top:3px">${esc(l.notes)}</div>` : ''}</td>
      <td>${callView ? `<a href="tel:${esc(l.phone)}">${esc(l.phone)}</a>` : l.score == null ? '<span class="mute">—</span>' : `<span class="pill ${l.score >= 70 ? 'ok' : l.score >= 40 ? 'warn' : 'bad'}" title="${esc(l.score_reason)}">${l.score}</span>`}</td>
      <td><select class="st" data-id="${l.id}" style="padding:5px 10px;width:auto;border-radius:99px">${Object.keys(STATUS).map((s) => `<option ${s === l.status ? 'selected' : ''}>${s}</option>`).join('')}</select></td>
      <td style="white-space:nowrap;text-align:right">${callView ? `<button class="btn s" data-em="${l.id}">Add email</button>` : `<button class="btn s ghost" data-th="${l.id}">Thread</button>`}<button class="btn s ghost danger" data-del="${l.id}">✕</button></td></tr>`).join('')}
    </tbody></table>` : `<div class="empty">Nothing here yet.<br>Add a <a href="#/sources">lead source</a>, click “Find leads now”, or import a CSV.</div>`}
  </div>`;
};
pages.leads.on = () => {
  const sel = () => $$('.sel:checked').map((c) => +c.value);
  const upd = () => $('#selc') && ($('#selc').textContent = sel().length);
  $$('.sel').forEach((c) => (c.onchange = upd));
  $('#all') && ($('#all').onchange = (e) => { $$('.sel').forEach((c) => (c.checked = e.target.checked)); upd(); });
  $$('[data-f]').forEach((b) => (b.onclick = () => { leadFilter = b.dataset.f; location.hash = '#/leads'; go(); }));
  $$('.st').forEach((s) => (s.onchange = async () => { await api('/leads/' + s.dataset.id, { status: s.value }, 'PATCH'); toast('Status updated'); refresh(); }));
  $$('[data-del]').forEach((b) => (b.onclick = () => act(b, async () => { await api('/leads/' + b.dataset.del, null, 'DELETE'); go(); })));
  $$('[data-em]').forEach((b) => (b.onclick = async () => {
    const email = prompt('Their email address:'); if (!email) return;
    try { await api('/leads/' + b.dataset.em, { email: email.trim().toLowerCase(), status: 'new' }, 'PATCH'); toast('Added. The team will email them.'); go(); } catch (e) { toast(e.message, true); }
  }));
  bindThreads();
  $('#find').onclick = (e) => act(e.target, async () => { bgMsg(await api('/leads/find', {}), 'Lead search'); });
  $('#csv').onchange = async (e) => {
    try { const r = await api('/leads', { leads: parseCSV(await e.target.files[0].text()) }); toast(`${r.added} added, ${r.skipped} skipped (duplicates or invalid)`); go(); } catch (err) { toast(err.message, true); }
  };
  $('#add').onclick = () => modal('Add a lead', `<form id="lf" class="grid g2">
    ${[['name', 'Name'], ['email', 'Email *'], ['company', 'Business'], ['role', 'Job title'], ['website', 'Website']].map(([k, l]) => `<div><label>${l}</label><input name="${k}" ${k === 'email' ? 'required type="email"' : ''}></div>`).join('')}
    <div style="grid-column:1/-1"><label>Notes</label><textarea name="notes" placeholder="Anything that helps personalise: how you found them, recent news…"></textarea></div>
    <div><button class="btn p">Add lead</button></div></form>`, (d) => {
    $('#lf', d).onsubmit = async (e) => { e.preventDefault(); const r = await api('/leads', { leads: [Object.fromEntries(new FormData(e.target))] }); toast(r.added ? 'Lead added' : 'Already exists or invalid email', !r.added); d.close(); go(); };
  });
  $('#score') && ($('#score').onclick = (e) => act(e.target, async () => { const r = await api('/leads/score', { ids: sel() }); toast(`Scored ${plural(r.scored, 'lead')}`); go(); }));
  $('#draft') && ($('#draft').onclick = (e) => act(e.target, async () => {
    const ids = sel(); if (!ids.length) throw new Error('Select at least one new lead.');
    const r = await api('/outreach/draft', { ids }); toast(`${plural(r.drafted, 'draft')} ready to review`); location.hash = '#/outreach';
  }));
};
function bindThreads() { $$('[data-th]').forEach((b) => (b.onclick = () => showThread(b.dataset.th))); }
async function showThread(id) {
  const t = await api(`/leads/${id}/thread`);
  modal(esc(t.lead.name || t.lead.company || t.lead.email),
    (t.lead.audit ? `<p class="mute" style="margin-top:0"><b>Website check:</b> ${esc(t.lead.audit)}</p>` : '') +
    (t.messages.length ? t.messages.map((m) => `<div class="bubble ${m.direction}"><div class="mute">${m.direction === 'in' ? 'Them' : 'You'} · ${m.status} · ${ago(m.sent_at || m.created)}</div><b>${esc(m.subject)}</b><div class="pre">${esc(m.body)}</div></div>`).join('') : '<div class="empty">No emails yet.</div>'));
}

// ---------------- outreach ----------------
pages.outreach = async () => {
  const [drafts, sent] = await Promise.all([api('/messages?status=draft'), api('/messages?status=sent')]);
  return `${head('Outreach', `With Autopilot on, emails send by themselves. Drafts wait here when the team wants your OK, or when you write them by hand. ${S.stats.sentToday}/${S.stats.cap} sent today.`,
    `<div class="row"><button class="btn" id="fu">Draft due follow-ups</button>${drafts.length ? `<button class="btn p" id="sendall">Send all ${drafts.length}</button>` : ''}</div>`)}
  ${drafts.length ? drafts.map((m) => `<div class="mail" data-id="${m.id}"><div class="to row"><span class="sp">To <b>${esc(m.name || m.company || '')}</b> &lt;${esc(m.email)}&gt;</span><span class="pill ${m.kind === 'reply' ? 'ok' : m.kind === 'followup' ? 'warn' : 'acc'}">${m.kind === 'first' ? 'first email' : m.kind}</span></div>
    <input class="subj" value="${esc(m.subject)}" style="margin-bottom:10px;font-weight:600"><textarea class="body">${esc(m.body)}</textarea>
    ${m.error ? `<div class="pill bad" style="margin-top:10px">Last error: ${esc(m.error)}</div>` : ''}
    <div class="row" style="margin-top:12px"><span class="mute sp">${m.kind !== 'reply' ? 'An unsubscribe line is added automatically.' : ''}</span><button class="btn s ghost danger del">Discard</button><button class="btn s p send">Send</button></div></div>`).join('')
    : `<div class="card empty">No drafts waiting.</div>`}
  <h3>Recently sent</h3>
  <div class="card">${sent.length ? `<table><tbody>${sent.slice(0, 30).map((m) => `<tr><td><b>${esc(m.name || m.company || m.email)}</b><div class="mute">${esc(m.email)}</div></td><td>${esc(m.subject)}<div class="mute">${m.kind}</div></td><td class="mute" style="text-align:right">${ago(m.sent_at)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">Nothing sent yet.</div>'}</div>`;
};
pages.outreach.on = () => {
  const save = (c) => api('/messages/' + c.dataset.id, { subject: $('.subj', c).value, body: $('.body', c).value }, 'PATCH');
  $$('.mail').forEach((c) => {
    $('.subj', c).onchange = $('.body', c).onchange = () => save(c);
    $('.del', c).onclick = (e) => act(e.target, async () => { await api('/messages/' + c.dataset.id, null, 'DELETE'); go(); });
    $('.send', c).onclick = (e) => act(e.target, async () => { await save(c); const r = await api('/messages/send', { ids: [+c.dataset.id] }); if (r.errors.length) throw new Error(r.errors[0]); toast('Sent'); go(); });
  });
  $('#fu').onclick = (e) => act(e.target, async () => { const r = await api('/outreach/followups', {}); toast(`${plural(r.drafted, 'follow-up')} drafted`); go(); });
  $('#sendall') && ($('#sendall').onclick = (e) => act(e.target, async () => {
    const cards = $$('.mail'); if (!confirm(`Send ${cards.length} emails now? They go out a few seconds apart.`)) return;
    for (const c of cards) await save(c);
    const r = await api('/messages/send', { ids: cards.map((c) => +c.dataset.id) }); toast(`Sent ${r.sent}`); if (r.errors.length) toast(r.errors[0], true); go();
  }));
};

// ---------------- replies ----------------
pages.inbox = async () => {
  const msgs = await api('/messages?status=received,handled');
  return `${head('Replies', 'The team reads every reply, sorts it by what the person wants, and answers. Follow-ups stop as soon as someone replies.', '<button class="btn p" id="ck">Check Gmail now</button>')}
  ${msgs.length ? msgs.map((m) => `<div class="card" style="${m.status === 'handled' ? 'opacity:.65' : ''}"><div class="row"><b class="sp">${esc(m.name || m.company || m.email)}</b>
    <span class="pill ${INTENT[m.intent] || ''}">${esc((m.intent || '').replace(/_/g, ' '))}</span><span class="mute">${ago(m.created)}</span></div>
    <p style="margin:10px 0 6px;font-family:var(--serif);font-size:17px">${esc(m.summary || '')}</p><div class="pre mute" style="max-height:150px;overflow:auto">${esc(m.body)}</div>
    <div class="row" style="margin-top:12px"><button class="btn s ghost" data-th="${m.lead_id}">Full thread</button><span class="sp"></span>
    ${m.status === 'received' ? `<button class="btn s" data-done="${m.id}">Mark done</button>` : ''}</div></div>`).join('')
    : '<div class="card empty">No replies yet. They appear here automatically.</div>'}`;
};
pages.inbox.on = () => {
  $('#ck').onclick = (e) => act(e.target, async () => { const r = await api('/inbox/check', {}); toast(`${plural(r.found || 0, 'new reply', 'new replies')}`); go(); });
  bindThreads();
  $$('[data-done]').forEach((b) => (b.onclick = async () => { await api('/messages/' + b.dataset.done, { status: 'handled' }, 'PATCH'); go(); }));
};

// ---------------- website requests ----------------
let sigTab = 'new';
pages.signals = async () => {
  const list = await api('/signals?status=' + sigTab);
  return `${head('Website requests', 'People who posted publicly that they want a new website or a redesign. Each weekday the team finds new posts, looks up the poster’s business, and emails them automatically when they publish an email. Nothing for you to do.', '<button class="btn p" id="sf">Search now</button>')}
  <div class="row" style="margin-bottom:14px"><label class="switch"><input type="checkbox" id="son" ${S.settings.signals !== '0' ? 'checked' : ''}><span></span></label><span class="mute sp">Search every day (about $0.03 a search)</span>
    <div class="tabs">${[['new', 'Recent'], ['done', 'Hidden']].map(([k, l]) => `<button class="${sigTab === k ? 'on' : ''}" data-tab="${k}">${l}</button>`).join('')}</div></div>
  ${list.length ? list.map((s) => `<div class="card" data-id="${s.id}"><div class="row"><span class="pill ${s.need === 'new' ? 'acc' : 'gold'}">${s.need === 'new' ? 'New website' : 'Redesign'}</span><span class="pill">${esc(s.platform)}</span>
      <span class="mute sp">${esc([s.location, s.posted].filter(Boolean).join(' · '))}</span>${s.lead_id ? '<span class="pill ok">emailed automatically</span>' : '<span class="pill" title="No public email found. Optional: reply on the post yourself.">no email found</span>'}</div>
    <p style="margin:12px 0 4px;font-family:var(--serif);font-size:18px">${esc(s.title || s.name || '')}</p><p class="mute" style="margin:0 0 12px">${esc(s.summary)}</p>
    <div class="row" style="margin-top:12px"><a class="btn s ghost" href="${esc(s.url)}" target="_blank" rel="noopener">Open post</a><span class="sp"></span>
      ${s.status === 'new' ? '<button class="btn s ghost" data-st="done">Hide</button>' : `<span class="mute">${s.status}</span>`}</div></div>`).join('')
    : `<div class="card empty">${sigTab === 'new' ? 'No requests yet. Press “Search now”, or wait for the daily search.' : 'Nothing here yet.'}</div>`}`;
};
pages.signals.on = () => {
  $('#sf').onclick = (e) => act(e.target, async () => bgMsg(await api('/signals/find', {}), 'Search for website requests'));
  $('#son').onchange = (e) => api('/settings', { signals: e.target.checked ? '1' : '0' });
  $$('[data-tab]').forEach((b) => (b.onclick = () => { sigTab = b.dataset.tab; go(); }));
  $$('.card[data-id]').forEach((c) => {
    const id = c.dataset.id;
    $$('[data-st]', c).forEach((b) => (b.onclick = async () => { await api('/signals/' + id, { status: b.dataset.st }, 'PATCH'); await refresh(); go(); }));
  });
};

// ---------------- brand ----------------
const BRAND = [
  ['name', 'Business name', 'Acme Studio'], ['website', 'Website', 'https://…'],
  ['offer', 'What do you sell?', 'Websites for local trades, $990 flat, live in 7 days', 1],
  ['services', 'All your services (one per line: service, who needs it)', 'Website redesign: dated or slow sites\nBooking forms: clinics with no online booking', 1],
  ['audience', 'Who buys it?', 'Plumbers, electricians and cafés with no website or an old one', 1],
  ['usp', 'Why you?', 'Fixed price, done in a week, no tech skills needed', 1],
  ['hook', 'Free offer that gets a first “yes”', 'Free homepage mockup of their business in 48 hours', 1],
  ['pricing', 'Pricing', 'From $990 one-off or $49/month'], ['proof', 'Proof (real only)', '40+ local sites built, 4.9★ Google'],
  ['tone', 'Voice', 'Friendly, plain English, no jargon'], ['avoid', 'Never say', 'cheap, guaranteed #1 on Google'],
  ['cta', 'Main call to action', 'Book a 15-minute call'], ['search_hint', 'Where to find buyers', 'Trades and cafés in South Australia', 1],
];
pages.brand = () => `${head('Brand', 'Everything the team writes comes from this page. Be specific and honest: it never claims anything that isn’t here.')}
  <div class="card"><label>Refresh from your website</label>
    <div class="row"><input id="url" value="${esc(S.brand.website || '')}" placeholder="yourbusiness.com" style="flex:1"><button class="btn" id="auto">Read website</button></div></div>
  <form id="bf" class="card"><div class="grid g2">
    ${BRAND.map(([k, l, ph, wide]) => `<div class="f" ${wide ? 'style="grid-column:1/-1"' : ''}><label>${l}</label>${wide ? `<textarea name="${k}" placeholder="${ph}" style="min-height:62px">${esc(S.brand[k] || '')}</textarea>` : `<input name="${k}" placeholder="${ph}" value="${esc(S.brand[k] || '')}">`}</div>`).join('')}
  </div><button class="btn p">Save brand</button></form>`;
pages.brand.on = () => {
  $('#auto').onclick = (e) => act(e.target, async () => { const r = await api('/brand/autofill', { url: $('#url').value }); for (const [k, v] of Object.entries(r)) { const el = $(`[name=${k}]`); if (el && v) el.value = v; } toast('Filled in from your website. Check it, then save.'); });
  $('#bf').onsubmit = (e) => { e.preventDefault(); act(e.submitter, async () => { await api('/brand', Object.fromEntries(new FormData(e.target))); await refresh(); toast('Brand saved'); }); };
};

// ---------------- strategy ----------------
const IDEAS = [
  ['Lead with a free, specific gift', 'Offer a free homepage mockup, a 5-point website audit or a 14-day trial. A small “yes” comes before a big one. Set it in Brand → Free offer.'],
  ['Mention one real thing about their site', 'The team checks each lead’s website (mobile, speed, security, out-of-date footer) and opens with one honest observation. It works far better than a generic pitch.'],
  ['Go local and narrow', 'Pick 2–3 categories in one region, e.g. plumbers in the Riverland. You learn their language fast, and referrals spread.'],
  ['Call the businesses with no website', 'Your “to call” list shows businesses that have no website. If you sell websites, a 2-minute call to them converts best.'],
  ['Show proof from the same niche', 'After your first client in a category, add it to Brand → Proof. Emails to that category will mention it.'],
  ['Make booking easy', 'A booking link means interested people pick a time on their own. No back-and-forth.'],
];
pages.strategy = async () => {
  const plans = await api('/plans');
  return `${head('Strategy', 'Ideas that win clients, and a 30-day plan written for your business.')}
  <div class="card"><h2>What wins clients</h2>${IDEAS.map(([t, d]) => `<div class="idea"><b>${t}</b><span>${d}</span></div>`).join('')}</div>
  <div class="card"><label>Your goal for the next 30 days</label>
    <div class="row"><input id="goal" placeholder="e.g. 5 new website clients with no ad budget" style="flex:1"><button class="btn p" id="gen">Write my plan</button></div></div>
  ${plans.map((p) => `<div class="card"><div class="row"><div class="sp"><h2 style="margin:0">${esc(p.goal || 'Plan')}</h2><div class="mute">${ago(p.created)}</div></div>
    <button class="btn s" data-copy="${p.id}">Copy</button><button class="btn s ghost danger" data-del="${p.id}">Delete</button></div><div class="md">${md(p.body)}</div></div>`).join('')}`;
};
pages.strategy.on = () => {
  $('#gen').onclick = (e) => act(e.target, async () => { await api('/plans', { goal: $('#goal').value }); toast('Plan ready'); go(); });
  bindRows('/plans', async (id) => (await api('/plans')).find((p) => p.id == id).body);
};

// ---------------- content ----------------
pages.content = async () => {
  const items = await api('/content');
  return `${head('Content', 'Posts, blogs, newsletters and ads in your brand voice. Copy them and publish where you like.')}
  <div class="card"><div class="grid" style="grid-template-columns:200px 1fr 100px auto;align-items:end">
    <div><label>Channel</label><select id="ch">${S.channels.map((c) => `<option>${c}</option>`).join('')}</select></div>
    <div><label>Topic</label><input id="topic" placeholder="e.g. Why tradies lose jobs without a website"></div>
    <div><label>Versions</label><select id="n"><option>1</option><option>2</option><option selected>3</option></select></div>
    <button class="btn p" id="gen">Write</button></div></div>
  ${items.length ? `<div class="grid g2">${items.map((c) => `<div class="card"><div class="row" style="margin-bottom:10px"><span class="pill acc">${esc(c.channel)}</span><span class="mute sp">${esc(c.topic)}</span>
    <button class="btn s" data-copy="${c.id}">Copy</button><button class="btn s ghost danger" data-del="${c.id}">✕</button></div><div class="pre">${esc(c.body)}</div></div>`).join('')}</div>`
    : '<div class="card empty">Nothing yet. Pick a channel and press Write.</div>'}`;
};
pages.content.on = () => {
  $('#gen').onclick = (e) => act(e.target, async () => { await api('/content', { channel: $('#ch').value, topic: $('#topic').value, count: $('#n').value }); go(); });
  bindRows('/content', async (id) => (await api('/content')).find((c) => c.id == id).body);
};
function bindRows(base, getText) {
  $$('[data-copy]').forEach((b) => (b.onclick = async () => copy(await getText(b.dataset.copy))));
  $$('[data-del]').forEach((b) => (b.onclick = () => act(b, async () => { await api(`${base}/${b.dataset.del}`, null, 'DELETE'); go(); })));
}

// ---------------- settings ----------------
pages.settings = () => {
  const s = S.settings;
  const f = (k, l, hint = '', type = 'text', ph = '') => `<div class="f"><label>${l}</label><input name="${k}" type="${type}" value="${esc(s[k])}" placeholder="${ph}">${hint ? `<div class="hint">${hint}</div>` : ''}</div>`;
  const badge = (ok) => `<span class="pill ${ok ? 'ok' : 'gold'}">${ok ? 'Connected' : 'Needed'}</span>`;
  return `${head('Settings', 'Your keys stay on this computer, in the <code>data</code> folder. The app talks only to OpenAI, Gmail and the websites it reads.')}
  <form id="sf">
  <div class="grid g2">
    <div class="card"><div class="row"><h2 class="sp">OpenAI</h2>${badge(S.ready.openai)}</div>
      ${f('openai_key', 'API key', 'platform.openai.com → API keys. $5 of credit lasts months.', 'password', 'sk-…')}
      ${f('model', 'Model', 'A small “mini” model keeps costs very low.')}
      <div class="grid g2">${f('price_in', '$ per 1M input tokens')}${f('price_out', '$ per 1M output tokens')}</div>
      <button type="button" class="btn s" id="to">Test OpenAI</button></div>
    <div class="card"><div class="row"><h2 class="sp">Gmail</h2>${badge(S.ready.gmail)}</div>
      ${f('gmail_user', 'Gmail address', '', 'email', 'you@gmail.com')}
      ${f('gmail_pass', 'App Password', 'Google Account → Security → 2-Step Verification on → search “App passwords” → create one. This is not your normal password.', 'password')}
      ${f('sender_name', 'Your name', 'Shown as the sender, and used to sign emails.', 'text', 'Jane Doe')}
      <button type="button" class="btn s" id="tg">Test Gmail</button></div>
  </div>
  <div class="card"><h2>Autopilot</h2><div class="grid g3">
    ${f('booking_link', 'Booking link', 'Calendly, Cal.com or a Google Calendar booking page.', 'url', 'https://calendly.com/you/15min')}
    ${f('report_to', 'Alerts and report go to', 'Leave empty to use your Gmail.', 'email')}
    ${f('daily_new_leads', 'New leads per day', '', 'number')}
    ${f('min_score', 'Only email leads scoring at least', 'Fit score, 0–100.', 'number')}
    ${f('work_start', 'Send emails from (hour)', 'Monday to Friday.', 'number')}
    ${f('work_end', 'Until (hour)', 'Your daily report is sent then.', 'number')}
    ${f('timezone', 'Time zone', 'Hours follow this zone, e.g. Australia/Adelaide, Australia/Sydney.')}</div></div>
  <div class="card"><h2>Sending rules</h2><div class="grid g3">
    ${f('daily_cap', 'Max emails a day', '20–40 is safe for a normal Gmail account.', 'number')}
    ${f('followup_days', 'Follow up after (days)', '', 'number')}
    ${f('max_followups', 'Follow-ups per lead', '', 'number')}</div>
    ${f('footer', 'Footer on outreach emails', 'Keep an opt-out line. Anti-spam laws require it.')}</div>
    <div class="f" style="margin-top:14px"><label>Your email signature</label><textarea name="signature" style="min-height:96px" placeholder="${esc([s.sender_name || 'Your name', S.brand.name || 'Business', 'Website · phone'].join('\n'))}">${esc(s.signature || '')}</textarea><div class="hint">Added under every email the team sends, including replies. {name} becomes “Your name” above. Leave empty to use your name, business and website.</div></div>
  <button class="btn p">Save settings</button></form>
  ${S.cronPath ? `<div class="card"><h2>Keep it running (hosting)</h2><p class="mute" style="margin-top:0">In your hosting panel, add a cron job that runs every 10 minutes and opens this link. It wakes the app so autopilot never pauses. Keep the link private.</p><code style="word-break:break-all">${esc(location.origin + S.cronPath)}</code></div>` : ''}
  <p class="mute" style="margin-top:22px">Total AI spend so far: $${S.usage.total.toFixed(3)}, across ${plural(S.usage.calls, 'task')}.</p>`;
};
pages.settings.on = () => {
  const save = async () => { S = await api('/settings', Object.fromEntries(new FormData($('#sf')))); };
  $('#sf').onsubmit = (e) => { e.preventDefault(); act(e.submitter, async () => { await save(); toast('Saved'); go(); }); };
  $('#to').onclick = (e) => act(e.target, async () => { await save(); await api('/test/openai', {}); toast('OpenAI works'); });
  $('#tg').onclick = (e) => act(e.target, async () => { await save(); await api('/test/gmail', {}); toast('Gmail works (sending and reading)'); });
};

// ---------------- modal + router ----------------
function modal(title, html, on) {
  const d = document.createElement('dialog');
  d.innerHTML = `<div class="hd"><span class="sp">${title}</span><button class="btn s ghost">✕</button></div><div class="bd">${html}</div>`;
  document.body.append(d); d.showModal();
  $('.hd button', d).onclick = () => d.close(); d.onclose = () => d.remove();
  on && on(d);
}
async function go() {
  const p = (location.hash.replace(/^#\/?/, '') || 'home').split('?')[0];
  const page = pages[p] || pages.home;
  $$('#nav a').forEach((a) => a.classList.toggle('on', a.dataset.p === (pages[p] ? p : 'home')));
  try { await refresh(); $('#view').innerHTML = await page(); page.on && page.on(); }
  catch (e) { if (!$('#login')) $('#view').innerHTML = `<div class="card empty">${esc(e.message)}</div>`; }
}
addEventListener('hashchange', go);
go();
