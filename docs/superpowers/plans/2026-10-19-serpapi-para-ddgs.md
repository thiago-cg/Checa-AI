# Plano — trocar a SerpAPI pelo `ddgs` sem perder funcionalidade

Data: 2026-10-19 · Branch: `claude/serpapi-to-ddgs-migration-9b3d8c` · Alvo: `ddgs==9.16.0` (PyPI, Python ≥ 3.10; aqui 3.14).

## 0. Resumo da decisão

- **Trocar o transporte, manter o contrato interno.** Todo o pipeline (agente, planejador, `normalizar_item`,
  pipeline estático, testes com payload fake) consome hoje um JSON no formato SerpAPI
  (`organic_results` / `news_results` / `top_stories` / `search_metadata.created_at`). O novo cliente
  `DDGSClient` chama o `ddgs` e **devolve o mesmo formato**. Assim a migração mexe em ~4 arquivos de produção
  em vez de ~20, e os ~10 testes que usam fakes no formato SerpAPI continuam valendo.
- **Provedor selecionável por um ciclo** (`BUSCA_PROVEDOR=ddgs|serpapi`, padrão `ddgs` só depois do gate da
  fase 6). A SerpAPI vira fallback/opção até a medição mostrar que não piorou; só então sai (fase 8).
- **Cassete no nível da chamada `ddgs`**, não do HTTP: o `ddgs` usa `primp` internamente e não passa pelo
  `replay.http_get`/curl_cffi. O resultado (lista de dicts) é gravado como cassete com pseudo-URL
  `ddgs://<função>?…`, reaproveitando `replay._executar`.
- **Backends fixos e ordenados**, nunca `backend="auto"` (o `auto` sorteia/mescla motores → replay e eval
  deixam de ser determinísticos e a comparação com o baseline perde sentido).

## 1. Inventário: o que a SerpAPI faz hoje

| Funcionalidade | Onde | Observação |
|---|---|---|
| Busca orgânica Google (`engine=google`, `hl=pt-br`, `gl=br`, `num=10`) | `serpapi_layer._base`, `query_agencias`, `construir_queries_*` | consulta crua + `(site:a OR site:b …)` das agências do catálogo |
| Google News (`engine=google_news`, padrão de `SERP_ENGINE`) | `construir_queries_news`, `agente.com_motor`, `_itens_news` (grupos `stories`) | data ISO (`iso_date`), `source.name/authors` |
| Google Scholar | `construir_queries` (`engine=google_scholar`) | só via `SERP_ENGINE=google_scholar`; não é usado no caminho do agente |
| `top_stories` do orgânico | `agente.absorver` (`TOP_STORIES_POR_BUSCA=3`), checagem de "vazio" em `buscar_ex` | entram marcados `_top_story=True` |
| Âncora de data relativa | `search_metadata.created_at` → `aplicabilidade.normalizar_data` | resolve "há 2 dias" |
| Data por resultado | orgânico `date` (relativa), News `iso_date` | tier `serpapi` em `corroboracao.tier_data` (5 absoluta / 3 relativa) |
| `displayed_link`, `thumbnail`, `position`, `about_this_result` | `normalizar_item` | `_fonte_desc` não é lido fora da camada (sem consumidor) |
| Motor por domínio (`site:` → orgânico) | `planejador.motor_por_dominio`, `BUSCA_SITE_NO_ORGANICO` | News não indexa agências |
| Relaxar consulta vazia / ler mais / ondas extras | `planejador_busca.py`, `agente.py` | regras puras, independem do provedor |
| Cache em memória (TTL, só não-vazios) e teto diário | `SerpAPIClient` (`CACHE_SERPAPI_TTL`, `SERPAPI_DAILY_CAP`) | `bloqueios_cap`, `ultimo_motivo` |
| 1 nova tentativa em timeout/conexão | `_get_com_nova_tentativa` | `SERPAPI_TIMEOUT_S=15` |
| Rodízio de chaves e cota (401/403/429) | `serpapi_chaves.py`, `replay._checar_cota_serpapi`, `CotaSerpAPIEsgotada` | eval para quando a cota acaba |
| Orçamento live (arquivo + processo) | `replay._reservar_serpapi`, `eval/serpapi_uso.json`, `--max-buscas-serpapi`, `SERPAPI_ORCAMENTO_RESTANTE` | |
| Cassetes record/replay | `replay._executar` + chave sha256 da URL sem segredos | ~2.900 cassetes em `eval/cassettes/` (checkout principal) |
| Liga/desliga | `ativo` = tem `SERPAPI_KEY`; testes usam `SerpAPIClient(api_key="")` | etapa `descoberta pulada` |
| Telemetria/eval | `fallback onde=serpapi*`, `http` com `serpapi.com`, `eval/run.py` (`serpapi_live`, `cota_serpapi_esgotada`), `/saude` em `api.py`, `cli runs`, `langfuse_export` | |

## 2. Mapeamento SerpAPI → ddgs

| SerpAPI | ddgs | Notas / risco |
|---|---|---|
| `engine=google` | `DDGS().text(q, region="br-pt", safesearch=…, max_results=num, backend=<1 por vez>)` | ordem padrão proposta: `google,bing,duckduckgo,brave` (`DDGS_TEXT_BACKENDS`), tentando o próximo só se o anterior falhar/vier vazio |
| `engine=google_news` | `DDGS().news(q, region="br-pt", max_results=…, backend=…)` | backends: `bing,duckduckgo,yahoo` (`DDGS_NEWS_BACKENDS`); `date` já vem ISO → mapeia para `iso_date` |
| `engine=google_scholar` | — | sem equivalente. Não está no caminho do agente: manter `SERP_ENGINE=google_scholar` só com `BUSCA_PROVEDOR=serpapi`; no ddgs, cai para `text` com fallback registrado |
| `top_stories` | `news()` com a mesma consulta pura (opcional, `DDGS_TOP_STORIES=1`) | 1 chamada a mais por consulta pura da onda 1; mapear os 3 primeiros para `top_stories` |
| `organic_results[].link/title/snippet` | `href/title/body` | direto |
| `news_results[].link/title/iso_date/source.name/thumbnail` | `url/title/date/source/image` | `source` do Bing vem "X on MSN.com": normalizar |
| `organic_results[].date` (relativa) | **não existe** no `text()` | perda real: ver §4 |
| `displayed_link` | derivado do host de `href` | `normalizar_item` já usa como fallback de `nome_fonte` |
| `position` | índice 1-based na lista | |
| `search_metadata.created_at` | carimbo UTC gerado pelo cliente **no momento da busca live** e gravado dentro do payload (logo, no cassete) | replay continua determinístico |
| `hl=pt-br`, `gl=br` | `region="br-pt"` | conferir no spike que todos os backends respeitam |
| `num` | `max_results` | |
| `api_key` / rodízio | — | sem chave; substituído por `DDGS_PROXY` opcional (e lista de proxies, se precisar) |
| HTTP 401/403/429 (cota) | `RatelimitException` / `TimeoutException` / `DDGSException` | ver §3.4 |

## 3. Desenho

### 3.1 Novo módulo `factcheck_mvp/ddgs_layer.py`

- `class DDGSClient` com **a mesma interface pública** do `SerpAPIClient`: `ativo`, `buscar(params)`,
  `buscar_ex(params) -> ResultadoBusca`, `engine_de`, `result_key`, `engine_default`, `uso_hoje`,
  `ultimo_motivo`, `bloqueios_cap`, `erros_rede`. `ResultadoBusca`, `ENGINES`, `RESULT_KEY` continuam
  vindo de `serpapi_layer` (ou vão para um `busca_base.py` comum).
- Recebe os mesmos `params` que o agente já monta (`q`, `engine`, `num`, `hl`, `gl`) e traduz:
  `engine=google → text`, `google_news → news`.
- `_para_formato_serpapi(funcao, resultados, backend, criado_em)` monta
  `{"organic_results"|"news_results": [...], "top_stories": [...], "search_metadata": {"created_at": …,
  "provedor": "ddgs", "backend": …}}`. Itens orgânicos ganham `link`, `title`, `snippet`, `position`,
  `displayed_link`; itens de notícia ganham `link`, `title`, `snippet`, `iso_date`, `source: {"name"}`, `thumbnail`.
- Copia o comportamento do cliente atual: cache em memória com TTL (só não-vazios), teto diário, `threading.Lock`,
  1 nova tentativa em timeout, nunca levanta (falha vira `ResultadoBusca(None, "erro")` + `telemetria.fallback`).
- `DDGS(...)` instanciado por chamada (o agente roda buscas em threads; evitar estado compartilhado do `primp`).
- `ativo` = `BUSCA_WEB` ligado (novo, padrão 1) e não desligado explicitamente (`DDGSClient(ativo=False)`
  substitui o `api_key=""` dos testes).

### 3.2 Fábrica de provedor

- `factcheck_mvp/busca_web.py: cliente_padrao()` → `DDGSClient()` ou `SerpAPIClient()` conforme
  `BUSCA_PROVEDOR`. Trocar as 3 construções diretas: `pipeline.py:223`, `api.py:69`, `cli.py:48`
  (e `eval/run.py`, `eval/simulacao.py`, `scripts/simular_usuario.py`, `avaliacao/avaliar_golden.py` se constroem).
- `agente._buscar` hoje testa `type(cliente).buscar is camada.SerpAPIClient.buscar` para decidir usar
  `buscar_ex`: generalizar para "tem `buscar_ex` e não sobrescreveu `buscar`" (classe base comum `ClienteBusca`).
- Atributo `Pipeline.serpapi` → manter nome (compat) com alias `Pipeline.busca`; renomear de vez na fase 8.

### 3.3 Replay / cassetes (`replay.py`)

- Nova função `replay.busca_ddgs(funcao: str, params: dict, ao_vivo: Callable[[], list]) -> list`:
  - URL-chave `ddgs://{funcao}?q=…&region=…&backend=…&max_results=…&safesearch=…&timelimit=…`
    (ordenada por `url_canonica`); chama `_executar("GET", url, None, _vivo)` onde `_vivo` embrulha a lista
    num `Resposta(200, {"content-type": "application/json"}, json_bytes, url)`.
  - Assim valem de graça: record reusa cassete, replay levanta `ReplayMiss`, `LLM_ONLY_RECORD`, evento `http`.
  - **O carimbo `created_at` vai dentro do JSON gravado**, então o replay reproduz a mesma âncora de data.
- Generalizar o orçamento: `_eh_serpapi(url)` → `_eh_busca_live(url)` (`serpapi.com` **ou** esquema `ddgs`);
  contador `eval/busca_uso.json` com campo por provedor (`{"serpapi": n, "ddgs": n}`) e `SERPAPI_USO_ARQ` →
  `BUSCA_USO_ARQ` (aceitando o nome antigo). O ddgs é grátis, mas o teto continua útil contra bloqueio de IP.
- **Não gravar** respostas de rate limit (como já é feito com 429/5xx), senão o replay congela a falha.

### 3.4 Erros e limites (substitui cota/rodízio)

- `ddgs.exceptions.RatelimitException` → espera com backoff (`DDGS_ESPERA_RATELIMIT_S`, ex. 2 s, 5 s) e tenta
  o **próximo backend** da lista; esgotados todos → `fallback("ddgs", "ratelimit: todos os backends")` e
  `ResultadoBusca(None, "erro")`. Novo `replay.BuscaLimitada` (análogo de `CotaSerpAPIEsgotada`) só quando
  o rate limit persiste num eval inteiro (`n` falhas seguidas) para o eval parar em vez de medir lixo.
- `TimeoutException` → 1 nova tentativa (mesma regra do `_eh_falha_de_rede`).
- `DDGSException("No results found")` → `motivo="vazio"` (não é erro; o planejador relaxa a consulta).
- Limitador de ritmo global `DDGS_RPS` (padrão ~1 req/s por backend) no mesmo molde de
  `_esperar_limite_openrouter`, porque a onda do agente dispara buscas em paralelo.
- `serpapi_chaves.py` fica só para o provedor `serpapi`; nada novo de segredo (proxy com usuário/senha entra em
  `telemetria._ENV_SEGREDOS` como `DDGS_PROXY`).

### 3.5 Sintaxe de consulta

- O limite de 32 palavras é do Google: manter `MAX_PALAVRAS_QUERY` mas configurável por backend
  (`DDGS_MAX_PALAVRAS`).
- `(site:a OR site:b …)`: suporte varia por backend (Google/Bing aceitam; DuckDuckGo/Brave são irregulares com
  `OR` + `site:`). O spike (§5, fase 1) decide por backend; onde não funcionar, usar
  `AGENTE_SITES_MODO=separado` automaticamente para aquele backend (já existe) — mesma cobertura de agências,
  mais chamadas (grátis).
- `planejador.motor_por_dominio` continua mandando `site:` para `engine=google` → `text()`; a consulta pura
  segue no motor configurado → `news()`. Nenhuma regra do planejador muda.

## 4. Perdas conhecidas e como compensar

| Perda | Impacto | Compensação |
|---|---|---|
| Data relativa no orgânico (`date`) | tier `serpapi` some para resultados de `text()`; relevância temporal (E4) depende mais da página | o deep crawl já prefere JSON-LD (tier 6) e trafilatura (4); para a consulta pura, `news()` traz data ISO (tier 5). Medir `data_pub` nula antes/depois no eval |
| `top_stories` | menos notícias recentes misturadas no orgânico | `DDGS_TOP_STORIES=1` usa `news()` como substituto |
| Google Scholar | não usado no caminho padrão | manter só no provedor `serpapi`; documentar |
| `about_this_result` | `_fonte_desc` não tem consumidor | nenhuma |
| Qualidade do ranking Google | o backend `google` do ddgs é scraping e pode bloquear; Bing/DDG ranqueiam diferente | ordem de fallback de backends + medição por backend no spike |
| SLA/estabilidade | ddgs raspa HTML; motores mudam e quebram a lib | pin de versão exato (`ddgs==9.16.0`), teste de fumaça live opcional, provedor `serpapi` como fallback (`BUSCA_PROVEDOR_FALLBACK=serpapi` se houver chave) |
| Termos de uso | raspagem de buscadores pode violar ToS; risco de bloqueio de IP no servidor do bot | decisão do responsável do projeto; `DDGS_PROXY`; registrar no README/privacidade |

## 5. Fases

### Fase 1 — Spike de medição (sem tocar produção)
1. `pip install ddgs==9.16.0` no venv; adicionar a `requirements-mvp.txt` e `requirements.txt`.
2. `scripts/sonda_ddgs.py`: pega as consultas reais já gravadas nos cassetes SerpAPI do split `dev`
   (campo `req.url` → `q`, `engine`), roda cada uma em cada backend (`text`: google, bing, duckduckgo, brave;
   `news`: bing, duckduckgo, yahoo) com `region="br-pt"` e mede, por backend:
   - sobreposição de URLs (canônicas) com o top-10 da SerpAPI e com as URLs que viraram evidência no eval;
   - % de consultas vazias; se `site:` e `(site:a OR site:b)` retornam só os domínios pedidos;
   - presença/formato de `date` no `news()`; latência; nº de rate limits em ritmo de 1 req/s.
3. Saída em `docs/review/sonda_ddgs.md`. **Gate:** escolher a ordem de backends e o modo de `site:` por
   backend; se nenhum backend chegar perto da SerpAPI no recall das agências, parar e reportar.

### Fase 2 — Cliente e formato
4. `ddgs_layer.py` (§3.1) + `busca_web.py` (§3.2) + config nova em `config.py` e `.env.mvp.example`:
   `BUSCA_PROVEDOR`, `BUSCA_WEB`, `DDGS_TEXT_BACKENDS`, `DDGS_NEWS_BACKENDS`, `DDGS_REGIAO=br-pt`,
   `DDGS_SAFESEARCH`, `DDGS_TIMEOUT_S`, `DDGS_RPS`, `DDGS_PROXY`, `DDGS_TOP_STORIES`, `DDGS_MAX_PALAVRAS`.
   Os nomes `SERPAPI_DAILY_CAP`/`CACHE_SERPAPI_TTL` passam a ter alias `BUSCA_DAILY_CAP`/`CACHE_BUSCA_TTL`.
5. `tests/test_ddgs_layer.py` com `DDGS` fake (monkeypatch em `ddgs.DDGS`): tradução de params, formato de
   saída, `top_stories`, âncora, vazio, rate limit → próximo backend, timeout → 1 retry, cache, teto diário,
   `ativo=False`, nunca levanta.

### Fase 3 — Replay e orçamento
6. `replay.busca_ddgs` + `_eh_busca_live` + contador por provedor (§3.3). `tests/test_replay.py`: cassete
   ddgs grava/lê, replay miss, record reusa, rate limit não é gravado, `created_at` preservado.
7. `eval/run.py`: `serpapi_live` → `busca_live` (com `por_provedor`), `cota_serpapi_esgotada` → `busca_bloqueada`,
   `--max-buscas-serpapi` → `--max-buscas` (aceitar o antigo), filtros das linhas que procuram `serpapi.com`
   e `onde=serpapi` passam a aceitar `ddgs`. `metricas.descoberta.pulada/falhou` continuam iguais.

### Fase 4 — Ligação no pipeline
8. `pipeline.py`, `api.py`, `cli.py`, `eval/simulacao.py`, `scripts/simular_usuario.py`,
   `avaliacao/avaliar_golden.py`: usar `busca_web.cliente_padrao()`. Mensagens de `limitacoes`/`etapa`:
   "SERPAPI_KEY ausente" → "busca web desligada (BUSCA_WEB=0)"; "SerpAPI sem resultados" → "busca web sem
   resultados" (cuidado: `pipeline.py:658` compara a string literal — trocar pela constante).
9. `agente._buscar` sem o `is SerpAPIClient.buscar` (§3.2). `api.py /saude`: `busca_provedor`,
   `busca_backends`, `busca_uso_hoje`, `busca_cap` (mantendo as chaves `serpapi_*` por um ciclo).
10. `normalizar_item`: `origem` passa a ser o provedor real (`"ddgs:bing"`, …); `corroboracao.tier_data`
    aceita `ddgs` com o mesmo peso de `serpapi`. `telegram_bot.py` texto de privacidade.

### Fase 5 — Testes existentes
11. `python3 -m pytest tests -q` verde **antes** de começar e **depois** de cada fase. Testes que dependem de
    `SerpAPIClient(api_key="")` (11 ocorrências) seguem valendo porque o provedor `serpapi` continua; os que
    testam o padrão (`test_pipeline`, `test_agente`, `test_missao_g`, `test_saude`, `test_env_exemplo`,
    `test_eval_harness`, `test_telemetria`) recebem a variante ddgs. Nenhum teste de lógica (planejador,
    sinais, agregador) deve precisar mudar: se mudar, o contrato vazou.

### Fase 6 — Medição (o loop do CLAUDE.md)
12. `python3 -m eval.run --modo record --split dev --nome ddgs-dev --env BUSCA_PROVEDOR=ddgs`
    (grava os cassetes ddgs; LLM local também grava o que faltar porque o conteúdo lido muda).
13. Replay de confirmação: `python3 -m eval.run --split dev --nome ddgs-dev-replay --env BUSCA_PROVEDOR=ddgs`
    — `http_miss_total` deve ser 0 e as métricas iguais às do record.
14. Comparar com o baseline (SerpAPI): acerto, **erro_grave**, indeterminada, `descoberta`
    (`pulada`/`falhou` ≈ 0), fallbacks por `onde`, nº médio de URLs únicas por afirmação, % de evidência vinda
    de agência de checagem, `data_pub` nula. Olhar `cli trace` dos casos que mudaram de resposta.
15. Repetir no `--split holdout` e no perfil secundário (`--env INDICE_CHECAGENS=1 --nome ddgs-indice`).
16. **Gate de aceite** (§6). Registrar em `eval/ITERACOES.md`: hipótese, mudança, métricas antes/depois,
    run_ids. Só então `--salvar-baseline` e padrão `BUSCA_PROVEDOR=ddgs`.

### Fase 7 — Documentação
17. `CLAUDE.md`, `README.md`, `docs/TELEMETRIA.md` (eventos `fallback onde=ddgs*`, `http` com `ddgs://`),
    `eval/README.md`, `.env.mvp.example`, `.claude/commands/iterar.md` (trocar o aviso de cota SerpAPI pelo de
    rate limit/bloqueio), `entrega/fluxo_aplicacao/*` se a entrega precisar refletir.

### Fase 8 — Remoção da SerpAPI (PR separado, depois de ≥1 rodada estável)
18. Remover `serpapi_chaves.py`, `SerpAPIClient`, `CotaSerpAPIEsgotada`, `SERPAPI_*` do config/env, testes
    `test_serpapi_layer.py` (o que for só SerpAPI), renomear `Pipeline.serpapi` → `Pipeline.busca`, mover
    funções neutras de `serpapi_layer.py` (agências, `normalizar_item`, `rotear_fonte`, `query_agencias`) para
    `busca_base.py`. Cassetes SerpAPI antigos podem ficar (não atrapalham) ou ser arquivados.

## 6. Critérios de aceite ("sem perdas")

- `pytest` verde; eval `dev` e `holdout` em replay com `http_miss_total = 0`.
- `erro_grave` **não aumenta** em nenhum split; acerto dentro de ±1 caso do baseline SerpAPI no `dev` e no
  `holdout` (diferença maior exige explicação por caso no ITERACOES.md, sem ajustar pesos para compensar).
- `descoberta.pulada` e `descoberta.falhou` ≤ baseline; fração de casos com ≥1 evidência de agência de
  checagem ≥ baseline − 5 p.p.
- Todas as capacidades do §1 existem com ddgs ou estão listadas no §4 com compensação medida.
- Nenhum fallback novo sem `telemetria.fallback`; nenhum I/O novo fora de `replay.*`.

## 7. Riscos e mitigação

1. **Bloqueio/rate limit em produção (bot)**: ritmo global, backoff, troca de backend, proxy opcional, provedor
   `serpapi` como fallback quando houver chave.
2. **Não determinismo**: backends fixos, um por vez, cassete por chamada com `backend` na chave.
3. **Quebra da lib**: versão fixada; `scripts/sonda_ddgs.py --rapido` como teste de fumaça manual antes de
   atualizar o pin.
4. **Baseline incomparável**: a mudança de provedor muda as páginas lidas; por isso o eval em record do
   `dev` + `holdout` é obrigatório antes de virar o padrão, e o baseline antigo fica guardado como
   `eval/baseline_serpapi.json` para referência.
5. **ToS**: decisão explícita do responsável antes da fase 6 em produção.

## 8. Arquivos tocados (estimativa)

Produção: `ddgs_layer.py` (novo), `busca_web.py` (novo), `replay.py`, `config.py`, `pipeline.py`, `agente.py`
(1 função), `api.py`, `cli.py`, `corroboracao.py` (1 linha), `telemetria.py`, `telegram_bot.py`,
`langfuse_export.py`. Eval/scripts: `eval/run.py`, `eval/simulacao.py`, `scripts/simular_usuario.py`,
`scripts/sonda_ddgs.py` (novo), `avaliacao/avaliar_golden.py`. Testes: `test_ddgs_layer.py` (novo),
`test_replay.py`, `test_pipeline.py`, `test_agente.py`, `test_missao_g.py`, `test_saude.py`,
`test_env_exemplo.py`, `test_eval_harness.py`, `test_telemetria.py`. Config: `requirements*.txt`,
`.env.mvp.example`. Docs: §5 fase 7.

## 9. Achados das buscas live (19/10, depois da implementação)

- **Bloqueio silencioso no ddgs 9.16:** HTTP != 200 vira `None` e o erro sai como "No results found". DuckDuckGo
  respondia 202 (captcha "anomaly"), Google e Brave 429: tudo parecia busca vazia. Corrigido em
  `ddgs_layer._instalar_deteccao_bloqueio` (202/403/429 -> `RatelimitException`); depende da versão fixada.
- **`(site:a OR site:b)`:** com parênteses a busca devolvia zero; sem eles, só as agências pedidas. `ddgs_layer.adaptar_consulta`
  tira os parênteses do grupo de `site:` (a perna das agências voltou com Aos Fatos, UOL Confere, Estadão Verifica).
  Atenção: esse teste pedia `backend=bing`, que no texto estava desligado (ver abaixo); quem respondeu foi o `auto`.
- **`bing` de texto desligado no ddgs 9.16** (`disabled = True` em `ddgs/engines/bing.py`; `yandex` também). Pedido
  à lib, ela avisava "backends do not exist or are disabled" e caía em `backend='auto'` (sorteio de motores:
  replay não determinístico e `search_metadata.backend` errado). Tudo que acima foi atribuído ao "Bing" no texto veio
  do `auto`. Corrigido: `ddgs_layer.backends_validos` só passa à lib motores de `ddgs.engines.ENGINES` (o resto é
  pulado com `fallback(onde="ddgs.cadeia")`, 1 aviso por processo) e, sem nenhum válido, a busca é erro, nunca
  `auto`. Ordem padrão de texto: `duckduckgo,yahoo,brave,google`; notícias seguem `bing,duckduckgo,yahoo` (o `bing`
  de notícias está habilitado). Google 0/85 e Brave 0/84 com resposta na sonda (429 desde a 1ª chamada). A sonda da fase 1 foi contaminada por bloqueio (duas instâncias em
  paralelo) e não decide nada: repetir com o IP limpo, com o lock e a consulta de controle novos.
- **Volume:** algumas centenas de buscas em ~30 min bastaram para o bloqueio. O eval em record (fase 6) precisa de
  `DDGS_RPS` baixo (≤ 0,3) ou proxy; com a cadeia toda limitada o caso sai com `busca_bloqueada`.
