"""Busca web com o `ddgs` (metasearch sem chave): mesmo contrato do SerpAPIClient.

`DDGSClient.buscar_ex(params)` aceita os params da camada (`q`, `engine`, `num`) e devolve o payload no
formato SerpAPI (`organic_results` | `news_results`, `top_stories`, `search_metadata`), para que agente,
planejador e `normalizar_item` não mudem. `google` -> `DDGS.text()`; `google_news` -> `DDGS.news()`;
`google_scholar` não existe no ddgs (cai em text, com telemetria.fallback).

Backends fixos e ordenados (nunca `auto`): um por chamada, na ordem de DDGS_TEXT_BACKENDS /
DDGS_NEWS_BACKENDS; passa ao próximo quando o atual falha, vem vazio ou limita a taxa. Cada chamada
live vai por `replay.busca_ddgs` (cassete por backend). Rate limit não é gravado. Nunca levanta.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException

from . import config, replay, telemetria
from .busca_web import ClienteBusca
from .serpapi_layer import ENGINES, RESULT_KEY, ResultadoBusca, limitar_palavras

log = logging.getLogger("factcheck.ddgs")

DDGS_ESPERA_NOVA_TENTATIVA_S = 1.5  # timeout de um backend: 1 nova tentativa nele, depois o próximo
TOP_STORIES_DDGS = 3  # mesmo corte do agente (TOP_STORIES_POR_BUSCA)
FRACAO_TIMEOUT_DESCARTE = 0.9  # "No results found" depois de 90% do DDGS_TIMEOUT_S = motor lento descartado
_LIMITE = re.compile(r"rate.?limit|too many requests|\b429\b", re.I)
_SEM_RESULTADO = re.compile(r"no results found", re.I)
_SUFIXO_FONTE = re.compile(r"\s+on\s+[\w.-]+\.[a-z]{2,}$", re.I)  # "Jornal on MSN.com" (Bing)
_limite_lock = threading.Lock()
_ultima_busca = 0.0
_pausa_lock = threading.Lock()
_pausa_ate = 0.0  # monotonic: até quando o ddgs fica em pausa depois de limitar em todos os backends


_HTTP_BLOQUEIO = (202, 403, 429)  # 202 = página "anomaly"/captcha do DuckDuckGo; 403/429 = Google, Brave…
# Versões do ddgs cuja `BaseSearchEngine.request` foi conferida (a troca abaixo copia a implementação dela).
DDGS_VERSOES_TESTADAS = ("9.16.0",)


def _instalar_deteccao_bloqueio() -> bool:
    """O ddgs (9.16) devolve None quando o motor responde HTTP != 200, e o erro chega como "No results found":
    bloqueio de IP parecia busca vazia (medido em 19/10: DuckDuckGo 202, Google e Brave 429). Troca o
    `request` dos motores para levantar RatelimitException com o status; o resto do ddgs fica igual.
    Só numa versão testada: em outra, a cópia poderia divergir da lib (fallback e nada é trocado)."""
    import ddgs as _ddgs
    versao = str(getattr(_ddgs, "__version__", "?"))
    try:
        from ddgs.base import BaseSearchEngine
    except ImportError as e:  # outra versão do ddgs: sem detecção, bloqueio volta a parecer vazio
        telemetria.fallback("ddgs", f"detecção de bloqueio indisponível: {type(e).__name__}: {e}")
        return False
    if getattr(BaseSearchEngine.request, "_crosscheck", False):
        return True
    if versao not in DDGS_VERSOES_TESTADAS:
        telemetria.fallback("ddgs", f"detecção de bloqueio desligada: ddgs {versao} não testado "
                                    f"({', '.join(DDGS_VERSOES_TESTADAS)}); bloqueio pode parecer busca vazia")
        return False

    def request(self: Any, *args: Any, **kwargs: Any) -> Any:
        resp = self.http_client.request(*args, **kwargs)
        if resp.status_code == 200:
            return resp.text
        if resp.status_code in _HTTP_BLOQUEIO:
            raise RatelimitException(f"ratelimit: {getattr(self, 'name', '?')} HTTP {resp.status_code}")
        return None

    request._crosscheck = True  # type: ignore[attr-defined]
    BaseSearchEngine.request = request  # type: ignore[method-assign]
    return True


_instalar_deteccao_bloqueio()


def _dormir(segundos: float) -> None:
    if segundos > 0:
        time.sleep(segundos)


def _lista(texto: str) -> List[str]:
    return [b.strip().lower() for b in (texto or "").split(",") if b.strip()]


_avisados: set = set()  # (funcao, backend) indisponíveis já avisados neste processo


def _habilitados(funcao: str) -> Optional[set]:
    """Motores que o ddgs instalado habilita para `funcao` (text|news), ou None se não der para saber.
    Ex.: no 9.16 o `bing` de texto vem com `disabled = True` (só o de notícias funciona)."""
    try:
        from ddgs.engines import ENGINES
        return set(ENGINES.get(funcao) or {})
    except Exception as e:  # registro de motores mudou: segue sem filtrar (o ddgs avisa)
        telemetria.fallback("ddgs.cadeia", f"lista de motores indisponível: {type(e).__name__}: {e}")
        return None


def backends_validos(funcao: str, configurados: List[str]) -> List[str]:
    """Só os backends configurados que o ddgs habilita, na ordem. Backend inexistente/desligado NUNCA chega
    à lib: com nenhum válido, o ddgs cai em `backend='auto'` (sorteia motores, quebra o replay e o
    `search_metadata.backend` mentiria). Cada backend descartado é avisado uma vez por processo."""
    hab = _habilitados(funcao)
    if hab is None:
        return list(configurados)
    out = []
    for b in configurados:
        if b in hab:
            out.append(b)
        elif (funcao, b) not in _avisados:
            _avisados.add((funcao, b))
            telemetria.fallback("ddgs.cadeia", f"{b}: backend de {funcao} inexistente ou desligado no ddgs "
                                               f"(habilitados: {', '.join(sorted(hab))}): pulado")
    return out


def _classificar(e: Exception) -> str:
    """ratelimit | timeout | vazio | erro. O ddgs embrulha o erro de um motor em DDGSException: a mensagem conta."""
    msg = str(e)
    if isinstance(e, RatelimitException) or _LIMITE.search(msg):
        return "ratelimit"
    if isinstance(e, TimeoutException) or "timed out" in msg.lower():
        return "timeout"
    if _SEM_RESULTADO.search(msg):
        return "vazio"
    return "erro"


def _host(url: str) -> str:
    try:
        h = urlsplit(url or "").hostname or ""
    except ValueError:
        h = ""
    return h[4:] if h.startswith("www.") else h


def _nome_fonte(fonte: str, url: str) -> str:
    """Bing e Yahoo devolvem "Jornal on MSN.com": fica só o nome; sem nome, o host da URL."""
    return _SUFIXO_FONTE.sub("", str(fonte or "")).strip() or _host(url)


def _organicos(resultados: List[Dict[str, Any]], backend: str = "") -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in resultados:
        link = str(r.get("href") or r.get("url") or "")
        if link:
            out.append({"position": len(out) + 1, "title": r.get("title") or "", "link": link,
                        "snippet": r.get("body") or "", "displayed_link": _host(link),
                        "_origem": f"ddgs:{backend}" if backend else "ddgs"})
    return out


def _noticias(resultados: List[Dict[str, Any]], backend: str = "") -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in resultados:
        link = str(r.get("url") or r.get("href") or "")
        if link:
            out.append({"position": len(out) + 1, "title": r.get("title") or "", "link": link,
                        "snippet": r.get("body") or "", "iso_date": r.get("date") or None,
                        "source": {"name": _nome_fonte(r.get("source") or "", link)},
                        "thumbnail": r.get("image") or None,
                        "_origem": f"ddgs:{backend}" if backend else "ddgs"})
    return out


def _top_stories(noticias: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mesma forma de um orgânico (source em texto, data ISO em `date`), como o SerpAPI devolve."""
    return [{"position": n["position"], "title": n["title"], "link": n["link"], "snippet": n["snippet"],
             "source": n["source"]["name"], "date": n["iso_date"], "thumbnail": n["thumbnail"],
             "_origem": n["_origem"]}
            for n in noticias[:TOP_STORIES_DDGS]]


# `(site:a OR site:b …)` de `query_agencias`: com parênteses a busca devolvia zero; sem eles, só as agências pedidas
# (teste live de 19/10, respondido pelo backend `auto` do ddgs: repetir por backend com o IP limpo). O grupo vira `site:a OR site:b …` no fim da consulta, que é onde ele já fica.
_GRUPO_SITES = re.compile(r"\(\s*(site:\S+(?:\s+OR\s+site:\S+)*)\s*\)", re.I)


def adaptar_consulta(q: str) -> str:
    """Consulta da camada (sintaxe Google) -> sintaxe aceita pelos backends do ddgs."""
    return " ".join(_GRUPO_SITES.sub(lambda m: m.group(1), q or "").split())


def _num(params: Dict[str, Any]) -> int:
    try:
        return max(1, int(params.get("num") or 10))
    except (TypeError, ValueError):
        return 10


def _meta(dados: Dict[str, Any], backend: str, engine: str) -> Dict[str, Any]:
    return {"created_at": dados.get("criado_em"), "provedor": "ddgs", "backend": backend, "engine": engine}


def _esperar_limite() -> None:
    """Espaça as buscas VIVAS ao ddgs (DDGS_RPS, global ao processo). Cassete não passa por aqui."""
    global _ultima_busca
    rps = float(config.DDGS_RPS or 0)
    if rps <= 0:
        return
    with _limite_lock:
        slot = max(time.monotonic(), _ultima_busca + 1.0 / rps)
        _ultima_busca = slot
    espera = slot - time.monotonic()
    if espera > 0:
        telemetria.evento("rate_limit", alvo="ddgs", espera_s=round(espera, 2))
        _dormir(espera)


def _ao_vivo(funcao: str, q: str, backend: str, num: int) -> Callable[[], Dict[str, Any]]:
    """Uma chamada real a 1 backend -> {"criado_em", "resultados"}. Rate limit vira BuscaLimitada."""
    def vivo() -> Dict[str, Any]:
        _esperar_limite()
        from ddgs import DDGS  # no momento da chamada: testes trocam ddgs.DDGS por um fake
        cliente = DDGS(proxy=(config.DDGS_PROXY or None), timeout=config.DDGS_TIMEOUT_S)
        kw = {"region": config.DDGS_REGIAO, "safesearch": config.DDGS_SAFESEARCH, "timelimit": None,
              "max_results": num, "page": 1, "backend": backend}
        t0 = time.monotonic()
        try:
            itens = cliente.news(q, **kw) if funcao == "news" else cliente.text(q, **kw)
        except DDGSException as e:
            tipo = _classificar(e)
            dur = time.monotonic() - t0
            if tipo == "vazio" and dur >= FRACAO_TIMEOUT_DESCARTE * float(config.DDGS_TIMEOUT_S or 0) > 0:
                # O ddgs espera `timeout` pelos motores e descarta o que não terminou como "No results found":
                # vazio que só chega no fim do prazo é motor lento (típico sob throttling), não falta de resultado.
                raise TimeoutException(f"{backend}: sem resposta em {dur:.1f}s (o ddgs descartou)") from e
            if tipo == "vazio":
                itens = []
            elif tipo == "ratelimit":
                raise replay.BuscaLimitada(f"{backend}: {telemetria.redigir(str(e))}"[:200]) from e
            else:
                raise
        return {"criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "resultados": list(itens or [])}
    return vivo


def _pausar() -> None:
    """Todos os backends limitaram: o ddgs fica DDGS_PAUSA_BLOQUEIO_S sem buscas (insistir piora o bloqueio)."""
    global _pausa_ate
    with _pausa_lock:
        _pausa_ate = time.monotonic() + max(0.0, float(config.DDGS_PAUSA_BLOQUEIO_S or 0))


def pausa_restante() -> float:
    """Segundos de pausa do ddgs que faltam (0 = livre)."""
    with _pausa_lock:
        return max(0.0, _pausa_ate - time.monotonic())


def resetar_pausa() -> None:
    """Esquece a pausa (testes; um processo novo também começa livre)."""
    global _pausa_ate
    with _pausa_lock:
        _pausa_ate = 0.0


class DDGSClient(ClienteBusca):
    """Mesma interface pública do SerpAPIClient, sem chave. `ativo` = BUSCA_WEB (ou `ativo=` explícito).

    Limitado em todos os backends (ou em pausa depois disso), a busca vai para a SerpAPI quando
    BUSCA_FALLBACK_SERPAPI=1 e há SERPAPI_KEY (`reserva=` troca o cliente de reserva, p/ testes)."""

    def __init__(self, ativo: bool | None = None, ttl: int | None = None, cache_max: int = 200,
                 engine: str | None = None, reserva: Any = None):
        self._ativo_fixo = ativo  # None = BUSCA_WEB; False desliga (testes)
        self._reserva = reserva  # None = SerpAPIClient() na primeira vez que precisar
        self.ttl = config.CACHE_BUSCA_TTL if ttl is None else ttl
        self.engine_default = (engine or getattr(config, "SERP_ENGINE", "google_news") or "google_news")
        if self.engine_default not in ENGINES:
            self.engine_default = "google"
        self._cache_max = cache_max
        self._cache: Dict[str, tuple] = {}  # chave -> (expira_em, payload)
        self._uso_n = 0  # buscas reais no dia (cache não conta)
        self._dia: str = datetime.now(timezone.utc).date().isoformat()
        self.bloqueios_cap = 0
        self.erros_rede = 0
        self.ultimo_motivo = "ok"  # ok|cap|erro|vazio|sem_chave
        self._trava = threading.Lock()  # buscas de uma onda rodam em paralelo (threads)

    @property
    def uso_hoje(self) -> int:
        hoje = datetime.now(timezone.utc).date().isoformat()
        if hoje != self._dia:
            self._dia, self._uso_n = hoje, 0
        return self._uso_n

    @property
    def rodizio(self) -> bool:
        return False  # sem chaves: nada a rodiziar

    @property
    def ativo(self) -> bool:
        if self._ativo_fixo is not None:
            return bool(self._ativo_fixo)
        return bool(config.BUSCA_WEB)

    def engine_de(self, params: Dict[str, Any]) -> str:
        """Motor efetivo: override por query > default do cliente."""
        eng = str((params or {}).get("engine") or self.engine_default).strip().lower()
        return eng if eng in ENGINES else "google"

    def result_key(self, params: Dict[str, Any]) -> str:
        return RESULT_KEY[self.engine_de(params)]

    def _chave(self, params: Dict[str, Any]) -> str:
        return "|".join(f"{k}={params.get(k)}" for k in ("engine", "q", "hl", "gl", "num"))

    def buscar_ex(self, params: Dict[str, Any]) -> ResultadoBusca:
        """Como SerpAPIClient.buscar_ex: motivo e cache DESTA chamada. Nunca levanta."""
        if not self.ativo:
            self.ultimo_motivo = "sem_chave"
            return ResultadoBusca(None, "sem_chave")
        q = limitar_palavras(adaptar_consulta(str(params.get("q") or "")), config.DDGS_MAX_PALAVRAS)
        if not q:
            self.ultimo_motivo = "vazio"
            return ResultadoBusca(None, "vazio")
        agora = time.time()
        chave = self._chave(params)
        with self._trava:
            hit = self._cache.get(chave)
            if hit and hit[0] > agora:
                return ResultadoBusca(hit[1], "ok", cache=True)
            hoje = datetime.now(timezone.utc).date().isoformat()
            if hoje != self._dia:
                self._dia, self._uso_n = hoje, 0
            cap = int(config.BUSCA_DAILY_CAP or 0)
            estourou = bool(cap and self._uso_n >= cap)
            if estourou:
                self.bloqueios_cap += 1
                self.ultimo_motivo = "cap"
        if estourou:
            log.warning("busca ddgs: teto diário atingido (%s/%s): descoberta pausada", self._uso_n, cap)
            telemetria.fallback("ddgs.cap", f"teto diário {self._uso_n}/{cap}")
            return ResultadoBusca(None, "cap")
        resta = pausa_restante()
        if resta > 0:
            return self._pela_reserva(params, f"ratelimit em todos os backends (ddgs em pausa por mais {resta:.0f}s)")
        try:
            payload = self._coletar(params, q)
        except replay.BuscaLimitada as e:
            _pausar()
            return self._pela_reserva(params, f"ratelimit em todos os backends: {e}")
        except Exception as e:  # busca é opcional: falha vira etapa, nunca exceção
            return self._falhou(f"{type(e).__name__}: {e}")
        tem = bool(payload.get(self.result_key(params)) or payload.get("top_stories"))
        with self._trava:
            self._uso_n += 1
            if tem:  # vazios não entram no cache (mesma regra do SerpAPIClient)
                if len(self._cache) >= self._cache_max:
                    mais_antiga = min(self._cache, key=lambda k: self._cache[k][0])
                    del self._cache[mais_antiga]
                self._cache[chave] = (agora + self.ttl, payload)
            self.ultimo_motivo = "ok" if tem else "vazio"
        return ResultadoBusca(payload, "ok" if tem else "vazio")

    def _cliente_reserva(self) -> Any:
        """SerpAPIClient de reserva, ou None (BUSCA_FALLBACK_SERPAPI=0 ou sem SERPAPI_KEY)."""
        if not config.BUSCA_FALLBACK_SERPAPI:
            return None
        with self._trava:  # a onda busca em threads: uma reserva só (um cache, um teto diário)
            if self._reserva is None:
                from .serpapi_layer import SerpAPIClient
                self._reserva = SerpAPIClient()
            reserva = self._reserva
        return reserva if getattr(reserva, "ativo", False) else None

    def _pela_reserva(self, params: Dict[str, Any], motivo: str) -> ResultadoBusca:
        """ddgs limitado: a MESMA consulta (sintaxe Google, sem `adaptar_consulta`) vai à SerpAPI. Sem reserva,
        vira erro com o motivo de bloqueio (é o que o eval conta em `busca_bloqueada`)."""
        reserva = self._cliente_reserva()
        if reserva is None:
            return self._falhou(motivo)
        # Motivo SEM "ratelimit em todos os backends": a busca foi feita (não conta como bloqueada no eval)
        telemetria.fallback("ddgs.reserva", "ddgs limitado, busca feita na serpapi"
                            + (" (em pausa)" if "pausa" in motivo else ""))
        try:
            res = reserva.buscar_ex(params)
        except Exception as e:  # reserva também nunca derruba a busca
            return self._falhou(f"{motivo}; serpapi falhou: {type(e).__name__}: {e}")
        with self._trava:
            self.ultimo_motivo = res.motivo
        return res

    def _falhou(self, detalhe: str) -> ResultadoBusca:
        msg = telemetria.redigir(detalhe)[:300]
        with self._trava:
            self.erros_rede += 1
            self.ultimo_motivo = "erro"
        log.warning("busca ddgs falhou: %s", msg[:150])
        telemetria.fallback("ddgs", msg)
        return ResultadoBusca(None, "erro")

    def _coletar(self, params: Dict[str, Any], q: str) -> Dict[str, Any]:
        """Payload no formato SerpAPI. Levanta só se a busca falhou (ver `_chain`)."""
        eng = self.engine_de(params)
        num = _num(params)
        if eng == "google_scholar":
            telemetria.fallback("ddgs.scholar", "google_scholar sem equivalente no ddgs: busca orgânica (text)")
        if eng == "google_news":
            dados, backend = self._chain("news", q, num)
            return {"news_results": _noticias(dados.get("resultados") or [], backend),
                    "search_metadata": _meta(dados, backend, eng)}
        dados, backend = self._chain("text", q, num)
        payload: Dict[str, Any] = {"organic_results": _organicos(dados.get("resultados") or [], backend),
                                   "search_metadata": _meta(dados, backend, eng)}
        if config.DDGS_TOP_STORIES and eng == "google" and "site:" not in q.lower():
            payload["top_stories"] = self._top(q, num)
        return payload

    def _top(self, q: str, num: int) -> List[Dict[str, Any]]:
        """Top stories = 1 cadeia de news() a mais (extra: sem elas a busca segue). Respeita a pausa e, se as
        notícias também estiverem limitadas em todos os backends, pausa o ddgs como a busca principal."""
        if pausa_restante() > 0:
            return []
        try:
            dados, backend = self._chain("news", q, num)
        except replay.BuscaLimitada:
            _pausar()
            telemetria.fallback("ddgs.top", "top stories indisponíveis: notícias limitadas (ddgs em pausa)")
            return []
        except Exception as e:
            telemetria.fallback("ddgs.top", f"top stories indisponíveis: {type(e).__name__}")
            return []
        return _top_stories(_noticias(dados.get("resultados") or [], backend))

    def _chain(self, funcao: str, q: str, num: int) -> Tuple[Dict[str, Any], str]:
        """Backends em ordem, um por chamada. -> (dados {criado_em, resultados}, backend com resultado | "").

        Vazio limpo em todos -> dados vazios, "". Se nenhum deu resultado e algum FALHOU: levanta
        BuscaLimitada quando TODOS limitaram a taxa ou não responderam (sob bloqueio um motor costuma só ficar
        lento); DDGSException nos demais casos. Desvios entre backends: `fallback(onde="ddgs.cadeia")`."""
        configurados = _lista(config.DDGS_TEXT_BACKENDS if funcao == "text" else config.DDGS_NEWS_BACKENDS)
        backends = backends_validos(funcao, configurados)
        if not backends:
            raise DDGSException(f"nenhum backend de {funcao} disponível (configurados: {', '.join(configurados) or '-'}; "
                                "DDGS_TEXT_BACKENDS / DDGS_NEWS_BACKENDS)")
        falhas: List[str] = []
        limitados = sem_resposta = 0
        ultimo: Dict[str, Any] = {}

        def falhou(backend: str, detalhe: str) -> None:
            """Registra a falha do backend e o rastro do desvio para o próximo (fallback explícito)."""
            falhas.append(f"{backend}: {detalhe}")
            telemetria.fallback("ddgs.cadeia", f"{backend}: {detalhe}: próximo backend")

        for backend in backends:
            busca = {"q": q, "region": config.DDGS_REGIAO, "backend": backend, "max_results": num,
                     "safesearch": config.DDGS_SAFESEARCH, "timelimit": None}
            dados = None
            for tentativa in (1, 2):
                try:
                    dados = replay.busca_ddgs(funcao, busca, _ao_vivo(funcao, q, backend, num))
                    break
                except replay.BuscaLimitada:
                    limitados += 1
                    falhou(backend, "ratelimit")
                    telemetria.evento("rate_limit", alvo="ddgs", backend=backend,
                                      espera_s=config.DDGS_ESPERA_RATELIMIT_S)
                    if backend != backends[-1]:  # sem próximo backend, esperar não adianta
                        _dormir(config.DDGS_ESPERA_RATELIMIT_S)
                    break
                except replay.ReplayMiss:  # a gravação não teve resposta deste backend (ele falhou ali)
                    falhou(backend, "sem cassete")
                    break
                except replay.OrcamentoSerpAPIEsgotado:
                    raise  # teto de buscas: os outros backends também parariam
                except Exception as e:
                    tipo = _classificar(e)
                    if tipo == "timeout" and tentativa == 1:
                        telemetria.fallback("ddgs.cadeia", f"{backend}: timeout: nova tentativa")
                        _dormir(DDGS_ESPERA_NOVA_TENTATIVA_S)
                        continue
                    if tipo == "timeout":
                        sem_resposta += 1
                    falhou(backend, f"{tipo} ({type(e).__name__}: {str(e)[:80]})")
                    break
            if dados is None:
                continue
            ultimo = dados
            if dados.get("resultados"):
                return dados, backend
        if falhas:
            if limitados and limitados + sem_resposta == len(backends):
                raise replay.BuscaLimitada(f"todos os backends limitaram a taxa ou não responderam "
                                           f"({limitados} limitado(s), {sem_resposta} sem resposta)")
            raise DDGSException("; ".join(falhas))
        return ultimo, ""
