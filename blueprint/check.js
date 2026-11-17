const p = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const targets = [
  { name: 'master', file: '.tmp/body.html', width: 665 },
  { name: 'pack', file: '.tmp-pack/body.html', width: 674 },
];

(async () => {
  const b = await p.launch({ executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', headless: 'new', args: ['--no-sandbox'] });
  for (const t of targets) {
    const target = path.join(__dirname, t.file);
    if (!fs.existsSync(target)) {
      console.log(t.name + ' SKIPPED (build it first: ' + (t.name === 'master' ? 'build.js' : 'build-pack.js') + ')');
      continue;
    }
    const pg = await b.newPage();
    await pg.setViewport({ width: t.width, height: 1000, deviceScaleFactor: 1 });
    await pg.goto('file:///' + target.replace(/\\/g, '/'));
    const r = await pg.evaluate(() => {
      const out = [];
      document.querySelectorAll('pre').forEach(el => {
        if (el.scrollWidth > el.clientWidth + 1) out.push({ k: 'pre', over: el.scrollWidth - el.clientWidth, t: el.textContent.trim().slice(0, 50).replace(/\s+/g, ' ') });
      });
      document.querySelectorAll('td,th,.card,.phase-hd').forEach(el => {
        if (el.scrollWidth > el.clientWidth + 1) out.push({ k: el.tagName + '.' + el.className, over: el.scrollWidth - el.clientWidth });
      });
      return out.slice(0, 12);
    });
    console.log(t.name + ' OVERFLOW ' + r.length);
    r.forEach(x => console.log('  ' + JSON.stringify(x)));
    await pg.close();
  }
  await b.close();
})();
