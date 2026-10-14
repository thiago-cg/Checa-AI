"""Missão G: rodízio de chaves da SerpAPI (1), max_tokens/esforço da reformulação (2), site: no orgânico (6)."""
import json

import pytest

from factcheck_mvp import (agente, config, llm, llm_openrouter, planejador_busca, replay, serpapi_chaves,
                           serpapi_layer, telemetria)

K1, K2, K3 = "chave-um-aaaaaaaa", "chave-dois-bbbbbbbb", "chave-tres-cccccccc"


@pytest.fixture
def chaves_env(monkeypatch):
    for i in range(2, serpapi_chaves.MAX_NUMERADAS + 1):
        monkeypatch.delenv(f"SERPAPI_KEY_{i}", raising=False)
    monkeypatch.delenv("SERPAPI_KEYS", raising=False)
    monkeypatch.setenv("SERPAPI_KEY", K1)
    monkeypatch.setenv("SERPAPI_KEY_2", K2)
    monkeypatch.setenv("SERPAPI_KEYS", f"{K2}, {K3}")
    monkeypatch.setattr(config, "SERPAPI_KEY", K1)
    replay.resetar_cota()
    yield
    replay.resetar_cota()


def _resp(status, corpo):
    return replay.Resposta(status, {"content-type": "application/json"}, json.dumps(corpo).encode(), "")


# ----------------------------------------------------------------------------- 1. rodízio
def test_chaves_em_ordem_sem_repetir(chaves_env):
    assert serpapi_chaves.chaves() == [K1, K2, K3]
    assert serpapi_chaves.posicao(K2) == "2 de 3"


def test_recusa_marca_a_chave_e_so_esgota_a_cota_na_ultima(chaves_env):
    for k, ultima in ((K1, False), (K2, False), (K3, True)):
        with pytest.raises(replay.CotaSerpAPIEsgotada) as e:
            replay._checar_cota_serpapi("GET", f"https://serpapi.com/search.json?q=x&api_key={k}",
                                        _resp(429, {"error": "sem buscas"}), 1.0)
        assert k not in str(e.value)  # a mensagem nunca leva a chave
        assert replay.cota_esgotada() is ultima
    assert serpapi_chaves.atual(K1) == ""


def test_cliente_repete_a_busca_com_a_proxima_chave(chaves_env, monkeypatch):
    usadas = []

    def falso_get(self, params_http):
        usadas.append(params_http["api_key"])
        if params_http["api_key"] == K1:
            replay._checar_cota_serpapi("GET", f"https://serpapi.com/search.json?api_key={K1}",
                                        _resp(401, {"error": "Invalid API key"}), 1.0)
        return _resp(200, {"organic_results": [{"link": "https://a.br/x", "title": "t"}]})

    monkeypatch.setattr(serpapi_layer.SerpAPIClient, "_get_com_nova_tentativa", falso_get)
    cli = serpapi_layer.SerpAPIClient(engine="google")
    r = cli.buscar_ex({"q": "teste", "engine": "google"})
    assert r.motivo == "ok" and usadas == [K1, K2]
    assert not replay.cota_esgotada()
    assert cli.api_key == K2  # as próximas buscas já começam pela chave boa


def test_cliente_sem_chave_sobrando_cai_em_erro(chaves_env, monkeypatch):
    def sempre_recusa(self, params_http):
        replay._checar_cota_serpapi("GET", f"https://serpapi.com/search.json?api_key={params_http['api_key']}",
                                    _resp(403, {"error": "acabou"}), 1.0)

    monkeypatch.setattr(serpapi_layer.SerpAPIClient, "_get_com_nova_tentativa", sempre_recusa)
    r = serpapi_layer.SerpAPIClient(engine="google").buscar_ex({"q": "teste"})
    assert r.motivo == "erro" and replay.cota_esgotada()


def test_chave_explicita_nao_entra_no_rodizio(chaves_env, monkeypatch):
    usadas = []

    def recusa(self, params_http):
        usadas.append(params_http["api_key"])
        replay._checar_cota_serpapi("GET", f"https://serpapi.com/search.json?api_key={params_http['api_key']}",
                                    _resp(401, {}), 1.0)

    monkeypatch.setattr(serpapi_layer.SerpAPIClient, "_get_com_nova_tentativa", recusa)
    assert serpapi_layer.SerpAPIClient(api_key="fixa-zzzzzzzz").buscar_ex({"q": "x"}).motivo == "erro"
    assert usadas == ["fixa-zzzzzzzz"]
    assert serpapi_layer.SerpAPIClient(api_key="").ativo is False


def test_sem_serpapi_key_busca_desligada_mesmo_com_numeradas(chaves_env, monkeypatch):
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    assert serpapi_layer.SerpAPIClient().ativo is False


def test_redigir_cobre_as_chaves_extras(chaves_env):
    assert telemetria.redigir(f"url?api_key={K3}&k={K2}") == "url?api_key=REDACTED&k=REDACTED"


# ----------------------------------------------------------------------------- 2. reformulação
def test_esforco_por_finalidade(monkeypatch):
    monkeypatch.delenv("OPENROUTER_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("OPENROUTER_REASONING_EFFORT_REFORMULAR", raising=False)
    monkeypatch.setattr(config, "AGENTE_REFORMULAR_ESFORCO", "high")
    with telemetria.finalidade("reformular"):
        assert llm_openrouter._esforco() == "high"
        monkeypatch.setenv("OPENROUTER_REASONING_EFFORT_REFORMULAR", "medium")
        assert llm_openrouter._esforco() == "medium"
    with telemetria.finalidade("juiz"):
        assert llm_openrouter._esforco() == ""
        monkeypatch.setenv("OPENROUTER_REASONING_EFFORT", "low")
        assert llm_openrouter._esforco() == "low"


def test_reformular_pede_2000_tokens(monkeypatch):
    pedido = {}

    def falso_chat_json(messages, schema, finalidade, max_tokens=0, timeout_s=0, validar=None):
        pedido.update(finalidade=finalidade, max_tokens=max_tokens)
        return llm.ResultadoLLM(ok=False, erro="sem rede no teste")

    monkeypatch.setattr(llm, "chat_json", falso_chat_json)
    agente.reformular(agente.Alvo(0, "vacina causa autismo", "vacina autismo"), ["vacina autismo"], [])
    assert pedido == {"finalidade": "reformular", "max_tokens": 2000}


# ----------------------------------------------------------------------------- 6. site: no orgânico
@pytest.mark.parametrize("flag,esperado", [(False, None), (True, "google")])
def test_site_no_organico(monkeypatch, flag, esperado):
    monkeypatch.setattr(config, "BUSCA_PLANEJADOR", False)
    monkeypatch.setattr(config, "BUSCA_SITE_NO_ORGANICO", flag)
    q = {"q": "vacina autismo (site:lupa.uol.com.br OR site:aosfatos.org)", "engine": "google_news"}
    novo = planejador_busca.motor_por_dominio(q, "google_news")
    assert (novo or {}).get("engine") == esperado
    # consulta pura nunca troca de motor
    assert planejador_busca.motor_por_dominio({"q": "vacina autismo"}, "google_news") is None


def test_onda1_com_news_manda_so_a_consulta_site_ao_organico(monkeypatch):
    monkeypatch.setattr(config, "SERP_ENGINE", "google_news")
    monkeypatch.setattr(config, "BUSCA_PLANEJADOR", False)
    monkeypatch.setattr(config, "BUSCA_SITE_NO_ORGANICO", True)
    monkeypatch.setattr(config, "AGENTE_SITES_MODO", "or")
    ags = [{"id": "lupa", "site": "lupa.uol.com.br"}, {"id": "af", "site": "aosfatos.org"}]
    plano = agente.plano_onda1([agente.Alvo(0, "vacina causa autismo", "vacina autismo")], ags)
    motores = {("site:" in q["q"]): q["engine"] for q, _, _ in plano}
    assert motores == {False: "google_news", True: "google"}
    assert len(plano) == 2  # nenhuma busca a mais
