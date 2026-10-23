# CrossCheckBR — guia para o Claude Code

Checador de fatos PT-BR (`factcheck_mvp/`). Saída: propensão `baixa|media|alta|indeterminada` **a se
tratar de desinformação**. Review completo: `docs/review/RELATORIO.md`. Contrato de telemetria/replay:
`docs/TELEMETRIA.md`. Eval: `eval/README.md`. Python: `python3` (não existe `python`).

## Comandos

```bash
python3 -m pytest tests -q                                  # sempre verde antes e depois
python3 -m eval.run [--modo replay|record] [--split dev] [--nome x] [--gate]
python3 -m factcheck_mvp.cli checar "texto" [--modo replay] [--json]
python3 -m factcheck_mvp.cli trace <run_id|last> [--eventos llm,fallback]
python3 -m factcheck_mvp.cli runs --n 10
```

- Traces: `runs/<run_id>/{trace.jsonl,resultado.json}`. Resultados do eval:
  `eval/resultados/<ts>-<nome>/{relatorio.md,metricas.json,casos.jsonl}`. Baseline: `eval/baseline.json`.
- Cassetes (HTTP+LLM gravados): `eval/cassettes/`; buscas do ddgs são `ddgs://…` (um por backend). Uso das
  buscas live (SerpAPI e ddgs, campo `por_provedor`): `eval/serpapi_uso.json` (outro caminho: `BUSCA_USO_ARQ`).

## O loop

1. `python3 -m eval.run --nome <iter>` (replay) → 2. ler `relatorio.md` e `metricas.json`
   (acerto, **erro_grave**, indeterminada, `descoberta`, fallbacks) → 3. `cli trace <run_id>` dos casos
   errados → 4. hipótese sobre a **etapa** culpada (afirmações, busca, deep crawl, juiz, sinais,
   agregador, travas) → 5. mudança pequena → 6. `pytest` + eval de novo → 7. comparar com o baseline
   (delta impresso; `--gate`) → registrar em `eval/ITERACOES.md`: hipótese, mudança, métricas antes/depois,
   run_ids olhados. Só atualize o baseline (`--salvar-baseline`) quando a mudança for aceita.

## Métrica principal e modos

- Principal = perfil **busca aberta** (padrão do eval: `INDICE_CHECAGENS=0`). O atalho do índice é
  métrica secundária: `--env INDICE_CHECAGENS=1 --nome indice`.
- Provedor de busca: `BUSCA_PROVEDOR=serpapi` (padrão) ou `ddgs`. O padrão só muda quando o eval aprovar o
  ddgs; até lá, meça o ddgs com `--env BUSCA_PROVEDOR=ddgs`.
- Se `metricas.descoberta.pulada` for alta (sem busca web: `BUSCA_WEB=0` ou, no serpapi, sem `SERPAPI_KEY`),
  o eval **não** julga mudanças de busca/juiz. Olhe sempre esse campo antes de concluir algo.
- **replay** (padrão) para iterar em lógica (sinais, agregador, travas, parsing): determinístico, sem rede.
- **record** quando a mudança altera queries, prompts ou páginas lidas (prompt novo = cassete novo;
  record reusa o que já existe e grava o que falta). Em replay, `http_miss_total > 0` = faltou gravar.
- Trocar de provedor = cassetes novos: `--modo record --env BUSCA_PROVEDOR=ddgs`.
- Buscas live (SerpAPI ou ddgs) são contadas no arquivo de uso; teto opcional via
  `SERPAPI_ORCAMENTO_RESTANTE` (só SerpAPI) e `--max-buscas` (alias `--max-buscas-serpapi`; todas as chamadas,
  1 por backend do ddgs tentado). Erro de cota da SerpAPI
  (HTTP 401/403/429) aparece como `fallback` pedindo nova `SERPAPI_KEY` no `.env`: pare e avise o usuário.
- ddgs não tem cota, mas tem rate limit e bloqueio de IP: busca perdida = `fallback onde=ddgs`; desvio entre
  backends = `onde=ddgs.cadeia` (1 backend limitado só passa ao próximo). Limitado em todos os backends = `busca_bloqueada` em
  `metricas.json` e aviso no fim do eval: pare e avise o usuário. Fora do eval, limitado em todos os backends
  a busca cai na SerpAPI (`BUSCA_FALLBACK_SERPAPI=1`, gasta cota; o eval desliga) e o ddgs pausa
  `DDGS_PAUSA_BLOQUEIO_S` (300 s). Em replay, backend que falhou na gravação
  aparece como miss (`sem cassete`) e a cadeia segue: miss de `ddgs://` com resposta no backend seguinte é
  esperado, não falta de gravação.

## Regras anti-autoengano

- Nunca editar casos, rótulos, `esperado` ou o baseline para "passar". Rótulo errado: corrija com
  justificativa na `nota` e registre em ITERACOES.md.
- Iterar só no split `dev`; rodar `--split holdout` ao fim de uma rodada e reportar os dois.
- Não ajustar pesos/limiares para acertar um caso específico; a mudança deve ter razão geral.
- Todo fallback novo emite `telemetria.fallback(onde, motivo)`; todo I/O novo usa `replay.*`.
- Erro grave (falso→baixa, verdadeiro→alta) pesa mais que acerto.
- Não commitar sem pedido. Não ler `bot.log` (tem segredos). Nunca imprimir chaves do `.env`.

## Ambiente

- LLM local OpenAI-compatível (Unsloth Studio) em `http://127.0.0.1:8888/v1`, modelo carregado hoje:
  `unsloth/LFM2.5-8B-A1B-GGUF`. **Não carregar outro modelo no Studio sem pedir** (troca o do usuário).
  Checar: `curl -s -m 3 http://127.0.0.1:8888/v1/models`.
- Busca web: `BUSCA_PROVEDOR` (`serpapi`|`ddgs`); `BUSCA_WEB=0` desliga. ddgs: `DDGS_TEXT_BACKENDS`,
  `DDGS_NEWS_BACKENDS`, `DDGS_RPS`, `DDGS_PROXY` (segredo: nunca imprimir). `/saude` mostra `busca_provedor`,
  `busca_backends`, `busca_uso_hoje`, `busca_cap`. Lista completa em `.env.mvp.example`.
- `.env` tem `SERPAPI_KEY`; não há `OPENROUTER_API_KEY` → juiz (OpenRouter) cai em fallback léxico
  (aparece como `fallback onde=juiz`/`openrouter.chat` no trace).
- O pipeline grava sites descobertos em `factcheck_mvp/data/catalogo.json`; CLI e eval usam cópia
  temporária por padrão (`--catalogo-real` desliga).
- `/iterar [n]` (`.claude/commands/iterar.md`) roda n rodadas do loop.
