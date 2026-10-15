# brag-plan — CrossCheckBR (versão técnica para feira de ciências)

**Ângulo.** Um tour técnico, passo a passo, de como o sistema chega a uma *propensão* à desinformação — sem veredito binário. O fio condutor é o caso “Café cura câncer”, e cada cena mostra o componente real do pipeline (`factcheck_mvp/`).

**Desvio deliberado do padrão do /brag-slim.** O padrão é ~20 s; aqui a duração é ditada pela narração, porque o pedido foi um vídeo *completo e didático* explicando todo o funcionamento: **8.0 min** (~7:57) + 2,5 s de cauda musical.

**Tom.** `polished` — sério, elegante, restrito; fades suaves (dip pelo fundo, sem sobreposição), holds longos, uma ideia por cena.

**Hook (0–16 s).** Mensagem encaminhada “Café cura câncer” → “Verdade ou mentira?” → nome do sistema + escala baixa/média/alta/indeterminada (frame do pôster).

**Destaques didáticos.** (1) *O LLM propõe, o código decide e confere* (juiz com citação verificada); (2) *1 cluster = 1 voto* e a conta do log-odds (1 fonte curada → média; 2 independentes → alta, p = 0,88); (3) *reprodutibilidade*: trace, cassetes, harness com holdout.

**Punchline.** “Não decide por você. Mostra as fontes, os pesos e o caminho.”

**Identidade visual.** Fundo azul-noite; azul `#38bdf8` = código determinístico, violeta `#a78bfa` = LLM; verde/âmbar/rosa/cinza = baixa/média/alta/indeterminada. Segoe UI Variable + Cascadia Mono. Legendas gravadas no vídeo (sala de feira é barulhenta).

**Áudio.** Narração pt-BR (voz sintética Microsoft Maria, SAPI) + pad ambiente em Lá menor (Am–F–C–G), plucks na pentatônica, efeitos (swells/pings/ticks) na mesma tonalidade, reverb comum, música com ducking sob a voz.

**Fidelidade.** Todos os números vêm do repositório: pesos/limiares de `decisao.py`, parâmetros de `config.py` (5 MB, 15 s, 2.500 chars, 0,90, 9 buscas), 13 agências/23 veículos do `catalogo.json`, 21.976 checagens do índice, resultados da Missão G em `eval/ITERACOES.md` (59,1–63,6%, 0 erros graves, 15/18 indeterminada), 1.226 testes. Exemplos de entrada/fontes/recibo são **ilustrativos** e estão rotulados assim; nenhuma execução real do pipeline é exibida.

## Storyboard

| # | cena | início | duração | conteúdo |
|---|---|---|---|---|
| 1 | hook | 0s | 17s | Hook — a mensagem “Café cura câncer”; revela o nome e a escala de propensão |
| 2 | principio | 17s | 23s | Princípio — propensão, não veredito; ausência de evidência ≠ evidência; LLM propõe, código decide |
| 3 | visao | 40s | 22s | Visão geral — as 10 etapas, código (azul) × LLM (roxo), laço do agente |
| 4 | recebimento | 63s | 25s | Etapa 1 · Recebimento — tipos de entrada, detectores (tempo, rumor, sátira, vago), janela temporal |
| 5 | afirmacoes | 88s | 33s | Etapa 2 · Afirmações — JSON atômico, núcleo × polaridade, validação e fallback |
| 6 | busca | 121s | 33s | Etapa 3 · Busca aberta — 2 consultas, rodízio de chaves, planejador, atalho do índice |
| 7 | leitura | 154s | 37s | Etapa 4 · Leitura — URL canônica, download seguro anti-SSRF, cascata de extração |
| 8 | clusters | 191s | 22s | Etapa 5 · Independência — 10 matérias → 4 clusters → 4 votos |
| 9 | juiz | 212s | 33s | Etapa 6 · Juiz — 4 classes + citação literal verificada pelo código |
| 10 | agente | 245s | 35s | Etapa 7 · Agente crítico — parar × nova onda; autoconsistência (3×) |
| 11 | decisao | 280s | 57s | Etapa 8 · Decisão — pesos, log-odds, limiar ln 3; 1 fonte = média, 2 = alta (88%) |
| 12 | travas | 336s | 36s | Etapa 9 · Travas — confiabilidade, tempo, conjunção, similaridade, sintetizador |
| 13 | relatorio | 372s | 26s | Etapa 10 · Relatório — templates neutros, varredura de frases proibidas, recibo por etapa |
| 14 | repro | 398s | 36s | Método — trace JSONL, cassetes (live/record/replay), harness dev/holdout, erro grave |
| 15 | resultados | 434s | 29s | Resultados — 59–64% de acerto, 0 erros graves; gargalo = recuperar evidência |
| 16 | fim | 463s | 15s | Encerramento — “não decide por você”: as fontes, os pesos, o caminho |
