""""Como chegamos aqui" na web: passo a passo com os números do caso, só a partir da decisão."""
from types import SimpleNamespace as NS

from factcheck_mvp.agregador import FRASES_BINARIAS, passos_para_pessoa


def _rel(contagem, votos=(), etapas=(("descoberta", "ok"),), limitacoes=(), onde="web", fontes=(), L=0.8,
         nivel="media", travas=None, parametros=None):
    dec = {"contagem": contagem, "votos": list(votos), "motivo": "fontes independentes contestam o que o texto afirma",
           "por_afirmacao": [{"afirmacao": "Vacina altera o DNA", "L": L, "n_votos": len(votos)}],
           "log_odds": L, "nivel": nivel, "travas": travas or {}, "parametros": parametros or {"tau": 1.0986}}
    return NS(decisao=dec, etapas=[NS(nome=n, status=s) for n, s in etapas], limitacoes=list(limitacoes),
              onde_encontrado=onde, fontes=list(fontes), header="🔴 Alta propensão", propensao="alta")


CONTAGEM = {"consultadas": 10, "lidas": 7, "julgadas": 10, "sustenta": 0, "refuta": 6, "relata": 3,
            "fora_do_tema": 1, "sem_juiz": 0}
VOTOS = [{"afirmacao": 0, "cluster": "aosfatos.org", "valor": 1.5, "motivo": "postura REFUTA (agência)",
          "nivel": "curada"},
         {"afirmacao": 0, "cluster": "g1.globo.com", "valor": -1.0, "motivo": "postura SUSTENTA", "nivel": "curada"},
         {"afirmacao": 0, "cluster": "site.com.br", "valor": 0.3, "motivo": "postura REFUTA (data: r=0.50)",
          "nivel": "alto_trafego"}]


def _por_titulo(passos):
    return {p["titulo"]: p for p in passos}


def test_passos_trazem_os_numeros_do_caso():
    p = _por_titulo(passos_para_pessoa(_rel(CONTAGEM, VOTOS)))
    assert p["O que checamos"]["itens"] == ["“Vacina altera o DNA”"]
    assert p["Busca na web"]["texto"] == "Buscamos notícias sobre o assunto e chegamos a 10 páginas."
    assert p["Leitura das páginas"]["texto"].startswith("Lemos o texto completo de 7 das 10 páginas.")
    assert p["O que cada fonte diz"]["itens"] == ["6 contestam o que o texto afirma",
                                                  "3 só relatam o assunto, sem confirmar nem contestar",
                                                  "1 trata de outro assunto e não conta"]
    assert p["Peso de cada veículo"]["itens"] == [
        "aosfatos.org: contesta, +1,50 (agência de checagem contestando)",
        "g1.globo.com: confirma, −1,00 (veículo verificado pela equipe)",
        "site.com.br: contesta, +0,30 (site muito acessado; reduzido de 0,60 porque publicada fora do período "
        "que o texto descreve)"]
    assert p["A soma"]["itens"] == ["+1,50 −1,00 +0,30 = +0,80"]
    assert p["A soma"]["texto"].startswith("Pontuação final: +0,80. Faixas: +1,10 ou mais = propensão alta")
    assert p["Resultado"]["texto"] == "🔴 Alta propensão: fontes independentes contestam o que o texto afirma."


def test_soma_limitada_por_trava_diz_o_motivo():
    votos = [{"afirmacao": 0, "cluster": "x.com", "valor": 0.45, "motivo": "postura REFUTA", "nivel": "plataforma"}] * 3
    rel = _rel(CONTAGEM, votos, L=1.0877, travas={"sem_fonte_confiavel": True})
    conta = _por_titulo(passos_para_pessoa(rel))["A soma"]["itens"][0]
    assert conta.startswith("+0,45 +0,45 +0,45 = +1,35, limitada a +1,09 (fica na faixa média) porque nenhum veículo")


def test_nivel_ajustado_depois_da_soma_e_explicado():
    votos = [{"afirmacao": 0, "cluster": "g1.globo.com", "valor": -2.0, "motivo": "postura SUSTENTA", "nivel": "curada"}]
    rel = _rel(CONTAGEM, votos, L=-2.0, nivel="media",
               parametros={"tau": 1.0986, "sintetizador": {"frase": "Foram apontadas inconsistências entre as fontes."}})
    itens = _por_titulo(passos_para_pessoa(rel))["A soma"]["itens"]
    assert itens[-1] == ("A pontuação cai na faixa baixa, mas o resultado foi ajustado para média: "
                         "foram apontadas inconsistências entre as fontes.")


def test_voto_sem_confiabilidade_nao_inventa_reducao():
    votos = [{"afirmacao": 0, "cluster": "site.com.br", "valor": 0.3, "motivo": "postura REFUTA"}]
    itens = _por_titulo(passos_para_pessoa(_rel(CONTAGEM, votos, L=0.3)))["Peso de cada veículo"]["itens"]
    assert itens == ["site.com.br: contesta, +0,30 (fonte)"]


def test_busca_que_falhou_nao_vira_nada_encontrado():
    rel = _rel({"consultadas": 0}, etapas=(("descoberta", "parcial"),),
               limitacoes=["SerpAPI falhou nesta consulta (detalhe no log do servidor)."])
    texto = _por_titulo(passos_para_pessoa(rel))["Busca na web"]["texto"]
    assert "falhou" in texto and "não encontramos" not in texto


def test_achado_na_base_explica_por_que_nao_buscou_na_web():
    rel = _rel(CONTAGEM, etapas=(("descoberta", "pulada"),), onde="base",
               fontes=[NS(tipo_fonte="veredito"), NS(tipo_fonte="veredito"), NS(tipo_fonte="descoberta")])
    p = _por_titulo(passos_para_pessoa(rel))
    assert "Busca na web" not in p
    assert p["Checagens já publicadas"]["texto"].startswith("Encontramos 2 checagens de agências")


def test_sem_decisao_detalhada_devolve_vazio():
    assert passos_para_pessoa(NS(decisao=None)) == []
    assert passos_para_pessoa(NS(decisao={"motivo": "x"})) == []


def test_passos_sem_frase_binaria():
    textos = " ".join(p["texto"] + " ".join(p["itens"]) for p in passos_para_pessoa(_rel(CONTAGEM, VOTOS))).lower()
    assert not any(f.lower() in textos for f in FRASES_BINARIAS)
