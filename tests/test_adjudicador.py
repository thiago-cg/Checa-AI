"""Adjudicador por afirmação (19/10): corrige a evidência com citação conferida; o nível sai de `decidir`."""
import json

import pytest

from factcheck_mvp import adjudicador, config, decisao, llm
from factcheck_mvp.adjudicador import Alvo, Correcao, ItemAdj, RespostaAdj, consenso, validar
from factcheck_mvp.decisao import AfirmacaoDecisao, Evidencias, ItemEvidencia, decidir

JUIZ = "llm-juiz:openrouter"
AF = "O Senado aprovou o fim da escala 6x1"
TEXTOS = {
    "https://lupa.uol.com.br/c": "É falso que o Senado já aprovou o fim da escala 6x1: a proposta ainda não foi votada "
                                 "no plenário e segue na comissão, segundo a agenda oficial da Casa.",
    "https://g1.globo.com/a": "O Senado aprovou nesta terça-feira a proposta que acaba com a escala 6x1, por 61 votos a "
                              "favor e 10 contra, em votação no plenário da Casa.",
    "https://www1.folha.uol.com.br/b": "Senadores aprovaram nesta terça a PEC do fim da escala 6x1 depois de meses de "
                                       "negociação entre governo e oposição no plenário.",
}
CIT_G1 = "O Senado aprovou nesta terça-feira a proposta que acaba com a escala 6x1, por 61 votos a favor"
CIT_FOLHA = "Senadores aprovaram nesta terça a PEC do fim da escala 6x1 depois de meses de negociação"


class _Af:
    def __init__(self, t):
        self.t = t

    def alvo(self):
        return self.t


def _cenario(classe_folha="SUSTENTA"):
    pecas = [{"url": u, "titulo": "", "corpo": t, "corpo_lido": True} for u, t in TEXTOS.items()]
    itens = [ItemEvidencia(url="https://lupa.uol.com.br/c", classe="REFUTA", motor=JUIZ, curada=True, corpo_lido=True,
                           agencia=True, data_pub="2026-09-20", citacao_verificada=True, veiculo="Lupa"),
             ItemEvidencia(url="https://g1.globo.com/a", classe="SUSTENTA", motor=JUIZ, curada=True, corpo_lido=True,
                           data_pub="2026-10-14", citacao_verificada=True, veiculo="g1"),
             ItemEvidencia(url="https://www1.folha.uol.com.br/b", classe=classe_folha, motor=JUIZ, curada=True,
                           corpo_lido=True, data_pub="2026-10-14", veiculo="Folha")]
    for it in itens:
        it.cluster = it.url
    julg = {(i, 0): {"classe": it.classe, "raciocinio": "", "citacao": ""} for i, it in enumerate(itens)}
    ev = Evidencias(afirmacoes=[AfirmacaoDecisao(texto=AF, nucleo=AF, calculada=True)], itens=itens,
                    n_lidas=3, n_consultadas=3, data_referencia="2026-10-19")
    return ev, [_Af(AF)], pecas, julg


@pytest.fixture
def ligado(monkeypatch):
    monkeypatch.setattr(config, "ADJUDICADOR", True)
    monkeypatch.setattr(config, "ADJUDICADOR_K", 1)
    monkeypatch.setattr(adjudicador.avaliador, "trecho_da_peca", lambda alvo, p: p.get("corpo") or "")
    return monkeypatch


def _llm(monkeypatch, *respostas):
    """chat_json simulado: devolve as respostas em ordem (None = falha). Guarda os prompts."""
    fila, prompts = list(respostas), []

    def fake(msgs, schema, **kw):
        prompts.append(msgs[0]["content"])
        r = fila.pop(0) if fila else None
        if r is None:
            return llm.ResultadoLLM(ok=False, erro="indisponível")
        return llm.ResultadoLLM(ok=True, dados=RespostaAdj.model_validate(r), modelo="fake")
    monkeypatch.setattr(adjudicador.llm, "chat_json", fake)
    return prompts


def _ordem(prompt):
    """Os itens vão ao LLM com posições primeiro, depois relatos, por URL: devolve a ordem das URLs."""
    return [u for u in sorted(TEXTOS, key=lambda u: prompt.index(TEXTOS[u][:40]))]


def test_desligado_nao_toca_na_evidencia(monkeypatch):
    monkeypatch.setattr(config, "ADJUDICADOR", False)
    ev, afs, pecas, julg = _cenario()
    assert adjudicador.aplicar(ev, afs, pecas, julg)["motivo"] == "desligado"
    assert ev.afirmacoes[0].tipo_temporal is None


def test_mudanca_citada_em_afirmacao_de_estado_leva_a_superacao(ligado):
    ev, afs, pecas, julg = _cenario()
    i = {u: k for k, u in enumerate(["https://g1.globo.com/a", "https://lupa.uol.com.br/c",
                                     "https://www1.folha.uol.com.br/b"])}
    prompts = _llm(ligado, {"tipo_temporal": "estado", "itens": [
        {"i": i["https://g1.globo.com/a"], "relata_mudanca": True, "citacao_mudanca": CIT_G1, "vale_em": "2026-10-14"},
        {"i": i["https://www1.folha.uol.com.br/b"], "relata_mudanca": True, "citacao_mudanca": CIT_FOLHA},
        {"i": i["https://lupa.uol.com.br/c"]}]})
    antes = decidir(ev)
    resumo = adjudicador.aplicar(ev, afs, pecas, julg)
    assert _ordem(prompts[0]) == list(i)  # a ordem que o teste supôs é a do prompt
    assert ev.afirmacoes[0].tipo_temporal == "estado" and len(resumo["afirmacoes"][0]["mudancas"]) == 2
    depois = decidir(ev)
    assert antes.nivel == "media" and depois.nivel == "baixa" and depois.travas["superacao"]


def test_mudanca_sem_citacao_conferida_e_rejeitada(ligado):
    ev, afs, pecas, julg = _cenario()
    _llm(ligado, {"tipo_temporal": "estado", "itens": [
        {"i": 0, "relata_mudanca": True, "citacao_mudanca": "o Senado finalmente aprovou tudo ontem à noite com festa"}]})
    resumo = adjudicador.aplicar(ev, afs, pecas, julg)
    assert not any(it.relata_mudanca for it in ev.itens)
    assert "mudança sem citação conferida" in resumo["afirmacoes"][0]["rejeitadas"][0]["motivos"]
    assert decidir(ev).nivel == "media"


def test_relata_vira_sustenta_so_com_citacao_e_atualiza_o_relatorio(ligado):
    ev, afs, pecas, julg = _cenario(classe_folha="RELATA_SEM_ENDOSSO")
    folha = 2  # posições primeiro (g1, lupa), depois o relato
    _llm(ligado, {"tipo_temporal": "evento", "itens": [{"i": folha, "revisao": "SUSTENTA", "citacao_revisao": CIT_FOLHA}]})
    adjudicador.aplicar(ev, afs, pecas, julg)
    assert ev.itens[2].classe == "SUSTENTA" and ev.itens[2].citacao_verificada is True
    assert julg[(2, 0)]["classe"] == "SUSTENTA" and julg[(2, 0)]["classe_juiz"] == "RELATA_SEM_ENDOSSO"


def test_relata_vira_sustenta_sem_citacao_e_rejeitado(ligado):
    ev, afs, pecas, julg = _cenario(classe_folha="RELATA_SEM_ENDOSSO")
    _llm(ligado, {"itens": [{"i": 2, "revisao": "SUSTENTA", "citacao_revisao": "trecho que não existe na página x y"}]})
    adjudicador.aplicar(ev, afs, pecas, julg)
    assert ev.itens[2].classe == "RELATA_SEM_ENDOSSO"


def test_inverter_a_direcao_vira_relata(ligado):
    ev, afs, pecas, julg = _cenario()
    _llm(ligado, {"itens": [{"i": 0, "revisao": "REFUTA", "citacao_revisao": CIT_G1}]})
    adjudicador.aplicar(ev, afs, pecas, julg)
    assert ev.itens[1].classe == "RELATA_SEM_ENDOSSO" and ev.itens[1].citacao_verificada is None


def test_falha_do_llm_deixa_a_evidencia_intacta(ligado):
    ev, afs, pecas, julg = _cenario()
    _llm(ligado, None)
    adjudicador.aplicar(ev, afs, pecas, julg)
    assert [it.classe for it in ev.itens] == ["REFUTA", "SUSTENTA", "SUSTENTA"]
    assert ev.afirmacoes[0].tipo_temporal is None


def test_resposta_normaliza_campos():
    r = RespostaAdj.model_validate({"tipo_temporal": "Estado atual", "itens": [
        {"i": 0, "revisao": "relata sem endosso", "relata_mudanca": "sim"}, {"i": 1, "revisao": None}]})
    assert r.tipo_temporal == "estado"
    assert r.itens[0].revisao == "RELATA_SEM_ENDOSSO" and r.itens[0].relata_mudanca is True
    assert r.itens[1].revisao == "manter"


# ------------------------------------------------------------------ validação pura
TXT = TEXTOS["https://g1.globo.com/a"]


def _alvo(classe="SUSTENTA", data="2026-10-14"):
    return [Alvo(j=7, texto=TXT, data_pub=data, classe=classe)]


@pytest.mark.parametrize("vale_em,esperado", [("2026-10-14", "2026-10-14"), ("2026-10-20", None),
                                               ("1990-01-01", None), ("ontem", None)])
def test_vale_em_nao_posterior_a_publicacao_nem_muito_antigo(vale_em, esperado):
    _, cs = validar(RespostaAdj(itens=[ItemAdj(i=0, vale_em=vale_em)]), _alvo())
    assert cs[0].vale_em == esperado


def test_indice_fora_do_intervalo_e_repetido_sao_ignorados():
    _, cs = validar(RespostaAdj(itens=[ItemAdj(i=5), ItemAdj(i=0), ItemAdj(i=0, revisao="RELATA_SEM_ENDOSSO")]), _alvo())
    assert len(cs) == 1 and cs[0].classe is None


def test_tipo_incerto_vira_none():
    tipo, _ = validar(RespostaAdj(tipo_temporal="incerto"), _alvo())
    assert tipo is None


# ------------------------------------------------------------------ consenso (K amostras)
def _a(tipo="estado", classe=None, mud=False, vale=None):
    return (tipo, [Correcao(j=7, classe=classe, citacao="c" if classe else "", relata_mudanca=mud, vale_em=vale)])


def test_consenso_posicao_e_mudanca_so_unanimes():
    tipo, cs = consenso([_a(classe="SUSTENTA", mud=True, vale="2026-10-14")] * 3)
    assert tipo == "estado" and cs[0].classe == "SUSTENTA" and cs[0].relata_mudanca and cs[0].vale_em == "2026-10-14"
    _, cs = consenso([_a(classe="SUSTENTA", mud=True), _a(classe="SUSTENTA", mud=True), _a()])
    assert cs[0].classe is None and not cs[0].relata_mudanca


def test_consenso_abstencao_nao_ajuda_a_criar_posicao():
    _, cs = consenso([_a(classe="SUSTENTA", mud=True), _a(classe="SUSTENTA", mud=True), None])
    assert cs[0].classe is None and not cs[0].relata_mudanca


def test_consenso_rebaixar_e_tipo_por_maioria_estrita():
    tipo, cs = consenso([_a(classe="RELATA_SEM_ENDOSSO"), _a(classe="RELATA_SEM_ENDOSSO", tipo="evento"), None])
    assert cs[0].classe == "RELATA_SEM_ENDOSSO" and tipo is None  # estado 1 × evento 1 de K=3: sem maioria


def test_k_maior_que_1_usa_sal_e_temperatura(ligado):
    ligado.setattr(config, "ADJUDICADOR_K", 3)
    ev, afs, pecas, julg = _cenario()
    vistos = []
    reais = (adjudicador.replay.com_sal, adjudicador.replay.temperatura)

    class Sal(reais[0]):
        def __init__(self, s):
            vistos.append(s)
            super().__init__(s)
    ligado.setattr(adjudicador.replay, "com_sal", Sal)
    resp = {"tipo_temporal": "estado", "itens": [{"i": 0, "relata_mudanca": True, "citacao_mudanca": CIT_G1}]}
    _llm(ligado, resp, resp, resp)
    adjudicador.aplicar(ev, afs, pecas, julg)
    assert vistos == ["adj1", "adj2"] and ev.itens[1].relata_mudanca


# ------------------------------------------------------------------ integração no pipeline (LLM simulado)
from test_sintetizador import _juiz_falso, _rodar_ibu, _resp, pipe_amb  # noqa: E402,F401  (fixture reaproveitada)


def _com_adjudicador(chamadas_adj, resposta):
    def envolve(fake):
        def f(messages, max_tokens, timeout_s, finalidade):
            if finalidade == "adjudicador":
                chamadas_adj.append(messages[-1]["content"])
                return json.dumps(resposta), "fake"
            return fake(messages, max_tokens, timeout_s, finalidade)
        return f
    return envolve


def test_pipeline_adjudicador_ligado_roda_antes_da_decisao_e_grava_o_evento(pipe_amb, monkeypatch):
    monkeypatch.setattr(config, "ADJUDICADOR", True)
    adj = []
    import test_sintetizador as ts  # `_rodar_ibu` monta o LLM falso por este nome: envolve-o com o adjudicador
    monkeypatch.setattr(ts, "_juiz_falso", lambda ch, s: _com_adjudicador(adj, {"tipo_temporal": "atemporal",
                                                                              "itens": []})(_juiz_falso(ch, s)))
    rel, chamadas = _rodar_ibu(pipe_amb, monkeypatch, [_resp("manter")], flag=False)
    assert len(adj) == 1 and "Ibuprofeno cura dengue" in adj[0]
    ev = next(d for t, d in pipe_amb["eventos"] if t == "evidencias")
    assert ev["afirmacoes"][0]["tipo_temporal"] == "atemporal"
    assert next(d for t, d in pipe_amb["eventos"] if t == "adjudicador")["aplicado"] is True
    assert rel.propensao == "alta"


def test_pipeline_adjudicador_desligado_nao_chama(pipe_amb, monkeypatch):
    monkeypatch.setattr(config, "ADJUDICADOR", False)
    rel, chamadas = _rodar_ibu(pipe_amb, monkeypatch, [_resp("manter")], flag=False)
    assert "adjudicador" not in chamadas and not [e for e in pipe_amb["eventos"] if e[0] == "adjudicador"]
    assert rel.propensao == "alta"
