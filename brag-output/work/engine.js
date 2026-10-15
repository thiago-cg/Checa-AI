/* Motor: todo frame é função pura de t (segundos globais). */
(function () {
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const prog = (t, t0, d) => clamp((t - t0) / (d || 0.0001));
  const easeOut = (x) => 1 - Math.pow(1 - clamp(x), 3);
  const easeIO = (x) => { x = clamp(x); return x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
  const lerp = (a, b, p) => a + (b - a) * p;
  window.U = { clamp, prog, easeOut, easeIO, lerp };

  const T = window.TIMING;
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const DRAW = (window.DRAW = {});

  // ---- cues: 12.5 | s3 | s3+.4 | s3@2/10 | e3 | e3-.2
  function cue(sc, v) {
    if (typeof v === 'number') return v;
    v = String(v).trim();
    if (/^-?[\d.]+$/.test(v)) return parseFloat(v);
    const m = /^([se])(\d+)(?:@([\d.]+)\/([\d.]+))?([+-][\d.]+)?$/.exec(v);
    if (!m) throw new Error('cue inválido: ' + v + ' em ' + sc.id);
    const s = sc.sentences[parseInt(m[2], 10) - 1];
    if (!s) throw new Error('frase inexistente: ' + v + ' em ' + sc.id);
    let t = m[1] === 'e' ? s.t1 : s.t0;
    if (m[3] !== undefined) t = s.t0 + (s.t1 - s.t0) * (parseFloat(m[3]) / parseFloat(m[4]));
    if (m[5]) t += parseFloat(m[5]);
    return t;
  }
  window.cue = cue;

  const scenes = T.scenes.map((sc) => ({ ...sc, el: document.getElementById('sc-' + sc.id) }));
  window.SCENES = scenes;

  // ---- prepara elementos
  function prep(sc) {
    const root = sc.el;
    sc.rv = $$('.rv', root).map((el) => ({
      el, t0: cue(sc, el.dataset.at || '0'), d: parseFloat(el.dataset.d || '0.6'),
      dy: parseFloat(el.dataset.dy ?? '16'), dx: parseFloat(el.dataset.dx || '0'),
      s0: parseFloat(el.dataset.s || '1'),
      out: el.dataset.out ? cue(sc, el.dataset.out) : null, od: parseFloat(el.dataset.od || '0.5'),
    }));
    sc.ty = $$('.ty', root).map((el) => {
      const chars = [];
      const walk = (node) => {
        Array.from(node.childNodes).forEach((n) => {
          if (n.nodeType === 3) {
            const f = document.createDocumentFragment();
            for (const ch of n.textContent) {
              const sp = document.createElement('span'); sp.textContent = ch; sp.className = 'c';
              sp.style.visibility = 'hidden'; f.appendChild(sp); chars.push(sp);
            }
            n.replaceWith(f);
          } else if (n.nodeType === 1) walk(n);
        });
      };
      walk(el);
      return { el, chars, t0: cue(sc, el.dataset.at || '0'), cps: parseFloat(el.dataset.cps || '30'), shown: -1 };
    });
    sc.ul = $$('.ul', root).map((el) => ({ el, t0: cue(sc, el.dataset.at || '0'), d: parseFloat(el.dataset.d || '0.5') }));
    sc.dr = $$('.dr', root).map((el) => {
      let len = 300; try { len = el.getTotalLength(); } catch (e) {}
      el.style.strokeDasharray = len; return { el, len, t0: cue(sc, el.dataset.at || '0'), d: parseFloat(el.dataset.d || '0.8') };
    });
    sc.cnt = $$('.cnt', root).map((el) => ({ el, t0: cue(sc, el.dataset.at || '0'), d: parseFloat(el.dataset.d || '1'),
      from: parseFloat(el.dataset.from || '0'), to: parseFloat(el.dataset.to || '0'), dec: parseInt(el.dataset.dec || '0', 10), pre: el.dataset.pre || '', suf: el.dataset.suf || '' }));
    sc.pl = $$('.pl', root).map((el) => ({ el, t0: cue(sc, el.dataset.pat || '0'), d: parseFloat(el.dataset.pd || '1.4') }));
  }
  scenes.forEach(prep);

  const sub = document.getElementById('sub');
  const subtxt = document.getElementById('subtxt');
  const bar = document.getElementById('bar');
  const bg = document.getElementById('bg');
  const FADE = 0.55;

  function drawScene(sc, lt) {
    for (const r of sc.rv) {
      let p = easeOut(prog(lt, r.t0, r.d));
      let o = p;
      if (r.out !== null) o *= 1 - easeOut(prog(lt, r.out, r.od));
      const el = r.el;
      el.style.opacity = o.toFixed(3);
      const k = 1 - p;
      const sc_ = r.s0 !== 1 ? ` scale(${(1 + (r.s0 - 1) * k).toFixed(4)})` : '';
      el.style.transform = (r.dy || r.dx || sc_) ? `translate(${(r.dx * k).toFixed(2)}px, ${(r.dy * k).toFixed(2)}px)${sc_}` : '';
    }
    for (const y of sc.ty) {
      const n = Math.max(0, Math.floor((lt - y.t0) * y.cps));
      if (n !== y.shown) {
        y.shown = n;
        y.chars.forEach((c, i) => { c.style.visibility = i < n ? 'visible' : 'hidden'; c.classList.toggle('cur', i === n - 1 && n < y.chars.length); });
      }
    }
    for (const u of sc.ul) u.el.style.setProperty('--p', easeOut(prog(lt, u.t0, u.d)).toFixed(3));
    for (const d of sc.dr) d.el.style.strokeDashoffset = (d.len * (1 - easeOut(prog(lt, d.t0, d.d)))).toFixed(1);
    for (const c of sc.cnt) {
      const v = lerp(c.from, c.to, easeOut(prog(lt, c.t0, c.d)));
      c.el.textContent = c.pre + v.toFixed(c.dec).replace('.', ',') + c.suf;
    }
    for (const g of sc.pl) {
      const x = prog(lt, g.t0, g.d); const v = x <= 0 || x >= 1 ? 0 : Math.sin(Math.PI * x);
      g.el.style.setProperty('--glow', v.toFixed(3));
    }
    if (DRAW[sc.id]) DRAW[sc.id](lt, sc);
  }

  window.renderAt = function (t) {
    t = clamp(t, 0, T.total - 0.001);
    bg.style.setProperty('--bx1', (20 + 8 * Math.sin(t / 9)).toFixed(2) + '%');
    bg.style.setProperty('--by1', (10 + 6 * Math.cos(t / 11)).toFixed(2) + '%');
    bg.style.setProperty('--bx2', (85 + 7 * Math.cos(t / 10)).toFixed(2) + '%');
    bg.style.setProperty('--by2', (90 + 5 * Math.sin(t / 8)).toFixed(2) + '%');
    let cur = null;
    for (const sc of scenes) {
      const lt = t - sc.start;
      if (lt >= 0 && lt < sc.dur) {
        cur = sc;
        const o = clamp(lt / FADE) * clamp((sc.dur - lt) / FADE);
        sc.el.style.display = 'block';
        sc.el.style.opacity = o.toFixed(3);
        drawScene(sc, lt);
      } else sc.el.style.display = 'none';
    }
    // legenda (frase corrente) com fade curto
    let txt = '', so = 0;
    if (cur) {
      const lt = t - cur.start;
      for (const s of cur.sentences) {
        const o = clamp((lt - (s.t0 - 0.12)) / 0.16) * clamp(((s.t1 + 0.28) - lt) / 0.2);
        if (o > 0) { txt = s.text; so = o; break; }
      }
    }
    if (subtxt.dataset.cur !== txt) { subtxt.dataset.cur = txt; subtxt.textContent = txt; }
    sub.style.opacity = so.toFixed(3);
    bar.style.width = (100 * t / T.total).toFixed(3) + '%';
  };

  window.__ready = (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(() => true);
})();
