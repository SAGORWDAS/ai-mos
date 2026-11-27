// Buying signals: public posts where someone asks to hire help for a NEW website or a REDESIGN.
// Hands-off: when the poster's business has a website with a public email, outreach emails them automatically.
// (We never post on the platforms themselves: they ban automated posting.)
const { getSetting, getJSON, run, get, log } = require('./db');
const { webSearch, parseList, findEmail, hasMx, domainOf } = require('./finder');

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
Reply with ONLY a JSON array (max 10), no other text: [{"url":"direct link to the post","platform":"Airtasker","need":"new or redesign","title":"","summary":"what they want, plus budget if stated, in one sentence","location":"","posted":"date or age as shown","name":"poster or business name if shown","business_website":"the poster's business website: from the post, or found by searching the business name they give; empty if unknown"}]. Never invent posts, links or websites.`;

  const rows = parseList(await webSearch(prompt)).filter((r) => /^https?:\/\//.test(r.url || ''));
  const fresh = [];
  for (const r of rows) {
    const need = /redesign|rebuild|fix|update|refresh/i.test(r.need || '') ? 'redesign' : 'new';
    const res = run('INSERT OR IGNORE INTO signals(url,platform,need,title,summary,location,posted,name,website) VALUES(?,?,?,?,?,?,?,?,?)',
      r.url, r.platform || domainOf(r.url), need, r.title || '', r.summary || '', r.location || '', r.posted || '', r.name || '', r.business_website || '');
    if (res.changes) fresh.push({ id: Number(res.lastInsertRowid), ...r, need });
  }
  if (!fresh.length) { log('signal', 'No new website requests found today'); return []; }

  // Their business site publishes an email → outreach emails them (top of the queue).
  for (const s of fresh) {
    const site = domainOf(s.business_website || '');
    if (!site) continue;
    const email = await findEmail(site, '', s.name || '');
    if (!email || get('SELECT 1 FROM leads WHERE email=?', email) || !(await hasMx(email.split('@')[1]))) continue;
    const l = run("INSERT OR IGNORE INTO leads(name,email,company,website,notes,source,score,score_reason) VALUES(?,?,?,?,?,?,90,'Asked publicly for a website')",
      '', email, s.name || site, 'https://' + site, `Posted on ${s.platform} asking for ${s.need === 'new' ? 'a new website' : 'a website redesign'}: ${s.summary || s.title}`, 'signal');
    if (l.changes) run('UPDATE signals SET lead_id=? WHERE id=?', Number(l.lastInsertRowid), s.id);
  }
  const emailed = fresh.filter((s) => get('SELECT lead_id FROM signals WHERE id=?', s.id).lead_id).length;
  log('signal', `Found ${fresh.length} new website request${fresh.length === 1 ? '' : 's'}; ${emailed} will be emailed automatically`);
  return fresh.map((s) => get('SELECT * FROM signals WHERE id=?', s.id));
}

module.exports = { findSignals };
