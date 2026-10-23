"""ddgs: tradução de params, formato SerpAPI, backends em ordem, erros, cache, teto e cassetes (sem rede)."""
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException

import ddgs
from factcheck_mvp import agente, busca_web, config, replay
from factcheck_mvp import ddgs_layer as dl
from factcheck_mvp import serpapi_layer as camada
from factcheck_mvp.serpapi_layer import ResultadoBusca
from factcheck_mvp import telemetria as tel

TEXT = [
    {"title": "A", "href": "https://www.g1.globo.com/a", "body": "snip a"},
    {"title": "B", "href": "https://www.uol.com.br/b", "body": "snip b"},
]
NEWS = [
    {"date": "2026-10-18T10:00:00+00:00", "title": "N1", "body": "b1",
     "url": "https://noticias.exemplo.com/n1", "image": "https://img.exemplo.com/x.jpg",
     "source": "Folha de S.Paulo on MSN.com"},
]


class FakeDDGS:
    """Roteiro por (funcao, backend): lista de resultados, exceção a levantar, ou tupla = sequência de desfechos."""
    roteiro: dict = {}
    fila: dict = {}
    chamadas: list = []
    instancias: list = []

    def __init__(self, proxy=None, timeout=5):
        self.proxy, self.timeout = proxy, timeout
        FakeDDGS.instancias.append(self)

    @classmethod
    def reset(cls):
        cls.roteiro, cls.fila, cls.chamadas, cls.instancias = {}, {}, [], []

    def _responder(self, funcao, query, kw):
        chave = (funcao, kw["backend"])
        FakeDDGS.chamadas.append({"funcao": funcao, "query": query, **kw})
        if chave in FakeDDGS.fila:
            fila = FakeDDGS.fila[chave]
            desfecho = fila.pop(0) if fila else DDGSException("No results found.")
        else:
            desfecho = FakeDDGS.roteiro.get(chave, DDGSException("No results found."))
        if isinstance(desfecho, BaseException):
            raise desfecho
        return list(desfecho)

    def text(self, query, **kw):
        return self._responder("text", query, kw)

    def news(self, query, **kw):
        return self._responder("news", query, kw)


@pytest.fixture
def amb(tmp_path, monkeypatch):
    monkeypatch.setenv("CASSETES_DIR", str(tmp_path / "cass"))
    monkeypatch.setenv("BUSCA_USO_ARQ", str(tmp_path / "uso.json"))
    monkeypatch.delenv("IO_MODO", raising=False)
    monkeypatch.delenv("SERPAPI_ORCAMENTO_RESTANTE", raising=False)
    replay.definir_modo(None)
    replay.definir_teto_serpapi(None)
    ajustes = {"BUSCA_WEB": True, "DDGS_RPS": 0.0, "DDGS_ESPERA_RATELIMIT_S": 2.0, "BUSCA_DAILY_CAP": 100,
               "CACHE_BUSCA_TTL": 3600, "DDGS_TOP_STORIES": False,
               "DDGS_TEXT_BACKENDS": "google,bing,duckduckgo,brave", "DDGS_NEWS_BACKENDS": "bing,duckduckgo,yahoo",
               "DDGS_MAX_PALAVRAS": 32, "DDGS_REGIAO": "br-pt", "DDGS_SAFESEARCH": "moderate", "DDGS_PROXY": "",
               "DDGS_TIMEOUT_S": 10, "SERP_ENGINE": "google_news", "BUSCA_PROVEDOR": "serpapi",
               # sem reserva por padrão: um teste nunca pode cair na SerpAPI de verdade
               "BUSCA_FALLBACK_SERPAPI": False, "DDGS_PAUSA_BLOQUEIO_S": 0}
    for nome, valor in ajustes.items():
        monkeypatch.setattr(config, nome, valor)
    FakeDDGS.reset()
    dl.resetar_pausa()
    dl._avisados.clear()
    # o FakeDDGS responde por qualquer nome de backend; a filtragem real tem testes próprios abaixo
    monkeypatch.setattr(dl, "_habilitados", lambda funcao: None)
    monkeypatch.setattr(ddgs, "DDGS", FakeDDGS)
    sleeps, fb = [], []
    monkeypatch.setattr(dl, "_dormir", lambda s: sleeps.append(s))
    monkeypatch.setattr(tel, "fallback", lambda onde, motivo="", **kw: fb.append((onde, str(motivo))))
    yield SimpleNamespace(tmp=tmp_path, sleeps=sleeps, fb=fb)
    replay.definir_modo(None)
    replay.definir_teto_serpapi(None)


def _cassetes(amb):
    return [json.loads(p.read_text(encoding="utf-8")) for p in (amb.tmp / "cass").glob("*.json")]


# --------------------------------------------------------------- params e formato
def test_text_traduz_params_e_devolve_formato_serpapi(amb):
    FakeDDGS.roteiro[("text", "google")] = TEXT
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "vacina causa autismo", "engine": "google", "num": 5,
                                              "hl": "pt-br", "gl": "br"})
    assert r.motivo == "ok" and r.payload is not None
    org = r.payload["organic_results"]
    assert org[0] == {"position": 1, "title": "A", "link": "https://www.g1.globo.com/a", "snippet": "snip a",
                      "displayed_link": "g1.globo.com", "_origem": "ddgs:google"}
    assert [o["position"] for o in org] == [1, 2] and "top_stories" not in r.payload
    meta = r.payload["search_metadata"]
    assert meta["provedor"] == "ddgs" and meta["backend"] == "google" and meta["engine"] == "google"
    assert datetime.fromisoformat(meta["created_at"]).tzinfo is not None  # âncora ISO com fuso
    chamada = FakeDDGS.chamadas[0]
    assert chamada["funcao"] == "text" and chamada["query"] == "vacina causa autismo"
    assert chamada["region"] == "br-pt" and chamada["safesearch"] == "moderate"
    assert chamada["max_results"] == 5 and chamada["backend"] == "google" and chamada["page"] == 1


def test_news_formato_e_fonte_sem_sufixo_do_bing(amb):
    FakeDDGS.roteiro[("news", "bing")] = NEWS
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google_news"})
    assert r.motivo == "ok" and "organic_results" not in r.payload
    n = r.payload["news_results"][0]
    assert n == {"position": 1, "title": "N1", "link": "https://noticias.exemplo.com/n1", "snippet": "b1",
                 "iso_date": "2026-10-18T10:00:00+00:00", "source": {"name": "Folha de S.Paulo"},
                 "thumbnail": "https://img.exemplo.com/x.jpg", "_origem": "ddgs:bing"}
    assert FakeDDGS.chamadas[0]["funcao"] == "news"
    assert r.payload["search_metadata"]["backend"] == "bing"


def test_payload_normaliza_com_a_mesma_ancora(amb):
    FakeDDGS.roteiro[("news", "bing")] = NEWS
    FakeDDGS.roteiro[("text", "google")] = TEXT
    cli = dl.DDGSClient(ativo=True)
    news = cli.buscar_ex({"q": "x", "engine": "google_news"}).payload
    ancora = news["search_metadata"]["created_at"]
    item = camada.normalizar_item(news["news_results"][0], engine="google_news", ancora=ancora)
    assert item["data_pub"] == "2026-10-18" and item["fonte"]["nome"] == "Folha de S.Paulo"
    org = cli.buscar_ex({"q": "y", "engine": "google"}).payload
    assert camada.normalizar_item(org["organic_results"][0], engine="google")["url"] == "https://www.g1.globo.com/a"


def test_google_scholar_cai_em_text_com_fallback(amb):
    FakeDDGS.roteiro[("text", "google")] = TEXT
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google_scholar"})
    assert r.motivo == "ok" and "organic_results" in r.payload
    assert FakeDDGS.chamadas[0]["funcao"] == "text"
    assert any(onde == "ddgs.scholar" and "google_scholar" in motivo for onde, motivo in amb.fb)


def test_consulta_cortada_por_ddgs_max_palavras(amb, monkeypatch):
    monkeypatch.setattr(config, "DDGS_MAX_PALAVRAS", 3)
    FakeDDGS.roteiro[("text", "google")] = TEXT
    dl.DDGSClient(ativo=True).buscar_ex({"q": "um dois três quatro cinco", "engine": "google"})
    assert FakeDDGS.chamadas[0]["query"] == "um dois três"


def test_proxy_e_timeout_chegam_ao_cliente_ddgs(amb, monkeypatch):
    monkeypatch.setattr(config, "DDGS_PROXY", "http://u:senha@proxy.exemplo:8080")
    monkeypatch.setattr(config, "DDGS_TIMEOUT_S", 7)
    FakeDDGS.roteiro[("text", "google")] = TEXT
    dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert FakeDDGS.instancias[0].proxy == "http://u:senha@proxy.exemplo:8080"
    assert FakeDDGS.instancias[0].timeout == 7


def test_proxy_vazio_vira_none(amb):
    FakeDDGS.roteiro[("text", "google")] = TEXT
    dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert FakeDDGS.instancias[0].proxy is None


# --------------------------------------------------------------- top stories
def test_top_stories_vem_das_noticias_quando_ligado(amb, monkeypatch):
    monkeypatch.setattr(config, "DDGS_TOP_STORIES", True)
    FakeDDGS.roteiro[("text", "google")] = TEXT
    FakeDDGS.roteiro[("news", "bing")] = NEWS * 4
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    tops = r.payload["top_stories"]
    assert len(tops) == dl.TOP_STORIES_DDGS
    assert tops[0] == {"position": 1, "title": "N1", "link": "https://noticias.exemplo.com/n1", "snippet": "b1",
                       "source": "Folha de S.Paulo", "date": "2026-10-18T10:00:00+00:00",
                       "thumbnail": "https://img.exemplo.com/x.jpg", "_origem": "ddgs:bing"}
    assert any(c["funcao"] == "news" for c in FakeDDGS.chamadas)


def test_top_stories_nao_roda_com_site_na_consulta(amb, monkeypatch):
    monkeypatch.setattr(config, "DDGS_TOP_STORIES", True)
    FakeDDGS.roteiro[("text", "google")] = TEXT
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x (site:g1.globo.com OR site:uol.com.br)", "engine": "google"})
    assert "top_stories" not in r.payload
    assert all(c["funcao"] == "text" for c in FakeDDGS.chamadas)


def test_top_stories_desligado_nao_pede_noticias(amb):
    FakeDDGS.roteiro[("text", "google")] = TEXT
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert "top_stories" not in r.payload
    assert all(c["funcao"] == "text" for c in FakeDDGS.chamadas)


def test_top_stories_falha_nao_derruba_a_busca(amb, monkeypatch):
    monkeypatch.setattr(config, "DDGS_TOP_STORIES", True)
    FakeDDGS.roteiro[("text", "google")] = TEXT
    FakeDDGS.roteiro[("news", "bing")] = RuntimeError("boom")
    FakeDDGS.roteiro[("news", "duckduckgo")] = RuntimeError("boom")
    FakeDDGS.roteiro[("news", "yahoo")] = RuntimeError("boom")
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "ok" and r.payload["top_stories"] == []


# --------------------------------------------------------------- backends, vazio e erros
def test_vazio_em_todos_os_backends_nao_e_erro_e_nao_vai_ao_cache(amb):
    cli = dl.DDGSClient(ativo=True)
    r = cli.buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "vazio" and r.payload["organic_results"] == []
    assert [c["backend"] for c in FakeDDGS.chamadas] == ["google", "bing", "duckduckgo", "brave"]
    assert cli.erros_rede == 0
    FakeDDGS.chamadas.clear()
    assert cli.buscar_ex({"q": "x", "engine": "google"}).motivo == "vazio"
    assert len(FakeDDGS.chamadas) == 4  # vazio não entrou no cache: refaz a cadeia


def test_backend_vazio_passa_ao_proximo(amb):
    FakeDDGS.roteiro[("text", "bing")] = TEXT
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "ok" and r.payload["search_metadata"]["backend"] == "bing"
    assert [c["backend"] for c in FakeDDGS.chamadas] == ["google", "bing"]


def test_rate_limit_passa_ao_proximo_backend_com_espera(amb):
    FakeDDGS.roteiro[("text", "google")] = RatelimitException("rate limited")
    FakeDDGS.roteiro[("text", "bing")] = TEXT
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "ok" and r.payload["search_metadata"]["backend"] == "bing"
    assert amb.sleeps == [2.0]  # DDGS_ESPERA_RATELIMIT_S
    assert [c["backend"] for c in FakeDDGS.chamadas] == ["google", "bing"]
    assert any("google: ratelimit" in motivo for _, motivo in amb.fb)  # o desvio deixa rastro


def test_rate_limit_embrulhado_em_ddgsexception_tambem_conta(amb):
    FakeDDGS.roteiro[("text", "google")] = DDGSException("Ratelimit exceeded for google")
    FakeDDGS.roteiro[("text", "bing")] = TEXT
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "ok" and r.payload["search_metadata"]["backend"] == "bing"


def test_rate_limit_em_todos_os_backends_vira_erro_com_fallback(amb):
    for b in ("google", "bing", "duckduckgo", "brave"):
        FakeDDGS.roteiro[("text", b)] = RatelimitException("429 too many requests")
    cli = dl.DDGSClient(ativo=True)
    r = cli.buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "erro" and cli.ultimo_motivo == "erro" and cli.erros_rede == 1
    assert any(onde == "ddgs" and "ratelimit" in motivo for onde, motivo in amb.fb)


def test_timeout_ganha_uma_nova_tentativa_no_mesmo_backend(amb):
    FakeDDGS.fila[("text", "google")] = [TimeoutException("timed out"), TEXT]
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "ok" and r.payload["search_metadata"]["backend"] == "google"
    assert [c["backend"] for c in FakeDDGS.chamadas] == ["google", "google"]
    assert amb.sleeps == [dl.DDGS_ESPERA_NOVA_TENTATIVA_S]
    assert any("timeout" in motivo for _, motivo in amb.fb)


def test_dois_timeouts_passam_ao_proximo_backend(amb):
    FakeDDGS.fila[("text", "google")] = [TimeoutException("timed out"), TimeoutException("timed out")]
    FakeDDGS.roteiro[("text", "bing")] = TEXT
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "ok" and r.payload["search_metadata"]["backend"] == "bing"
    assert [c["backend"] for c in FakeDDGS.chamadas] == ["google", "google", "bing"]


def test_erro_nao_levanta_e_registra_fallback(amb):
    for b in ("google", "bing", "duckduckgo", "brave"):
        FakeDDGS.roteiro[("text", b)] = RuntimeError("motor quebrou")
    cli = dl.DDGSClient(ativo=True)
    r = cli.buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "erro" and r.payload is None
    assert any(onde == "ddgs" and "motor quebrou" in motivo for onde, motivo in amb.fb)
    assert any("RuntimeError" in motivo for _, motivo in amb.fb)


def test_falha_ao_criar_cliente_nao_levanta(amb, monkeypatch):
    def quebra(proxy=None, timeout=5):
        raise ValueError("proxy inválido")
    monkeypatch.setattr(ddgs, "DDGS", quebra)
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "erro"


def test_backends_vazios_na_config_e_erro(amb, monkeypatch):
    monkeypatch.setattr(config, "DDGS_TEXT_BACKENDS", " , ")
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "erro" and FakeDDGS.chamadas == []


def test_backend_nunca_e_auto(amb):
    FakeDDGS.roteiro[("text", "google")] = TEXT
    dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert all(c["backend"] != "auto" for c in FakeDDGS.chamadas)


# --------------------------------------------------------------- cache, teto, ativo
def test_cache_em_memoria_guarda_resultados_nao_vazios(amb):
    FakeDDGS.roteiro[("text", "google")] = TEXT
    cli = dl.DDGSClient(ativo=True)
    primeira = cli.buscar_ex({"q": "x", "engine": "google"})
    segunda = cli.buscar_ex({"q": "x", "engine": "google"})
    assert primeira.cache is False and segunda.cache is True
    assert len(FakeDDGS.chamadas) == 1 and cli.uso_hoje == 1


def test_teto_diario_bloqueia_sem_chamar_ddgs(amb, monkeypatch):
    monkeypatch.setattr(config, "BUSCA_DAILY_CAP", 1)
    FakeDDGS.roteiro[("text", "google")] = TEXT
    cli = dl.DDGSClient(ativo=True)
    assert cli.buscar_ex({"q": "um", "engine": "google"}).motivo == "ok"
    FakeDDGS.chamadas.clear()
    r = cli.buscar_ex({"q": "dois", "engine": "google"})
    assert r.motivo == "cap" and cli.bloqueios_cap == 1 and cli.ultimo_motivo == "cap"
    assert FakeDDGS.chamadas == []


def test_ativo_false_ou_busca_web_desligada_nao_chama_nada(amb, monkeypatch):
    assert dl.DDGSClient(ativo=False).ativo is False
    r = dl.DDGSClient(ativo=False).buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "sem_chave" and r.payload is None
    monkeypatch.setattr(config, "BUSCA_WEB", False)
    assert dl.DDGSClient().ativo is False
    assert dl.DDGSClient().buscar({"q": "x", "engine": "google"}) is None
    assert FakeDDGS.chamadas == []


def test_busca_web_ligada_por_padrao_e_sem_chave(amb):
    assert dl.DDGSClient().ativo is True  # BUSCA_WEB=1: não depende de SERPAPI_KEY
    assert dl.DDGSClient().rodizio is False


def test_limitador_de_ritmo_espaca_buscas_vivas(amb, monkeypatch):
    monkeypatch.setattr(config, "DDGS_RPS", 2.0)
    FakeDDGS.roteiro[("text", "google")] = TEXT
    esperas = []
    monkeypatch.setattr(dl, "_dormir", lambda s: esperas.append(s))
    monkeypatch.setattr(dl, "_ultima_busca", 0.0)
    cli = dl.DDGSClient(ativo=True)
    cli.buscar_ex({"q": "um", "engine": "google"})
    cli.buscar_ex({"q": "dois", "engine": "google"})
    assert len(esperas) >= 1 and all(0 < s <= 0.5 for s in esperas)


def test_limitador_nao_espera_no_cassete(amb, monkeypatch):
    monkeypatch.setattr(config, "DDGS_RPS", 1.0)
    FakeDDGS.roteiro[("text", "google")] = TEXT
    esperas = []
    monkeypatch.setattr(dl, "_dormir", lambda s: esperas.append(s))
    with replay.modo("record"):
        dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    esperas.clear()
    FakeDDGS.reset()
    with replay.modo("replay"):
        r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "ok" and esperas == []


# --------------------------------------------------------------- cassetes e replay
def test_record_grava_por_backend_e_replay_reproduz_com_created_at(amb):
    FakeDDGS.roteiro[("text", "google")] = TEXT
    with replay.modo("record"):
        r1 = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    docs = _cassetes(amb)
    assert len(docs) == 1 and docs[0]["req"]["url"].startswith("ddgs://text?")
    assert "backend=google" in docs[0]["req"]["url"]
    gravado = json.loads(docs[0]["resp"]["texto"])
    assert gravado["criado_em"] == r1.payload["search_metadata"]["created_at"]
    FakeDDGS.reset()
    with replay.modo("replay"):
        r2 = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r2.motivo == "ok" and r2.payload == r1.payload
    assert FakeDDGS.chamadas == []  # replay não toca o ddgs


def test_record_reusa_cassete_sem_chamar_ddgs(amb):
    FakeDDGS.roteiro[("text", "google")] = TEXT
    with replay.modo("record"):
        dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    FakeDDGS.reset()
    with replay.modo("record"):
        r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "ok" and FakeDDGS.chamadas == []


def test_replay_sem_cassete_nao_chama_ddgs_e_registra_miss(amb):
    FakeDDGS.roteiro[("text", "google")] = TEXT
    with replay.modo("replay"):
        r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "erro" and FakeDDGS.chamadas == []
    assert any(onde == "ddgs" for onde, _ in amb.fb)


def test_rate_limit_nao_e_gravado_e_o_backend_que_respondeu_grava(amb, monkeypatch):
    monkeypatch.setattr(config, "DDGS_ESPERA_RATELIMIT_S", 0.0)
    FakeDDGS.roteiro[("text", "google")] = RatelimitException("rate limited")
    FakeDDGS.roteiro[("text", "bing")] = TEXT
    with replay.modo("record"):
        r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r.motivo == "ok" and r.payload["search_metadata"]["backend"] == "bing"
    docs = _cassetes(amb)
    assert len(docs) == 1 and "backend=bing" in docs[0]["req"]["url"]


def test_replay_reproduz_mesmo_com_backend_que_falhou_na_gravacao(amb, monkeypatch):
    monkeypatch.setattr(config, "DDGS_ESPERA_RATELIMIT_S", 0.0)
    FakeDDGS.roteiro[("text", "google")] = RatelimitException("rate limited")
    FakeDDGS.roteiro[("text", "bing")] = TEXT
    with replay.modo("record"):
        r1 = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    FakeDDGS.reset()
    with replay.modo("replay"):
        r2 = dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    assert r2.motivo == r1.motivo == "ok" and r2.payload == r1.payload


def test_orcamento_serpapi_do_arquivo_nao_barra_o_ddgs(amb, monkeypatch):
    """SERPAPI_ORCAMENTO_RESTANTE protege a cota PAGA: buscas grátis do ddgs não gastam nem são barradas."""
    monkeypatch.setenv("SERPAPI_ORCAMENTO_RESTANTE", "1")
    FakeDDGS.roteiro[("text", "google")] = TEXT
    cli = dl.DDGSClient(ativo=True)
    assert cli.buscar_ex({"q": "um", "engine": "google"}).motivo == "ok"
    assert cli.buscar_ex({"q": "dois", "engine": "google"}).motivo == "ok"
    uso = replay.uso_serpapi()
    assert uso["usadas"] == 0 and uso["restantes"] == 1 and uso["por_provedor"] == {"ddgs": 2}


def test_teto_do_processo_vale_para_o_ddgs_e_para_a_cadeia(amb):
    replay.definir_teto_serpapi(1)
    FakeDDGS.roteiro[("text", "google")] = TEXT
    cli = dl.DDGSClient(ativo=True)
    assert cli.buscar_ex({"q": "um", "engine": "google"}).motivo == "ok"
    FakeDDGS.chamadas.clear()
    r = cli.buscar_ex({"q": "dois", "engine": "google"})
    assert r.motivo == "erro" and FakeDDGS.chamadas == []  # teto estoura antes da chamada
    assert any(onde == "ddgs" and "orcamento" in motivo for onde, motivo in amb.fb)


def test_contador_separa_por_provedor(amb):
    FakeDDGS.roteiro[("text", "google")] = TEXT
    dl.DDGSClient(ativo=True).buscar_ex({"q": "x", "engine": "google"})
    uso = json.loads((amb.tmp / "uso.json").read_text(encoding="utf-8"))
    assert uso["total_live"] == 1 and uso["por_provedor"] == {"ddgs": 1}
    assert replay.uso_serpapi()["por_provedor"] == {"ddgs": 1}


# --------------------------------------------------------------- helpers, fábrica e agente
def test_nome_da_fonte_e_host_sem_www():
    assert dl._nome_fonte("Folha de S.Paulo on MSN.com", "https://x.com/a") == "Folha de S.Paulo"
    assert dl._nome_fonte("", "https://www.g1.globo.com/a") == "g1.globo.com"
    assert dl._nome_fonte("Agência Brasil", "https://x.com") == "Agência Brasil"


def test_result_key_e_motor_padrao(amb):
    cli = dl.DDGSClient(ativo=True)
    assert cli.result_key({"engine": "google_news"}) == "news_results"
    assert cli.result_key({"engine": "google_scholar"}) == "organic_results"
    assert cli.engine_de({}) == "google_news"  # SERP_ENGINE do ambiente de teste
    assert cli.engine_de({"engine": "xpto"}) == "google"


def test_cliente_padrao_segue_busca_provedor(amb, monkeypatch):
    assert isinstance(busca_web.cliente_padrao(), camada.SerpAPIClient)
    monkeypatch.setattr(config, "BUSCA_PROVEDOR", "ddgs")
    assert isinstance(busca_web.cliente_padrao(), dl.DDGSClient)
    monkeypatch.setattr(config, "BUSCA_PROVEDOR", "xpto")
    assert isinstance(busca_web.cliente_padrao(), camada.SerpAPIClient)
    assert any(onde == "busca" for onde, _ in amb.fb)


def test_clientes_reais_herdam_buscar_da_base():
    assert camada.SerpAPIClient.buscar is busca_web.ClienteBusca.buscar
    assert dl.DDGSClient.buscar is busca_web.ClienteBusca.buscar


def test_agente_usa_buscar_ex_do_ddgs(amb):
    FakeDDGS.roteiro[("text", "google")] = TEXT
    r = agente._buscar(dl.DDGSClient(ativo=True), {"q": "x", "engine": "google"})
    assert r.motivo == "ok" and r.payload["organic_results"]


def test_agente_respeita_fake_que_sobrescreve_so_buscar(amb):
    class Fake(busca_web.ClienteBusca):
        def buscar(self, params):
            return {"organic_results": [{"link": "https://x.com/a", "title": "T"}]}

        def buscar_ex(self, params):
            raise AssertionError("o agente não deveria usar buscar_ex")

    r = agente._buscar(Fake(), {"q": "x", "engine": "google"})
    assert r.motivo == "ok" and r.payload["organic_results"][0]["link"] == "https://x.com/a"


def test_agente_fake_so_com_buscar_sem_buscar_ex(amb):
    class Fake:
        def buscar(self, params):
            return None

        ultimo_motivo = "vazio"

    r = agente._buscar(Fake(), {"q": "x", "engine": "google"})
    assert r.motivo == "vazio" and r.payload is None


def test_origem_do_item_normalizado_e_o_backend_do_ddgs(amb):
    """`normalizar_item` grava a origem real (ddgs:<backend>), não "serpapi"."""
    from factcheck_mvp.serpapi_layer import normalizar_item
    FakeDDGS.roteiro[("text", "google")] = [{"title": "A", "href": "https://g1.globo.com/a", "body": "x"}]
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "origem teste", "engine": "google"})
    assert normalizar_item(r.payload["organic_results"][0], engine="google")["origem"] == "ddgs:google"
    assert normalizar_item({"link": "https://x.com/a", "title": "t"}, engine="google")["origem"] == "serpapi"


def test_bloqueio_http_do_motor_vira_ratelimit_e_nao_vazio():
    """ddgs 9.16 trocava HTTP != 200 por "No results found": 202/403/429 agora levantam RatelimitException."""
    from ddgs.base import BaseSearchEngine
    from ddgs.exceptions import RatelimitException

    class Resp:
        def __init__(self, status, text=""):
            self.status_code, self.text = status, text

    class Motor:
        name = "duckduckgo"

        def __init__(self, resp):
            self.http_client = SimpleNamespace(request=lambda *a, **k: resp)

    assert getattr(BaseSearchEngine.request, "_crosscheck", False)
    assert BaseSearchEngine.request(Motor(Resp(200, "<html/>")), "GET", "u") == "<html/>"
    assert BaseSearchEngine.request(Motor(Resp(404)), "GET", "u") is None
    for status in (202, 403, 429):
        with pytest.raises(RatelimitException, match=f"HTTP {status}"):
            BaseSearchEngine.request(Motor(Resp(status)), "GET", "u")
    assert dl._classificar(DDGSException("ratelimit: duckduckgo HTTP 202")) == "ratelimit"


def test_grupo_de_sites_perde_os_parenteses(amb):
    from factcheck_mvp.serpapi_layer import query_agencias
    q = "vacina autismo (site:aosfatos.org OR site:lupa.uol.com.br OR site:g1.globo.com/fato-ou-fake)"
    assert dl.adaptar_consulta(q) == ("vacina autismo site:aosfatos.org OR site:lupa.uol.com.br OR "
                                      "site:g1.globo.com/fato-ou-fake")
    assert dl.adaptar_consulta("(site:boatos.org)") == "site:boatos.org"
    assert dl.adaptar_consulta("lula (2022) pix") == "lula (2022) pix"  # parêntese sem site: fica
    ag = [{"site": "aosfatos.org"}, {"site": "lupa.uol.com.br"}]
    FakeDDGS.roteiro[("text", "google")] = TEXT
    dl.DDGSClient(ativo=True).buscar_ex(query_agencias("vacina autismo", ag)[0])
    assert FakeDDGS.chamadas[0]["query"] == "vacina autismo site:aosfatos.org OR site:lupa.uol.com.br"


# --------------------------------------------------------------- reserva SerpAPI
class ReservaFake:
    """Cliente de reserva (no lugar do SerpAPIClient): registra as consultas e devolve um payload SerpAPI."""

    def __init__(self, ativo=True):
        self.ativo, self.consultas = ativo, []

    def buscar_ex(self, params):
        self.consultas.append(dict(params))
        return ResultadoBusca({"organic_results": [{"link": "https://serp.exemplo/a", "title": "S"}]}, "ok")


def _tudo_limitado():
    for b in ("google", "bing", "duckduckgo", "brave"):
        FakeDDGS.roteiro[("text", b)] = RatelimitException(f"{b} 429")


def test_limitado_em_todos_os_backends_cai_na_serpapi_e_pausa(amb, monkeypatch):
    monkeypatch.setattr(config, "BUSCA_FALLBACK_SERPAPI", True)
    monkeypatch.setattr(config, "DDGS_PAUSA_BLOQUEIO_S", 300)
    _tudo_limitado()
    reserva = ReservaFake()
    c = dl.DDGSClient(ativo=True, reserva=reserva)
    q = {"q": "vacina autismo (site:aosfatos.org OR site:lupa.uol.com.br)", "engine": "google", "num": 10}
    r = c.buscar_ex(q)
    assert r.motivo == "ok" and r.payload["organic_results"][0]["link"] == "https://serp.exemplo/a"
    assert reserva.consultas[0]["q"] == q["q"]  # sintaxe Google intacta (com parênteses) para a SerpAPI
    assert any("busca feita na serpapi" in m for _, m in amb.fb)
    assert not any("ratelimit em todos os backends" in m for _, m in amb.fb)  # não conta como bloqueada
    # em pausa: a próxima busca nem tenta o ddgs
    n = len(FakeDDGS.chamadas)
    assert c.buscar_ex({"q": "outra consulta", "engine": "google"}).motivo == "ok"
    assert len(FakeDDGS.chamadas) == n and len(reserva.consultas) == 2 and dl.pausa_restante() > 0


def test_sem_reserva_o_bloqueio_vira_erro_contado_no_eval(amb, monkeypatch):
    monkeypatch.setattr(config, "BUSCA_FALLBACK_SERPAPI", True)
    _tudo_limitado()
    r = dl.DDGSClient(ativo=True, reserva=ReservaFake(ativo=False)).buscar_ex({"q": "x y", "engine": "google"})
    assert r.motivo == "erro" and any("ratelimit em todos os backends" in m for _, m in amb.fb)


def test_reserva_desligada_nao_chama_serpapi(amb):
    _tudo_limitado()
    reserva = ReservaFake()
    r = dl.DDGSClient(ativo=True, reserva=reserva).buscar_ex({"q": "x y", "engine": "google"})
    assert r.motivo == "erro" and reserva.consultas == []


def test_bloqueio_misto_ratelimit_e_timeout_tambem_cai_na_serpapi(amb, monkeypatch):
    """Sob bloqueio um motor costuma só ficar lento: limitado + sem resposta em todos = BuscaLimitada."""
    monkeypatch.setattr(config, "BUSCA_FALLBACK_SERPAPI", True)
    for b in ("google", "bing", "duckduckgo"):
        FakeDDGS.roteiro[("text", b)] = RatelimitException(f"{b} 429")
    FakeDDGS.roteiro[("text", "brave")] = TimeoutException("brave timed out")
    reserva = ReservaFake()
    r = dl.DDGSClient(ativo=True, reserva=reserva).buscar_ex({"q": "x y", "engine": "google"})
    assert r.motivo == "ok" and len(reserva.consultas) == 1
    assert [c["backend"] for c in FakeDDGS.chamadas].count("brave") == 2  # timeout ganhou 1 nova tentativa


def test_so_timeout_sem_ratelimit_nao_vira_bloqueio(amb, monkeypatch):
    monkeypatch.setattr(config, "BUSCA_FALLBACK_SERPAPI", True)
    monkeypatch.setattr(config, "DDGS_TEXT_BACKENDS", "google")
    FakeDDGS.roteiro[("text", "google")] = TimeoutException("timed out")
    reserva = ReservaFake()
    r = dl.DDGSClient(ativo=True, reserva=reserva).buscar_ex({"q": "x y", "engine": "google"})
    assert r.motivo == "erro" and reserva.consultas == [] and dl.pausa_restante() == 0


def test_vazio_no_fim_do_prazo_e_motor_lento_nao_vazio(amb, monkeypatch):
    """O ddgs descarta motor que passa do timeout como "No results found": vazio que chega no prazo = timeout."""
    monkeypatch.setattr(config, "DDGS_TEXT_BACKENDS", "google,bing")
    monkeypatch.setattr(config, "DDGS_TIMEOUT_S", 1e-9)  # qualquer duração passa de 90% do prazo
    FakeDDGS.roteiro[("text", "bing")] = TEXT
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x y", "engine": "google"})
    assert r.motivo == "ok" and r.payload["search_metadata"]["backend"] == "bing"
    assert [c["backend"] for c in FakeDDGS.chamadas].count("google") == 2  # timeout: 1 nova tentativa
    assert any(onde == "ddgs.cadeia" and "google: timeout" in m for onde, m in amb.fb)


def test_vazio_rapido_continua_vazio(amb):
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x y", "engine": "google"})
    assert r.motivo == "vazio" and len(FakeDDGS.chamadas) == 4  # 1 por backend, sem nova tentativa


def test_top_stories_limitadas_pausam_o_ddgs(amb, monkeypatch):
    monkeypatch.setattr(config, "DDGS_TOP_STORIES", True)
    monkeypatch.setattr(config, "DDGS_PAUSA_BLOQUEIO_S", 300)
    FakeDDGS.roteiro[("text", "google")] = TEXT
    for b in ("bing", "duckduckgo", "yahoo"):
        FakeDDGS.roteiro[("news", b)] = RatelimitException(f"{b} 429")
    c = dl.DDGSClient(ativo=True)
    r = c.buscar_ex({"q": "consulta pura", "engine": "google"})
    assert r.motivo == "ok" and r.payload["top_stories"] == [] and dl.pausa_restante() > 0
    assert any(onde == "ddgs.top" and "pausa" in m for onde, m in amb.fb)


def test_reserva_unica_entre_threads(amb, monkeypatch):
    import threading
    monkeypatch.setattr(config, "BUSCA_FALLBACK_SERPAPI", True)
    criadas = []

    class Serp:
        ativo = True

        def __init__(self):
            criadas.append(self)

    monkeypatch.setattr(camada, "SerpAPIClient", Serp)
    c = dl.DDGSClient(ativo=True)
    ts = [threading.Thread(target=c._cliente_reserva) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(criadas) == 1


def test_deteccao_de_bloqueio_so_em_versao_testada(amb, monkeypatch):
    from ddgs.base import BaseSearchEngine

    def original(self, *a, **k):
        return None

    monkeypatch.setattr(BaseSearchEngine, "request", original)
    monkeypatch.setattr(ddgs, "__version__", "99.0.0")
    assert dl._instalar_deteccao_bloqueio() is False and BaseSearchEngine.request is original
    assert any("não testado" in m for _, m in amb.fb)
    monkeypatch.setattr(ddgs, "__version__", dl.DDGS_VERSOES_TESTADAS[0])
    assert dl._instalar_deteccao_bloqueio() is True and BaseSearchEngine.request._crosscheck


# --------------------------------------------------------------- backends desligados no ddgs
def test_backend_desligado_no_ddgs_e_pulado_e_nunca_vira_auto(amb, monkeypatch):
    """ddgs 9.16: `bing` de texto vem com disabled=True; passado à lib, ela caía em backend='auto'."""
    monkeypatch.setattr(dl, "_habilitados", lambda funcao: {"duckduckgo", "yahoo"} if funcao == "text" else None)
    monkeypatch.setattr(config, "DDGS_TEXT_BACKENDS", "bing,duckduckgo,yahoo")
    FakeDDGS.roteiro[("text", "duckduckgo")] = TEXT
    c = dl.DDGSClient(ativo=True)
    r = c.buscar_ex({"q": "x y", "engine": "google"})
    assert r.motivo == "ok" and r.payload["search_metadata"]["backend"] == "duckduckgo"
    assert [ch["backend"] for ch in FakeDDGS.chamadas] == ["duckduckgo"]  # bing nunca chega à lib
    avisos = [m for o, m in amb.fb if o == "ddgs.cadeia" and "bing" in m and "desligado" in m]
    assert len(avisos) == 1
    c.buscar_ex({"q": "outra", "engine": "google"})  # aviso só 1 vez por processo
    assert len([m for o, m in amb.fb if o == "ddgs.cadeia" and "bing" in m and "desligado" in m]) == 1


def test_nenhum_backend_valido_e_erro_nao_auto(amb, monkeypatch):
    monkeypatch.setattr(dl, "_habilitados", lambda funcao: {"duckduckgo"})
    monkeypatch.setattr(config, "DDGS_TEXT_BACKENDS", "bing,yandex")
    r = dl.DDGSClient(ativo=True).buscar_ex({"q": "x y", "engine": "google"})
    assert r.motivo == "erro" and FakeDDGS.chamadas == []
    assert any(o == "ddgs" and "nenhum backend de text" in m for o, m in amb.fb)


def test_habilitados_reflete_o_ddgs_instalado():
    from ddgs.engines import ENGINES
    assert dl._habilitados("text") == set(ENGINES["text"])
    padrao = [b.strip() for b in "duckduckgo,yahoo,brave,google".split(",")]
    assert dl.backends_validos("text", padrao) == padrao  # o padrão do config só tem motores habilitados
    assert set(dl.backends_validos("news", ["bing", "duckduckgo", "yahoo"])) <= set(ENGINES["news"])
