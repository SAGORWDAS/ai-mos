// Quick, factual website check used to personalise the first email.
async function auditSite(website) {
  if (!website) return 'They have NO website (only a directory listing).';
  const url = /^https?:/.test(website) ? website : 'https://' + website;
  const t0 = Date.now();
  let res, html;
  try {
    res = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(20000), redirect: 'follow' });
    html = await res.text();
  } catch {
    return 'Their website did not load when we checked it.';
  }
  const ms = Date.now() - t0, obs = [];
  const year = new Date().getFullYear();
  if (!res.ok) obs.push(`Homepage returned an error (${res.status})`);
  if (res.url.startsWith('http:')) obs.push('Site is not on HTTPS (browsers mark it "Not secure")');
  if (!/<meta[^>]+name=["']viewport/i.test(html)) obs.push('No mobile viewport tag, so the site is probably hard to use on phones');
  if (ms > 3500) obs.push(`Homepage took ${(ms / 1000).toFixed(1)}s to load`);
  if (!/<meta[^>]+name=["']description["'][^>]+content=["'][^"']{20,}/i.test(html)) obs.push('No meta description (weaker Google search snippet)');
  const cy = [...html.matchAll(/(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?(\d{4})/gi)].map((m) => +m[1]).filter((y) => y > 1995 && y <= year);
  if (cy.length && Math.max(...cy) < year - 1) obs.push(`Footer copyright says ${Math.max(...cy)}, so the site looks unmaintained`);
  if (!/<form/i.test(html) && !/calendly|book(ing)?|appointment|schedule/i.test(html)) obs.push('No contact form or online booking on the homepage');
  const builder = html.match(/wix\.com|squarespace|weebly|godaddy|jimdo|site123/i)?.[0];
  if (builder) obs.push(`Built with ${builder.replace(/\..*/, '')}`);
  if (html.length > 3e6) obs.push('Very heavy homepage (slow on mobile data)');
  return obs.length ? obs.join('; ') : 'Site looks modern; no obvious issues.';
}

module.exports = { auditSite };
