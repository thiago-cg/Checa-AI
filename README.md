# Checa AI

Assistente de checagem de fatos em português do Brasil. A pessoa envia o texto, o título ou o link de uma notícia e
recebe a **propensão** de aquele conteúdo ser desinformação (baixa, média, alta ou indeterminada), com as fontes que
embasam a estimativa e o passo a passo da análise. O Checa AI nunca diz que algo "é falso" ou "é verdade": mostra os
indícios e devolve a decisão para quem lê.

| | |
|---|---|
| **Repositório** | https://github.com/thiago-cg/Checa-AI |
| **Site do projeto** | https://mariadenis.github.io/crosscheckbr-site/ |
| **Robô no Telegram** | [@fn_tic_bot](https://t.me/fn_tic_bot) |
| **Dataset e modelo** | https://github.com/thiago-cg/FakenewsBR |

## Como funciona

| Etapa | O que acontece |
|---|---|
| 1. Recebimento | A mensagem é classificada como texto, título ou link. O link só é lido quando pertence a um portal do catálogo; senão, o robô pede o texto. Imagem, vídeo e áudio recebem uma orientação. |
| 2. Afirmações | O texto vira afirmações verificáveis, sem a moldura de encaminhamento ("me mandaram que…") e mantendo o autor de uma fala. |
| 3. Base de checagens | Cada afirmação é procurada nas checagens já publicadas por 9 agências (cerca de 22 mil registros) e, com chave configurada, na Google Fact Check Tools. |
| 4. Busca na web | Só quando a base não tem checagem aplicável: busca na web (SerpAPI) pelo que veículos e agências publicaram. |
| 5. Leitura e julgamento | As páginas são lidas por inteiro, e um modelo de linguagem diz se cada uma confirma, contesta ou só relata a afirmação, com um trecho citado conferido na página. |
| 6. Estimativa | Uma regra fixa e documentada combina as fontes independentes e os selos das agências e chega à propensão. A conclusão é escrita por modelos de texto neutros. |

Os detalhes estão em [Como funciona](https://mariadenis.github.io/crosscheckbr-site/como-funciona/) e nos
[requisitos](entrega/requisitos/requisitos.md).

## Entrega

| Item | Onde está |
|---|---|
| Requisitos funcionais e não funcionais | [`entrega/requisitos/`](entrega/requisitos/) (`requisitos.md` e PDF) |
| Organização, Scrum e papéis | [`entrega/organizacao/`](entrega/organizacao/) (`organizacao.md` e PDF) |
| Guiding Questions | [`entrega/guiding_questions/`](entrega/guiding_questions/) |
| Análise exploratória dos dados (EDA) | [`entrega/EDA/`](entrega/EDA/) |
| Dataset | [`entrega/dataset/`](entrega/dataset/) |
| Treinamento do modelo | [`entrega/treinamento_modelo/`](entrega/treinamento_modelo/) |
| Relatório técnico do modelo (FakenewsBR v6 + BERTimbau) | [`entrega/relatorico_tecnico/`](entrega/relatorico_tecnico/) |

## Estrutura do repositório

| Pasta | Conteúdo |
|---|---|
| `factcheck_mvp/` | A aplicação: pipeline de checagem, robô do Telegram (`telegram_bot.py`), interface de programação e página (`api.py`), linha de comando (`cli.py`) |
| `factcheck_mvp/data/` | Base de checagens (`checagens.jsonl.gz`), catálogo de portais e tabelas de selos |
| `tests/` | Testes automatizados |
| `eval/` | Avaliação do sistema com casos rotulados e registro das iterações (`ITERACOES.md`) |
| `scripts/` | Benchmark da base, simulação de usuário e utilitários |
| `docs/` | Próximos passos, telemetria e revisões técnicas |
| `entrega/` | Entregáveis do desafio (tabela acima) |

## Como rodar

Requer Python 3.

```bash
git clone https://github.com/thiago-cg/Checa-AI.git
cd Checa-AI
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-mvp.txt
cp .env.mvp.example .env      # preencha as chaves (veja abaixo)

python3 -m pytest tests -q                                   # testes
python3 -m factcheck_mvp.cli checar "café cura câncer"       # uma checagem no terminal
python3 -m factcheck_mvp.cli trace last                      # passo a passo da última checagem
uvicorn factcheck_mvp.api:app --port 8000                    # página em http://127.0.0.1:8000
python3 -m factcheck_mvp.telegram_bot                        # robô do Telegram
```

| Chave no `.env` | Para quê | Sem ela |
|---|---|---|
| `OPENROUTER_API_KEY` | Modelo de linguagem (afirmações e julgamento das fontes) | As fontes não são julgadas e a resposta é "indeterminada" |
| `SERPAPI_KEY` | Busca na web | Só a base de checagens é consultada |
| `TELEGRAM_TOKEN` | Robô do Telegram | A página e a interface de programação funcionam |
| `GOOGLE_FACTCHECK_API_KEY` | Checagens da Google Fact Check Tools (opcional) | Só a base própria |

Todas as variáveis, com explicação, estão em [`.env.mvp.example`](.env.mvp.example). O `.env` nunca vai para o
repositório.

## Equipe

| Integrante | GitHub |
|---|---|
| Thiago Correia Gonzaga | [@thiago-cg](https://github.com/thiago-cg) |
| Maria Eduarda Denis Duarte Marques | [@mariadenis](https://github.com/mariadenis) |
| Guilherme Silva Dutra | [@GuiDutra21](https://github.com/GuiDutra21) |
| Gabriella Oliveira de Souza Dias | [@Gabizinha88](https://github.com/Gabizinha88) |
| Eliane Orlandin do Carmo | [@Eliane-orlandin](https://github.com/Eliane-orlandin) |
| Daltro Oliveira Vinuto | [@Daltro-Oliveira-Vinuto](https://github.com/Daltro-Oliveira-Vinuto) |

Papéis e forma de trabalho: [`entrega/organizacao/`](entrega/organizacao/).
