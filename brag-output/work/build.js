/* Conteúdo gerado em tempo de carga (antes do motor ler os .rv). */
(function () {
  const h = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstChild; };
  const $ = (s) => document.querySelector(s);

  // ---------- VISÃO GERAL ----------
  (function () {
    const body = $('#visao-body');
    const N = [
      ['Recebimento', 'regras: tempo, rumor, sátira', 'code'],
      ['Afirmações', 'LLM → JSON validado', 'llm'],
      ['Busca aberta', 'SerpAPI · 2 consultas', 'code'],
      ['Leitura', 'deep crawl + extração', 'code'],
      ['Independência', 'clusters de fontes', 'code'],
      ['Juiz', '4 classes + citação', 'llm'],
      ['Agente crítico', 'para ou reescreve', 'llm'],
      ['Decisão', 'log-odds · limiar', 'code'],
      ['Travas', 'só rebaixam', 'code'],
      ['Relatório', 'templates neutros', 'code'],
    ];
    const FR = [0, 1, 2, 3, 4, 5, 6, 7, 7.7, 8.5].map((x) => x / 9.4);
    const W = 300, H = 150, GX = 345, Y0 = 14, Y1 = 306;
    const pos = (k) => (k < 5 ? { x: k * GX, y: Y0 } : { x: (4 - (k - 5)) * GX, y: Y1 });
    let svg = '<svg class="abs" width="1680" height="690" style="left:0;top:0" xmlns="http://www.w3.org/2000/svg">';
    N.forEach((n, k) => {
      const p = pos(k);
      const at = `s2@${FR[k].toFixed(3)}/1`;
      const gl = n[2] === 'llm' ? ' gl pl" data-pat="s3+0.6" style="--gc:rgba(167,139,250,.75);' : '" style="';
      body.appendChild(h(`<div class="node ${n[2]} rv${gl}left:${p.x}px;top:${p.y}px;width:${W}px;height:${H}px" data-at="${at}" data-dy="14">
        <div class="nn">ETAPA ${k + 1}</div><div class="nt">${n[0]}</div><div class="nd">${n[1]}</div></div>`));
      if (k < 9) {
        const q = pos(k + 1), at2 = `s2@${FR[k + 1].toFixed(3)}/1`;
        let d;
        if (k < 4) d = `M${p.x + W + 6} ${p.y + 75} H${q.x - 8}`;
        else if (k === 4) d = `M${p.x + 150} ${p.y + H + 6} V${q.y - 8}`;
        else d = `M${p.x - 6} ${p.y + 75} H${q.x + W + 8}`;
        svg += `<path class="dr" data-at="${at2}-0.25" data-d="0.4" d="${d}" stroke="#9aa8c2" stroke-width="3" fill="none" marker-end="url(#ah)"/>`;
      }
    });
    // laço: agente crítico (k=6) → busca (k=2)
    const a = pos(6), b = pos(2);
    svg += `<path class="dr" data-at="s2@${(FR[6] + 0.03).toFixed(3)}/1" data-d="0.9" d="M${a.x + 150} ${a.y - 6} C${a.x + 150} ${a.y - 76}, ${b.x + 150} ${b.y + H + 70}, ${b.x + 150} ${b.y + H + 8}" stroke="#a78bfa" stroke-width="3" stroke-dasharray="9 9" fill="none" marker-end="url(#ahv)"/>`;
    svg += '</svg>';
    body.insertBefore(h(svg), body.firstChild);
    body.appendChild(h(`<div class="abs rv" data-at="s2@${(FR[6] + 0.08).toFixed(3)}/1" style="left:${b.x + 70}px;top:${b.y + H + 104}px;font-size:21px;color:var(--llm);font-weight:700">nova onda de busca</div>`));
    body.appendChild(h(`<div class="row rv" data-at="s3" style="position:absolute;left:0;top:560px;width:1680px;gap:44px;justify-content:center">
      <span class="tag code">código determinístico · 7 etapas</span><span class="tag llm">modelo de linguagem · 3 etapas</span></div>`));
  })();

  // ---------- BUSCA: candidatos ----------
  (function () {
    const list = $('#cand-list');
    const T = [['checagem', 70], ['geral', 88], ['checagem', 55], ['geral', 76], ['geral', 62], ['checagem', 82]];
    T.forEach((t, k) => {
      const ch = t[0] === 'checagem';
      list.appendChild(h(`<div class="row rv" data-at="s2+${(1.3 + k * 0.28).toFixed(2)}" data-dy="8" style="gap:14px;height:42px;margin-bottom:6px">
        <span class="chip" style="width:112px;justify-content:center;font-size:16px;padding:3px 0;${ch ? 'color:var(--sustenta);border-color:rgba(94,234,212,.5)' : 'color:#cbd5e1'}">${t[0]}</span>
        <div style="flex:1"><div style="height:11px;border-radius:6px;background:rgba(203,213,225,.28);width:${t[1]}%"></div><div style="height:8px;border-radius:5px;background:rgba(148,163,184,.16);width:${t[1] - 22}%;margin-top:7px"></div></div></div>`));
    });
    const n = $('#cand-n'); n.className += ' cnt'; n.dataset.at = 's2+1.3'; n.dataset.d = '2'; n.dataset.from = '0'; n.dataset.to = '24'; n.dataset.suf = ' URLs';
  })();

  // ---------- CLUSTERS ----------
  (function () {
    const body = $('#cl-body');
    const G = [
      { t: 'mesma agência de notícias', s: 'Reuters, AFP, Estadão Conteúdo…', n: 4, c: '56,189,248' },
      { t: 'mesmo grupo econômico', s: 'domínio-base em comum', n: 3, c: '167,139,250' },
      { t: 'corpo quase idêntico', s: 'trechos de 5 palavras ≥ 80%', n: 2, c: '251,191,36' },
      { t: 'fonte independente', s: 'texto próprio', n: 1, c: '94,234,212' },
    ];
    const GW = 380, GAP = (1680 - 4 * GW) / 3, GY = 118, GH = 262;
    window.CL = { chips: [], tmove: 's2+0.5' };
    let idx = 0;
    G.forEach((g, gi) => {
      const gx = gi * (GW + GAP);
      const F = [0.14, 0.34, 0.56, 0.78][gi];
      body.appendChild(h(`<div class="panel rv" data-at="s2@${(F - 0.07).toFixed(2)}/1" style="position:absolute;left:${gx}px;top:${GY}px;width:${GW}px;height:${GH}px;border-color:rgba(${g.c},.55);background:rgba(${g.c},.06)">
        <div style="padding:14px 20px 0"><div style="font-size:22px;font-weight:700;color:rgb(${g.c})">${g.t}</div><div class="mute" style="font-size:17px;margin-top:4px;line-height:1.25">${g.s}</div></div></div>`));
      body.appendChild(h(`<div class="abs rv" data-at="s3@${gi}/4" style="left:${gx}px;top:${GY + GH + 18}px;width:${GW}px;text-align:center"><span class="pill" style="font-size:24px;padding:8px 26px;background:rgba(${g.c},.16);border:1.5px solid rgba(${g.c},.6);color:rgb(${g.c})">1 voto</span></div>`));
      for (let k = 0; k < g.n; k++) {
        const i = idx++;
        const x0 = i * 171, y0 = 52;
        const x1 = gx + 22 + (k % 2) * 156, y1 = GY + 102 + Math.floor(k / 2) * 64;
        const el = h(`<div class="abs chip rv" data-at="s1@${(i / 10 * 0.9).toFixed(2)}/1" data-dy="10" style="left:${x0}px;top:${y0}px;width:140px;height:50px;justify-content:center;font-size:19px">Matéria ${i + 1}</div>`);
        body.appendChild(el);
        window.CL.chips.push({ el, x0, y0, x1, y1, c: g.c, tm: `s2@${F.toFixed(2)}/1` });
      }
    });
  })();

  // ---------- DECISÃO: pesos + eixo ----------
  (function () {
    const rows = $('#wt-rows');
    const W = [
      ['Agência de checagem curada', 1.0, '1,0', '56,189,248'],
      ['Órgão público · site muito acessado', 0.6, '0,6', '148,163,184'],
      ['Rede social · plataforma', 0.45, '0,45', '148,163,184'],
      ['Site pouco acessado', 0.3, '0,3', '148,163,184'],
      ['Selo de checagem aplicável', 1.5, '1,5', '251,191,36'],
    ];
    W.forEach((w, k) => {
      rows.appendChild(h(`<div class="row rv" data-at="s3@${(k + 0.2) / 5.3}/1" data-dy="8" style="height:54px;gap:16px">
        <div style="width:300px;font-size:21px;line-height:1.15;color:#dbe4f5">${w[0]}</div>
        <div style="flex:1;height:20px;border-radius:10px;background:rgba(148,163,184,.12)"><div style="height:100%;width:${(w[1] / 1.5 * 100).toFixed(1)}%;border-radius:10px;background:rgb(${w[3]});opacity:.85"></div></div>
        <div class="mono" style="width:56px;text-align:right;font-size:24px;color:rgb(${w[3]});font-weight:700">${w[2]}</div></div>`));
    });
    const ax = $('#axis'), U = 760 / 6;
    for (let i = -3; i <= 3; i++) {
      const x = (i + 3) * U;
      ax.appendChild(h(`<div class="abs" style="left:${x - 1}px;top:76px;width:2px;height:16px;background:rgba(148,163,184,.55)"></div>`));
      ax.appendChild(h(`<div class="abs mono" style="left:${x - 24}px;top:124px;width:48px;text-align:center;font-size:19px;color:var(--mute)">${i > 0 ? '+' + i : i < 0 ? '−' + Math.abs(i) : '0'}</div>`));
    }
  })();

  // ---------- RELATÓRIO: recibo ----------
  (function () {
    const rows = $('#rec-rows');
    const R = [['recebimento', 'ok'], ['afirmacoes', 'ok'], ['base-checagem', 'pulada'], ['descoberta', 'ok'], ['deep-crawl', 'parcial'], ['corroboracao', 'ok'], ['avaliador', 'ok'], ['juiz', 'ok'], ['agregacao', 'ok']];
    const C = { ok: '52,211,153', parcial: '251,191,36', falha: '251,113,133', pulada: '148,163,184' };
    R.forEach((r, k) => {
      rows.appendChild(h(`<div class="row rv" data-at="s3@${(k + 0.1) / 9.4}/1" data-dy="8" style="height:50px;justify-content:space-between;border-bottom:1px solid rgba(148,163,184,.14)">
        <span class="mono" style="font-size:23px">${r[0]}</span>
        <span class="pill" style="font-size:17px;min-width:96px;text-align:center;background:rgba(${C[r[1]]},.14);border:1.5px solid rgba(${C[r[1]]},.55);color:rgb(${C[r[1]]})">${r[1]}</span></div>`));
    });
  })();

  // ---------- RESULTADOS: barras ----------
  (function () {
    const box = $('#bars');
    window.BARS = [];
    const B = [['Controle', 59.1, '26 de 44'], ['Planejador de busca', 63.6, '28 de 44'], ['site: no Google orgânico', 63.6, '28 de 44'], ['Todas combinadas', 62.2, '28 de 45']];
    B.forEach((b, k) => {
      const el = h(`<div class="row rv" data-at="s1+${(0.5 + k * 0.45).toFixed(2)}" data-dy="10" style="height:78px;gap:18px">
        <div style="width:300px"><div style="font-size:24px;font-weight:650">${b[0]}</div><div class="lab" style="font-size:17px">${b[2]} casos</div></div>
        <div style="flex:1;height:34px;border-radius:17px;background:rgba(148,163,184,.12);position:relative;overflow:hidden"><div class="bfill" style="position:absolute;left:0;top:0;bottom:0;width:0;border-radius:17px;background:linear-gradient(90deg,#38bdf8,#818cf8)"></div></div>
        <span class="mono cnt" data-at="s1+${(0.9 + k * 0.45).toFixed(2)}" data-d="1.2" data-from="0" data-to="${b[1]}" data-dec="1" data-suf="%" style="width:120px;font-size:30px;font-weight:700;text-align:right">0%</span></div>`);
      box.appendChild(el);
      window.BARS.push({ el, fill: el.querySelector('.bfill'), v: b[1], t0: `s1+${(0.9 + k * 0.45).toFixed(2)}` });
    });
    box.appendChild(h(`<div class="rv" data-at="s1+2.9" style="margin-top:6px;font-size:22px;color:var(--baixa);font-weight:650">✓ erro grave: 0 em todas as variantes</div>`));
  })();
})();
