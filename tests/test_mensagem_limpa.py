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


def _visivel(h):
    import html, re
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S)                 # código da página
    h = re.sub(r"<details class=\"tecnico[^\"]*\">.*?</details>", "", h, flags=re.S)  # detalhes técnicos recolhidos
    return html.unescape(re.sub(r"<[^>]+>", " ", h))


def _cartao(h, trecho_url):
    return next(c for c in h.split("<div class='p-4 rounded-xl") if trecho_url in c)


def test_web_limpa_sem_repeticao_nem_jargao_fora_dos_detalhes_tecnicos():
    from factcheck_mvp.api import _render_html
    h = _render_html("o bolsonaro morreu", _rel())
    v = _visivel(h)
    assert "Checa AI" in h and "CrossCheckBR" not in h
    assert "A única checagem encontrada" in v and "não é um veredito" in v
    assert "fonte(s)" not in v and "página(s)" not in v          # o resumo antigo, cheio de (s), saiu
    assert v.count("Propensão média de ser fake news") == 1        # sem repetir o resultado
    assert not [j for j in JARGAO if j in v], [j for j in JARGAO if j in v]
    assert "Já existe uma checagem de agência" in v and "Modelo automático" not in v
    assert v.count("É falso que o ex-presidente morreu") == 1      # trecho igual ao título não repete
    assert 'href="https://www.boatos.org/politica/x.html"' in h    # o link da fonte continua
    assert "fallback-regex" in h                                   # o detalhe técnico continua disponível
    import re
    resumo = re.search(r"<p class='resumo[^']*'>(.*?)</p>", h, re.S).group(1)
    assert verificar_neutralidade(resumo) == []    # a NOSSA conclusão (o título da fonte é da agência)


def test_bot_usa_as_mesmas_limitacoes_e_etapas_e_lembra_que_nao_e_veredito():
    from factcheck_mvp.telegram_bot import formatar
    t = formatar(_rel())
    assert "placeholder" not in t and "Web pulada" not in t and "Já existe uma checagem de agência" in t
    assert "Modelo automático" not in t and "avaliador" not in t
    assert "não é um veredito" in t


def test_selo_so_aparece_quando_a_fonte_confirma_ou_contesta():
    """Selo de página que só relata (ou trata de outro boato) não aparece: a pessoa leria que ele vale para a
    mensagem dela."""
    from factcheck_mvp.api import _render_html
    from factcheck_mvp.telegram_bot import formatar
    rel = _rel()
    outra = FonteEvidencia(url="https://www.boatos.org/politica/tunel.html", postura="RELATA_SEM_ENDOSSO",
                           relevante=True, titulo="É falso que bolsonarista morreu ao cavar túnel",
                           portal_nome="Boatos.org", veredito="FALSO", corpo_lido=True, confiabilidade="curada")
    rel.fontes.append(outra)
    h = _render_html("x", rel)
    cartao_outra = _cartao(h, "tunel.html")
    cartao_principal = _cartao(h, "x.html")
    assert "selo da agência" not in cartao_outra and "selo da agência: FALSO" in cartao_principal
    t = formatar(rel)
    linha_outra = next(l for l in t.splitlines() if "túnel" in l)
    assert "selo" not in linha_outra and any("selo da agência: FALSO" in l for l in t.splitlines())


def test_json_da_api_traz_os_campos_para_a_pessoa():
    """A página em JavaScript usa só o JSON de /checar: os campos para a pessoa vêm prontos da API."""
    from factcheck_mvp.agregador import preparar_para_pessoa
    rel = preparar_para_pessoa(_rel())
    d = rel.model_dump()
    assert d["resumo_pessoa"].startswith("A única checagem encontrada") and "não é um veredito" in d["resumo_pessoa"]
    assert d["limitacoes_pessoa"] == ["Já existe uma checagem de agência sobre isso, então não buscamos outras notícias na web."]
    assert d["etapas_pessoa"] == ["✅ Identificação das afirmações", "✅ Base de checagens", "✅ Estimativa final"]
    assert d["fontes"][0]["selo_visivel"] is True


def test_pagina_em_javascript_usa_os_campos_para_a_pessoa():
    from pathlib import Path
    t = (Path(__file__).resolve().parents[1] / "factcheck_mvp" / "templates" / "index.html").read_text(encoding="utf-8")
    # O JS não desenha o relatório: insere o bloco do servidor (_relatorio_html, coberto acima).
    assert "fetch('/checar-html'" in t and "renderClientRelatorio" not in t
    assert "rel.justificativa" not in t               # o parágrafo longo que repetia o resultado saiu
    assert "IFCN" not in t and "Laudo" not in t
