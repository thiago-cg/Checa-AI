/* Apresentação: cada slide é uma cena do vídeo, parada no estado assentado (função pura de t).
   Teclas: ←/→ (ou PageUp/PageDown, espaço), Home/End, N = notas, F = tela cheia. Clique: metade esquerda volta, direita avança. */
(function () {
  const stage = document.getElementById('stage');
  const notes = document.getElementById('notes');
  const count = document.getElementById('count');
  let idx = 0;

  // escala o palco de 1920×1080 para a janela, centralizado (letterbox)
  function fit() {
    const s = Math.min(innerWidth / 1920, innerHeight / 1080);
    const x = (innerWidth - 1920 * s) / 2, y = (innerHeight - 1080 * s) / 2;
    stage.style.transform = `translate(${x}px, ${y}px) scale(${s})`;
  }

  function show(n) {
    const scenes = window.SCENES;
    idx = Math.max(0, Math.min(scenes.length - 1, n));
    const sc = scenes[idx];
    // 0,7 s antes do fim da cena: tudo já entrou e o fade de saída ainda não começou
    window.renderAt(sc.start + sc.dur - 0.7);
    count.textContent = `${idx + 1} / ${scenes.length}`;
    notes.textContent = window.NOTES[sc.id] || '';
    history.replaceState(null, '', '#' + (idx + 1));
  }

  addEventListener('keydown', (e) => {
    const k = e.key;
    if (k === 'ArrowRight' || k === 'ArrowDown' || k === 'PageDown' || k === ' ') { e.preventDefault(); show(idx + 1); }
    else if (k === 'ArrowLeft' || k === 'ArrowUp' || k === 'PageUp') { e.preventDefault(); show(idx - 1); }
    else if (k === 'Home') show(0);
    else if (k === 'End') show(window.SCENES.length - 1);
    else if (k === 'n' || k === 'N') notes.classList.toggle('on');
    else if (k === 'f' || k === 'F') {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    }
  });

  addEventListener('click', (e) => show(e.clientX > innerWidth / 2 ? idx + 1 : idx - 1));
  addEventListener('resize', fit);
  addEventListener('hashchange', () => {
    const n = parseInt(location.hash.slice(1), 10);
    if (!isNaN(n) && n - 1 !== idx) show(n - 1);
  });

  fit();
  window.__ready.then(() => {
    const n = parseInt(location.hash.slice(1), 10);
    show(isNaN(n) ? 0 : n - 1);
  });
})();
