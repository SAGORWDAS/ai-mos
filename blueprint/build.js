// AI-MOS blueprint renderer: HTML parts -> cover.pdf + body.pdf -> merged PDF
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
const { PDFDocument } = require('pdf-lib');

const ROOT = __dirname;
const PARTS = path.join(ROOT, 'parts');
const OUT = path.join(ROOT, '..', 'AI-MOS-Blueprint.pdf');
const TMP = path.join(ROOT, '.tmp');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

const MM = 96 / 25.4;

function readParts() {
  return fs.readdirSync(PARTS).filter(f => f.endsWith('.html')).sort();
}

const WS = path.join(__dirname, '..');

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function resolveIncludes(html) {
  return html.replace(/\{\{INCLUDE:([^}]+)\}\}/g, (_, rel) => {
    const p = path.join(WS, rel.trim());
    if (!fs.existsSync(p)) throw new Error('Missing include: ' + rel);
    const body = fs.readFileSync(p, 'utf8').replace(/\r\n/g, '\n').replace(/\s+$/, '');
    return escapeHtml(body);
  });
}

function buildHtml() {
  const files = readParts();
  const head = fs.readFileSync(path.join(PARTS, files[0]), 'utf8'); // 00-head.html
  const styleMatch = head.match(/<style>([\s\S]*?)<\/style>/);
  const style = styleMatch ? styleMatch[1] : '';
  const titleMatch = head.match(/<title>([\s\S]*?)<\/title>/);
  const title = titleMatch ? titleMatch[1] : 'AI-MOS';

  const coverFile = files.find(f => f.includes('01-cover'));
  const cover = fs.readFileSync(path.join(PARTS, coverFile), 'utf8');
  const bodyParts = files
    .slice(1)
    .filter(f => f !== coverFile && !f.startsWith('99-'))
    .map(f => resolveIncludes(fs.readFileSync(path.join(PARTS, f), 'utf8')));

  const coverHtml = `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>${title}</title>
<style>${style}
@page { size: A4; margin: 0; }
html, body { margin: 0; padding: 0; }
.cover { margin: 0 !important; width: 210mm !important; height: 297mm !important; padding: 24mm 20mm 0 !important; }
</style></head><body>${cover}</body></html>`;

  const bodyHtml = `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>${title}</title>
<style>${style}</style></head><body>
${bodyParts.join('\n')}
</body></html>`;

  fs.mkdirSync(TMP, { recursive: true });
  fs.writeFileSync(path.join(TMP, 'cover.html'), coverHtml, 'utf8');
  fs.writeFileSync(path.join(TMP, 'body.html'), bodyHtml, 'utf8');
  return { coverHtmlPath: path.join(TMP, 'cover.html'), bodyHtmlPath: path.join(TMP, 'body.html') };
}

const FOOTER = `<div style="width:100%;font-family:'Segoe UI',Arial,sans-serif;font-size:6.6px;color:#7a7a7a;padding:0 17mm;display:flex;justify-content:space-between;align-items:flex-end;letter-spacing:0.09em;text-transform:uppercase;">
  <span>AI-MOS &middot; Product &amp; Engineering Blueprint &middot; BP-001 v1.0</span>
  <span>Internal</span>
  <span><span class="pageNumber"></span> / <span class="totalPages"></span></span>
</div>`;

(async () => {
  const { coverHtmlPath, bodyHtmlPath } = buildHtml();
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--font-render-hinting=none'],
  });
  const page = await browser.newPage();
  await page.emulateMediaType('print');

  await page.goto('file:///' + coverHtmlPath.replace(/\\/g, '/'), { waitUntil: 'load' });
  const coverPdf = await page.pdf({ format: 'A4', printBackground: true, margin: { top: 0, right: 0, bottom: 0, left: 0 } });
  fs.writeFileSync(path.join(TMP, 'cover.pdf'), coverPdf);

  // QA screenshot of the cover
  await page.setViewport({ width: Math.round(210 * MM), height: Math.round(297 * MM), deviceScaleFactor: 2 });
  await page.screenshot({ path: path.join(TMP, 'qa-cover.png'), fullPage: false });

  await page.goto('file:///' + bodyHtmlPath.replace(/\\/g, '/'), { waitUntil: 'load' });
  const bodyPdf = await page.pdf({
    format: 'A4', printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: FOOTER,
    margin: { top: '21mm', right: '17mm', bottom: '19mm', left: '17mm' },
  });
  fs.writeFileSync(path.join(TMP, 'body.pdf'), bodyPdf);

  // QA screenshots of the first content screen
  await page.setViewport({ width: 880, height: 1180, deviceScaleFactor: 2 });
  await page.screenshot({ path: path.join(TMP, 'qa-body.png'), clip: { x: 0, y: 0, width: 880, height: 1180 } });

  const merged = await PDFDocument.create();
  for (const f of ['cover.pdf', 'body.pdf']) {
    const doc = await PDFDocument.load(fs.readFileSync(path.join(TMP, f)));
    const pages = await merged.copyPages(doc, doc.getPageIndices());
    pages.forEach(p => merged.addPage(p));
  }
  merged.setTitle('AI-MOS — Product & Engineering Blueprint');
  merged.setAuthor('AI-MOS Programme');
  merged.setSubject('Implementation baseline v1.0');
  merged.setCreator('AI-MOS blueprint renderer');
  const bytes = await merged.save();
  fs.writeFileSync(OUT, bytes);

  await browser.close();
  console.log('WROTE ' + OUT);
  console.log('PAGES ' + merged.getPageCount());
})();
