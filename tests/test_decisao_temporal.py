"""Rodada de 19/10 no agregador: M1 (conjunção monotônica), M3 (motivo da média), R11t (R11 com data) e
S1 (superação por mudança de estado, com linha do tempo)."""
import random

import pytest

from factcheck_mvp import decisao
from factcheck_mvp.agregador import verificar_neutralidade
from factcheck_mvp.decisao import AfirmacaoDecisao, Evidencias, ItemEvidencia, decidir

JUIZ = "llm-juiz:openrouter"
ORDEM = {"baixa": 0, "media": 1, "indeterminada": 1, "alta": 2}


def _it(url, classe, af=0, data=None, agencia=False, curada=True, mud=None, veiculo="", conf=None, vale_em=None):
    return ItemEvidencia(url=url, afirmacao=af, cluster=url, classe=classe, motor=JUIZ, citacao_verificada=True,
                         curada=curada, corpo_lido=True, agencia=agencia, data_pub=data, relata_mudanca=mud,
                         veiculo=veiculo, confiabilidade=conf, vale_em=vale_em)


def _ev(itens, textos=("O Senado aprovou o fim da escala 6x1",), tipo=None, ref=None, consulta=None):
    afs = [AfirmacaoDecisao(texto=t, nucleo=t, calculada=True, tipo_temporal=tipo) for t in textos]
    return Evidencias(afirmacoes=afs, itens=itens, n_lidas=len(itens), n_consultadas=len(itens),
                      data_referencia=ref, data_consulta=consulta)


def _neutro(d):
    assert verificar_neutralidade(f"{d.header()} {d.why_1linha()} {d.justificativa()}") == []


# ------------------------------------------------------------------ M1: conjunção monotônica
def _tres_partes(com_detalhe: bool):
    itens = [_it(f"https://v{a}{k}.com.br/x", "SUSTENTA", af=a) for a in (0, 2) for k in "xy"]
    if com_detalhe:
        itens.append(_it("https://g1.globo.com/z", "SUSTENTA", af=1))
    return _ev(itens, textos=("Lula defendeu o fim da 6x1", "A votação é em 14/10", "Flávio votará a favor"))


def test_m1_achar_uma_fonte_para_o_detalhe_nao_piora_o_nivel():
    """Caso 20261014-151128: duas partes com 2 fontes curadas e uma com só o g1. Sem fonte na parte do meio já
    dava baixa; achar UMA confirmação dela levava a média (confirmar aumentava a propensão)."""
    sem, com = decidir(_tres_partes(False)), decidir(_tres_partes(True))
    assert sem.nivel == com.nivel == "baixa"
    assert com.por_afirmacao[1]["confirmacao_fraca"] and com.travas["parte_com_confirmacao_fraca"]
    assert '"A votação é em 14/10" tem confirmação mais fraca' in com.justificativa()
    _neutro(com)


def test_m1_parte_fraca_com_voto_que_contesta_continua_contando():
    """Mista: a parte com uma fonte contestando (mesmo com L_a < 0) não é "só confirmação" e segura a média."""
    itens = [_it(f"https://v{k}.com.br/x", "SUSTENTA", af=0) for k in "xy"]
    itens += [_it("https://a.com.br/1", "SUSTENTA", af=1),
              _it("https://c.com.br/1", "REFUTA", af=1, conf="alto_trafego")]  # B: −1,0 + 0,6 = −0,4
    d = decidir(_ev(itens, textos=("A", "B")))
    assert -decisao.TAU < d.por_afirmacao[1]["L"] < 0
    assert d.nivel == "media" and "confirmacao_fraca" not in d.por_afirmacao[1]


def test_m1_funcao_parte_fraca_pura_e_mista():
    assert decisao._combinar_afirmacoes([-2.0, -0.5]) == -2.0
    assert decisao._combinar_afirmacoes([-2.0, -0.5], [False, True]) == -0.5
    assert decisao._combinar_afirmacoes([-0.4, -0.9]) == -0.4  # nenhuma decisiva: o máximo, como antes


@pytest.mark.parametrize("seed", range(40))
def test_m1_propriedade_acrescentar_sustenta_nunca_sobe_o_nivel(seed):
    """Propriedade: em qualquer texto de 1 a 4 partes com fontes nos dois sentidos, acrescentar uma SUSTENTA
    (fonte nova, cluster novo) nunca sobe o nível; acrescentar uma REFUTA nunca desce."""
    rnd = random.Random(seed)
    n = rnd.randint(1, 4)
    niveis = ("curada", "alto_trafego", "institucional", "plataforma", "baixo_trafego")
    itens = [_it(f"https://f{i}.com.br/x", rnd.choice(("SUSTENTA", "REFUTA", "SUSTENTA")), af=rnd.randrange(n),
                 conf=rnd.choice(niveis)) for i in range(rnd.randint(1, 7))]
    textos = tuple(f"Parte {k}" for k in range(n))
    base = decidir(_ev(itens, textos=textos))
    alvo = rnd.randrange(n)
    for conf in niveis:
        mais_s = decidir(_ev(itens + [_it(f"https://novo-{conf}.com/x", "SUSTENTA", af=alvo, conf=conf)], textos=textos))
        mais_r = decidir(_ev(itens + [_it(f"https://novo-{conf}.com/x", "REFUTA", af=alvo, conf=conf)], textos=textos))
        if base.nivel != "indeterminada":
            assert ORDEM[mais_s.nivel] <= ORDEM[base.nivel], (base.nivel, mais_s.nivel)
            assert ORDEM[mais_r.nivel] >= ORDEM[base.nivel], (base.nivel, mais_r.nivel)


# ------------------------------------------------------------------ M3: motivo da média
def test_m3_media_por_cobertura_e_media_por_conflito_tem_motivos_diferentes():
    cobertura = decidir(_ev([_it("https://g1.globo.com/a", "SUSTENTA")]))
    conflito = decidir(_ev([_it("https://g1.globo.com/a", "SUSTENTA"), _it("https://bbc.com/a", "REFUTA")]))
    assert cobertura.nivel == conflito.nivel == "media"
    assert "falta uma segunda fonte independente" in cobertura.motivo
    assert "fontes divergem" in conflito.motivo


# ------------------------------------------------------------------ R11t: a R11 só vale no mesmo período
LUPA = dict(agencia=True, veiculo="Lupa")


def _cenario_6x1(mud=None, conf=None):
    return [_it("https://lupa.uol.com.br/c", "REFUTA", data="2026-09-20", **LUPA),
            _it("https://g1.globo.com/a", "SUSTENTA", data="2026-10-14", mud=mud, veiculo="g1", conf=conf),
            _it("https://www1.folha.uol.com.br/b", "SUSTENTA", data="2026-10-14", mud=mud, veiculo="Folha", conf=conf)]


def test_r11t_confirmacao_posterior_a_checagem_vota_e_o_conflito_da_media():
    """Antes: alta (as duas confirmações de outubro eram anuladas pela checagem de setembro)."""
    d = decidir(_ev(_cenario_6x1(), ref="2026-10-19"))
    assert d.nivel == "media" and not d.posturas_suprimidas
    assert [x["url"] for x in d.posturas_posteriores] == ["https://g1.globo.com/a", "https://www1.folha.uol.com.br/b"]
    assert d.travas["confirmacao_posterior_a_checagem"]
    assert "a situação pode ter mudado" in d.motivo and "continuaram pesando" in d.justificativa()
    _neutro(d)


def test_r11t_confirmacao_do_mesmo_periodo_continua_anulada():
    """Boato desmentido e repetido no mesmo período (caso Bolsa Família 15%): a R11 vale como antes."""
    itens = [_it("https://lupa.uol.com.br/c", "REFUTA", data="2026-09-24", **LUPA),
             _it("https://tvbrusque.com.br/x", "SUSTENTA", data="2026-09-26", curada=False)]
    d = decidir(_ev(itens))
    assert d.nivel == "alta" and len(d.posturas_suprimidas) == 1 and not d.posturas_posteriores


@pytest.mark.parametrize("tipo", ["evento", "atemporal"])
def test_r11t_evento_e_atemporal_nao_mudam_com_o_tempo(tipo):
    d = decidir(_ev(_cenario_6x1(), tipo=tipo))
    assert d.nivel == "alta" and len(d.posturas_suprimidas) == 2


def test_r11t_sem_data_vale_como_antes():
    itens = [_it("https://lupa.uol.com.br/c", "REFUTA", data=None, **LUPA),
             _it("https://g1.globo.com/a", "SUSTENTA", data="2026-10-14")]
    assert decidir(_ev(itens)).posturas_suprimidas


# ------------------------------------------------------------------ S1: superação por mudança de estado
def test_s1_estado_com_mudanca_relatada_supera_a_checagem_antiga():
    d = decidir(_ev(_cenario_6x1(mud=True), tipo="estado", ref="2026-10-19"))
    assert d.nivel == "baixa" and d.travas["superacao"]
    assert [(x["tipo"], x["url"]) for x in d.superacoes] == [("superada", "https://lupa.uol.com.br/c")]
    assert [x["data"] for x in d.linha_do_tempo] == ["2026-09-20", "2026-10-14", "2026-10-14"]
    j = d.justificativa()
    assert "Linha do tempo de" in j and "20/09/2026, Lupa contesta (posição superada" in j
    assert "14/10/2026, g1 confirma e relata mudança da situação" in j
    assert "superada por mudança relatada depois" in d.why_1linha()
    _neutro(d)


def test_s1_sem_relato_de_mudanca_nao_ha_superacao():
    """Fonte nova que só repete o contrário é conflito (boato reciclado), não superação."""
    d = decidir(_ev(_cenario_6x1(mud=None), tipo="estado", ref="2026-10-19"))
    assert not d.superacoes and not d.linha_do_tempo and d.nivel == "media"


def test_s1_mudanca_relatada_por_fonte_pouco_confiavel_nao_supera():
    d = decidir(_ev(_cenario_6x1(mud=True, conf="baixo_trafego"), tipo="estado", ref="2026-10-19"))
    assert not d.superacoes


def test_s1_conteudo_anterior_a_mudanca_e_avaliado_na_data_dele():
    """Decisão da usuária (19/10): vale a data do conteúdo. Conteúdo de 25/09 dizendo que já foi aprovado: na data
    dele a checagem valia; a mudança de 14/10 é posterior e não pesa."""
    d = decidir(_ev(_cenario_6x1(mud=True), tipo="estado", ref="2026-09-25"))
    assert d.nivel == "alta"
    assert {x["tipo"] for x in d.superacoes} == {"mudanca_posterior_ao_conteudo"}
    assert "mudança posterior à data do conteúdo, não pesou" in d.justificativa()
    _neutro(d)


def test_s1_sem_data_do_conteudo_usa_a_data_da_consulta():
    d = decidir(_ev(_cenario_6x1(mud=True), tipo="estado", ref=None, consulta="2026-10-19"))
    assert d.nivel == "baixa" and d.travas["superacao"]


def test_s1_simetrico_era_verdade_e_deixou_de_ser():
    """Confirmações antigas ("X é ministro") superadas por mudança relatada depois ("foi demitido")."""
    itens = [_it("https://g1.globo.com/a", "SUSTENTA", data="2026-08-01", veiculo="g1"),
             _it("https://bbc.com/a", "SUSTENTA", data="2026-08-02", veiculo="BBC"),
             _it("https://estadao.com.br/b", "REFUTA", data="2026-10-10", mud=True, veiculo="Estadão"),
             _it("https://folha.uol.com.br/b", "REFUTA", data="2026-10-11", mud=True, veiculo="Folha")]
    d = decidir(_ev(itens, textos=("Fulano é ministro da Saúde",), tipo="estado", ref="2026-10-19"))
    assert d.nivel == "alta" and len([x for x in d.superacoes if x["tipo"] == "superada"]) == 2


def test_s1_vale_em_tem_precedencia_sobre_a_data_de_publicacao():
    """Página publicada em 15/10 que descreve a situação de 10/09 não é posterior à checagem de 20/09."""
    itens = [_it("https://lupa.uol.com.br/c", "REFUTA", data="2026-09-20", **LUPA),
             _it("https://g1.globo.com/a", "SUSTENTA", data="2026-10-15", vale_em="2026-09-10", mud=True)]
    d = decidir(_ev(itens, tipo="estado", ref="2026-10-19"))
    assert not [x for x in d.superacoes if x["tipo"] == "superada"]


def test_s1_sem_tipo_temporal_nao_ha_superacao():
    d = decidir(_ev(_cenario_6x1(mud=True), tipo=None, ref="2026-10-19"))
    assert not d.superacoes and d.nivel == "media"
