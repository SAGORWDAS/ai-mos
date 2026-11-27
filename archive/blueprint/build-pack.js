// Build Pack renderer: parts-pack/*.html + generated task cards -> AI-MOS-Build-Pack.pdf
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
const { PDFDocument } = require('pdf-lib');
const TASKS = require('./tasks');

const ROOT = __dirname;
const PARTS = path.join(ROOT, 'parts');
const PACK = path.join(ROOT, 'parts-pack');
const OUT = path.join(ROOT, '..', 'AI-MOS-Build-Pack.pdf');
const TMP = path.join(ROOT, '.tmp-pack');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const WS = path.join(ROOT, '..');

const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function masterStyle() {
  const head = fs.readFileSync(path.join(PARTS, '00-head.html'), 'utf8');
  return (head.match(/<style>([\s\S]*?)<\/style>/) || [, ''])[1];
}

const PACK_CSS = `
@page { size: A4; margin: 20mm 16mm 18mm 16mm; }
/* --- pack cover: white ground, inverse of the master --- */
.pc { background:#fff; color:#000; margin:0; padding:0; width:210mm; height:297mm; position:relative; }
.pc .inner { padding: 26mm 20mm 0; }
.pc .top { display:table; width:100%; }
.pc .top .l { display:table-cell; font-family:"Segoe UI",sans-serif; font-size:7pt; letter-spacing:.22em; text-transform:uppercase; color:#5a5a5a; }
.pc .top .r { display:table-cell; text-align:right; font-family:"Segoe UI",sans-serif; font-size:7pt; letter-spacing:.22em; text-transform:uppercase; color:#5a5a5a; }
.pc .rule-top { border-top:2.2pt solid #000; margin: 9mm 0 0; }
.pc h1.big { font-family:Georgia,serif; font-size:58pt; line-height:.94; letter-spacing:-.03em; font-weight:normal; margin: 14mm 0 0; }
.pc h1.big .thin { color:#b0b0b0; }
.pc .sub { font-family:Georgia,serif; font-size:13pt; line-height:1.34; margin:6mm 0 0; max-width:140mm; color:#1a1a1a; }
.pc .lede2 { font-family:Campria,Georgia,serif; font-size:9.4pt; line-height:1.6; color:#4a4a4a; max-width:128mm; margin:7mm 0 0; }
.pc .band { position:absolute; left:0; right:0; bottom:0; height:62mm; background:#000; color:#fff; padding: 12mm 20mm; }
.pc .band .t { font-family:"Segoe UI",sans-serif; font-size:6.4pt; letter-spacing:.2em; text-transform:uppercase; color:#9a9a9a; }
.pc .band .m { display:table; width:100%; margin-top:4mm; }
.pc .band .m .c { display:table-cell; width:33%; vertical-align:top; padding-right:5mm; }
.pc .band .m .k { font-family:"Segoe UI",sans-serif; font-size:6.2pt; letter-spacing:.18em; text-transform:uppercase; color:#7a7a7a; display:block; margin-bottom:1.2mm; }
.pc .band .m .v { font-size:8.2pt; color:#f0f0f0; display:block; line-height:1.4; }
/* cover contents */
.pcc { margin: 12mm 0 0; border-top:1pt solid #000; max-width:150mm; }
.pcc-row { display:table; width:100%; border-bottom:.4pt solid #d8d8d8; padding:1.5mm 0; }
.pcc-row .n { display:table-cell; width:10mm; font-family:"Segoe UI",sans-serif; font-size:7pt; color:#9a9a9a; letter-spacing:.1em; padding-top:.4mm; }
.pcc-row .t { display:table-cell; width:66mm; font-family:Georgia,serif; font-size:9.4pt; }
.pcc-row .d { display:table-cell; font-family:"Segoe UI",sans-serif; font-size:7.2pt; color:#6a6a6a; padding-top:.6mm; }

/* --- task cards --- */
.card { border-top:1pt solid #000; padding-top:2.2mm; margin:0 0 4.2mm; break-inside:avoid; page-break-inside:avoid; }
.card .hd { display:table; width:100%; }
.card .cid { display:table-cell; width:18mm; font-family:Consolas,monospace; font-size:8.2pt; font-weight:700; padding-top:.2mm; }
.card .cmeta { display:table-cell; font-family:"Segoe UI",sans-serif; font-size:6.3pt; letter-spacing:.13em; text-transform:uppercase; color:#5a5a5a; padding-top:.6mm; }
.card .cmeta .blk { border:.5pt solid #000; padding:.2mm 1.1mm; margin-left:2mm; color:#000; }
.card h5 { font-family:Georgia,serif; font-weight:normal; font-size:9.7pt; line-height:1.25; margin:1mm 0 1.4mm; }
.card .row { display:table; width:100%; }
.card .k { display:table-cell; width:13mm; font-family:"Segoe UI",sans-serif; font-size:6pt; letter-spacing:.11em; text-transform:uppercase; color:#8a8a8a; padding:.5mm 0 0; }
.card .v { display:table-cell; font-size:7.5pt; line-height:1.36; padding-bottom:.5mm; }
.card .v.f { font-family:Consolas,monospace; font-size:6.7pt; color:#2a2a2a; }
.card .v.n { color:#4a4a4a; }
.phase-hd { border-top:2.2pt solid #000; padding-top:2.6mm; margin:7mm 0 3.5mm; break-after:avoid; break-inside:avoid; page-break-after:avoid; page-break-inside:avoid; }
.phase-hd .e { font-family:"Segoe UI",sans-serif; font-size:6.6pt; letter-spacing:.2em; text-transform:uppercase; color:#7a7a7a; }
.phase-hd h3 { font-family:Georgia,serif; font-size:13pt; font-weight:normal; margin:1mm 0 1.2mm; text-transform:none; letter-spacing:0; color:#000; }
.phase-hd .g { font-size:8pt; color:#4a4a4a; line-height:1.4; }
`;

function renderCard(t) {
  const blocking = t.blocking ? '<span class="blk">blocking</span>' : '';
  const steps = t.steps.map(esc).join(' &rarr; ');
  return `
<div class="card">
  <div class="hd">
    <div class="cid">${esc(t.id)}</div>
    <div class="cmeta">${esc(t.phase)} &middot; ${esc(t.kind)}${blocking}</div>
  </div>
  <h5>${esc(t.title)}</h5>
  <div class="row"><div class="k">files</div><div class="v f">${t.files.map(esc).join(' &middot; ')}</div></div>
  <div class="row"><div class="k">load</div><div class="v n">${t.load.map(esc).join(' &middot; ')}</div></div>
  <div class="row"><div class="k">do</div><div class="v">${steps}</div></div>
  <div class="row"><div class="k">done</div><div class="v">${t.done.map(esc).join('; ')}</div></div>
  <div class="row"><div class="k">never</div><div class="v n">${esc(t.dont)}</div></div>
</div>`;
}

const PHASE_META = {
  'PH-0': ['Decisions and spikes', 'Exit: a merchant account exists, authenticated mail reaches an inbox, one priced call per tier, brand facts written by a human. Work from PH-0.md — every artifact already has a template.'],
  'PH-1': ['Foundation', 'Exit: one agent task runs end to end, is costed, is audited, and a second organisation sees nothing.'],
  'PH-2': ['Marketing intelligence', 'Exit: one sentence becomes a plan with tasks, cost, approvals and metrics, reviewed and approved by a human.'],
  'PH-3': ['Acquisition', 'Exit: 10 real approved emails delivered, 2 replies classified, 1 reply answered, 1 opt-out suppressed.'],
  'PH-4': ['Conversation and revenue', 'Exit: demo booked in both calendars, checkout paid, webhook verified, customer and onboarding created.'],
  'PH-5': ['Measurement and learning', 'Exit: cost per won customer computed from real money, split by cost line.'],
  'PH-6': ['Scale and hardening', 'Exit: two tenants isolated under audit, a restore drill timed, a new role added in under a day.'],
};

function renderCards() {
  let html = '';
  let last = null;
  for (const t of TASKS) {
    if (t.phase !== last) {
      const [name, gate] = PHASE_META[t.phase];
      const count = TASKS.filter(x => x.phase === t.phase).length;
      html += `<div class="phase-hd"><div class="e">${t.phase} &middot; ${count} tasks</div>
        <h3>${esc(name)}</h3><div class="g">${esc(gate)}</div></div>`;
      last = t.phase;
    }
    html += renderCard(t);
  }
  return html;
}

function resolveIncludes(html) {
  return html.replace(/\{\{INCLUDE:([^}]+)\}\}/g, (_, rel) => {
    const p = path.join(WS, rel.trim());
    if (!fs.existsSync(p)) throw new Error('Missing include: ' + rel);
    return esc(fs.readFileSync(p, 'utf8').replace(/\r\n/g, '\n').replace(/\s+$/, ''));
  }).replace(/\{\{CARDS\}\}/g, () => renderCards());
}

function readPackParts() {
  return fs.readdirSync(PACK).filter(f => f.endsWith('.html')).sort()
    .map(f => resolveIncludes(fs.readFileSync(path.join(PACK, f), 'utf8')));
}

const FOOTER = `<div style="width:100%;font-family:'Segoe UI',Arial,sans-serif;font-size:6.4px;color:#7a7a7a;padding:0 16mm;display:flex;justify-content:space-between;align-items:flex-end;letter-spacing:0.09em;text-transform:uppercase;">
  <span>AI-MOS &middot; Build Pack &middot; BP-001-BP</span>
  <span>Open this, not the blueprint</span>
  <span><span class="pageNumber"></span> / <span class="totalPages"></span></span>
</div>`;

(async () => {
  const style = masterStyle();
  const parts = readPackParts();
  const coverPart = parts[0];
  const bodyParts = parts.slice(1);

  fs.mkdirSync(TMP, { recursive: true });

  const coverHtml = `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>AI-MOS Build Pack</title>
<style>${style}
${PACK_CSS}
@page { size: A4; margin: 0; }
html, body { margin:0; padding:0; }
</style></head><body>${coverPart}</body></html>`;

  const bodyHtml = `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>AI-MOS Build Pack</title>
<style>${style}
${PACK_CSS}
</style></head><body>
${bodyParts.join('\n')}
</body></html>`;

  fs.writeFileSync(path.join(TMP, 'cover.html'), coverHtml, 'utf8');
  fs.writeFileSync(path.join(TMP, 'body.html'), bodyHtml, 'utf8');

  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--font-render-hinting=none'],
  });
  const page = await browser.newPage();
  await page.emulateMediaType('print');

  await page.goto('file:///' + path.join(TMP, 'cover.html').replace(/\\/g, '/'), { waitUntil: 'load' });
  const coverPdf = await page.pdf({ format: 'A4', printBackground: true, margin: { top: 0, right: 0, bottom: 0, left: 0 } });
  fs.writeFileSync(path.join(TMP, 'cover.pdf'), coverPdf);

  await page.goto('file:///' + path.join(TMP, 'body.html').replace(/\\/g, '/'), { waitUntil: 'load' });
  const bodyPdf = await page.pdf({
    format: 'A4', printBackground: true, displayHeaderFooter: true,
    headerTemplate: '<div></div>', footerTemplate: FOOTER,
    margin: { top: '20mm', right: '16mm', bottom: '18mm', left: '16mm' },
  });
  fs.writeFileSync(path.join(TMP, 'body.pdf'), bodyPdf);

  const merged = await PDFDocument.create();
  for (const f of ['cover.pdf', 'body.pdf']) {
    const doc = await PDFDocument.load(fs.readFileSync(path.join(TMP, f)));
    (await merged.copyPages(doc, doc.getPageIndices())).forEach(p => merged.addPage(p));
  }
  merged.setTitle('AI-MOS — Build Pack');
  merged.setAuthor('AI-MOS Programme');
  merged.setSubject('Low-token developer companion to AI-MOS-BP-001');
  fs.writeFileSync(OUT, await merged.save());

  await browser.close();
  console.log('WROTE ' + OUT);
  console.log('PAGES ' + merged.getPageCount());
  console.log('CARDS ' + TASKS.length);
})();
