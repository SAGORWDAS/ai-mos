// Lead finder: OpenAI web search → matching companies → public contact email from their site.
const dns = require('node:dns').promises;
const { getSetting, setSetting, getJSON, run, all, get, log } = require('./db');

const BAD_LOCAL = /^(no-?reply|donotreply|privacy|abuse|legal|jobs|careers|hr|recruit|billing|invoice|accounts?|security|webmaster|postmaster|dmca|press|media|unsubscribe)/i;
const GOOD_LOCAL = ['founder', 'ceo', 'hello', 'hi', 'contact', 'sales', 'team', 'info', 'partners', 'business'];

async function webSearch(prompt) {
  const key = getSetting('openai_key');
  if (!key) throw new Error('Add your OpenAI API key in Settings first.');
  const model = getSetting('model') || 'gpt-4o-mini';
  let lastErr;
  for (const tool of ['web_search', 'web_search_preview']) {
    const res = await fetch('https://api.openai.com/v1/responses', {
      method: 'POST',
      headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, tools: [{ type: tool }], input: prompt, max_output_tokens: 3000 }),
      signal: AbortSignal.timeout(180000),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { lastErr = new Error(`OpenAI search: ${data.error?.message || res.statusText}`); continue; }
    const u = data.usage || {};
    const cost = ((u.input_tokens || 0) * +getSetting('price_in') + (u.output_tokens || 0) * +getSetting('price_out')) / 1e6 + 0.025; // + search call fee
    run('INSERT INTO usage(task,model,tin,tout,cost) VALUES(?,?,?,?,?)', 'find', model, u.input_tokens || 0, u.output_tokens || 0, cost);
    return (data.output || []).flatMap((o) => o.content || []).filter((c) => c.type === 'output_text').map((c) => c.text).join('\n');
  }
  throw lastErr;
}

function parseList(text) {
  const m = text.match(/\[[\s\S]*\]/);
  if (!m) return [];
  try { return JSON.parse(m[0]); } catch { return []; }
}

const domainOf = (u) => { try { return new URL(/^https?:/.test(u) ? u : 'https://' + u).hostname.replace(/^www\./, '').toLowerCase(); } catch { return ''; } };

async function hasMx(domain) {
  try { return (await dns.resolveMx(domain)).length > 0; } catch { return false; }
}

const FREE_MAIL = /@(gmail|googlemail|outlook|hotmail|live|yahoo|icloud|me|proton|protonmail|zoho|aol|gmx)\.[a-z.]+$/i;

// Look on the person's/company's own site for a public email: on its domain,
// or a personal address (gmail etc.) that the site itself publishes.
async function findEmail(website, hinted, person = '') {
  const domain = domainOf(website);
  if (!domain) return '';
  const ok = (e) => e && !BAD_LOCAL.test(e) && !/\.(png|jpe?g|gif|webp|svg)$/i.test(e) && !/example\.|sentry|wixpress/i.test(e)
    && (e.toLowerCase().endsWith('@' + domain) || FREE_MAIL.test(e));
  const first = person.trim().split(/\s+/)[0]?.toLowerCase() || '';
  const rank = (e) => {
    const local = e.split('@')[0];
    if (first.length > 2 && local.includes(first)) return 0; // their own name
    if (!GOOD_LOCAL.some((g) => local === g) && !FREE_MAIL.test(e)) return 1; // looks personal on own domain
    const i = GOOD_LOCAL.indexOf(local);
    return i < 0 ? 3 : 2 + i / 10;
  };
  const found = new Set();
  for (const p of ['', '/contact', '/contact-us', '/about', '/about-me', '/about-us', '/work-with-me', '/hire-me', '/team']) {
    try {
      const r = await fetch(`https://${domain}${p}`, { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(10000), redirect: 'follow' });
      if (!r.ok) continue;
      const html = (await r.text()).slice(0, 400000);
      for (const e of html.match(/[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/gi) || []) if (ok(e)) found.add(e.toLowerCase());
      if ([...found].some((e) => rank(e) <= 1)) break; // found a personal address, stop crawling
    } catch { /* site unreachable */ }
  }
  // An address suggested by search is only trusted on the site's own domain (free-mail must be seen on the site).
  if (!found.size && hinted && hinted.toLowerCase().endsWith('@' + domain) && ok(hinted)) found.add(hinted.toLowerCase());
  return [...found].sort((a, b) => rank(a) - rank(b))[0] || '';
}

// Find up to `want` new leads. Returns number added.
async function findLeads(want = 10) {
  const b = getJSON('brand', {});
  if (!b.name) throw new Error('Set up your brand first.');
  const known = all("SELECT website FROM leads WHERE website!='' ORDER BY id DESC LIMIT 80").map((r) => domainOf(r.website)).filter(Boolean);
  const own = domainOf(b.website || '');
  const target = getSetting('target') || 'both';
  const who = {
    companies: 'real small and mid-size companies',
    people: 'real individual professionals who sell their own services through a personal or one-person website (freelancers, consultants, coaches, designers, developers, agency owners, therapists, photographers, etc.)',
    both: 'a mix of real individual professionals who sell services through their own website (freelancers, consultants, coaches, solo agency owners) and small companies',
  }[target] || target;
  // Target markets: rotate through niche × place, one combination per search.
  const lines = (k) => getSetting(k).split('\n').map((x) => x.trim()).filter(Boolean);
  const niches = lines('niches'), places = lines('places');
  let market = '';
  if (niches.length) {
    const i = +getSetting('market_cursor') || 0;
    setSetting('market_cursor', i + 1);
    const niche = niches[i % niches.length], place = places.length ? places[Math.floor(i / niches.length) % places.length] : '';
    market = `${niche}${place ? ' in ' + place : ''}`;
  }
  const prompt = `Find ${Math.min(want + 5, 15)} ${market ? `real, independent ${market} (established businesses with their own website, not chains or franchises)` : who} that are a strong fit to buy this product. Use web search. Each must have its own website that shows a contact email. For individuals, give their full name.
Product: ${b.name} — ${b.offer || ''}
Ideal customer: ${b.audience || ''}
${!market && b.search_hint ? 'Where/what to look for: ' + b.search_hint : ''}
Do NOT include: ${[own, ...known].filter(Boolean).join(', ') || 'none'}; competitors; huge enterprises; directories or listicle sites.
Reply with ONLY a JSON array, no other text: [{"company":"","website":"https://...","contact_name":"","role":"","email":"","why":"one specific reason they need it"}]. Leave email/contact_name "" if not shown publicly. Never guess emails.`;

  const rows = parseList(await webSearch(prompt));
  let added = 0;
  for (const r of rows) {
    if (added >= want) break;
    const domain = domainOf(r.website || '');
    if (!domain || domain === own || known.includes(domain)) continue;
    known.push(domain);
    const email = await findEmail(domain, r.email, r.contact_name || '');
    if (!email || get('SELECT 1 FROM leads WHERE email=?', email) || !(await hasMx(email.split('@')[1]))) continue;
    const res = run('INSERT OR IGNORE INTO leads(name,email,company,role,website,notes,source) VALUES(?,?,?,?,?,?,?)',
      r.contact_name || '', email, r.company || domain, r.role || '', 'https://' + domain, r.why || '', 'ai');
    if (res.changes) added++;
  }
  return added;
}

module.exports = { findLeads, findEmail, domainOf, webSearch, parseList, hasMx };
