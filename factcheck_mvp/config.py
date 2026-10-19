"""Configuração via ambiente (.env). Nenhum segredo tem default utilizável."""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool = False) -> bool:
    bruto = os.getenv(name, "").strip().lower()
    if not bruto:
        return default
    return bruto in ("1", "true", "on", "sim", "yes")


TELEGRAM_TOKEN = _get("TELEGRAM_TOKEN")
SERPAPI_KEY = _get("SERPAPI_KEY")
SERPAPI_TIMEOUT_S = _int("SERPAPI_TIMEOUT_S", 15)  # por tentativa; timeout/conexão ganha 1 nova tentativa
# Google Fact Check Tools API (ClaimReview de várias agências; base extra, só com INDICE_CHECAGENS=1).
# Vazio = desligado. Chave do Google Cloud com a "Fact Check Tools API" habilitada.
FACTCHECK_API_KEY = _get("GOOGLE_FACTCHECK_API_KEY")
FACTCHECK_MAX_ITENS = _int("FACTCHECK_MAX_ITENS", 5)
FACTCHECK_TIMEOUT_S = _int("FACTCHECK_TIMEOUT_S", 8)
OPENROUTER_API_KEY = _get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = _get("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash")
OPENROUTER_FALLBACK_MODEL = _get("OPENROUTER_FALLBACK_MODEL", "google/gemma-4-26b-a4b-it:free")
OPENROUTER_MODEL_JUIZ = _get("OPENROUTER_MODEL_JUIZ")  # vazio = mesmo modelo dos demais passos
# Roteamento de provider (ex: StreamLake fp8 p/ deepseek-v4-flash).
# Lista separada por vírgula; vazio = roteamento padrão da OpenRouter.
OPENROUTER_PROVIDER_ORDER = _get("OPENROUTER_PROVIDER_ORDER", "StreamLake")
OPENROUTER_TIMEOUT_S = _int("OPENROUTER_TIMEOUT_S", 30)
# Padrões de linguagem via LLM (sinal de estilo, fora do nível). Desligado por padrão desde a auditoria de 13/10.
PADROES_LLM = os.getenv("PADROES_LLM", "0").strip().lower() in ("1", "true", "on", "sim", "yes")
OPENROUTER_MAX_TOKENS = _int("OPENROUTER_MAX_TOKENS", 600)
# TypeSafe Jev (Decisions API): 1 request = 3 noul (~centenas de ms).
# Uso restrito à classificação de schema (descoberta_site); o julgamento de
# notícias é do LLM-juiz (juiz_llm.py).
JEV_TIMEOUT_S = _int("JEV_TIMEOUT_S", 12)
# Juiz N×1: avalia cada relevante 1:1 (manchete+corpo) sem corte prévio.
# JUIZ_MAX_NOTICIAS é teto de EXIBIÇÃO em `pipeline._fontes`, nunca de avaliação —
# com piso 10: valores abaixo de 10 não cortam a exibição (compat com testes
# legados que fixam 2 e exigem a 3ª fonte no relatório); na prática só eleva o
# teto acima de 10.
JUIZ_MAX_NOTICIAS = _int("JUIZ_MAX_NOTICIAS", 10)
# Juiz de 4 classes (fase 2): itens por chamada, tamanho do trecho, tokens de saída
# (o modelo local é de raciocínio: reserve folga) e limiar da citação verificada.
JUIZ_LOTE = _int("JUIZ_LOTE", 5)
JUIZ_TRECHO_MAX = _int("JUIZ_TRECHO_MAX", 2500)
JUIZ_MAX_TOKENS = _int("JUIZ_MAX_TOKENS", 4000)
JUIZ_CITACAO_MIN = _float("JUIZ_CITACAO_MIN", 0.9)
# Teto total do julgamento 1:1 (N avaliações por consulta): timeout/cap preserva
# o parcial já avaliado (ver `pipeline._julgar`); nunca descarta tudo.
JUIZ_TIMEOUT_TOTAL_S = _int("JUIZ_TIMEOUT_TOTAL_S", 600)
# Lotes do juiz em paralelo (o Studio local serve 1 slot bem; OpenRouter aguenta mais)
JUIZ_CONCORRENCIA = _int("JUIZ_CONCORRENCIA", 1)
# Timeout de 1 chamada LLM (local de raciocínio + prompt de ~5k tokens é lento)
LLM_TIMEOUT_S = _int("LLM_TIMEOUT_S", 240)
# LLM local de raciocínio: 0 (padrão) pula o <think> via prefill; 1 deixa raciocinar (lento)
LLM_LOCAL_RACIOCINIO = _get("LLM_LOCAL_RACIOCINIO", "0").strip().lower() in ("1", "true", "sim", "on")
UNSLOTH_BASE_URL = _get("UNSLOTH_BASE_URL", "http://127.0.0.1:8888/v1")
UNSLOTH_MODEL_NAME = _get("UNSLOTH_MODEL_NAME")
UNSLOTH_API_KEY = _get("UNSLOTH_API_KEY", "not-needed")
LAYA_THRESHOLD = _float("LAYA_THRESHOLD", 0.80)
LAYA_MODEL = _get("LAYA_MODEL", "auto")
LAYA_DEVICE = _get("LAYA_DEVICE", "")  # vazio = cpu (seguro); cuda|mps só com teste local
RELEVANCIA_MIN = _float("RELEVANCIA_MIN", 0.30)
INDICE_SCORE_MIN = _float("INDICE_SCORE_MIN", 1.0)
MAX_AFIRMACOES = _int("MAX_AFIRMACOES", 3)
MAX_EVIDENCIAS = _int("MAX_EVIDENCIAS", 5)
CACHE_SERPAPI_TTL = _int("CACHE_SERPAPI_TTL", 3600)
FAKE_MODEL_PATH = _get("FAKE_MODEL_PATH")  # vazio = mock explícito (RF08 até o modelo real)
# Modelo real só opina em texto longo: em manchete solta o BERTimbau v6 erra
# por formato (curto → fake). Confiança baixa: é um sinal a mais, não o principal.
FAKE_MODEL_MIN_PALAVRAS = _int("FAKE_MODEL_MIN_PALAVRAS", 80)
FAKE_MODEL_CONFIANCA = _float("FAKE_MODEL_CONFIANCA", 0.5)
# Cache de relatórios completos (mesmo texto repetido não refaz busca/LLM).
RESULT_CACHE_TTL = _int("RESULT_CACHE_TTL", 1800)
RESULT_CACHE_MAX = _int("RESULT_CACHE_MAX", 256)
# Feedback 👍/👎 do bot (JSONL local; vira dado rotulado p/ calibrar pesos).
FEEDBACK_PATH = _get("FEEDBACK_PATH", "")
# Safety / cost caps (não quebram bot+API: só degradam p/ parcial/pulada)
SERPAPI_DAILY_CAP = _int("SERPAPI_DAILY_CAP", 100)
# Busca web (fábrica em busca_web.py). `serpapi` = padrão até o eval aprovar o `ddgs` (ver docs/superpowers).
BUSCA_PROVEDOR = _get("BUSCA_PROVEDOR", "serpapi").strip().lower()
# 1 = a busca web está ligada (no ddgs, não depende de chave); 0 = a descoberta fica pulada.
BUSCA_WEB = _bool("BUSCA_WEB", True)
# Teto diário e TTL do cache de busca: nomes neutros; sem eles, valem os SERPAPI_* de sempre.
BUSCA_DAILY_CAP = _int("BUSCA_DAILY_CAP", SERPAPI_DAILY_CAP)
CACHE_BUSCA_TTL = _int("CACHE_BUSCA_TTL", CACHE_SERPAPI_TTL)
# ddgs: backends em ORDEM, um por chamada (nunca `auto`: sorteia motores e quebra o replay). Passa ao próximo
# quando o atual falha, vem vazio ou limita a taxa. Só motores que o ddgs habilita (backend desligado é pulado):
# no 9.16 o `bing` de TEXTO vem desligado (`disabled = True`); o de notícias funciona.
DDGS_TEXT_BACKENDS = _get("DDGS_TEXT_BACKENDS", "duckduckgo,yahoo,brave,google")
DDGS_NEWS_BACKENDS = _get("DDGS_NEWS_BACKENDS", "bing,duckduckgo,yahoo")
DDGS_REGIAO = _get("DDGS_REGIAO", "br-pt")
DDGS_SAFESEARCH = _get("DDGS_SAFESEARCH", "moderate")
DDGS_TIMEOUT_S = _int("DDGS_TIMEOUT_S", 10)  # por tentativa; timeout ganha 1 nova tentativa
# Buscas VIVAS por segundo no processo (cassete não espera). 0 = sem limite.
DDGS_RPS = _float("DDGS_RPS", 1.0)
DDGS_PROXY = _get("DDGS_PROXY", "")  # vazio = conexão direta
# 1 = cada busca orgânica sem `site:` também pede notícias e usa as 3 primeiras como top stories.
DDGS_TOP_STORIES = _bool("DDGS_TOP_STORIES", True)
# Palavras mantidas na consulta (o limite de 32 é do Google; o ddgs aceita o mesmo corte).
DDGS_MAX_PALAVRAS = _int("DDGS_MAX_PALAVRAS", 32)
# ddgs limitado em TODOS os backends: 1 = a busca vai para a SerpAPI (se houver SERPAPI_KEY; gasta cota).
# O eval desliga (ENV_PADRAO), para não misturar provedores na medição do ddgs.
BUSCA_FALLBACK_SERPAPI = _bool("BUSCA_FALLBACK_SERPAPI", True)
# Depois de limitar em todos os backends, o ddgs fica estes segundos sem buscas (vão direto à reserva). 0 = sem pausa.
DDGS_PAUSA_BLOQUEIO_S = _int("DDGS_PAUSA_BLOQUEIO_S", 300)
# Espera (s) após rate limit de um backend, antes do próximo.
DDGS_ESPERA_RATELIMIT_S = _float("DDGS_ESPERA_RATELIMIT_S", 2.0)
# Estratégia no orgânico: `agente` (padrão: onda 1 determinística → extração → juiz →
# crítico pós-juiz com onda extra reescrita por LLM; ver agente.py), `simples` (crua +
# dirigida leve), `avancada` (crua + site: das agências do catálogo) ou `ambas` (união).
# Motor: `google_news` é o padrão desde a Missão G (o que foi medido); as consultas com `site:` vão ao
# orgânico (BUSCA_SITE_NO_ORGANICO). `google` = tudo no orgânico.
SERP_ENGINE = _get("SERP_ENGINE", "google_news")
SERP_ESTRATEGIA = _get("SERP_ESTRATEGIA", "agente")
# Teto de buscas SerpAPI do agente POR REQUISIÇÃO (onda 1 + ondas extras). Padrão 9 =
# 3 afirmações x (2 da onda 1 + 1 extra). A onda 1 reserva n_afirmações x AGENTE_MAX_ONDAS_EXTRAS.
AGENTE_MAX_BUSCAS = _int("AGENTE_MAX_BUSCAS", 9)
# Ondas extras por afirmação (o crítico pós-juiz decide se gasta; 0 = só onda 1).
AGENTE_MAX_ONDAS_EXTRAS = _int("AGENTE_MAX_ONDAS_EXTRAS", 1)
# Teto de tempo de UMA onda do agente (o que voltou antes do teto é preservado).
AGENTE_TIMEOUT_S = _int("AGENTE_TIMEOUT_S", 60)
# Corte de URLs por afirmação (round-robin preservado; a seleção p/ o juiz vem depois).
AGENTE_MAX_POR_AFIRMACAO = _int("AGENTE_MAX_POR_AFIRMACAO", 12)
# Hosts extras de agências de checagem além das derivadas do catálogo (vírgula).
SERP_SITES_EXTRAS = _get("SERP_SITES_EXTRAS", "")
# Onda 1, parte (b): "or" = 1 consulta com (site:a OR site:b …) de todas as agências que couberem;
# "separado" = 1 consulta `site:` por agência, nas AGENTE_SITES_SEPARADOS primeiras do catálogo (D1)
AGENTE_SITES_MODO = _get("AGENTE_SITES_MODO", "or").strip().lower()
AGENTE_SITES_SEPARADOS = _int("AGENTE_SITES_SEPARADOS", 3)
# Teto por afirmação p/ crawl+avaliação (N×1: cada relevante). Literal = 12
# (= `AGENTE_MAX_POR_AFIRMACAO`); literal (não alias no import) p/ não congelar
# quando o env muda em runtime — o pipeline lê `AGENTE_MAX_POR_AFIRMACAO` direto.
DEEP_CRAWL_MAX_PAGES = _int("DEEP_CRAWL_MAX_PAGES", 12)
# Teto total de páginas lidas por consulta (todas as afirmações) antes do juiz.
# Crawl-primeiro N×1: cobre cada relevante — 3 afirmações × teto por afirmação = 36.
# Literais (não `MAX_AFIRMACOES * AGENTE_MAX_POR_AFIRMACAO` no import): o pipeline
# resolve `total = max(DEEP_CRAWL_TOTAL, 3 × por_afirm)` em runtime p/ respeitar
# env/monkeypatch e sempre cobrir cada relevante.
DEEP_CRAWL_TOTAL = _int("DEEP_CRAWL_TOTAL", 36)
# Confiabilidade (confiabilidade.py): fora do catálogo, "site muito acessado" = entre os
# N domínios mais acessados da lista Tranco (data/trafego_tranco.csv.gz guarda até 200 mil).
TRAFEGO_RANK_MAX = _int("TRAFEGO_RANK_MAX", 200_000)
# Teto do deep crawl por consulta (N×1): timeout/cap preserva o parcial já lido
# (ver `pipeline._ler` + `aprofundar.aprofundar`); nunca descarta tudo.
DEEP_CRAWL_TIMEOUT_S = _int("DEEP_CRAWL_TIMEOUT_S", 15)
DEEP_CRAWL_MAX_BYTES = _int("DEEP_CRAWL_MAX_BYTES", 5_000_000)
API_RATE_LIMIT_PER_MIN = _int("API_RATE_LIMIT_PER_MIN", 30)
# Descoberta de catálogo (modo descoberta: tetos MENORES que o deep crawl)
DISCOVERY_MAX_SITES = _int("DISCOVERY_MAX_SITES", 2)
DISCOVERY_TIMEOUT_S = _int("DISCOVERY_TIMEOUT_S", 8)
DISCOVERY_MAX_BYTES = _int("DISCOVERY_MAX_BYTES", 5_000_000)
# Avisos de configuração inválida (valor ≤ 0 ou não inteiro → default). O pipeline grava cada
# aviso como fallback("config") no trace da consulta, em vez de falhar o bot por um env ruim.
AVISOS_CONFIG: list = []


def _janela_positiva(name: str, default: int, avisos: list | None = None) -> int:
    """Inteiro > 0 (dias) lido do ambiente. Vazio → default em silêncio; inválido → default + aviso."""
    bruto = os.getenv(name, "")
    if not bruto.strip():
        return default
    try:
        valor = int(bruto)
    except (TypeError, ValueError):
        valor = 0
    if valor <= 0:
        (AVISOS_CONFIG if avisos is None else avisos).append(
            f"{name}={bruto!r} inválido (esperado inteiro > 0); usando {default}")
        return default
    return valor


# E4 relevância temporal: janelas (dias) por marcador; lidas em aplicabilidade.janela_temporal.
E4_JANELA_HOJE = _janela_positiva("E4_JANELA_HOJE", 2)
E4_JANELA_ONTEM = _janela_positiva("E4_JANELA_ONTEM", 3)
E4_JANELA_SEMANA = _janela_positiva("E4_JANELA_SEMANA", 8)
E4_JANELA_ANTEONTEM = _janela_positiva("E4_JANELA_ANTEONTEM", 4)
E4_JANELA_SEMANA_PASSADA = _janela_positiva("E4_JANELA_SEMANA_PASSADA", 15)
E4_JANELA_MES = _janela_positiva("E4_JANELA_MES", 32)
# Data sem ano ("dia 8", "8 de março") só ancora o evento se a ocorrência mais recente estiver a até
# este número de dias da referência (aplicabilidade.marco_do_evento). Regra geral: texto de checagem
# fala de fato recente; data sem ano a mais de ~2 meses para trás tende a ser outra data (aniversário,
# data histórica) e a inferência do ano erra. 60 dias ≈ o dobro da janela de mês (E4_JANELA_MES = 32).
E4_MARCO_MAX_DIAS = _janela_positiva("E4_MARCO_MAX_DIAS", 60)
# Cascata de extração: ReaderLM-v2 como penúltimo nível (desligado por padrão; servidor próprio)
EXTRACAO_READERLM = _get("EXTRACAO_READERLM", "0")
READERLM_BASE_URL = _get("READERLM_BASE_URL", "http://127.0.0.1:8889/v1")

# Modo de avaliação (auditoria E, A1): só a API subida para uma simulação liga isto. Habilita os campos
# `eval_excluir_urls` (fonte deixada de fora) e `eval_repeticao` (juiz sem cache) da EntradaConsulta; sem
# ele esses campos são ignorados (com `fallback onde=eval`). Nunca ligar em produção.
EVAL_MODO = _bool("EVAL_MODO", False)
# Missão F / A4: seleção do trecho do juiz. "novo" (padrão) = título + lide + conclusão/veredito + frases com
# termos, sem boilerplate (trecho_juiz.py); "antigo" = lide de 2 frases + frases com termos (p/ medir antes/depois).
JUIZ_TRECHO_MODO = _get("JUIZ_TRECHO_MODO", "novo").strip().lower()
# Missão F / A2: sintetizador por afirmação (sintetizador.py). Uma chamada LLM por afirmação relê todos os
# itens julgados e pode REBAIXAR o nível (para media/indeterminada) ou sinalizar "buscar_mais"; nunca sobe
# o nível nem muda a direção (trava no código). Padrão ligado desde a Missão G (não piorou na medição de 14/10; 0 para desligar).
SINTETIZADOR = _get("SINTETIZADOR", "1").strip().lower() in ("1", "true", "sim", "on")
SINTETIZADOR_MAX_ITENS = _int("SINTETIZADOR_MAX_ITENS", 12)    # itens julgados enviados por afirmação
SINTETIZADOR_MAX_TOKENS = _int("SINTETIZADOR_MAX_TOKENS", 1200)
SINTETIZADOR_TIMEOUT_S = _int("SINTETIZADOR_TIMEOUT_S", 90)    # 1 chamada LLM (por afirmação)

# Missão F / A5: planejador de busca (factcheck_mvp/planejador_busca.py). Padrão ligado desde a Missão G (não piorou na medição de 14/10; 0 para desligar). Com 0 a busca é a de
# antes (mesmas consultas, mesmo motor, mesmo número de ondas). Ligado: relaxa consulta vazia, manda `site:` ao
# Google orgânico, lê mais resultados quando os primeiros são fora do tema e usa o orçamento que sobra.
BUSCA_PLANEJADOR = _bool("BUSCA_PLANEJADOR", True)
# Rodadas de relaxamento por onda (cada rodada = 1 busca por consulta vazia, dentro do orçamento do caso).
BUSCA_RELAXAR_RODADAS = _int("BUSCA_RELAXAR_RODADAS", 2)
# Teto de resultados lidos por busca ao "ler mais" (a leitura normal é ORGANICOS_POR_BUSCA = 8).
BUSCA_LER_MAX = _int("BUSCA_LER_MAX", 16)
# Fração mínima de páginas NAO_TRATA (sem nenhuma postura) para considerar os primeiros resultados fora do tema.
BUSCA_FORA_TEMA_FRACAO = _float("BUSCA_FORA_TEMA_FRACAO", 0.5)
# Ondas extras por afirmação com o planejador (o padrão sem ele é AGENTE_MAX_ONDAS_EXTRAS = 1).
BUSCA_EXTRAS_MAX = _int("BUSCA_EXTRAS_MAX", 3)
# Missão F / A6: trava de similaridade no atalho do índice (trava_indice.py). Com 1 só cluster decidindo
# por selo do índice, exige similaridade mínima (Dice, 0..1) entre a alegação checada e o núcleo da
# afirmação; abaixo do limiar o nível tem teto "media". 0,6 = o `cobertura_min` do próprio índice.
INDICE_TRAVA_SIMILARIDADE = _get("INDICE_TRAVA_SIMILARIDADE", "1").strip().lower() in ("1", "true", "sim", "on")
INDICE_TRAVA_SIM_MIN = _float("INDICE_TRAVA_SIM_MIN", 0.6)
# Missão F / item 7 (Extrator): limpeza determinística pós-LLM do núcleo e da consulta (tira marcadores
# temporais, moldura de entrega e palavras-ruído que zeram o AND do Google News). Muda consultas. Padrão ligado desde a Missão G (não piorou na medição de 14/10; 0 para desligar).
EXTRATOR_LIMPEZA = _bool("EXTRATOR_LIMPEZA", True)
# Missão F / A3 — autoconsistência do juiz: quando UM julgamento SUSTENTA/REFUTA decide o nível (um só
# cluster com voto), o item é rejulgado K-1 vezes sem cache (temperatura > 0 + seed por repetição) e vale a
# maioria; se as classes divergirem na direção, o item vira RELATA_SEM_ENDOSSO. Padrão ligado desde a Missão G (não piorou na medição de 14/10; 0 para desligar).
JUIZ_AUTOCONSISTENCIA = _get("JUIZ_AUTOCONSISTENCIA", "1").strip().lower() in ("1", "true", "sim", "on")
JUIZ_AUTOCONSISTENCIA_K = _int("JUIZ_AUTOCONSISTENCIA_K", 3)  # julgamentos no total (o original + K-1)
JUIZ_AUTOCONSISTENCIA_TEMP = _float("JUIZ_AUTOCONSISTENCIA_TEMP", 0.5)  # temperatura das repetições
# Missão G / item 2: reformulação de consulta do agente. O Haiku raciocina antes de responder e o raciocínio conta
# nos max_tokens: com 300, gastou 258 e a consulta saiu truncada. Esforço via `reasoning.effort` do OpenRouter.
AGENTE_REFORMULAR_MAX_TOKENS = _int("AGENTE_REFORMULAR_MAX_TOKENS", 2000)
AGENTE_REFORMULAR_ESFORCO = _get("AGENTE_REFORMULAR_ESFORCO", "high").strip().lower()
# Missão G / item 6: consulta com `site:` vai ao Google orgânico; as puras seguem em SERP_ENGINE (Google News).
# Só a troca de motor do A5 (sem relaxar/ler mais/ondas extras): não acrescenta buscas. Padrão ligado desde a Missão G (não piorou na medição de 14/10; 0 para desligar).
BUSCA_SITE_NO_ORGANICO = _bool("BUSCA_SITE_NO_ORGANICO", True)
