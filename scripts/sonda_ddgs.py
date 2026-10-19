"""Sonda de medição: busca SerpAPI -> ddgs (Fase 1 de docs/superpowers/plans/2026-10-19-serpapi-para-ddgs.md).

Não altera factcheck_mvp/, tests/, eval/ nem configuração. Não lê .env nem bot.log.

Pega consultas reais já gravadas nos cassetes SerpAPI (eval/cassettes/*.json, campo req.url
e resp.texto) e roda cada uma nos backends do ddgs, com region="br-pt" e max_results=10:

* texto (engine=google, inclusive as com `site:`/OR): google, bing, duckduckgo, brave;
* notícias (engine=google_news): bing, duckduckgo, yahoo.

Medidas por backend:
* % de chamadas vazias, nº de ratelimit / timeout / erro, latência média;
* vazias com latência >= timeout (suspeitas: o ddgs pode devolver "No results" quando o
  motor demora mais que o timeout de espera);
* cobertura: fração das URLs do top-10 da SerpAPI (e dos hosts) que o ddgs também devolve;
* consultas com `site:`: no modo OR (como o agente manda hoje) e no modo "separado" (uma
  consulta por domínio). Mede fração dos resultados nos domínios pedidos e fração dos
  domínios pedidos que aparecem;
* notícias (e texto): fração com `date` preenchida e formato observado.

Uso:
  python scripts/sonda_ddgs.py                 # n=30, rps=1 (medição completa)
  python scripts/sonda_ddgs.py --rapido        # teste de fumaça (n=5)
  python scripts/sonda_ddgs.py --cassetes DIR  # outra pasta de cassetes
  python scripts/sonda_ddgs.py --reanalisar    # regera o .md a partir do .json (sem rede)

Saídas: docs/review/sonda_ddgs.md (tabelas + recomendação) e docs/review/sonda_ddgs.json (dados brutos).
Os .json são gravados a cada 10 chamadas (campo "parcial": true enquanto roda).
"""
from __future__ import annotations

import argparse
import atexit
import importlib.metadata
import json
import os
import random
import re
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

RAIZ = Path(__file__).resolve().parents[1]
SAIDA_DIR = RAIZ / "docs" / "review"
ARQ_MD = SAIDA_DIR / "sonda_ddgs.md"
ARQ_JSON = SAIDA_DIR / "sonda_ddgs.json"

BACKENDS_TEXTO = ["google", "bing", "duckduckgo", "brave"]
BACKENDS_NOTICIAS = ["bing", "duckduckgo", "yahoo"]
REGIAO = "br-pt"
MAX_RESULTADOS = 10
SEMENTE_PADRAO = 42
TIMEOUT_PADRAO = 5  # segundos, como no plano (DDGS(proxy=None, timeout=5))
RPS_PADRAO = 1.0
N_PADRAO = 30
# Consulta trivial que qualquer backend saudável responde. Se vier vazia, o backend é marcado
# como possível bloqueio de IP (o ddgs devolve 429/202 como "No results found").
CONTROLE_QUERY = "Brasil capital Brasília"
CONTROLE_A_CADA = 25  # tarefas entre uma rodada de controle e outra (7 chamadas por rodada)
ARQ_LOCK = SAIDA_DIR / "sonda_ddgs.lock"


# --------------------------------------------------------------------------- utilidades de URL

def host_de(url: str) -> str:
    """Host em minúsculas, sem 'www.'. Vazio se a URL não for parseável."""
    try:
        host = (urlsplit((url or "").strip()).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def normalizar_url(url: str) -> str:
    """host sem www + path sem barra final; sem esquema, query nem fragmento."""
    host = host_de(url)
    if not host:
        return ""
    try:
        caminho = urlsplit(url.strip()).path.rstrip("/")
    except ValueError:
        caminho = ""
    return f"{host}{caminho}"


def host_do_site(bruto: str) -> str:
    """'site:gov.br/saude/x' -> 'gov.br'."""
    host = bruto.split("/")[0].lower()
    return host[4:] if host.startswith("www.") else host


def casa_site(host: str, site: str) -> bool:
    return bool(host) and bool(site) and (host == site or host.endswith("." + site))


# --------------------------------------------------------------------------- cassetes

def pasta_cassetes_padrao() -> Path:
    """Os cassetes gravados ficam no checkout principal, não no worktree."""
    if RAIZ.parent.name == "worktrees" and RAIZ.parents[1].name == ".claude":
        principal = RAIZ.parents[2] / "eval" / "cassettes"
        if principal.is_dir():
            return principal
    return RAIZ / "eval" / "cassettes"


def consulta_base(q: str) -> str:
    """Consulta sem o grupo (site:a OR site:b ...) nem `site:` soltos."""
    base = re.sub(r"\(\s*site:[^)]*\)", " ", q)
    base = re.sub(r"\bsite:\S+", " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base or q


def carregar_consultas(pasta: Path, max_links: int = MAX_RESULTADOS) -> list[dict]:
    """Lê os cassetes SerpAPI úteis (status 200, com resultados) e deduplica por (engine, q)."""
    vistos: set[tuple[str, str]] = set()
    saida: list[dict] = []
    for arq in sorted(pasta.glob("*.json")):
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        url = str((d.get("req") or {}).get("url") or "")
        try:
            p = urlsplit(url)
        except ValueError:
            continue
        host = (p.hostname or "").lower()
        if host != "serpapi.com" and not host.endswith(".serpapi.com"):
            continue
        qs = parse_qs(p.query)
        q = (qs.get("q") or [""])[0].strip()
        engine = (qs.get("engine") or ["google"])[0]
        if not q or engine not in ("google", "google_news"):
            continue
        resp = d.get("resp") or {}
        if resp.get("status") != 200:
            continue
        try:
            corpo = json.loads(resp.get("texto") or "{}")
        except ValueError:
            continue
        if not isinstance(corpo, dict):
            continue
        itens = corpo.get("news_results" if engine == "google_news" else "organic_results") or []
        links = [str(x["link"]) for x in itens if isinstance(x, dict) and x.get("link")]
        if not links:
            continue
        chave = (engine, q)
        if chave in vistos:
            continue
        vistos.add(chave)
        sites: list[str] = []
        for bruto in re.findall(r"site:([^\s)]+)", q):
            if bruto not in sites:
                sites.append(bruto)
        hosts_sites: list[str] = []
        for bruto in sites:
            h = host_do_site(bruto)
            if h and h not in hosts_sites:
                hosts_sites.append(h)
        if engine == "google_news":
            cat = "noticias"
        elif sites:
            cat = "site"
        else:
            cat = "texto"
        saida.append({
            "engine": engine,
            "cat": cat,
            "q": q,
            "base": consulta_base(q),
            "sites": sites,
            "sites_hosts": hosts_sites,
            "serp_urls": links[:max_links],
        })
    return saida


def amostrar(cands: list[dict], n: int, seed: int) -> list[dict]:
    """Amostra estratificada: ~40% notícias, ~30% google com site:, resto google simples."""
    rnd = random.Random(seed)
    por: dict[str, list[dict]] = {"noticias": [], "site": [], "texto": []}
    for c in cands:
        por[c["cat"]].append(c)
    for k in por:
        por[k].sort(key=lambda c: c["q"])
    alvos = {"noticias": round(n * 0.4), "site": round(n * 0.3)}
    alvos["texto"] = n - alvos["noticias"] - alvos["site"]
    escolhidos: list[dict] = []
    sobra = 0
    for k in ("noticias", "site", "texto"):
        pool = por[k]
        m = min(alvos[k], len(pool))
        escolhidos += rnd.sample(pool, m)
        sobra += alvos[k] - m
    if sobra:
        ids = {id(c) for c in escolhidos}
        resto = [c for k in ("noticias", "site", "texto") for c in por[k] if id(c) not in ids]
        rnd.shuffle(resto)
        escolhidos += resto[:sobra]
    for i, c in enumerate(escolhidos, 1):
        c["id"] = f"c{i:02d}"
    return escolhidos


def montar_tarefas(amostra: list[dict], sep_max: int) -> list[dict]:
    """Uma tarefa = (consulta, backend, tipo, modo, sub-consulta). Ordem fixa e reproduzível."""
    tarefas: list[dict] = []
    for c in amostra:
        if c["cat"] == "noticias":
            for b in BACKENDS_NOTICIAS:
                tarefas.append(_tarefa(c, b, "noticias", "normal", c["q"], None))
        else:
            for b in BACKENDS_TEXTO:
                tarefas.append(_tarefa(c, b, "texto", "normal", c["q"], None))
    sites_vistos = 0
    for c in amostra:
        if c["cat"] != "site" or sites_vistos >= sep_max:
            continue
        sites_vistos += 1
        for s in c["sites"]:
            sub = f"{c['base']} site:{s}"
            for b in BACKENDS_TEXTO:
                tarefas.append(_tarefa(c, b, "texto", "separado", sub, s))
    return tarefas


def _tarefa(c, backend, tipo, modo, sub, site) -> dict:
    return {
        "consulta": c["id"], "engine": c["engine"], "cat": c["cat"], "q": c["q"],
        "serp_urls": c["serp_urls"], "sites": c["sites"], "sites_hosts": c["sites_hosts"],
        "backend": backend, "tipo": tipo, "modo": modo, "sub_query": sub,
        "site": site, "site_host": host_do_site(site) if site else None,
    }


# --------------------------------------------------------------------------- execução

class Limitador:
    """Ritmo global: no máximo `rps` chamadas por segundo (sequencial)."""

    def __init__(self, rps: float):
        self.intervalo = 1.0 / rps if rps and rps > 0 else 0.0
        self.ultimo = 0.0

    def esperar(self) -> None:
        if not self.intervalo:
            return
        falta = self.ultimo + self.intervalo - time.monotonic()
        if falta > 0:
            time.sleep(falta)
        self.ultimo = time.monotonic()


def classificar_erro(e: BaseException) -> str:
    from ddgs.exceptions import RatelimitException, TimeoutException

    # Com todos os motores falhando, o ddgs embrulha a exceção original em DDGSException(err).
    interno = e.args[0] if e.args and isinstance(e.args[0], BaseException) else None
    for alvo in (interno, e):
        if isinstance(alvo, RatelimitException):
            return "ratelimit"
        if isinstance(alvo, TimeoutException):
            return "timeout"
    msg = str(e).lower()
    if "no results" in msg:
        return "vazio"
    if "ratelimit" in msg or "rate limit" in msg or "429" in msg or "too many" in msg:
        return "ratelimit"
    if "timed out" in msg or "timeout" in msg:
        return "timeout"
    return "erro"


def executar(tipo: str, backend: str, query: str, timeout_s: float) -> dict:
    """1 chamada live a 1 backend, via `replay.busca_ddgs` (CLAUDE.md: todo I/O passa por replay): entra no
    contador de buscas live (`eval/serpapi_uso.json`, `por_provedor.ddgs`) e no evento `http`."""
    from ddgs import DDGS
    if str(RAIZ) not in sys.path:
        sys.path.insert(0, str(RAIZ))
    from factcheck_mvp import ddgs_layer  # noqa: F401  (detecção de bloqueio: 202/403/429 viram ratelimit)
    from factcheck_mvp import replay

    funcao = "news" if tipo == "noticias" else "text"
    kwargs = dict(region=REGIAO, safesearch="moderate", timelimit=None,
                  max_results=MAX_RESULTADOS, page=1, backend=backend)

    def _vivo() -> dict:
        ddgs = DDGS(proxy=None, timeout=timeout_s)
        itens = ddgs.news(query, **kwargs) if funcao == "news" else ddgs.text(query, **kwargs)
        return {"criado_em": datetime.now().isoformat(timespec="seconds"), "resultados": list(itens or [])}

    t0 = time.monotonic()
    try:
        replay.definir_modo("live")  # a sonda mede a rede: nunca lê nem grava cassete
        dados = replay.busca_ddgs(funcao, {"q": query, "region": REGIAO, "backend": backend,
                                           "max_results": MAX_RESULTADOS, "safesearch": "moderate"}, _vivo)
        lat = (time.monotonic() - t0) * 1000
        itens = dados.get("resultados") or []
        return {"status": "vazio" if not itens else "ok", "itens": itens, "lat_ms": lat, "erro": None}
    except Exception as e:  # noqa: BLE001 - a sonda mede falhas, não as esconde
        lat = (time.monotonic() - t0) * 1000
        return {"status": classificar_erro(e), "itens": [], "lat_ms": lat,
                "erro": f"{type(e).__name__}: {str(e)[:160]}"}


def montar_registro(t: dict, r: dict, timeout_s: float, suspeita: bool = False) -> dict:
    urls, hosts, datas, fontes = [], [], [], []
    chaves: list[str] = []
    for it in r["itens"]:
        if not isinstance(it, dict):
            continue
        if not chaves:
            chaves = sorted(it.keys())
        if t["tipo"] == "texto":
            url = str(it.get("href") or it.get("url") or "")
        else:
            url = str(it.get("url") or it.get("href") or "")
        urls.append(url)
        hosts.append(host_de(url))
        d = it.get("date")
        datas.append(str(d) if d else None)
        fontes.append(str(it.get("source") or "") if t["tipo"] == "noticias" else None)
    return {
        "consulta": t["consulta"], "engine": t["engine"], "cat": t["cat"], "q": t["q"],
        "modo": t["modo"], "sub_query": t["sub_query"], "site": t["site"], "site_host": t["site_host"],
        "tipo": t["tipo"], "backend": t["backend"], "status": r["status"], "n": len(urls),
        "lat_ms": round(r["lat_ms"]), "timeout_s": timeout_s, "erro": r["erro"],
        "suspeita_bloqueio": bool(suspeita),
        "urls": urls, "hosts": hosts, "datas": datas, "fontes": fontes, "chaves": chaves,
        "serp_urls": t["serp_urls"], "sites_hosts": t["sites_hosts"],
    }


def salvar_json(meta: dict, consultas: list[dict], registros: list[dict], parcial: bool) -> None:
    SAIDA_DIR.mkdir(parents=True, exist_ok=True)
    dados = {"meta": {**meta, "parcial": parcial, "atualizado_em": datetime.now().isoformat(timespec="seconds")},
             "consultas": consultas, "registros": registros}
    ARQ_JSON.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


def rodar(args: argparse.Namespace) -> None:
    pasta = Path(args.cassetes) if args.cassetes else pasta_cassetes_padrao()
    cands = carregar_consultas(pasta)
    if not cands:
        sys.exit(f"Nenhum cassete SerpAPI útil em {pasta}")
    n = 5 if args.rapido else args.n
    sep_max = 1 if args.rapido else args.sep_max
    amostra = amostrar(cands, n, args.seed)
    tarefas = montar_tarefas(amostra, sep_max)
    print(f"Cassetes úteis: {len(cands)} em {pasta}", flush=True)
    print(f"Amostra: {len(amostra)} consultas; tarefas: {len(tarefas)}; rps={args.rps}; timeout={args.timeout}s", flush=True)

    try:
        versao = importlib.metadata.version("ddgs")
    except importlib.metadata.PackageNotFoundError:
        versao = "desconhecida"
    meta = {"ddgs": versao, "n": n, "seed": args.seed, "rps": args.rps, "timeout_s": args.timeout,
            "sep_max": sep_max, "rapido": bool(args.rapido), "regiao": REGIAO,
            "backends_texto": BACKENDS_TEXTO, "backends_noticias": BACKENDS_NOTICIAS,
            "cassetes_disponiveis": len(cands), "tarefas": len(tarefas),
            "iniciado_em": datetime.now().isoformat(timespec="seconds")}
    consultas = [{"consulta": c["id"], "engine": c["engine"], "cat": c["cat"], "q": c["q"],
                  "sites": c["sites"], "sites_hosts": c["sites_hosts"], "serp_urls": c["serp_urls"]}
                 for c in amostra]

    registros: list[dict] = []
    lim = Limitador(args.rps)
    total = len(tarefas)
    bloqueado: dict[tuple[str, str], bool] = {}
    rodadas_controle_falhas = 0
    ratelimits_seguidos = 0
    encerramento = "concluído"
    for i, t in enumerate(tarefas, 1):
        if (i - 1) % CONTROLE_A_CADA == 0:
            tudo_falhou = _rodada_controle(registros, bloqueado, lim, args.timeout)
            rodadas_controle_falhas = rodadas_controle_falhas + 1 if tudo_falhou else 0
            if rodadas_controle_falhas >= 2:
                encerramento = (f"interrompido na tarefa {i}/{total}: controle falhou em todos os backends "
                                "em 2 rodadas seguidas (provável bloqueio de IP)")
                print(f"AVISO: {encerramento}.", flush=True)
                break
        chave = (t["tipo"], t["backend"])
        if bloqueado.get(chave):
            # backend marcado como bloqueado pelo último controle: não gasta chamada nele
            r = {"status": "pulado_bloqueio", "itens": [], "lat_ms": 0.0, "erro": None}
        else:
            lim.esperar()
            r = executar(t["tipo"], t["backend"], t["sub_query"], args.timeout)
        registros.append(montar_registro(t, r, args.timeout, suspeita=bloqueado.get(chave, False)))
        print(f"[{i}/{total}] {t['tipo']:8s} {t['modo']:8s} {t['backend']:10s} {t['consulta']} "
              f"-> {r['status']} ({len(r['itens'])} res, {r['lat_ms']:.0f} ms)", flush=True)
        ratelimits_seguidos = ratelimits_seguidos + 1 if r["status"] == "ratelimit" else 0
        if ratelimits_seguidos >= 8:
            encerramento = f"interrompido na tarefa {i}/{total}: 8 ratelimits seguidos"
            print(f"AVISO: {encerramento}.", flush=True)
            break
        if i % 10 == 0 or i == total:
            salvar_json(meta, consultas, registros, parcial=i < total)

    meta["encerramento"] = encerramento
    meta["concluido_em"] = datetime.now().isoformat(timespec="seconds")
    salvar_json(meta, consultas, registros, parcial=encerramento != "concluído")
    escrever_md(meta, consultas, registros)
    print(f"Pronto ({encerramento}): {ARQ_MD} e {ARQ_JSON}", flush=True)


def _rodada_controle(registros: list[dict], bloqueado: dict, lim: "Limitador", timeout_s: float) -> bool:
    """Consulta trivial em todos os backends. Vazio/erro = possível bloqueio. Devolve True se tudo falhou."""
    alvos = [("texto", b) for b in BACKENDS_TEXTO] + [("noticias", b) for b in BACKENDS_NOTICIAS]
    falhas = 0
    for tipo, b in alvos:
        lim.esperar()
        r = executar(tipo, b, CONTROLE_QUERY, timeout_s)
        ok = r["status"] == "ok"
        bloqueado[(tipo, b)] = not ok
        falhas += 0 if ok else 1
        t = {"consulta": "ctrl", "engine": "controle", "cat": "controle", "q": CONTROLE_QUERY,
             "serp_urls": [], "sites": [], "sites_hosts": [], "backend": b, "tipo": tipo,
             "modo": "controle", "sub_query": CONTROLE_QUERY, "site": None, "site_host": None}
        registros.append(montar_registro(t, r, timeout_s))
        print(f"  controle {tipo:8s} {b:10s} -> {r['status']} ({len(r['itens'])} res, {r['lat_ms']:.0f} ms)",
              flush=True)
    if falhas:
        print(f"  AVISO: controle falhou em {falhas}/{len(alvos)} backends (possível bloqueio de IP "
              "ou backend fora do ar)", flush=True)
    return falhas == len(alvos)


# --------------------------------------------------------------------------- análise

def media(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def classe_data(d: str | None) -> str:
    if not d:
        return "vazia"
    s = str(d).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return "iso"
    if re.search(r"\b(hora|horas|minuto|minutos|dia|dias|semana|semanas|m[eê]s|meses|ano|anos|ago|"
                 r"hour|hours|day|days|week|weeks|month|months|minute|minutes|year|years)\b", s, re.I):
        return "relativa"
    if re.search(r"\d{4}", s):
        return "data_outro_formato"
    return "outro"


def fracao_no_dominio(r: dict) -> float | None:
    if not r["hosts"] or not r["sites_hosts"]:
        return None
    return sum(1 for h in r["hosts"] if any(casa_site(h, s) for s in r["sites_hosts"])) / len(r["hosts"])


def sites_cobertos(hosts: list[str], sites: list[str]) -> float | None:
    if not sites:
        return None
    return sum(1 for s in sites if any(casa_site(h, s) for h in hosts)) / len(sites)


def metricas(regs: list[dict], tipo: str, backend: str, cat: str | None = None) -> dict:
    recs = [r for r in regs if r["modo"] == "normal" and r["tipo"] == tipo and r["backend"] == backend
            and (cat is None or r["cat"] == cat) and r["status"] != "pulado_bloqueio"]
    n = len(recs)
    cont = Counter(r["status"] for r in recs)
    timeout_s = recs[0]["timeout_s"] if recs else TIMEOUT_PADRAO
    cob_url, cob_host = [], []
    for r in recs:
        if r["serp_urls"]:
            s = {normalizar_url(u) for u in r["serp_urls"]} - {""}
            d = {normalizar_url(u) for u in r["urls"]} - {""}
            if s:
                cob_url.append(len(s & d) / len(s))
            sh = {host_de(u) for u in r["serp_urls"]} - {""}
            dh = {h for h in r["hosts"] if h}
            if sh:
                cob_host.append(len(sh & dh) / len(sh))
    itens_total = sum(len(r["urls"]) for r in recs)
    com_data = sum(1 for r in recs for d in r["datas"] if d)
    formatos = Counter(classe_data(d) for r in recs for d in r["datas"])
    exemplos: dict[str, list[str]] = {}
    for r in recs:
        for d in r["datas"]:
            k = classe_data(d)
            if d and len(exemplos.setdefault(k, [])) < 2 and d not in exemplos[k]:
                exemplos[k].append(d)
    fontes = Counter()
    for r in recs:
        for f in r["fontes"] or []:
            if f:
                fontes[f] += 1
    pct = (lambda x: x / n) if n else (lambda x: None)
    return {
        "n": n,
        "ok": cont.get("ok", 0), "vazio": cont.get("vazio", 0), "ratelimit": cont.get("ratelimit", 0),
        "timeout": cont.get("timeout", 0), "erro": cont.get("erro", 0),
        "pct_vazio": pct(cont.get("vazio", 0)),
        "pct_falha": pct(cont.get("ratelimit", 0) + cont.get("timeout", 0) + cont.get("erro", 0)),
        "pct_ratelimit": pct(cont.get("ratelimit", 0)),
        "vazio_lento": sum(1 for r in recs if r["status"] == "vazio" and r["lat_ms"] >= timeout_s * 1000),
        "lat_media_ms": media([r["lat_ms"] for r in recs]),
        "lat_mediana_ms": statistics.median([r["lat_ms"] for r in recs]) if recs else None,
        "cob_url": media(cob_url), "cob_host": media(cob_host),
        "itens_medio": (itens_total / n) if n else None,
        "pct_data": (com_data / itens_total) if itens_total else None,
        "formatos": dict(formatos), "exemplos_data": exemplos,
        "fontes_exemplo": [f for f, _ in fontes.most_common(6)],
        "erros_exemplo": [e for e, _ in Counter(r["erro"] for r in recs if r["erro"]).most_common(3)],
    }


def metricas_site(regs: list[dict], backend: str) -> dict:
    or_recs = [r for r in regs if r["modo"] == "normal" and r["cat"] == "site" and r["backend"] == backend
               and r["status"] != "pulado_bloqueio"]
    sep = [r for r in regs if r["modo"] == "separado" and r["backend"] == backend
           and r["status"] != "pulado_bloqueio"]
    out: dict = {"n_or": len(or_recs), "n_sep": len(sep)}
    if or_recs:
        out["or_vazio"] = sum(1 for r in or_recs if r["status"] == "vazio") / len(or_recs)
        out["or_no_dominio"] = media([fracao_no_dominio(r) for r in or_recs if r["n"] > 0])
        out["or_sites_cobertos"] = media([sites_cobertos(r["hosts"], r["sites_hosts"]) or 0.0 for r in or_recs])
        out["or_resultados_medio"] = media([r["n"] for r in or_recs])
    if sep:
        grupos: dict[str, list[dict]] = {}
        for r in sep:
            grupos.setdefault(r["consulta"], []).append(r)
        cobs, res_total, no_dom = [], [], []
        for subs in grupos.values():
            sites_h = subs[0]["sites_hosts"]
            cobertos = {r["site_host"] for r in subs if any(casa_site(h, r["site_host"]) for h in r["hosts"])}
            if sites_h:
                cobs.append(len(cobertos & set(sites_h)) / len(sites_h))
            res_total.append(sum(r["n"] for r in subs))
            no_dom += [fracao_no_dominio(r) for r in subs if r["n"] > 0]
        out["sep_vazio"] = sum(1 for r in sep if r["status"] == "vazio") / len(sep)
        out["sep_no_dominio"] = media(no_dom)
        out["sep_sites_cobertos"] = media(cobs)
        out["sep_resultados_medio"] = media(res_total)
    return out


def decisao_or(m: dict) -> str:
    """Regra: `separado` se cobrir pelo menos 10 p.p. mais domínios pedidos; senão OR se a
    fração no domínio e o acerto forem razoáveis; senão revisar."""
    cob_or = m.get("or_sites_cobertos")
    cob_sep = m.get("sep_sites_cobertos")
    if cob_or is None and cob_sep is None:
        return "sem dado"
    if cob_sep is not None and (cob_or is None or cob_sep >= cob_or + 0.10):
        return "trocar por separado"
    no_dom = m.get("or_no_dominio") or 0.0
    if no_dom >= 0.5 and m.get("or_vazio", 1.0) <= 0.3:
        return "manter OR"
    return "OR ruim; separado não ganha: revisar"


def pontuacao(m: dict) -> float:
    return (0.5 * (m["cob_url"] or 0.0) + 0.3 * (m["cob_host"] or 0.0)
            + 0.2 * (1 - (m["pct_vazio"] or 0.0)) - 0.3 * (m["pct_ratelimit"] or 0.0))


def elegiveis(backends: list[str], regs: list[dict], tipo: str) -> list[tuple[str, float]]:
    ok = []
    for b in backends:
        m = metricas(regs, tipo, b)
        if not m["n"]:
            continue
        if (m["pct_vazio"] or 0) <= 0.5 and (m["pct_falha"] or 0) <= 0.3:
            ok.append((b, pontuacao(m)))
    return sorted(ok, key=lambda x: -x[1])


# --------------------------------------------------------------------------- relatório

def pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.0f}%"


def num(x: float | None, casas: int = 0) -> str:
    return "—" if x is None else f"{x:.{casas}f}"


def tabela(cabecalho: list[str], linhas: list[list[str]]) -> str:
    saida = ["| " + " | ".join(cabecalho) + " |", "|" + "|".join("---" for _ in cabecalho) + "|"]
    saida += ["| " + " | ".join(str(c) for c in linha) + " |" for linha in linhas]
    return "\n".join(saida)


def escrever_md(meta: dict, consultas: list[dict], regs: list[dict]) -> None:
    linhas: list[str] = []
    a = linhas.append
    a("# Sonda ddgs: medição da migração SerpAPI -> ddgs (Fase 1)")
    a("")
    if meta.get("aviso"):
        a(f"> **AVISO DE CONTAMINAÇÃO:** {meta['aviso']}")
        a("")
    pulados = sum(1 for r in regs if r["status"] == "pulado_bloqueio")
    falhas_ctrl = sum(1 for r in regs if r["modo"] == "controle" and r["status"] != "ok")
    if pulados or falhas_ctrl:
        a(f"> **Possível bloqueio de IP detectado:** {falhas_ctrl} controles falharam; {pulados} buscas puladas "
          "nos backends bloqueados. Veja a seção de controles.")
        a("")
    a(f"Gerado em {datetime.now().isoformat(timespec='seconds')} pelo `scripts/sonda_ddgs.py`. "
      f"Dados brutos em `docs/review/sonda_ddgs.json`.")
    a("")
    a(f"- ddgs {meta.get('ddgs')}; região `{REGIAO}`; max_results {MAX_RESULTADOS}; timeout {meta.get('timeout_s')} s; "
      f"ritmo {meta.get('rps')} req/s (sequencial).")
    a(f"- Amostra: {meta.get('n')} consultas (seed {meta.get('seed')}) de {meta.get('cassetes_disponiveis')} cassetes SerpAPI úteis; "
      f"{len(regs)} chamadas ao ddgs.")
    cats = Counter(c["cat"] for c in consultas)
    a(f"- Categorias da amostra: notícias {cats.get('noticias', 0)}, google com `site:` {cats.get('site', 0)}, "
      f"google simples {cats.get('texto', 0)}.")
    if meta.get("parcial"):
        a("- **ATENÇÃO: execução parcial** (interrompida antes do fim).")
    a("")
    a("Score de texto/notícias (só para ordenar): 0.5 x cobertura de URLs + 0.3 x cobertura de hosts + "
      "0.2 x (1 - % vazio) - 0.3 x % ratelimit. Elegível: % vazio <= 50% e % falhas <= 30%. "
      "A cobertura é contra a SerpAPI, que é o que o eval usa hoje, mas não é o gabarito: "
      "ddgs e Google podem ser igualmente bons e divergir na ordem.")
    a("")

    # --- texto
    a("## Texto (engine=google da SerpAPI)")
    a("")
    linhas_t, notas_t = [], []
    for b in BACKENDS_TEXTO:
        m = metricas(regs, "texto", b)
        if not m["n"]:
            continue
        linhas_t.append([b, m["n"], pct(m["pct_vazio"]), f"{m['vazio_lento']}", m["ratelimit"], m["timeout"], m["erro"],
                         num(m["lat_media_ms"]), pct(m["cob_url"]), pct(m["cob_host"]),
                         num(m["itens_medio"], 1), pct(m["pct_data"]), f"{pontuacao(m):.2f}"])
        if m["erros_exemplo"]:
            notas_t.append(f"- `{b}`: {m['erros_exemplo'][0]}")
    a(tabela(["backend", "chamadas", "% vazio", "vazio lento*", "ratelimit", "timeout", "erro",
              "lat média ms", "cob. URL", "cob. host", "itens/busca", "% com data", "score"], linhas_t))
    a("")
    a("\\* vazio lento = resposta vazia com latência >= timeout. Como o ddgs só coleta motores que terminam dentro da "
      "espera, esse vazio pode ser lentidão e não ausência de resultado.")
    a("")
    if notas_t:
        a("Erros mais comuns:")
        a("")
        linhas_erro = notas_t
        a("\n".join(linhas_erro))
        a("")

    # --- notícias
    a("## Notícias (engine=google_news da SerpAPI)")
    a("")
    linhas_n, datas_n = [], []
    for b in BACKENDS_NOTICIAS:
        m = metricas(regs, "noticias", b)
        if not m["n"]:
            continue
        linhas_n.append([b, m["n"], pct(m["pct_vazio"]), m["vazio_lento"], m["ratelimit"], m["timeout"], m["erro"],
                         num(m["lat_media_ms"]), pct(m["cob_url"]), pct(m["cob_host"]), num(m["itens_medio"], 1),
                         pct(m["pct_data"]), f"{pontuacao(m):.2f}"])
        fmts = ", ".join(f"{k}: {v}" for k, v in sorted(m["formatos"].items(), key=lambda kv: -kv[1]))
        exs = "; ".join(f"{k} `{v[0]}`" for k, v in m["exemplos_data"].items() if v)
        datas_n.append(f"- `{b}`: formatos ({fmts or '—'}). Exemplos: {exs or '—'}. "
                       f"Fontes mais comuns: {', '.join(m['fontes_exemplo']) or '—'}.")
    a(tabela(["backend", "chamadas", "% vazio", "vazio lento*", "ratelimit", "timeout", "erro",
              "lat média ms", "cob. URL", "cob. host", "itens/busca", "% com data", "score"], linhas_n))
    a("")
    if datas_n:
        a("Datas e fontes observadas:")
        a("")
        a("\n".join(datas_n))
        a("")

    # --- site:
    a("## Consultas com `site:` (OR como o agente manda hoje, e separado por domínio)")
    a("")
    linhas_s = []
    for b in BACKENDS_TEXTO:
        m = metricas_site(regs, b)
        if not m["n_or"] and not m["n_sep"]:
            continue
        linhas_s.append([
            b, m["n_or"], pct(m.get("or_vazio")), pct(m.get("or_no_dominio")), pct(m.get("or_sites_cobertos")),
            num(m.get("or_resultados_medio"), 1), m["n_sep"], pct(m.get("sep_vazio")), pct(m.get("sep_no_dominio")),
            pct(m.get("sep_sites_cobertos")), num(m.get("sep_resultados_medio"), 1), decisao_or(m),
        ])
    a(tabela(["backend", "OR: consultas", "OR: % vazio", "OR: res. no domínio", "OR: domínios cobertos",
              "OR: res./busca", "sep: buscas", "sep: % vazio", "sep: res. no domínio",
              "sep: domínios cobertos", "sep: res. (total por consulta)", "decisão"], linhas_s))
    a("")
    a("\"Domínios cobertos\" = fração dos domínios pedidos com ao menos um resultado daquele domínio. "
      "\"Res. no domínio\" = fração dos resultados que pertencem a algum domínio pedido.")
    a("")

    # --- recomendação
    a("## Recomendação")
    a("")
    et = elegiveis(BACKENDS_TEXTO, regs, "texto")
    en = elegiveis(BACKENDS_NOTICIAS, regs, "noticias")
    a(f"- `DDGS_TEXT_BACKENDS={','.join(b for b, _ in et) or '(nenhum elegível)'}`")
    a(f"- `DDGS_NEWS_BACKENDS={','.join(b for b, _ in en) or '(nenhum elegível)'}`")
    trocar = [b for b in BACKENDS_TEXTO if decisao_or(metricas_site(regs, b)) == "trocar por separado"]
    manter = [b for b in BACKENDS_TEXTO if decisao_or(metricas_site(regs, b)) == "manter OR"]
    a(f"- `site:` com OR: trocar por `separado` nos backends {', '.join(trocar) or 'nenhum'}; "
      f"manter OR nos backends {', '.join(manter) or 'nenhum'}.")
    a("")

    # --- controles de sanidade
    a("## Controles de sanidade (consulta trivial por backend)")
    a("")
    chaves = [("texto", b) for b in BACKENDS_TEXTO] + [("noticias", b) for b in BACKENDS_NOTICIAS]
    linhas_c = []
    buscas_feitas = 0
    primeira_falha: dict[tuple[str, str], int] = {}
    contagem: dict[tuple[str, str], list[int]] = {}
    for r in regs:
        if r["modo"] == "controle":
            k = (r["tipo"], r["backend"])
            c = contagem.setdefault(k, [0, 0])
            c[0] += 1
            if r["status"] == "ok":
                c[1] += 1
            elif k not in primeira_falha:
                primeira_falha[k] = buscas_feitas
        elif r["status"] != "pulado_bloqueio":
            buscas_feitas += 1
    for k in chaves:
        tot, oks = contagem.get(k, [0, 0])
        if not tot:
            linhas_c.append([k[0], k[1], "sem controle (coleta anterior à rodada de controle)", "—", "—"])
        else:
            pulados_k = sum(1 for r in regs if (r["tipo"], r["backend"]) == k and r["status"] == "pulado_bloqueio")
            linhas_c.append([k[0], k[1], f"{oks}/{tot}", str(primeira_falha.get(k, "—")), str(pulados_k)])
    a(tabela(["tipo", "backend", "controles ok", "após quantas buscas caiu", "buscas puladas"], linhas_c))
    a("")
    a("Controle = consulta trivial (\"" + CONTROLE_QUERY + "\"). Falha = vazio ou erro. Um backend com controle "
      "falho é tratado como bloqueado: as buscas dele são puladas até um controle voltar a passar. O ddgs não expõe "
      "o 429/202 do motor, por isso o bloqueio aparece como \"No results found\".")
    a("")

    # --- observações
    a("## Observações")
    a("")
    if meta.get("n", 0) and any(metricas(regs, "texto", b)["vazio_lento"] for b in BACKENDS_TEXTO):
        a("- Há vazios com latência >= timeout: confirme antes de usar estes números como taxa de vazio real "
          "(ver nota da tabela de texto).")
    a("- O ddgs não devolve `date` no `text()` (esperado); a coluna % com data de texto mostra se algum backend devolve.")
    a("- Cobertura usa a SerpAPI como referência, não como gabarito. Divergência de ranking não é erro por si só.")
    a("- Se algum backend mostrar ratelimit em massa, o script para após 8 seguidos (ver JSON).")
    a("")
    ARQ_MD.parent.mkdir(parents=True, exist_ok=True)
    ARQ_MD.write_text("\n".join(linhas), encoding="utf-8")


def reanalisar() -> None:
    if not ARQ_JSON.exists():
        sys.exit(f"Não existe {ARQ_JSON}; rode a sonda antes.")
    dados = json.loads(ARQ_JSON.read_text(encoding="utf-8"))
    escrever_md(dados["meta"], dados["consultas"], dados["registros"])
    print(f"Regerado: {ARQ_MD}")


def main() -> None:
    p = argparse.ArgumentParser(description="Sonda ddgs vs cassetes SerpAPI (Fase 1 da migração).")
    p.add_argument("--cassetes", help="pasta com os cassetes SerpAPI (padrão: checkout principal eval/cassettes)")
    p.add_argument("--n", type=int, default=N_PADRAO, help=f"nº de consultas amostradas (padrão {N_PADRAO})")
    p.add_argument("--seed", type=int, default=SEMENTE_PADRAO, help="semente da amostra")
    p.add_argument("--rps", type=float, default=RPS_PADRAO, help="chamadas por segundo (padrão 1)")
    p.add_argument("--timeout", type=float, default=TIMEOUT_PADRAO, help="timeout do DDGS em s (padrão 5)")
    p.add_argument("--sep-max", type=int, default=9, help="nº de consultas site: medidas também no modo separado")
    p.add_argument("--rapido", action="store_true", help="teste de fumaça: n=5, 1 consulta site: no modo separado")
    p.add_argument("--reanalisar", action="store_true", help="só regera o .md a partir do .json (sem rede)")
    args = p.parse_args()
    if args.reanalisar:
        reanalisar()
        return
    adquirir_lock()
    rodar(args)


def adquirir_lock() -> None:
    """Uma instância por vez: lock com o pid; removido ao sair. Resíduo de execução morta: apagar à mão."""
    SAIDA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(ARQ_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        dono = ARQ_LOCK.read_text(encoding="utf-8").strip() if ARQ_LOCK.exists() else "?"
        sys.exit(f"Outra sonda já está rodando (pid {dono}). Se for resíduo de execução morta, apague {ARQ_LOCK}.")
    os.write(fd, str(os.getpid()).encode("ascii"))
    os.close(fd)
    atexit.register(lambda: ARQ_LOCK.unlink(missing_ok=True))


if __name__ == "__main__":
    main()
