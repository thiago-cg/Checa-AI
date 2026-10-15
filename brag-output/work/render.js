// uso: node render.js <workers> [posterJpg]   — renderiza seg/seg_k.mp4 (vídeo sem áudio, 30 fps) em paralelo
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { createRequire } = require('module');
const SP = process.env.NODE_SP;
const puppeteer = createRequire(path.join(SP, 'node', 'x.js'))('puppeteer-core');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const FPS = 30;
const TAIL = 2.5; // cauda de áudio/fade final
const timing = JSON.parse(fs.readFileSync(path.join(__dirname, 'timing.json'), 'utf8'));
const TOTAL_FRAMES = Math.round((timing.total + TAIL) * FPS);
const NW = parseInt(process.argv[2] || '4', 10);
const poster = process.argv[3] && fs.existsSync(process.argv[3]) ? fs.readFileSync(process.argv[3]) : null;
const only = process.argv[4] ? process.argv[4].split(',').map(Number) : null; // re-render só alguns segmentos
fs.mkdirSync(path.join(__dirname, 'seg'), { recursive: true });

async function worker(k, a, b) {
  const out = path.join(__dirname, 'seg', `seg_${k}.mp4`);
  const browser = await puppeteer.launch({ executablePath: EDGE, headless: 'new', userDataDir: path.join(process.env.NODE_SP, 'prof' + k), args: ['--no-sandbox', '--force-device-scale-factor=1', '--hide-scrollbars'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto('file:///' + path.join(__dirname, 'index.html').replace(/\\/g, '/'));
  await page.evaluate('window.__ready');
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p', '-c:v', 'libx264', '-preset', 'medium', '-crf', '17',
    '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-r', String(FPS), out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((res) => ff.on('close', res));
  const t0 = Date.now();
  for (let i = a; i < b; i++) {
    let buf;
    if (i === 0 && poster) buf = poster;
    else {
      await page.evaluate((t) => window.renderAt(t), i / FPS);
      buf = await page.screenshot({ type: 'jpeg', quality: 93, optimizeForSpeed: true });
    }
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
    if ((i - a) % 200 === 0) console.log(`w${k} ${i - a}/${b - a}  ${(((i - a + 1) / ((Date.now() - t0) / 1000))).toFixed(1)} fps`);
  }
  ff.stdin.end();
  await done;
  await browser.close();
  console.log(`w${k} OK frames ${a}-${b}`);
}

(async () => {
  const per = Math.ceil(TOTAL_FRAMES / NW);
  const jobs = [];
  for (let k = 0; k < NW; k++) {
    if (only && !only.includes(k)) continue;
    jobs.push(worker(k, k * per, Math.min(TOTAL_FRAMES, (k + 1) * per)));
  }
  await Promise.all(jobs);
  console.log('ALL DONE total frames', TOTAL_FRAMES);
})().catch((e) => { console.error(e); process.exit(1); });
