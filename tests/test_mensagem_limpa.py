"""Resposta limpa para a pessoa: uma explicação, sem jargão interno, limitações em linguagem simples."""
from factcheck_mvp.agregador import (ETAPAS_PARA_PESSOA, limitacoes_para_pessoa, resumo_para_pessoa,
                                     verificar_neutralidade)
from factcheck_mvp.schemas import EntradaConsulta, EtapaRecibo, FonteEvidencia, RelatorioChecagem

MOTIVO = ("a única checagem encontrada trata de uma alegação parecida, mas não igual, à do texto: "
          "falta uma segunda fonte independente")
JARGAO = ("fallback", "L=+", "INDICE_CHECAGENS", "RF08", "placeholder", "llm-juiz", "avaliador", "p=0.")


def _rel():
    fonte = FonteEvidencia(url="https://www.boatos.org/politica/x.html", postura="REFUTA", relevante=True,
                           titulo="É falso que o ex-presidente morreu", quote="É falso que o ex-presidente morreu",
                           portal_nome="Boatos.org", veredito="FALSO", corpo_lido=True, confiabilidade="curada")
    return RelatorioChecagem(
        propensao="media", header="🟡 Propensão média de ser fake news",
        why_1linha="1 fonte(s) independente(s) contestam e 0 confirmam o que o texto afirma; 5 página(s) lida(s), 4 fora do tema.",
        justificativa="Propensão média de ser fake news. 1 fonte(s) independente(s) contestam (...). Isso não é um veredito.",
        consulta=EntradaConsulta(tipo="titulo", conteudo="o bolsonaro morreu"),
        fontes=[fonte], perguntas_guia=["Compare a data do fato com a data da publicação."],
        etapas=[EtapaRecibo(nome="afirmacoes", status="ok", detalhe="1 afirmação(ões) via fallback-regex"),
                EtapaRecibo(nome="base-checagem", status="ok", detalhe="5 checagem(ns) no índice (atalho INDICE_CHECAGENS=1)"),
                EtapaRecibo(nome="avaliador", status="ok", detalhe="5/5 avaliação(ões) 1:1"),
                EtapaRecibo(nome="modelo", status="ok", detalhe="estilo prob_fake=0.5"),
                EtapaRecibo(nome="agregacao", status="ok", detalhe="propensão media (L=+1.09, p=0.75)")],
        limitacoes=["Web pulada: checagem aplicável na base.", "Modelo de estilo ainda é um placeholder (RF08 parcial)."],
        decisao={"nivel": "media", "motivo": MOTIVO,
                 "votos": [{"urls": ["https://www.boatos.org/politica/x.html"], "direcao": 1.0, "valor": 1.09,
                            "afirmacao": 0, "cluster": "boatos.org"}]})


def test_limitacoes_em_linguagem_simples_e_sem_as_internas():
    lims = limitacoes_para_pessoa(["Web pulada: checagem aplicável na base.",
                                   "Modelo de estilo ainda é um placeholder (RF08 parcial).",
                                   "Descoberta web desligada (sem SERPAPI_KEY).",
                                   "Uma limitação nova que ninguém mapeou."])
    assert lims[0].startswith("Já existe uma checagem de agência") and "SERPAPI" not in " ".join(lims)
    assert not any("placeholder" in l for l in lims)
    assert lims[-1] == "Uma limitação nova que ninguém mapeou."  # desconhecida passa como está


def test_resumo_usa_o_motivo_e_lembra_que_nao_e_veredito():
    r = resumo_para_pessoa(_rel().decisao, "reserva")
    assert r.startswith("A única checagem encontrada trata de uma alegação parecida")
    assert "não é um veredito" in r
    assert resumo_para_pessoa(None, "Texto de reserva.").startswith("Texto de reserva.")


def test_etapas_para_pessoa_tiram_as_internas():
    assert {"avaliador", "modelo", "padroes", "descoberta-catalogo"}.isdisjoint(ETAPAS_PARA_PESSOA)
    assert {"base-checagem", "juiz", "agregacao"} <= set(ETAPAS_PARA_PESSOA)


def test_bot_usa_as_mesmas_limitacoes_e_etapas_e_lembra_que_nao_e_veredito():
    from factcheck_mvp.telegram_bot import formatar
    t = formatar(_rel())
    assert "placeholder" not in t and "Web pulada" not in t and "Já existe uma checagem de agência" in t
    assert "Modelo automático" not in t and "avaliador" not in t
    assert "não é um veredito" in t
