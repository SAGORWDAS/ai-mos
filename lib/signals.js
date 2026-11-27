// Buying signals: public posts where someone asks to hire help for a NEW website or a REDESIGN.
// The team finds them and writes a reply; you post it yourself (platforms ban automated posting).
const { getSetting, getJSON, run, get, log } = require('./db');
const { webSearch, parseList, findEmail, hasMx, domainOf } = require('./finder');
const team = require('./agents');

const lines = (k) => getSetting(k).split('\n').map((x) => x.trim()).filter(Boolean);

async function findSignals() {
  const b = getJSON('brand', {});
  if (!b.name) throw new Error('Set up your brand first.');
  const places = lines('places');
  const where = places.length ? `${places.join(', ')}, or elsewhere in Australia` : 'Australia';
  const prompt = `Search the web for PUBLIC posts from the last 21 days where a person or business wants to HIRE someone to build a NEW website, or to REDESIGN, rebuild or fix their existing website.
Location: ${where}.
Look on: Airtasker, Reddit (e.g. r/smallbusiness, r/Adelaide, r/australia, r/AusFinance), Gumtree, Upwork, Freelancer.com, public LinkedIn posts, public Facebook posts and groups, local forums.
Include only genuine requests to hire. Exclude designers or agencies advertising themselves, tutorials, listicles, and closed or old jobs.
Reply with ONLY a JSON array (max 10), no other text: [{"url":"direct link to the post","platform":"Airtasker","need":"new or redesign","title":"","summary":"what they want, plus budget if stated, in one sentence","location":"","posted":"date or age as shown","name":"poster or business name if shown","business_website":"their current site if mentioned, else empty"}]. Never invent posts or links.`;

  const rows = parseList(await webSearch(prompt)).filter((r) => /^https?:\/\//.test(r.url || ''));
  const fresh = [];
  for (const r of rows) {
    const need = /redesign|rebuild|fix|update|refresh/i.test(r.need || '') ? 'redesign' : 'new';
    const res = run('INSERT OR IGNORE INTO signals(url,platform,need,title,summary,location,posted,name,website) VALUES(?,?,?,?,?,?,?,?,?)',
      r.url, r.platform || domainOf(r.url), need, r.title || '', r.summary || '', r.location || '', r.posted || '', r.name || '', r.business_website || '');
    if (res.changes) fresh.push({ id: Number(res.lastInsertRowid), ...r, need });
  }
  if (!fresh.length) { log('signal', 'No new website requests found today'); return []; }

  // One AI call writes every reply (cheap).
  const replies = await team.signalReplies(fresh, (getSetting('sender_name') || '').split(' ')[0]);
  for (const x of replies) if (x && x.id) run('UPDATE signals SET reply=? WHERE id=?', x.reply || '', x.id);

  // If they named their business site and it publishes an email, the normal outreach can follow up too.
  for (const s of fresh) {
    const site = domainOf(s.business_website || '');
    if (!site) continue;
    const email = await findEmail(site, '', s.name || '');
    if (!email || get('SELECT 1 FROM leads WHERE email=?', email) || !(await hasMx(email.split('@')[1]))) continue;
    const l = run("INSERT OR IGNORE INTO leads(name,email,company,website,notes,source,score,score_reason) VALUES(?,?,?,?,?,?,90,'Asked publicly for a website')",
      '', email, s.name || site, 'https://' + site, `Posted on ${s.platform} asking for ${s.need === 'new' ? 'a new website' : 'a website redesign'}: ${s.summary || s.title}`, 'signal');
    if (l.changes) run('UPDATE signals SET lead_id=? WHERE id=?', Number(l.lastInsertRowid), s.id);
  }
  log('signal', `Found ${fresh.length} new website request${fresh.length === 1 ? '' : 's'}. Replies are ready to post.`);
  return fresh.map((s) => get('SELECT * FROM signals WHERE id=?', s.id));
}

module.exports = { findSignals };
