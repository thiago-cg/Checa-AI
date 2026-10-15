# work/ — como reconstruir o vídeo

Fontes: `narration.json` (roteiro; `s` = grafia fonética p/ a voz), `index.html` = `p1/p2/p3.html` (`assemble.py`),
`style.css`, `build.js` (conteúdo gerado), `engine.js` (todo frame é função pura de t), `scenes.js`, `timing.js/json`.

Pipeline (Windows, Edge + ffmpeg + Python/numpy + Node com `puppeteer-core` instalado em `$NODE_SP/node`):

    powershell -File tts.ps1 -Rate 2          # voz Microsoft Maria (pt-BR) -> audio/*.wav (uma frase por arquivo)
    python3 build_timing.py                   # timing.json/js + narration.npy
    python3 build_audio.py                    # música + efeitos + mix.wav (ducking sob a voz)
    node poster.js ../brag.jpg                # pôster sem legenda
    node render.js 4 ../brag.jpg              # 4 navegadores -> seg/seg_k.mp4 (frame 0 = pôster)
    bash finalize.sh                          # concat + mux -> ../brag.mp4
    node shots.js <dir> hook:e4 decisao:s6@3/10 ...   # stills de revisão (cena:cue)

Removidos para poupar espaço (regeneráveis): `audio/*.wav`, `seg/`, `mix.wav`, `narration.wav/.npy`, `video_all.mp4`.
`narration.m4a` = trilha de voz isolada.
