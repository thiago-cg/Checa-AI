"""Adjudicador por afirmação (19/10): um LLM relê o CONJUNTO julgado e corrige a EVIDÊNCIA, nunca o nível.

O juiz julga uma página por vez; o agregador (`decisao.decidir`) soma votos. O que nenhum dos dois vê é o
conjunto: a página que o juiz marcou "só relata" mas noticia o fato em voz própria, a postura que não se
sustenta lida ao lado das outras, e o TEMPO — afirmação sobre uma situação que muda (aprovado/vigente,
preso/solto, cargo, posição de alguém) e página que relata essa mudança. Aqui há uma chamada LLM por
afirmação, ANTES da decisão, que devolve:

  * `tipo_temporal` da afirmação: estado | evento | atemporal | incerto;
  * por item: `vale_em` (data a que o que a página afirma se refere), `relata_mudanca` + citação, e uma
    `revisao` opcional da classe do juiz, com citação.

Quem manda é o validador determinístico (`validar`):

  * RELATA_SEM_ENDOSSO → SUSTENTA/REFUTA só com citação conferida no texto que o LLM viu (a mesma régua do
    juiz, `juiz_llm.verificar_citacao` ≥ JUIZ_CITACAO_MIN);
  * SUSTENTA/REFUTA → RELATA_SEM_ENDOSSO é livre (perder a posição é a direção segura);
  * SUSTENTA ↔ REFUTA nunca: vira RELATA_SEM_ENDOSSO (a leitura da página é instável);
  * `relata_mudanca` só com citação conferida e classe final SUSTENTA/REFUTA;
  * `vale_em` só data ISO válida, não posterior à publicação e até 10 anos antes dela;
  * com ADJUDICADOR_K > 1, cada chamada roda com sal próprio (cassete próprio) e só vale o que é unânime
    (revisão que dá posição, mudança) ou maioria estrita (tipo temporal, revisão para RELATA).

A decisão continua uma função pura sobre a evidência corrigida: a superação temporal (S1) e a R11 com data
(R11t) vivem em `decisao.py`. Atrás de `ADJUDICADOR` (padrão 0: prompt novo = cassete novo; ligar depois de
gravar e medir). Nunca levanta: falha = evidência intacta + `telemetria.fallback("adjudicador", ...)`.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, field_validator

from . import avaliador, config, decisao, juiz_llm, llm, replay, telemetria

log = logging.getLogger("factcheck.adjudicador")

TIPOS = ("estado", "evento", "atemporal", "incerto")
REVISOES = ("manter", "SUSTENTA", "REFUTA", "RELATA_SEM_ENDOSSO")
_TRATA = ("SUSTENTA", "REFUTA", "RELATA_SEM_ENDOSSO")
_VALE_EM_MAX_ANOS = 10


def habilitado() -> bool:
    return bool(getattr(config, "ADJUDICADOR", False))


def k_total() -> int:
    try:
        return max(1, int(getattr(config, "ADJUDICADOR_K", 1)))
    except (TypeError, ValueError):
        return 1


# ----------------------------------------------------------------------------- schema
def _norm(s: Any) -> str:
    return juiz_llm._norm(str(s if s is not None else ""))


class ItemAdj(BaseModel):
    i: int
    vale_em: str = ""
    relata_mudanca: bool = False
    citacao_mudanca: str = ""
    revisao: Literal["manter", "SUSTENTA", "REFUTA", "RELATA_SEM_ENDOSSO"] = "manter"
    citacao_revisao: str = ""
    motivo: str = ""

    @field_validator("revisao", mode="before")
    @classmethod
    def _revisao(cls, v):
        k = _norm(v).upper().replace(" ", "_")
        if not k or k.startswith("MANT") or k in ("NENHUMA", "NAO", "IGUAL"):
            return "manter"
        if k.startswith("RELATA"):
            return "RELATA_SEM_ENDOSSO"
        if k in ("SUSTENTA", "REFUTA"):
            return k
        raise ValueError(f"revisao deve ser manter, SUSTENTA, REFUTA ou RELATA_SEM_ENDOSSO (veio {v!r})")

    @field_validator("relata_mudanca", mode="before")
    @classmethod
    def _bool(cls, v):
        if isinstance(v, str):
            return _norm(v) in ("true", "sim", "1", "yes")
        return bool(v)

    @field_validator("vale_em", "citacao_mudanca", "citacao_revisao", "motivo", mode="before")
    @classmethod
    def _txt(cls, v):
        return "" if v is None else str(v)


class RespostaAdj(BaseModel):
    tipo_temporal: Literal["estado", "evento", "atemporal", "incerto"] = "incerto"
    motivo_tipo: str = ""
    itens: List[ItemAdj] = []

    @field_validator("tipo_temporal", mode="before")
    @classmethod
    def _tipo(cls, v):
        k = _norm(v)
        for t in TIPOS:
            if k.startswith(t[:5]):
                return t
        return "incerto"

    @field_validator("motivo_tipo", mode="before")
    @classmethod
    def _txt(cls, v):
        return "" if v is None else str(v)


INSTRUCAO = """Você revisa o CONJUNTO de páginas que um juiz já classificou, uma a uma, frente a uma AFIRMAÇÃO. Você não decide se a afirmação é verdadeira: só corrige a leitura das páginas e marca o que o tempo muda.

AFIRMAÇÃO: "{afirmacao}"

Classes do juiz: SUSTENTA (a página afirma, com a própria voz, o mesmo que a afirmação), REFUTA (a página diz que a afirmação é falsa, enganosa ou sem comprovação), RELATA_SEM_ENDOSSO (trata do assunto ou de algo parecido sem tomar posição).

Tarefa 1 — "tipo_temporal" da AFIRMAÇÃO:
- "estado": descreve uma situação que pode mudar com o tempo (algo aprovado, vigente, suspenso; alguém preso, solto, no cargo; a posição atual de alguém; um preço, placar ou recorde atual).
- "evento": descreve um fato pontual, que aconteceu ou não numa ocasião (alguém disse, fez, publicou; um acidente, uma votação numa data).
- "atemporal": ciência, saúde, definição, algo que não depende de data.
- "incerto": se não der para saber.

Tarefa 2 — para CADA item:
- "vale_em": a data (AAAA-MM-DD) a que o que a página afirma se refere, SÓ se o texto a disser explicitamente ou a der pela data do item ("nesta terça", "hoje"); senão "".
- "relata_mudanca": true só se a página diz, com a própria voz, que a situação MUDOU (ex.: "foi aprovado nesta terça", "mudou de posição", "foi solto", "passou a valer", "deixou o cargo"). Notícia que só repete a afirmação ou o desmentido não é mudança.
- "citacao_mudanca": quando "relata_mudanca" é true, copie LITERALMENTE do "texto" do item um trecho contínuo (10 a 30 palavras) que mostra a mudança; senão "".
- "revisao": "manter" na maioria dos casos. Use outra classe só quando a leitura do juiz está errada OLHANDO O CONJUNTO:
  * RELATA_SEM_ENDOSSO que na verdade afirma o fato com a própria voz (noticia como fato, não só atribui a alguém) → "SUSTENTA"; que na verdade desmente → "REFUTA";
  * SUSTENTA ou REFUTA por inferência, por silêncio, ou sobre uma alegação diferente (outro sujeito, número, data, lugar) → "RELATA_SEM_ENDOSSO".
- "citacao_revisao": para "SUSTENTA" ou "REFUTA", copie LITERALMENTE do "texto" do item o trecho (10 a 30 palavras) que mostra a posição; senão "".
- "motivo": uma frase curta, em português.

Regras:
- Use só os itens abaixo; não use conhecimento próprio. Datas: use só as do texto e a "data" do item.
- Copie as citações sem mudar nenhuma palavra, sem reticências, sem traduzir.
- Responda SOMENTE com JSON, um objeto por item, na ordem:
{{"tipo_temporal": "<estado|evento|atemporal|incerto>", "motivo_tipo": "<frase curta>", "itens": [{{"i": 0, "vale_em": "", "relata_mudanca": false, "citacao_mudanca": "", "revisao": "manter", "citacao_revisao": "", "motivo": "<frase curta>"}}]}}

ITENS:
{itens}"""


# ----------------------------------------------------------------------------- entrada
def _curto(s: Any, n: int) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


@dataclass
class Alvo:
    """Um item enviado ao LLM: o índice em `ev.itens`, o texto que ele viu (contra o qual as citações são
    conferidas) e a data de publicação."""
    j: int
    texto: str
    data_pub: Optional[str]
    classe: str


def montar_itens(ai: int, alvo: str, ev: "decisao.Evidencias", pecas: List[Dict[str, Any]],
                 julg: Dict[Tuple[int, int], Dict[str, Any]], limite: int = 0) -> Tuple[List[Alvo], List[Dict]]:
    """Itens da afirmação `ai` que tratam dela (SUSTENTA, REFUTA, RELATA), com corpo lido e juiz de verdade.
    Primeiro os que tomam posição, depois os relatos, até `limite`. -> (alvos, payload do prompt)."""
    por_url = {p.get("url"): p for p in pecas}
    por_url_af = {(pecas[pi].get("url"), a): r for (pi, a), r in julg.items() if pi < len(pecas)}
    brutos = []
    for j, it in enumerate(ev.itens):
        if (it.afirmacao != ai or it.classe not in _TRATA or not it.corpo_lido
                or (it.motor or "").startswith("fallback")):
            continue
        p = por_url.get(it.url) or {}
        trecho = avaliador.trecho_da_peca(alvo, p) if p else ""
        texto = _curto(f"{p.get('titulo') or ''}\n{trecho}", int(getattr(config, "ADJUDICADOR_TRECHO_MAX", 1500)))
        if not texto:
            continue
        r = por_url_af.get((it.url, ai)) or {}
        brutos.append((0 if it.classe in decisao.CLASSES_VOTO else 1, it.url, j, texto, r))
    brutos.sort(key=lambda x: (x[0], x[1]))
    limite = limite or int(getattr(config, "ADJUDICADOR_MAX_ITENS", 12)) or 12
    alvos, payload = [], []
    for i, (_, _, j, texto, r) in enumerate(brutos[:limite]):
        it = ev.itens[j]
        alvos.append(Alvo(j=j, texto=texto, data_pub=it.data_pub, classe=it.classe))
        payload.append({"i": i, "veiculo": it.veiculo or "", "data": it.data_pub or "",
                        "agencia_de_checagem": "sim" if it.eh_agencia() else "nao", "classe_do_juiz": it.classe,
                        "raciocinio_do_juiz": _curto(r.get("raciocinio"), 240), "texto": texto})
    return alvos, payload


# ----------------------------------------------------------------------------- validação (o essencial)
@dataclass
class Correcao:
    """O que sobra de uma resposta depois do validador, por item (índice em `ev.itens`)."""
    j: int
    classe: Optional[str] = None           # classe nova (None = mantém)
    citacao: str = ""
    vale_em: Optional[str] = None
    relata_mudanca: bool = False
    citacao_mudanca: str = ""
    motivo: str = ""
    rejeitado: List[str] = field(default_factory=list)


def _cita(citacao: str, texto: str) -> bool:
    return juiz_llm.verificar_citacao(citacao, texto) >= (config.JUIZ_CITACAO_MIN or 0.9)


def _vale_em(v: str, data_pub: Optional[str]) -> Optional[str]:
    try:
        d = datetime.strptime((v or "").strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    try:
        pub = datetime.strptime((data_pub or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return d.isoformat()
    if d > pub or d < pub - timedelta(days=365 * _VALE_EM_MAX_ANOS):
        return None
    return d.isoformat()


def validar(resp: RespostaAdj, alvos: List[Alvo]) -> Tuple[Optional[str], List[Correcao]]:
    """Aplica as regras de transição e confere as citações. -> (tipo_temporal ou None, correções)."""
    tipo = resp.tipo_temporal if resp.tipo_temporal in decisao.TIPOS_TEMPORAIS else None
    vistos = set()
    saida: List[Correcao] = []
    for x in resp.itens:
        if not (0 <= x.i < len(alvos)) or x.i in vistos:
            continue
        vistos.add(x.i)
        a = alvos[x.i]
        c = Correcao(j=a.j, motivo=_curto(x.motivo, 300))
        final = a.classe
        if x.revisao != "manter" and x.revisao != a.classe:
            if a.classe in decisao.CLASSES_VOTO and x.revisao in decisao.CLASSES_VOTO:
                c.classe, c.rejeitado = "RELATA_SEM_ENDOSSO", ["inverter a direção vira RELATA_SEM_ENDOSSO"]
            elif x.revisao == "RELATA_SEM_ENDOSSO":
                c.classe = "RELATA_SEM_ENDOSSO"
            elif _cita(x.citacao_revisao, a.texto):
                c.classe, c.citacao = x.revisao, _curto(x.citacao_revisao, 400)
            else:
                c.rejeitado.append(f"revisão para {x.revisao} sem citação conferida")
            final = c.classe or a.classe
        c.vale_em = _vale_em(x.vale_em, a.data_pub) if x.vale_em else None
        if x.vale_em and c.vale_em is None:
            c.rejeitado.append(f"vale_em inválido: {x.vale_em[:20]}")
        if x.relata_mudanca:
            if final not in decisao.CLASSES_VOTO:
                c.rejeitado.append("mudança em item sem posição")
            elif not _cita(x.citacao_mudanca, a.texto):
                c.rejeitado.append("mudança sem citação conferida")
            else:
                c.relata_mudanca, c.citacao_mudanca = True, _curto(x.citacao_mudanca, 400)
        saida.append(c)
    return tipo, saida


def consenso(amostras: List[Optional[Tuple[Optional[str], List[Correcao]]]]) -> Tuple[Optional[str], List[Correcao]]:
    """K amostras validadas (None = chamada que falhou: abstenção) → uma. Com K = 1, a própria amostra.
    Tipo e revisão para RELATA: maioria estrita sobre K. Revisão que DÁ posição, mudança e vale_em: unânimes
    (as K amostras válidas e iguais). Assim a abstenção nunca ajuda a criar posição."""
    k = len(amostras)
    validas = [a for a in amostras if a is not None]
    if not validas:
        return None, []
    if k == 1:
        return validas[0]
    tipo, n = Counter(t for t, _ in validas).most_common(1)[0]
    tipo = tipo if n * 2 > k else None
    por_j: Dict[int, List[Correcao]] = {}
    for _, cs in validas:
        for c in cs:
            por_j.setdefault(c.j, []).append(c)
    saida = []
    for j, cs in por_j.items():
        base = Correcao(j=j, motivo=cs[0].motivo)
        unanime = len(cs) == k
        cl, n = Counter(c.classe for c in cs).most_common(1)[0]
        if cl == "RELATA_SEM_ENDOSSO" and n * 2 > k:
            base.classe = cl
        elif cl in decisao.CLASSES_VOTO and unanime and n == k:
            base.classe, base.citacao = cl, next(c.citacao for c in cs if c.classe == cl)
        if unanime and all(c.relata_mudanca for c in cs) and base.classe != "RELATA_SEM_ENDOSSO":
            base.relata_mudanca, base.citacao_mudanca = True, cs[0].citacao_mudanca
        datas = {c.vale_em for c in cs}
        if unanime and len(datas) == 1:
            base.vale_em = datas.pop()
        saida.append(base)
    return tipo, saida


# ----------------------------------------------------------------------------- LLM
def adjudicar_afirmacao(afirmacao: str, alvos: List[Alvo], payload: List[Dict]) -> Tuple[Optional[str], List[Correcao], Dict]:
    """K chamadas (sal próprio cada) + validação + consenso. Nunca levanta."""
    k = k_total()
    linhas = "\n".join(json.dumps(d, ensure_ascii=False) for d in payload)
    prompt = INSTRUCAO.format(afirmacao=_curto(afirmacao, 500), itens=linhas)
    amostras: List[Optional[Tuple[Optional[str], List[Correcao]]]] = []
    info: Dict[str, Any] = {"k": k, "erros": [], "modelo": ""}
    for rep in range(k):
        res = _chamar(prompt, rep)
        if not res.ok:
            info["erros"].append((res.erro or "LLM indisponível")[:200])
            amostras.append(None)
            continue
        info["modelo"] = res.modelo
        amostras.append(validar(res.dados, alvos))
    tipo, corr = consenso(amostras)
    return tipo, corr, info


def _chamar(prompt: str, rep: int) -> "llm.ResultadoLLM":
    """Uma chamada. A 1ª sem sal (cassete da chamada única); as repetições com sal e temperatura próprios."""
    kw = dict(finalidade="adjudicador", max_tokens=int(getattr(config, "ADJUDICADOR_MAX_TOKENS", 2500)),
              timeout_s=int(getattr(config, "ADJUDICADOR_TIMEOUT_S", 120)))
    msgs = [{"role": "user", "content": prompt}]
    try:
        if not rep:
            return llm.chat_json(msgs, RespostaAdj, **kw)
        with replay.com_sal(f"adj{rep}"), replay.temperatura(float(getattr(config, "ADJUDICADOR_TEMP", 0.5))):
            return llm.chat_json(msgs, RespostaAdj, **kw)
    except Exception as e:  # chat_json não levanta; defesa para o contrato "nunca levanta"
        return llm.ResultadoLLM(ok=False, erro=f"{type(e).__name__}: {str(e)[:200]}")


# ----------------------------------------------------------------------------- aplicação
def aplicar(ev: "decisao.Evidencias", afs: List[Any], pecas: List[Dict[str, Any]],
            julg: Dict[Tuple[int, int], Dict[str, Any]]) -> Dict[str, Any]:
    """Corrige `ev` (classe, vale_em, relata_mudanca dos itens; tipo_temporal das afirmações) e `julg` (o que o
    relatório mostra) no lugar, ANTES da decisão. -> resumo para o evento `adjudicador`. Nunca levanta."""
    resumo: Dict[str, Any] = {"aplicado": False, "afirmacoes": []}
    if not habilitado():
        resumo["motivo"] = "desligado"
        return resumo
    try:
        por_url_af = {(pecas[pi].get("url"), a): (pi, a) for (pi, a) in julg if pi < len(pecas)}
        for ai, af in enumerate(afs):
            alvo = af.alvo() if hasattr(af, "alvo") else str(af)
            alvos, payload = montar_itens(ai, alvo, ev, pecas, julg)
            if not alvos:
                continue
            tipo, corr, info = adjudicar_afirmacao(alvo, alvos, payload)
            if info["erros"] and not corr and tipo is None:
                telemetria.fallback("adjudicador", f"LLM indisponível ou JSON inválido: {info['erros'][0]}",
                                    afirmacao=ai)
            if ai < len(ev.afirmacoes):
                ev.afirmacoes[ai].tipo_temporal = tipo
            entrada = {"afirmacao": ai, "tipo_temporal": tipo, "n_itens": len(alvos), "k": info["k"],
                       "modelo": info["modelo"], "erros": info["erros"][:3], "revisoes": [], "mudancas": [],
                       "rejeitadas": []}
            for c in corr:
                it = ev.itens[c.j]
                if c.classe and c.classe != it.classe:
                    entrada["revisoes"].append({"url": it.url, "de": it.classe, "para": c.classe, "motivo": c.motivo})
                    chave = por_url_af.get((it.url, it.afirmacao))
                    r = julg.get(chave) if chave else None
                    if r is not None:
                        r.setdefault("classe_juiz", r.get("classe"))
                        r["classe"] = c.classe
                        r["adjudicador"] = {"de": it.classe, "para": c.classe, "motivo": c.motivo}
                        if c.classe in decisao.CLASSES_VOTO:
                            r.update(citacao=c.citacao, citacao_verificada=True)
                    it.classe = c.classe
                    it.citacao_verificada = True if c.classe in decisao.CLASSES_VOTO else None
                if c.vale_em:
                    it.vale_em = c.vale_em
                if c.relata_mudanca:
                    it.relata_mudanca = True
                    entrada["mudancas"].append({"url": it.url, "data": it.vale_em or it.data_pub,
                                                "citacao": c.citacao_mudanca[:200]})
                if c.rejeitado:
                    entrada["rejeitadas"].append({"url": it.url, "motivos": c.rejeitado})
            resumo["afirmacoes"].append(entrada)
            resumo["aplicado"] = True
        return resumo
    except Exception as e:  # o adjudicador nunca derruba o pipeline: a evidência fica como estava
        telemetria.fallback("adjudicador", f"aplicar: {type(e).__name__}: {str(e)[:200]}")
        resumo["erro"] = f"{type(e).__name__}: {str(e)[:200]}"
        return resumo


def rodar(ev: "decisao.Evidencias", afs: List[Any], pecas: List[Dict[str, Any]],
          julg: Dict[Tuple[int, int], Dict[str, Any]]) -> Dict[str, Any]:
    """Ponto de entrada do pipeline: `aplicar` + evento de telemetria `adjudicador`."""
    resumo = aplicar(ev, afs, pecas, julg)
    if resumo.get("aplicado") or resumo.get("erro"):
        telemetria.evento("adjudicador", **resumo)
    return resumo
