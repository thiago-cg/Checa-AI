// uso: node shots.js outDir t1 t2 ...   (t em segundos globais; "id:lt" também vale: ex. decisao:30)
const path = require('path');
const fs = require('fs');
const { createRequire } = require('module');
const SP = process.env.NODE_SP;
const puppeteer = createRequire(path.join(SP, 'node', 'x.js'))('puppeteer-core');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
(async () => {
  const out = process.argv[2]; fs.mkdirSync(out, { recursive: true });
  const args = process.argv.slice(3);
  const browser = await puppeteer.launch({ executablePath: EDGE, headless: 'new', args: ['--no-sandbox', '--force-device-scale-factor=1', '--hide-scrollbars'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  const errs = [];
  page.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await page.goto('file:///' + path.join(__dirname, 'index.html').replace(/\\/g, '/'));
  await new Promise(r=>setTimeout(r,500));
  if (errs.length) { console.log('LOAD ERRORS:\n' + errs.join('\n')); }
  await page.evaluate('window.__ready');
  for (const a of args) {
    let t;
    if (a.includes(':')) {
      const [id, lt] = a.split(':');
      t = await page.evaluate((id, lt) => { const s = window.SCENES.find((x) => x.id === id); return s.start + (/^[se][0-9]/.test(lt) ? window.cue(s, lt) : parseFloat(lt)); }, id, lt);
    } else t = parseFloat(a);
    await page.evaluate((t) => window.renderAt(t), t);
    const name = a.replace(/[:+@\/]/g, '_');
    await page.screenshot({ path: path.join(out, name + '.png') });
    console.log('shot', a, t.toFixed(2));
  }
  if (errs.length) console.log('ERRORS:\n' + errs.join('\n'));
  await browser.close();
})();
