// uso: node poster.js out.jpg [t]  — pôster 1920x1080 sem legenda no melhor frame assentado
const path = require('path');
const fs = require('fs');
const { createRequire } = require('module');
const SP = process.env.NODE_SP;
const puppeteer = createRequire(path.join(SP, 'node', 'x.js'))('puppeteer-core');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
(async () => {
  const browser = await puppeteer.launch({ executablePath: EDGE, headless: 'new', args: ['--no-sandbox', '--force-device-scale-factor=1', '--hide-scrollbars'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto('file:///' + path.join(__dirname, 'index.html').replace(/\\/g, '/'));
  await page.evaluate('window.__ready');
  const t = process.argv[3] ? parseFloat(process.argv[3]) : await page.evaluate(() => { const s = window.SCENES.find((x) => x.id === 'hook'); return s.start + window.cue(s, 'e4') - 0.3; });
  await page.evaluate((t) => { window.renderAt(t); document.getElementById('sub').style.display = 'none'; document.getElementById('barwrap').style.display = 'none'; }, t);
  await page.screenshot({ path: process.argv[2], type: 'jpeg', quality: 95 });
  console.log('poster at', t.toFixed(2));
  await browser.close();
})();
