# Checa AI

Assistente de checagem de fatos em português do Brasil.

| | |
|---|---|
| **Repositório** | https://github.com/thiago-cg/Checa-AI |
| **Site do projeto** | https://mariadenis.github.io/crosscheckbr-site/ |
| **Robô no Telegram** | [@fn_tic_bot](https://t.me/fn_tic_bot) |
| **Dataset e modelo** | https://github.com/thiago-cg/FakenewsBR |

Este README está dividido em três partes:

1. [O que é o projeto](#1-o-que-é-o-projeto)
2. [Como rodar](#2-como-rodar)
3. [Organização das pastas](#3-organização-das-pastas)

---

## 1. O que é o projeto

### O problema

Boa parte da desinformação no Brasil circula em aplicativos de mensagem, encaminhada por pessoas que não têm
tempo nem ferramentas para conferir o que receberam. Agências de checagem publicam milhares de verificações, mas
encontrar a checagem certa, ou descobrir o que a imprensa publicou sobre um assunto, exige esforço que quase
ninguém faz antes de compartilhar.

### A solução

O **Checa AI** ajuda uma pessoa a decidir se compartilha uma notícia. Ela envia o **texto**, o **título** ou o
**link** da notícia pelo Telegram e recebe:

- a **propensão** de aquele conteúdo ser desinformação: **baixa**, **média**, **alta** ou **indeterminada**;
- as **fontes** que embasam a estimativa, cada uma com o veículo, o trecho citado, o endereço e se ela confirma,
  contesta ou só relata a afirmação;
- o **passo a passo** da análise e as limitações da consulta.

O Checa AI **nunca diz que algo "é falso" ou "é verdade"**. Ele mostra os indícios e devolve a decisão para quem
lê. Essa neutralidade é uma regra do sistema, verificada por testes automatizados.

**Público:** pessoas leigas que recebem notícias em aplicativos de mensagem (público principal), estudantes,
professores e jornalistas de checagem.

**Fora do escopo:** análise de imagem, vídeo e áudio (o robô responde com uma orientação), outros idiomas e
outros aplicativos de mensagem.

### Como funciona

Cada consulta passa por um pipeline de seis etapas:

| Etapa | O que acontece |
|---|---|
| 1. Recebimento | A mensagem é classificada como texto, título ou link. O link só é lido quando pertence a um portal do catálogo; senão, o robô pede o texto. Imagem, vídeo e áudio recebem uma orientação. |
| 2. Afirmações | Um modelo de linguagem transforma o texto em afirmações verificáveis, sem a moldura de encaminhamento ("me mandaram que…") e mantendo o autor de uma fala. |
| 3. Base de checagens | Cada afirmação é procurada nas checagens já publicadas por 9 agências (cerca de 22 mil registros) e, com chave configurada, na Google Fact Check Tools. |
| 4. Busca na web | Só quando a base não tem checagem aplicável: busca na web (SerpAPI) pelo que veículos e agências publicaram. |
| 5. Leitura e julgamento | As páginas são lidas por inteiro, e um modelo de linguagem (o "juiz") diz se cada uma confirma, contesta ou só relata a afirmação, com um trecho citado que é conferido na página. |
| 6. Estimativa | Uma regra fixa e documentada, e não um modelo de linguagem, combina as fontes independentes e os selos das agências e chega à propensão. A conclusão é escrita por modelos de texto neutros. |

Alguns princípios que guiam a estimativa:

- **Fontes independentes:** republicações, aliases do mesmo portal e veículos do mesmo grupo contam como uma única fonte.
- **Só vota quem foi lido:** uma fonte vista só pelo título aparece como "só manchete" e não entra na conta.
- **A posição vale mais que o selo:** um selo "verdadeiro" numa página que refuta a afirmação conta contra ela.
- **Data importa:** fonte de outro período perde peso quando o texto fala em "hoje", "ontem", "nesta semana".
- **Sem julgamento, sem estimativa:** se nenhuma fonte foi julgada, a resposta é "indeterminada".
- **Falha não derruba a resposta:** a falha de qualquer etapa vira uma limitação declarada.

As 9 agências da base são: Lupa, Aos Fatos, Boatos.org, E-Farsas, Fato ou Fake (G1), Estadão Verifica, Projeto
Comprova, UOL Confere e AFP Checamos. A base é atualizada todo dia por um fluxo do GitHub Actions, que abre um
pull request para revisão humana e é barrado se a qualidade do índice cair.

Além da propensão, a resposta pode trazer dois **sinais de estilo**, que não entram na estimativa: a
probabilidade dada pelo modelo próprio da equipe (BERTimbau ajustado, ver abaixo) e os padrões típicos de
desinformação encontrados no texto (apelo à urgência, tom alarmista, fonte vaga, falta de data ou local, título
sensacionalista).

Mais detalhes em [Como funciona](https://mariadenis.github.io/crosscheckbr-site/como-funciona/) e nos
[requisitos](entrega/requisitos/requisitos.md).

### O modelo próprio (FakenewsBR v6)

A equipe treinou um classificador de estilo a partir do **BERTimbau** (BERT em português), ajustado sobre o Pool
v6 do FakenewsBR (91.080 textos rotulados, com remoção de duplicatas), com pesos por grupo e calibração de Platt.
Resultado no conjunto de teste (13.661 textos):

| Acurácia | Macro-F1 | Pior grupo | ROC-AUC | ECE |
|---:|---:|---:|---:|---:|
| 82,5% | 0,785 | 0,617 (LIAR-BR) | 0,896 | 0,024 |

O modelo é opcional na aplicação (ligado por `FAKE_MODEL_PATH`). A análise exploratória, o treino e o relatório
técnico estão em [`entrega/`](entrega/).

### Tecnologias utilizadas

| Área | Tecnologia | Para quê |
|---|---|---|
| Linguagem | **Python 3** | Todo o sistema |
| Canais | **python-telegram-bot** | Robô do Telegram |
| | **FastAPI** + **Uvicorn** | Página na internet e interface de programação (`POST /checar`, `GET /saude`, `GET /portais`) |
| | **Pydantic** | Estruturas tipadas de entrada e saída, compartilhadas por todos os canais, e validação das respostas do modelo de linguagem |
| Modelos de linguagem | **OpenRouter** | Extração das afirmações e julgamento das fontes (provedor principal) |
| | **LLM local OpenAI-compatível** (Unsloth Studio) | Provedor reserva; sem nenhum dos dois, o sistema cai em regras fixas e responde "indeterminada" |
| Busca | **SerpAPI** | Busca na web por veículos e agências |
| | **Google Fact Check Tools** | Checagens indexadas pelo Google (opcional) |
| Base de checagens | **rank-bm25** + **NLTK** (stopwords e RSLPStemmer) | Índice de busca textual sobre as cerca de 22 mil checagens |
| | **lxml** | Leitura dos feeds RSS/Atom e mapas de site das agências |
| Coleta e extração | **curl_cffi** | Download das páginas |
| | **trafilatura**, **BeautifulSoup**, JSON-LD | Extração do corpo da notícia em cascata (dados estruturados → trafilatura → seletor do catálogo → regex) |
| | **Crawl4AI** | Crawler de notícias de portais brasileiros (`br_news_crawler.py`) |
| | **laya** | Classificador rápido de relevância |
| Modelo próprio | **PyTorch** + **Hugging Face Transformers** (BERTimbau) | Classificador de estilo, treino e inferência |
| | pandas, scikit-learn, matplotlib | Análise exploratória e avaliação do modelo |
| Qualidade | **pytest** | Mais de 1.200 testes automatizados |
| | Harness de avaliação próprio (`eval/`) | Casos rotulados, métricas, comparação com baseline e replay das chamadas externas gravadas |
| | Telemetria própria (`runs/<id>/trace.jsonl`) | Registro de cada etapa, fonte e chamada ao modelo, com segredos removidos |
| Automação | **GitHub Actions** | Atualização diária da base de checagens |

---

## 2. Como rodar

### Pré-requisitos

- Python 3.10 ou superior (o projeto é usado com 3.12)
- Git
- Chaves de API (opcionais, mas recomendadas; veja a tabela abaixo)

### Instalação

Linux ou macOS:

```bash
git clone https://github.com/thiago-cg/Checa-AI.git
cd Checa-AI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-mvp.txt
cp .env.mvp.example .env      # depois preencha as chaves
```

Windows (PowerShell):

```powershell
git clone https://github.com/thiago-cg/Checa-AI.git
cd Checa-AI
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-mvp.txt
copy .env.mvp.example .env    # depois preencha as chaves
```

Para ligar o modelo próprio (BERTimbau), instale também `pip install -r requirements-modelo.txt` e aponte
`FAKE_MODEL_PATH` no `.env` para a pasta com os pesos treinados.

### Configuração

| Chave no `.env` | Para quê | Sem ela |
|---|---|---|
| `OPENROUTER_API_KEY` | Modelo de linguagem (afirmações e julgamento das fontes) | Usa o LLM local, se houver; senão as fontes não são julgadas e a resposta é "indeterminada" |
| `SERPAPI_KEY` | Busca na web | Só a base de checagens é consultada |
| `TELEGRAM_TOKEN` | Robô do Telegram | A página e a interface de programação funcionam |
| `GOOGLE_FACTCHECK_API_KEY` | Checagens da Google Fact Check Tools (opcional) | Só a base própria |
| `UNSLOTH_BASE_URL` | Endereço de um LLM local OpenAI-compatível (opcional) | Só o OpenRouter |

Todas as variáveis, com explicação, estão em [`.env.mvp.example`](.env.mvp.example). O `.env` nunca vai para o
repositório.

### Executando

No Windows, troque `python3` por `python`.

```bash
# Testes
python3 -m pytest tests -q

# Uma checagem no terminal
python3 -m factcheck_mvp.cli checar "café cura câncer"

# Passo a passo da última checagem (lido de runs/)
python3 -m factcheck_mvp.cli trace last

# Página e interface de programação em http://127.0.0.1:8000
uvicorn factcheck_mvp.api:app --port 8000

# Robô do Telegram (no Windows também dá para usar rodar_bot.bat)
python3 -m factcheck_mvp.telegram_bot
```

### Avaliação do sistema

```bash
python3 -m eval.run                      # avalia os casos rotulados, sem rede (replay das chamadas gravadas)
python3 -m eval.run --modo record        # grava as chamadas que faltam (usa rede e chaves)
python3 -m eval.run --gate               # falha se o resultado piorar em relação ao baseline
```

O relatório de cada rodada fica em `eval/resultados/`. Detalhes em [`eval/README.md`](eval/README.md).

### Treino do modelo próprio

O pipeline completo de treino está em [`entrega/treinamento_modelo/`](entrega/treinamento_modelo/) e roda com
`./treinar.sh` (recomenda-se GPU). Veja o README da pasta.

---

## 3. Organização das pastas

```
Checa-AI/
├── factcheck_mvp/            A aplicação
│   ├── pipeline.py           Orquestra as etapas da checagem
│   ├── telegram_bot.py       Robô do Telegram
│   ├── api.py                Página na internet e interface de programação (FastAPI)
│   ├── cli.py                Linha de comando (checar, trace, runs)
│   ├── afirmacoes.py         Extração das afirmações verificáveis
│   ├── indice.py             Busca na base de checagens (BM25)
│   ├── ingestor.py           Coleta das checagens das agências (RSS, WordPress, mapas de site)
│   ├── serpapi_layer.py      Busca na web
│   ├── agente.py             Planejamento e execução das buscas
│   ├── extracao.py           Extração do corpo das páginas
│   ├── juiz_llm.py           Julgamento das fontes pelo modelo de linguagem
│   ├── corroboracao.py       Agrupamento de fontes independentes
│   ├── decisao.py            Regra fixa que calcula a propensão
│   ├── agregador.py          Monta a resposta e verifica a neutralidade
│   ├── modelo_fake.py        Modelo próprio (BERTimbau) como sinal de estilo
│   ├── llm.py                Cliente único de modelo de linguagem (OpenRouter → LLM local)
│   ├── telemetria.py         Registro de cada execução em runs/
│   ├── replay.py             Gravação e reprodução de chamadas externas
│   └── data/                 Base de checagens (checagens.jsonl.gz), catálogo de portais e tabelas de selos
├── tests/                    Testes automatizados (pytest)
├── eval/                     Avaliação do sistema: casos rotulados, baseline e registro das iterações (ITERACOES.md)
├── avaliacao/                Conjunto de referência (golden set) e script de avaliação
├── scripts/                  Benchmark do índice, simulação de usuário e utilitários
├── docs/                     Próximos passos, contrato de telemetria e revisões técnicas
├── entrega/                  Entregáveis do desafio (tabela abaixo)
├── .github/workflows/        Atualização diária da base de checagens
├── br_news_crawler.py        Crawler de portais de notícias (Crawl4AI)
├── requirements-mvp.txt      Dependências da aplicação
├── requirements-modelo.txt   Dependências extras para ligar o BERTimbau
├── .env.mvp.example          Modelo de configuração, com todas as variáveis
└── rodar_bot.bat             Atalho para subir o robô no Windows
```

Pastas geradas localmente e fora do repositório: `runs/` (registro de cada execução), `eval/resultados/` e
`eval/cassettes/` (chamadas gravadas) e `reports/`.

### Entregáveis (`entrega/`)

| Item | Onde está |
|---|---|
| Requisitos funcionais e não funcionais | [`entrega/requisitos/`](entrega/requisitos/) (`requisitos.md` e PDF) |
| Organização, Scrum e papéis | [`entrega/organizacao/`](entrega/organizacao/) (`organizacao.md` e PDF) |
| Guiding Questions | [`entrega/guiding_questions/`](entrega/guiding_questions/) |
| Análise exploratória dos dados (EDA) | [`entrega/EDA/`](entrega/EDA/) |
| Dataset | [`entrega/dataset/`](entrega/dataset/) |
| Treinamento do modelo | [`entrega/treinamento_modelo/`](entrega/treinamento_modelo/) |
| Relatório técnico do modelo (FakenewsBR v6 + BERTimbau) | [`entrega/relatorico_tecnico/`](entrega/relatorico_tecnico/) |
| Desenho do fluxo e arquitetura da aplicação | [`entrega/fluxo_aplicacao/`](entrega/fluxo_aplicacao/) (`FLUXO_APLICACAO.md` e HTML) |

---

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
