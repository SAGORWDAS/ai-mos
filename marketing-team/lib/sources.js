// Lead sources: business directories (e.g. a local business listing site).
// directory → category pages → listing pages → business website → published email.
const { all, get, run, log } = require('./db');
const { findEmail, domainOf } = require('./finder');

const UA = 'Mozilla/5.0 (compatible; MarketingTeamBot/1.0)';
const SOCIAL = /(facebook|instagram|linkedin|twitter|x\.com|youtube|tiktok|pinterest|google\.|goo\.gl|apple\.com|wa\.me|whatsapp|maps\.|bing\.|yelp|gravatar|wordpress\.org|w3\.org|schema\.org|ogp\.me|cloudflare|jquery|gstatic|addthis|sharethis)/i;
const CHROME = /\/(login|register|signin|signup|submit|about|contact|privacy|policies|policy|terms|disclaimer|map|events?|news|blog|search|tags?|cart|account|faq|advertise|pricing|feed|wp-|recent)/i;
const norm = (h) => h.replace(/\/$/, '');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getPage(url) {
  const r = await fetch(url, { headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(15000), redirect: 'follow' });
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return (await r.text()).slice(0, 800000);
}

function links(html, base) {
  const out = [];
  for (const m of html.matchAll(/<a\b[^>]*href=["']([^"'#]+)["'][^>]*>([\s\S]*?)<\/a>/gi)) {
    try { out.push({ url: new URL(m[1].replace(/&amp;/g, '&'), base).href, text: m[2].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim() }); } catch { /* bad href */ }
  }
  return out;
}

const decode = (s) => s.replace(/&amp;/g, '&').replace(/&#0?39;|&apos;/g, "'").replace(/&quot;/g, '"').replace(/&#8211;|&ndash;/g, '–').trim();

// robots.txt: respect Disallow rules for all bots.
const robotsCache = new Map();
async function allowed(url) {
  const u = new URL(url);
  if (!robotsCache.has(u.host)) {
    let rules = [];
    try {
      const txt = await (await fetch(`${u.origin}/robots.txt`, { headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(8000) })).text();
      let applies = false;
      for (const line of txt.split('\n')) {
        const [k, ...v] = line.split(':'); const key = k.trim().toLowerCase(), val = v.join(':').trim();
        if (key === 'user-agent') applies = val === '*';
        else if (applies && key === 'disallow' && val) rules.push(val);
      }
    } catch { rules = []; }
    robotsCache.set(u.host, rules);
  }
  return !robotsCache.get(u.host).some((p) => u.pathname.startsWith(p));
}

// List the categories a directory offers (so the user can pick).
async function listCategories(dirUrl) {
  const root = new URL(/^https?:/.test(dirUrl) ? dirUrl : 'https://' + dirUrl);
  const seen = new Map();
  for (const path of ['/categories/', '/category/', '/directory/', '/']) {
    try {
      const html = await getPage(root.origin + path);
      for (const l of links(html, root.origin)) {
        const u = new URL(l.url);
        if (u.host === root.host && /\/(categor(y|ies)|directory|c)\/[^/]+/i.test(u.pathname) && l.text && l.text.length < 80) seen.set(u.href, decode(l.text));
      }
      if (seen.size > 5) break;
    } catch { /* try next */ }
  }
  return [...seen].map(([url, name]) => ({ url, name })).sort((a, b) => a.name.localeCompare(b.name));
}

// Pick out listing pages on a category page.
async function listingUrls(catUrl, chromeSet) {
  const host = new URL(catUrl).host;
  const urls = new Map();
  let page = catUrl;
  for (let i = 0; i < 5 && page; i++) { // follow up to 5 pages of results
    const html = await getPage(page);
    let next = null;
    for (const l of links(html, page)) {
      const u = new URL(l.url);
      if (u.host !== host) continue;
      if (/^(next|›|»|next page)/i.test(l.text) || /[?&]page=\d|\/page\/\d/.test(u.href) && l.text === String(i + 2)) next = next || u.href;
      if (chromeSet.has(norm(u.href)) || CHROME.test(u.pathname) || /\/(categor(y|ies)|directory|c)\//i.test(u.pathname) || u.pathname === '/' || u.search) continue;
      if (!urls.has(norm(u.href))) urls.set(norm(u.href), u.href);
    }
    page = next && next !== page ? next : null;
    await sleep(600);
  }
  return [...urls.values()];
}

// Read one listing page: business name, website, email, phone.
async function readListing(url) {
  const html = await getPage(url);
  const host = new URL(url).host;
  const name = decode((html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i)?.[1] || html.match(/<title>([^<|–-]+)/i)?.[1] || '').replace(/<[^>]+>/g, ''));
  const email = (html.match(/mailto:([^"'?>\s]+)/i)?.[1] || '').toLowerCase();
  const phone = decode(html.match(/tel:([^"'>\s]+)/i)?.[1] || '');
  let website = '';
  for (const l of links(html, url)) {
    const u = new URL(l.url);
    if (!/^https?:$/.test(u.protocol) || u.host === host || SOCIAL.test(u.host)) continue;
    website = u.origin; break;
  }
  return { name, email: /^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(email) ? email : '', phone, website };
}

// Process up to `max` new listings from one source. Returns { emails, calls }.
async function runSource(src, max = 20) {
  const cats = JSON.parse(src.categories || '[]');
  if (!cats.length) throw new Error('Pick at least one category for ' + src.url);
  const root = new URL(src.url);
  const chrome = new Set();
  try { for (const l of links(await getPage(root.origin + '/'), root.origin)) chrome.add(norm(l.url)); } catch { /* ok */ }
  let emails = 0, calls = 0, checked = 0;
  const limit = max * 3; // many listings have no email; check more than we need
  for (const cat of cats) {
    if (checked >= limit || emails >= max) break;
    let list = [];
    try { list = await listingUrls(cat.url, chrome); } catch (e) { log('error', `${cat.name}: ${e.message}`); continue; }
    for (const url of list) {
      if (checked >= limit || emails >= max) break;
      if (get('SELECT 1 FROM seen WHERE url=?', norm(url)) || !(await allowed(url))) continue;
      run('INSERT OR IGNORE INTO seen(url) VALUES(?)', norm(url));
      checked++;
      try {
        const b = await readListing(url);
        await sleep(700);
        if (!b.name) continue;
        let email = b.email;
        if (!email && b.website) email = await findEmail(b.website, '', '');
        const note = `${cat.name} · listed on ${root.host}${b.website ? '' : ' · has NO website'}${b.phone ? ' · ' + b.phone : ''}`;
        if (email) {
          if (run('INSERT OR IGNORE INTO leads(name,email,company,website,notes,source,phone) VALUES(?,?,?,?,?,?,?)', '', email, b.name, b.website, note, root.host, b.phone).changes) emails++;
        } else if (b.phone && !get('SELECT 1 FROM leads WHERE phone=?', b.phone)) {
          run("INSERT INTO leads(company,website,notes,source,phone,status) VALUES(?,?,?,?,?,'call')", b.name, b.website, note, root.host, b.phone);
          calls++;
        }
      } catch { /* listing unreachable */ }
    }
  }
  run("UPDATE sources SET last_run=datetime('now'), found=found+? WHERE id=?", emails + calls, src.id);
  log('find', `${root.host}: ${emails} new email lead${emails === 1 ? '' : 's'}, ${calls} to call (checked ${checked} listings)`);
  return { emails, calls, checked };
}

async function runAll(max) {
  let emails = 0;
  for (const s of all('SELECT * FROM sources WHERE active=1')) {
    if (emails >= max) break;
    try { emails += (await runSource(s, max - emails)).emails; } catch (e) { log('error', e.message); }
  }
  return emails;
}

module.exports = { listCategories, runSource, runAll, readListing, listingUrls };
