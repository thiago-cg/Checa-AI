/* Animações específicas por cena (funções puras de lt). */
(function () {
  const { lerp, prog, easeOut, easeIO } = U;
  const fmt = (v, d = 1) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(d).replace('.', ',');

  DRAW.clusters = (lt, sc) => {
    for (const c of CL.chips) {
      const p = easeIO(prog(lt, cue(sc, c.tm), 1.3));
      c.el.style.left = lerp(c.x0, c.x1, p).toFixed(1) + 'px';
      c.el.style.top = lerp(c.y0, c.y1, p).toFixed(1) + 'px';
      c.el.style.borderColor = p > 0.7 ? `rgba(${c.c},.75)` : '';
    }
  };

  DRAW.decisao = (lt, sc) => {
    const tA = cue(sc, 's6@1/10'), tB = cue(sc, 's6@5/10');
    let L = 0;
    if (lt >= tA) L = lerp(0, 1, easeOut(prog(lt, tA + 0.3, 0.9)));
    if (lt >= tB) L = lerp(1, 2, easeOut(prog(lt, tB + 0.3, 0.9)));
    const m = document.getElementById('marker');
    m.style.opacity = prog(lt, tA, 0.4).toFixed(3);
    m.style.left = (380 + L * (760 / 6)).toFixed(2) + 'px';
    const r = document.getElementById('readout');
    const second = lt >= tB + 0.3;
    r.style.opacity = prog(lt, tA + 0.9, 0.5).toFixed(3);
    r.innerHTML = second
      ? 'L = <b>+2,0</b> → p = <b>0,88</b> → <b style="color:var(--alta)">ALTA</b>'
      : 'L = <b>+1,0</b> &lt; τ → p = 0,73 → <b style="color:var(--media)">MÉDIA</b>';
  };

  DRAW.resultados = (lt, sc) => {
    for (const b of BARS) b.fill.style.width = (b.v * easeOut(prog(lt, cue(sc, b.t0), 1.2))).toFixed(2) + '%';
    const e = easeOut(prog(lt, cue(sc, 's2+0.4'), 1.1));
    document.getElementById('seg-i').style.width = (15 / 18 * 100 * e).toFixed(2) + '%';
    document.getElementById('seg-m').style.width = (3 / 18 * 100 * e).toFixed(2) + '%';
  };
})();
