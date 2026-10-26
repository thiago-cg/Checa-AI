"""RF12/RNF02: redação neutra do relatório (escala, nunca binário).

Desde a fase 2 a DECISÃO mora em `decisao.decidir` (uma função pura; log-odds
simétrico; um voto por cluster). Este módulo guarda só o que é de linguagem:
frases proibidas, emoji por nível, perguntas-guia e o header. O antigo
`agregar` (soma ponderada de sinais heterogêneos, "cobertura ampla" = −0,5,
direção de selo por substring) foi removido.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

from . import telemetria

# Qualquer conclusão binária é proibida na saída (RF12). Varredura em testes.
FRASES_BINARIAS = (
    "é falso", "é falsa", "é verdade", "é verdadeiro", "é mentira",
    "fake news confirmada", "notícia falsa", "notícia verdadeira",
)
# Neutralidade (check #6): adjetivos/partidarismo nunca saem no relatório
EXPRESSOES_PROIBIDAS = FRASES_BINARIAS + (
    "com certeza", "sem dúvida", "absurdo", "ridículo",
    "esquerdalha", "bolsominion", "petista", "bolsonarista",
    "corrupto", "idiota", "chocante", "incrível",
)
EMOJI_PROPENSAO = {"baixa": "🟢", "media": "🟡", "alta": "🔴", "indeterminada": "⚪"}
# Linguagem para o usuário: sempre "propensão de ser fake news", nunca veredito.
TITULO_PROPENSAO = {
    "alta": "Alta propensão de ser fake news",
    "media": "Propensão média de ser fake news",
    "baixa": "Baixa propensão de ser fake news",
    "indeterminada": "Não foi possível estimar a propensão de ser fake news",
}

_PERGUNTAS_GUIA = [
    "Compare a data do fato com a data da publicação: o conteúdo é atual ou reciclado?",
    "Quem assina o conteúdo original? Há veículo conhecido por trás?",
    "A mesma informação aparece em mais de um veículo independente? Quais?",
]


# E5 (opção b): selo sempre atribuído à agência ("Selo da Lupa: FALSO");
# a NOSSA conclusão continua em escala de propensão, nunca binária.
_SELO_ATRIBUIDO_RE = re.compile(
    r"selo\s+d[ao]\s+(?P<agencia>.+?)\s*:\s*(?P<selo>(?:(?!\bselo\s+d[ao]\b)[^.,;:])+)",
    re.IGNORECASE,
)

def formatar_selo(agencia: str, selo: str, artigo: str = "da") -> str:
    """Selo sempre atribuído à agência: "Selo da Lupa: FALSO"."""
    if artigo not in ("da", "do"):
        raise ValueError(f"artigo deve ser 'da' ou 'do', recebido: {artigo!r}")
    return f"Selo {artigo} {(agencia or '').strip()}: {(selo or '').strip()}"


# B1a/C1: raciocínio do avaliador por fonte. É texto livre do LLM, então sai SEMPRE atribuído ao
# avaliador automático, numa linha só. A varredura NÃO isenta essa linha: quem a protege é o render.
# Se o raciocínio traz expressão proibida (ou selo em formato atribuído), a linha é OMITIDA
# (`linha_raciocinio`): bot e web seguem a mesma regra que a varredura.
ROTULO_RACIOCINIO = "Avaliação automática:"


def texto_de_linha(texto: Any) -> str:
    """Achata em UMA linha: quebras (\\n, \\r, U+2028/2029, NEL) e espaços repetidos viram um espaço.
    Título, citação e raciocínio vindos de página entram assim, para não forjar linha própria."""
    return " ".join(str(texto or "").split())


def _normalizar_texto(texto: str) -> str:
    """Forma comparável pela varredura (I2): NFKC; qualquer espaço (NBSP, U+2028/2029, quebras)
    vira espaço; formatação e controle (zero-width, soft hyphen, BOM, bidi) somem; espaços se
    colapsam; minúsculas. Os acentos são mantidos (ver `_sem_acento`)."""
    s = unicodedata.normalize("NFKC", texto or "")
    s = re.sub(r"\s", " ", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) not in ("Cf", "Cc"))
    return re.sub(r"\s+", " ", s).strip().casefold()


def _sem_acento(texto: str) -> str:
    """Sem diacríticos: decompõe (NFD) e descarta as marcas combinantes."""
    return "".join(ch for ch in unicodedata.normalize("NFD", texto) if unicodedata.category(ch) != "Mn")


def _padrao_sem_acento(expressao: str) -> "re.Pattern[str]":
    """Expressão como palavras inteiras, sem acento: "e falso" casa "é falso" e "E falso", mas não
    "acidente falso" nem "que falso"."""
    palavras = [re.escape(_sem_acento(_normalizar_texto(p))) for p in expressao.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(palavras) + r"(?!\w)")


_PADROES_SEM_ACENTO = {e: _padrao_sem_acento(e) for e in EXPRESSOES_PROIBIDAS}


def _expressoes_achadas(base: str) -> List[str]:
    """Expressões de EXPRESSOES_PROIBIDAS em `base` (já normalizado). Com acento: como trecho (como
    antes). Sem acento: como palavras inteiras. Vale a união: nenhuma das duas formas escapa."""
    sem = _sem_acento(base)
    return [e for e in EXPRESSOES_PROIBIDAS
            if _normalizar_texto(e) in base or _PADROES_SEM_ACENTO[e].search(sem)]


def linha_raciocinio(raciocinio: Optional[str], limite: Optional[int] = None) -> str:
    """Linha atribuída: "🧠 Avaliação automática: <raciocinio>" ("" se vazio ou omitido).

    C1: se o raciocínio (normalizado, I2) traz expressão proibida ou selo em formato atribuído, a
    linha é OMITIDA e registra-se `telemetria.fallback("raciocinio", ...)`. Quebras viram espaço,
    para a linha continuar sendo uma só. `limite` corta só a EXIBIÇÃO, com "…"; o dado em `Fonte`
    nunca muda."""
    texto = texto_de_linha(raciocinio)
    if not texto:
        return ""
    base = _normalizar_texto(texto)
    achadas = _expressoes_achadas(base)
    if achadas or _SELO_ATRIBUIDO_RE.search(base):
        binaria = any(e in FRASES_BINARIAS for e in achadas)
        telemetria.fallback("raciocinio", "expressao binaria omitida" if binaria
                            else "expressao proibida omitida")
        return ""
    if limite and len(texto) > limite:
        texto = texto[: limite - 1].rstrip() + "…"
    return f"🧠 {ROTULO_RACIOCINIO} {texto}"


_DATA_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def data_publicacao_legivel(data_pub: Optional[str], precisao: Optional[str] = None) -> str:
    """Data de publicação para o usuário (bot e web), a partir da data NORMALIZADA (UTC−3, a
    mesma que a decisão usou). Precisão "ano" (placeholder de ano do extrator ou "há N meses")
    mostra só o ano; as demais, DD/MM/AAAA. Sem data ISO reconhecível devolve "": nunca o texto
    bruto (um "há 3 dias" não vira "publicada em há 3 dias")."""
    m = _DATA_ISO_RE.match(str(data_pub or "").strip())
    if not m:
        return ""
    ano, mes, dia = m.groups()
    return ano if precisao == "ano" else f"{dia}/{mes}/{ano}"


# M5: unidade relativa normalizada (as chaves de aplicabilidade) -> (singular, plural) em português.
_UNIDADES_RELATIVAS_PT = {
    "minuto": ("minuto", "minutos"), "minutos": ("minuto", "minutos"),
    "minute": ("minuto", "minutos"), "minutes": ("minuto", "minutos"),
    "hora": ("hora", "horas"), "horas": ("hora", "horas"),
    "hour": ("hora", "horas"), "hours": ("hora", "horas"),
    "dia": ("dia", "dias"), "dias": ("dia", "dias"),
    "day": ("dia", "dias"), "days": ("dia", "dias"),
    "semana": ("semana", "semanas"), "semanas": ("semana", "semanas"),
    "week": ("semana", "semanas"), "weeks": ("semana", "semanas"),
    "mes": ("mês", "meses"), "meses": ("mês", "meses"),
    "month": ("mês", "meses"), "months": ("mês", "meses"),
    "ano": ("ano", "anos"), "anos": ("ano", "anos"),
    "year": ("ano", "anos"), "years": ("ano", "anos"),
}


def _tempo_relativo_pt(bruta: Optional[str]) -> Optional[str]:
    """"3 dias", "1 semana", "2 meses" a partir da data relativa bruta ("há 3 dias", "3 days ago").
    None se a bruta não é relativa. Só chama a detecção e o parser de aplicabilidade."""
    from .aplicabilidade import _normalizar, _relativa, e_relativa
    if not e_relativa(bruta):
        return None
    qtd, unidade = _relativa(_normalizar(bruta))
    sing, plur = _UNIDADES_RELATIVAS_PT.get(unidade, (unidade, unidade))
    return f"{qtd} {sing if qtd == 1 else plur}"


def data_publicacao_exibida(data_pub: Optional[str], precisao: Optional[str] = None,
                            bruta: Optional[str] = None) -> str:
    """Data de publicação para o usuário (bot e web). Bruta absoluta: "publicada em 06/10/2026".
    Bruta relativa ("há 3 dias"): a data normalizada veio da âncora (a data da busca), não da página,
    então sai aproximada: "publicada há cerca de 3 dias (≈06/10/2026)". "" sem data reconhecível."""
    dtxt = data_publicacao_legivel(data_pub, precisao)
    if not dtxt:
        return ""
    tempo = _tempo_relativo_pt(bruta)
    if tempo is None:
        return f"publicada em {dtxt}"
    return f"publicada há cerca de {tempo} (≈{dtxt})"


def _agencias_checagem() -> frozenset:
    """Nomes normalizados das agências de checagem do catálogo (leitura fresca)."""
    nomes = set()
    try:
        from .catalogo import Catalogo, normalizar_nome
        for p in Catalogo.carregar().checagem():
            for n in [p.get("nome"), p.get("id")] + list(p.get("aliases_nome") or []):
                k = normalizar_nome(n)
                if k:
                    nomes.add(k)
    except Exception as e:
        from . import telemetria
        telemetria.fallback("agregador", f"catalogo indisponivel p/ selo atribuido: {e}")
    return frozenset(nomes)


def verificar_neutralidade(texto: str) -> List[str]:
    """Retorna expressões proibidas encontradas (vazio = neutro).

    E5: o selo atribuído ("Selo da Lupa: FALSO", com agência do catálogo) é citação, não veredito
    nosso, e é ignorado. Selo em outro formato (agência não cadastrada) é sinalizado com o trecho.
    C1: a linha do raciocínio NÃO é isenta; `linha_raciocinio` a omite quando traz expressão proibida.
    I2: o texto é normalizado (Unicode e sem acento) antes da busca (`_normalizar_texto`).
    """
    base = _normalizar_texto(texto)
    registradas = _agencias_checagem()

    def _corta(m: re.Match) -> str:
        from .catalogo import normalizar_nome
        if normalizar_nome(m.group(1)) in registradas:
            return " "
        return m.group(0)

    resto = _SELO_ATRIBUIDO_RE.sub(_corta, base)
    achadas = _expressoes_achadas(resto)
    achadas += [m.group(0).strip() for m in _SELO_ATRIBUIDO_RE.finditer(resto)]
    return list(dict.fromkeys(achadas))


def perguntas_guia() -> List[str]:
    """Perguntas para o usuário avaliar sozinho. A de data ("Compare a data…") é sempre a
    primeira: com desconto temporal ela já está no topo, então não há parâmetro para isso."""
    return list(_PERGUNTAS_GUIA)


def titulo_propensao(propensao: str) -> str:
    return TITULO_PROPENSAO.get(propensao, TITULO_PROPENSAO["indeterminada"])


def gerar_header(propensao: str, why: str = "") -> Dict[str, str]:
    """Header legível em segundos (check #1). O `why` vem de `Decisao.why_1linha()`."""
    emoji = EMOJI_PROPENSAO.get(propensao, "⚪")
    return {"header": f"{emoji} {titulo_propensao(propensao)}", "why_1linha": why}


# ------------------------------------------------- rótulos do bot e da web (mesma linguagem)
NOMES_ETAPAS = {
    "recebimento": "Leitura do texto",
    "afirmacoes": "Identificação das afirmações",
    "base-checagem": "Base de checagens",
    "descoberta-agente": "Planejamento da busca",
    "descoberta": "Busca de notícias",
    "deep-crawl": "Leitura das notícias",
    "juiz": "Análise das fontes",
    "corroboracao": "Comparação entre veículos",
    "agregacao": "Estimativa final",
    "agente-critico": "Revisão da busca",
    "descoberta-catalogo": "Novos sites no catálogo",
    "modelo": "Modelo automático",
    "padroes": "Padrões de desinformação",
}
STATUS_ETAPA = {"ok": "✅", "parcial": "⚠️", "pulada": "⏭️", "falha": "❌"}

# Etapas que a pessoa vê em "Como chegamos aqui". As demais (avaliador, modelo de estilo, padrões,
# planejamento e revisão da busca, catálogo) são internas: ficam só nos detalhes técnicos e no trace.
ETAPAS_PARA_PESSOA = ("recebimento", "afirmacoes", "base-checagem", "descoberta", "deep-crawl", "juiz",
                      "corroboracao", "agregacao")

# Limitações do pipeline em linguagem simples (prefixo do texto original -> texto para a pessoa; None = interna,
# não aparece). Limitação sem tradução aqui passa como está.
_LIMITACOES_PARA_PESSOA = (
    ("Web pulada: checagem aplicável na base",
     "Já existe uma checagem de agência sobre isso, então não buscamos outras notícias na web."),
    ("Modelo de estilo ainda é um placeholder", None),
    ("Relato de segunda-mão",
     "A mensagem é um relato de segunda mão (\"me disseram que…\"): checamos o fato principal."),
    ("Texto com marcas de opinião/sátira",
     "O texto parece opinião ou humor: isso não dá para checar como fato."),
    ("Afirmação vaga",
     "A afirmação é vaga: diga qual dado e qual período (por exemplo, a inflação de 2025) que checamos de novo."),
    ("Descoberta web atingiu o teto",
     "A busca na web demorou demais e foi interrompida: o resultado pode estar incompleto."),
    ("Sem julgamento de conteúdo",
     "O serviço que analisa as notícias está indisponível agora: tente de novo mais tarde."),
    ("Descoberta web desligada",
     "A busca na web está desligada: usamos só as checagens já publicadas."),
    ("SerpAPI falhou",
     "A busca na web falhou agora: usamos só as checagens já publicadas."),
    ("SerpAPI sem resultados",
     "A busca na web não encontrou notícias sobre isso."),
)


def mostra_selo(fonte: Any, direcoes: Dict[str, float]) -> bool:
    """O selo da agência só aparece quando a fonte confirma ou contesta a afirmação: ao lado de uma página
    que só relata (ou trata de outro boato), a pessoa leria que o selo vale para a mensagem dela."""
    return bool(getattr(fonte, "veredito", None)) and postura_legivel(fonte, direcoes) in (
        "contesta o que o texto afirma", "confirma o que o texto afirma")


def limitacoes_para_pessoa(limitacoes: List[str]) -> List[str]:
    """Limitações reescritas para quem lê, sem as internas e sem repetição (mesma ordem)."""
    saida: List[str] = []
    for lim in limitacoes or []:
        texto = next((novo for prefixo, novo in _LIMITACOES_PARA_PESSOA if lim.startswith(prefixo)), lim)
        if texto and texto not in saida:
            saida.append(texto)
    return saida


def preparar_para_pessoa(rel: Any) -> Any:
    """Preenche no relatório os campos para a pessoa (a página em JavaScript usa só o JSON)."""
    direcoes = direcoes_por_url(getattr(rel, "decisao", None))
    rel.resumo_pessoa = resumo_para_pessoa(rel.decisao, rel.why_1linha or rel.justificativa)
    rel.limitacoes_pessoa = limitacoes_para_pessoa(rel.limitacoes)
    rel.etapas_pessoa = [f"{STATUS_ETAPA.get(e.status, '')} {NOMES_ETAPAS.get(e.nome, e.nome)}".strip()
                         for e in (rel.etapas or []) if e.nome in ETAPAS_PARA_PESSOA]
    for f in rel.fontes or []:
        f.selo_visivel = mostra_selo(f, direcoes)
    return rel


def resumo_para_pessoa(decisao: Any, reserva: str = "") -> str:
    """Uma explicação em português comum: o motivo da decisão (já escrito para pessoas), com a lembrança
    de que não é veredito (RF14). Sem `decisao` (relatório antigo), usa o texto de reserva."""
    motivo = str((decisao or {}).get("motivo") or "").strip() if isinstance(decisao, dict) else ""
    base = (motivo[:1].upper() + motivo[1:]) if motivo else (reserva or "").strip()
    if base and not base.endswith((".", "!", "?")):
        base += "."
    return (base + " Isso não é um veredito: compare as fontes abaixo e decida por conta própria.").strip()


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def _num(x: float, sinal: bool = True) -> str:
    """Número com vírgula decimal e sinal explícito (+1,50 / −0,60)."""
    s = f"{abs(x):.2f}".replace(".", ",")
    return (("+" if x >= 0 else "−") + s) if sinal else s


_FAIXA = {"alta": "alta", "baixa": "baixa", "media": "média", "indeterminada": "indeterminada"}

# Razão de uma trava ter limitado a pontuação de uma afirmação (decisao._agregar).
_TRAVAS_SOMA = (
    ("sem_fonte_confiavel", "nenhum veículo verificado, órgão público ou site muito acessado toma essa posição; "
                            "redes sociais e sites pouco acessados sozinhos não definem o resultado"),
    ("so_fontes_de_outro_periodo", "as fontes que tomam essa posição são de antes do período que o texto descreve"),
    ("indice_similaridade_baixa", "a única checagem encontrada trata de uma alegação parecida, mas não igual"),
)


def _peso_explicado(v: Dict[str, Any], nivel: Optional[str], dec: Dict[str, Any]) -> str:
    """Por que o voto pesou o que pesou, a partir do motivo do voto e da confiabilidade da fonte.
    Sem a confiabilidade (relatório antigo), só diz o tipo do voto: não inventa uma redução."""
    from . import confiabilidade as cf
    motivo = str(v.get("motivo") or "")
    if "agência" not in motivo and nivel not in cf.FATOR_POSTURA:
        return "selo de checagem publicada" if motivo.startswith("selo") else "fonte"
    if "agência" in motivo:
        quem, base = "agência de checagem contestando", 1.5
    elif motivo.startswith("selo"):
        selo = ", ".join(v.get("vereditos") or []) or "da checagem"
        quem, base = f"selo {selo} de checagem publicada", 1.5 * cf.FATOR_VEREDITO[nivel]
    else:
        quem, base = cf.ROTULO[nivel], cf.FATOR_POSTURA[nivel]
    peso = abs(float(v.get("valor") or 0))
    if peso >= base - 0.005:
        return quem
    urls = set(v.get("urls") or [])
    if "data:" in motivo:
        porque = "publicada fora do período que o texto descreve"
    elif any(a.get("url") in urls for a in dec.get("posturas_atenuadas") or []):
        porque = "uma agência de checagem já contestou essa afirmação"
    else:
        porque = "a página teve credibilidade baixa na avaliação automática"
    return f"{quem}; reduzido de {_num(base, False)} porque {porque}"


def _passos_da_soma(rel: Any, dec: Dict[str, Any], votos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Os passos "Peso de cada veículo" e "A soma": os mesmos números de decisao.decidir, só traduzidos."""
    from . import confiabilidade as cf
    nivel_url = {f.url: getattr(f, "confiabilidade", None) for f in getattr(rel, "fontes", None) or []}
    tau = float((dec.get("parametros") or {}).get("tau") or 1.0986)
    por_af = [a for a in dec.get("por_afirmacao") or [] if isinstance(a, dict)]
    varias = sum(1 for a in por_af if a.get("n_votos")) > 1

    itens = []
    for v in votos:
        nivel = v.get("nivel") or next((nivel_url[u] for u in v.get("urls") or [] if nivel_url.get(u)), None)
        pos = "contesta" if float(v["valor"]) > 0 else "confirma"
        af = f" (afirmação {int(v.get('afirmacao', 0)) + 1})" if varias else ""
        itens.append(f"{v['cluster']}{af}: {pos}, {_num(float(v['valor']))} ({_peso_explicado(v, nivel, dec)})")
    pesos = " · ".join(f"{cf.ROTULO[n]} {_num(cf.FATOR_POSTURA[n], False)}"
                       for n in (cf.CURADA, cf.INSTITUCIONAL, cf.ALTO_TRAFEGO, cf.PLATAFORMA, cf.BAIXO_TRAFEGO))
    passos = [{"titulo": "Peso de cada veículo",
               "texto": ("Cada veículo que confirma ou contesta vale um voto; várias reportagens do mesmo veículo "
                         "contam uma vez só. Contestar soma pontos (+) e confirmar tira pontos (−). O peso depende "
                         f"de quem é a fonte: agência de checagem 1,50 · {pesos}."),
               "itens": itens}]

    contas = []
    for i, a in enumerate(por_af):
        vs = [float(v["valor"]) for v in votos if int(v.get("afirmacao", 0)) == i]
        if not vs:
            continue
        soma, L_a = sum(vs), float(a.get("L") or 0)
        conta = " ".join(_num(x) for x in vs) + f" = {_num(soma)}"
        if varias:
            conta = f"Afirmação {i + 1}: {conta}"
        if abs(L_a - soma) > 0.005:
            razoes = [r for chave, r in _TRAVAS_SOMA if (dec.get("travas") or {}).get(chave)]
            conta += (f", limitada a {_num(L_a)} (fica na faixa média) porque "
                      + ("; ".join(razoes) if razoes else "uma regra de segurança da decisão se aplicou"))
        if a.get("fora_da_conjuncao"):
            conta += " (não entra no total: só há fontes de outro período)"
        contas.append(conta)
    L = float(dec.get("log_odds") or 0)
    if varias:
        if L < 0:  # decisao._combinar_afirmacoes: sem parte contestada, vale a confirmação mais fraca
            contas.append(f"Total do texto: {_num(L)}. Todas as partes foram confirmadas; vale a confirmação "
                          "mais fraca entre elas.")
        else:
            contas.append(f"Total do texto: {_num(L)}. Basta uma parte contestada para o texto contar como "
                          "contestado; partes confirmadas não compensam as contestadas.")
    faixa = "alta" if L >= tau else "baixa" if L <= -tau else "media"
    final = dec.get("nivel") or getattr(rel, "propensao", "")
    if final == "indeterminada":
        contas.append("Mesmo com essa pontuação, não foi possível estimar a propensão: "
                      + str(dec.get("motivo") or "").rstrip(".") + ".")
    elif final and final != faixa:
        # Regra posterior à soma (ex.: o sintetizador viu contradição entre as fontes) mudou o nível.
        porque = str(((dec.get("parametros") or {}).get("sintetizador") or {}).get("frase") or dec.get("motivo") or "")
        contas.append(f"A pontuação cai na faixa {_FAIXA[faixa]}, mas o resultado foi ajustado para "
                      f"{_FAIXA[final]}" + (f": {porque[:1].lower() + porque[1:].rstrip('.')}." if porque else "."))
    t = _num(tau, False)
    passos.append({"titulo": "A soma",
                   "texto": (f"Pontuação final: {_num(L)}. Faixas: +{t} ou mais = propensão alta; −{t} ou menos "
                             f"= propensão baixa; entre as duas = propensão média."),
                   "itens": contas})
    return passos


def passos_para_pessoa(rel: Any) -> List[Dict[str, Any]]:
    """"Como chegamos aqui" com os números do caso: o que foi checado, quanto se leu, o que cada fonte
    disse, quantos veículos independentes contaram e por que o resultado saiu assim. Só dados já na
    decisão (nada novo é calculado aqui). Cada passo: {"titulo", "texto", "itens"}. Lista vazia =
    relatório sem decisão detalhada (a página usa a lista curta de `etapas_pessoa`)."""
    dec = getattr(rel, "decisao", None)
    if not isinstance(dec, dict) or not isinstance(dec.get("contagem"), dict):
        return []
    c = dec["contagem"]
    status = {e.nome: e.status for e in (getattr(rel, "etapas", None) or [])}
    passos: List[Dict[str, Any]] = []

    afs = [str(a.get("afirmacao") or "").strip() for a in dec.get("por_afirmacao") or [] if isinstance(a, dict)]
    afs = [a for a in afs if a]
    if afs:
        passos.append({"titulo": "O que checamos",
                       "texto": ("Separamos do texto a afirmação que dá para verificar:" if len(afs) == 1 else
                                 f"Separamos do texto {len(afs)} afirmações que dá para verificar:"),
                       "itens": [f"“{a}”" for a in afs]})

    agencias = [f for f in getattr(rel, "fontes", None) or [] if getattr(f, "tipo_fonte", "") == "veredito"]
    busca_falhou = any(str(l).startswith("SerpAPI falhou") for l in getattr(rel, "limitacoes", None) or [])
    if getattr(rel, "onde_encontrado", "web") == "base" and agencias:
        passos.append({"titulo": "Checagens já publicadas",
                       "texto": (f"Encontramos {_plural(len(agencias), 'checagem', 'checagens')} de agências sobre "
                                 "o assunto. Por isso não buscamos outras notícias na web."), "itens": []})
    elif busca_falhou or status.get("descoberta") == "falha":
        passos.append({"titulo": "Busca na web", "texto": "A busca na web falhou nesta consulta: não foi "
                                                          "possível procurar notícias sobre o assunto.", "itens": []})
    elif status.get("descoberta") in ("ok", "parcial"):
        consultadas = int(c.get("consultadas") or 0)
        texto = (f"Buscamos notícias sobre o assunto e chegamos a {_plural(consultadas, 'página', 'páginas')}."
                 if consultadas else "Buscamos notícias sobre o assunto, mas não encontramos nenhuma página.")
        passos.append({"titulo": "Busca na web", "texto": texto, "itens": []})

    consultadas, lidas = int(c.get("consultadas") or 0), int(c.get("lidas") or 0)
    if consultadas:
        if lidas >= consultadas:
            texto = f"Lemos o texto completo {'da única página' if consultadas == 1 else f'das {consultadas} páginas'}."
        else:
            texto = (f"Lemos o texto completo de {lidas} das {consultadas} páginas. "
                     "Das outras, só tivemos acesso ao título.")
        passos.append({"titulo": "Leitura das páginas", "texto": texto, "itens": []})

    julgadas = int(c.get("julgadas") or 0)
    if julgadas:
        itens = []
        for chave, um, varios in (("refuta", "contesta o que o texto afirma", "contestam o que o texto afirma"),
                                  ("sustenta", "confirma o que o texto afirma", "confirmam o que o texto afirma"),
                                  ("relata", "só relata o assunto, sem confirmar nem contestar",
                                   "só relatam o assunto, sem confirmar nem contestar"),
                                  ("fora_do_tema", "trata de outro assunto e não conta",
                                   "tratam de outro assunto e não contam")):
            n = int(c.get(chave) or 0)
            if n:
                itens.append(f"{n} {um if n == 1 else varios}")
        sem = int(c.get("sem_juiz") or 0)
        if sem:
            itens.append(f"{_plural(sem, 'página não pôde ser analisada', 'páginas não puderam ser analisadas')}")
        passos.append({"titulo": "O que cada fonte diz",
                       "texto": f"Comparamos cada página com a afirmação ({_plural(julgadas, 'página', 'páginas')}):",
                       "itens": itens})

    votos = [v for v in dec.get("votos") or [] if isinstance(v, dict) and v.get("cluster") and v.get("valor")]
    if votos:
        passos.extend(_passos_da_soma(rel, dec, votos))

    motivo = str(dec.get("motivo") or "").strip().rstrip(".")
    if motivo:
        passos.append({"titulo": "Resultado",
                       "texto": f"{getattr(rel, 'header', '') or titulo_propensao(rel.propensao)}: "
                                f"{motivo[:1].lower() + motivo[1:]}.", "itens": []})
    return passos


_POSTURA_SEM_VOTO = {
    "RELATA_SEM_ENDOSSO": "relata o assunto sem tomar posição",
    "NAO_TRATA": "não trata do assunto",
    "SUSTENTA": "trata do assunto",   # votos anulados (conflito com selo/cluster)
    "REFUTA": "trata do assunto",
}


def direcoes_por_url(decisao: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """url -> direção do voto (+1 contesta o que o texto afirma, -1 confirma).

    Vem dos votos da decisão, que já aplicam a polaridade do usuário: se ele
    NEGA o núcleo, uma página que REFUTA o núcleo está do lado dele."""
    saida: Dict[str, float] = {}
    for v in (decisao or {}).get("votos", []) or []:
        for u in v.get("urls", []) or []:
            saida[u] = v.get("direcao", 0.0)
    return saida


def rotulo_selo(fonte: Any) -> str:
    """Selo da fonte para exibição. O que veio só do título da busca diz isso e para qual
    afirmação vale (o selo é da afirmação da agência, que pode ter polaridade diferente)."""
    v = getattr(fonte, "veredito", None)
    if not v:
        return ""
    if getattr(fonte, "origem_veredito", None) == "titulo-busca":
        ac = (getattr(fonte, "afirmacao_checada", None) or "").strip()
        return f"selo da agência no título: {v}" + (f" para “{ac[:100]}”" if ac else "")
    return f"selo da agência: {v}"


def postura_legivel(fonte: Any, direcoes: Dict[str, float]) -> str:
    """O que a fonte faz frente ao que o usuário enviou, em linguagem simples."""
    d = direcoes.get(getattr(fonte, "url", ""), 0.0)
    if d > 0:
        return "contesta o que o texto afirma"
    if d < 0:
        return "confirma o que o texto afirma"
    return _POSTURA_SEM_VOTO.get(getattr(fonte, "postura", None) or "", "não avaliada")
