# Sonda ddgs: medição da migração SerpAPI -> ddgs (Fase 1)

> **AVISO DE CONTAMINAÇÃO:** Coleta contaminada por bloqueio de IP; não usar como medida de qualidade. Duas instâncias da sonda rodaram em paralelo e foram paradas pelo coordenador por volta da tarefa 376 de 571. Google e Brave devolveram 'No results' em todas as chamadas desde a primeira (0 com resultado em 85 e 84 chamadas no log), e DuckDuckGo em quase todas (10 de 97). Isso bate com o bloqueio relatado (DuckDuckGo 202; Google e Brave 429), que o ddgs 9.16 devolve como 'No results found'. O log não permite datar o início do bloqueio, porque o ddgs esconde o código de erro. Google e Brave já estavam vazios nas sondagens de diagnóstico antes da rodada completa. Bing respondeu com resultados em 44 de 97 chamadas, com latência subindo (texto 3 a 10 s, notícias perto de 0,5 s) e timeouts no fim. Os números abaixo cobrem 370 das 571 tarefas (JSON gravado às 15:18:44; o log tem 376).

Gerado em 2026-10-19T15:21:10 pelo `scripts/sonda_ddgs.py`. Dados brutos em `docs/review/sonda_ddgs.json`.

- ddgs 9.16.0; região `br-pt`; max_results 10; timeout 5 s; ritmo 1.0 req/s (sequencial).
- Amostra: 30 consultas (seed 42) de 194 cassetes SerpAPI úteis; 370 chamadas ao ddgs.
- Categorias da amostra: notícias 13, google com `site:` 9, google simples 8.
- **ATENÇÃO: execução parcial** (interrompida antes do fim).

Score de texto/notícias (só para ordenar): 0.5 x cobertura de URLs + 0.3 x cobertura de hosts + 0.2 x (1 - % vazio) - 0.3 x % ratelimit. Elegível: % vazio <= 50% e % falhas <= 30%. A cobertura é contra a SerpAPI, que é o que o eval usa hoje, mas não é o gabarito: ddgs e Google podem ser igualmente bons e divergir na ordem.

## Texto (engine=google da SerpAPI)

| backend | chamadas | % vazio | vazio lento* | ratelimit | timeout | erro | lat média ms | cob. URL | cob. host | itens/busca | % com data | score |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| google | 17 | 100% | 0 | 0 | 0 | 0 | 601 | 0% | 0% | 0.0 | — | 0.00 |
| bing | 17 | 53% | 6 | 0 | 1 | 0 | 6029 | 4% | 15% | 3.8 | 0% | 0.16 |
| duckduckgo | 17 | 100% | 0 | 0 | 0 | 0 | 217 | 0% | 0% | 0.0 | — | 0.00 |
| brave | 17 | 100% | 5 | 0 | 0 | 0 | 1779 | 0% | 0% | 0.0 | — | 0.00 |

\* vazio lento = resposta vazia com latência >= timeout. Como o ddgs só coleta motores que terminam dentro da espera, esse vazio pode ser lentidão e não ausência de resultado.

Erros mais comuns:

- `google`: DDGSException: No results found.
- `bing`: DDGSException: No results found.
- `duckduckgo`: DDGSException: No results found.
- `brave`: DDGSException: No results found.

## Notícias (engine=google_news da SerpAPI)

| backend | chamadas | % vazio | vazio lento* | ratelimit | timeout | erro | lat média ms | cob. URL | cob. host | itens/busca | % com data | score |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bing | 13 | 54% | 0 | 0 | 0 | 0 | 488 | 2% | 7% | 2.1 | 100% | 0.12 |
| duckduckgo | 13 | 100% | 0 | 0 | 0 | 0 | 225 | 0% | 0% | 0.0 | — | 0.00 |
| yahoo | 13 | 100% | 0 | 0 | 0 | 0 | 720 | 0% | 0% | 0.0 | — | 0.00 |

Datas e fontes observadas:

- `bing`: formatos (iso: 27). Exemplos: iso `2025-11-14T03:00:00+00:00`. Fontes mais comuns: globo, Terra, correiobraziliense.com.br, catracalivre.com.br, O GLOBO, O Dia.
- `duckduckgo`: formatos (—). Exemplos: —. Fontes mais comuns: —.
- `yahoo`: formatos (—). Exemplos: —. Fontes mais comuns: —.

## Consultas com `site:` (OR como o agente manda hoje, e separado por domínio)

| backend | OR: consultas | OR: % vazio | OR: res. no domínio | OR: domínios cobertos | OR: res./busca | sep: buscas | sep: % vazio | sep: res. no domínio | sep: domínios cobertos | sep: res. (total por consulta) | decisão |
|---|---|---|---|---|---|---|---|---|---|---|---|
| google | 9 | 100% | — | 0% | 0.0 | 66 | 100% | — | 0% | 0.0 | OR ruim; separado não ganha: revisar |
| bing | 9 | 78% | 100% | 9% | 2.2 | 66 | 44% | 100% | 40% | 31.3 | trocar por separado |
| duckduckgo | 9 | 100% | — | 0% | 0.0 | 66 | 86% | 78% | 10% | 10.8 | trocar por separado |
| brave | 9 | 100% | — | 0% | 0.0 | 65 | 100% | — | 0% | 0.0 | OR ruim; separado não ganha: revisar |

"Domínios cobertos" = fração dos domínios pedidos com ao menos um resultado daquele domínio. "Res. no domínio" = fração dos resultados que pertencem a algum domínio pedido.

## Recomendação

- `DDGS_TEXT_BACKENDS=(nenhum elegível)`
- `DDGS_NEWS_BACKENDS=(nenhum elegível)`
- `site:` com OR: trocar por `separado` nos backends bing, duckduckgo; manter OR nos backends nenhum.

## Controles de sanidade (consulta trivial por backend)

| tipo | backend | controles ok | após quantas buscas caiu | buscas puladas |
|---|---|---|---|---|
| texto | google | sem controle (coleta anterior à rodada de controle) | — | — |
| texto | bing | sem controle (coleta anterior à rodada de controle) | — | — |
| texto | duckduckgo | sem controle (coleta anterior à rodada de controle) | — | — |
| texto | brave | sem controle (coleta anterior à rodada de controle) | — | — |
| noticias | bing | sem controle (coleta anterior à rodada de controle) | — | — |
| noticias | duckduckgo | sem controle (coleta anterior à rodada de controle) | — | — |
| noticias | yahoo | sem controle (coleta anterior à rodada de controle) | — | — |

Controle = consulta trivial ("Brasil capital Brasília"). Falha = vazio ou erro. Um backend com controle falho é tratado como bloqueado: as buscas dele são puladas até um controle voltar a passar. O ddgs não expõe o 429/202 do motor, por isso o bloqueio aparece como "No results found".

## Observações

- Há vazios com latência >= timeout: confirme antes de usar estes números como taxa de vazio real (ver nota da tabela de texto).
- O ddgs não devolve `date` no `text()` (esperado); a coluna % com data de texto mostra se algum backend devolve.
- Cobertura usa a SerpAPI como referência, não como gabarito. Divergência de ranking não é erro por si só.
- Se algum backend mostrar ratelimit em massa, o script para após 8 seguidos (ver JSON).
