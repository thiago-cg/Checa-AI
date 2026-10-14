"""Rodízio de chaves da SerpAPI (Missão G / item 1).

Chaves lidas do ambiente, nesta ordem e sem repetição: `SERPAPI_KEY`, `SERPAPI_KEY_2` … `SERPAPI_KEY_20` e
`SERPAPI_KEYS` (vírgula). Quando a SerpAPI recusa uma chave (HTTP 401/403/429: cota da conta esgotada ou chave
inválida), `replay` marca a chave como esgotada NESTE processo e o cliente repete a mesma busca com a próxima.
Só quando todas se esgotam o pipeline vê a cota esgotada (e o eval para, como antes).

Nunca registra nem devolve o valor de uma chave: telemetria e CLI falam só em "chave N de M".
Uso: `python -m factcheck_mvp.serpapi_chaves status [--conta]` (`--conta` consulta as buscas restantes de cada
conta em serpapi.com/account.json, que não gasta busca).
"""
from __future__ import annotations

import os
import threading
from typing import List, Optional, Set

MAX_NUMERADAS = 20

_lock = threading.Lock()
_esgotadas: Set[str] = set()


def chaves() -> List[str]:
    """Chaves configuradas, na ordem de uso, sem vazias nem repetidas (lidas do ambiente a cada chamada)."""
    brutas = [os.environ.get("SERPAPI_KEY", "")]
    brutas += [os.environ.get(f"SERPAPI_KEY_{i}", "") for i in range(2, MAX_NUMERADAS + 1)]
    brutas += (os.environ.get("SERPAPI_KEYS", "") or "").split(",")
    out: List[str] = []
    for c in brutas:
        c = (c or "").strip()
        if c and c not in out:
            out.append(c)
    return out


def atual(preferida: Optional[str] = None) -> str:
    """Primeira chave ainda não esgotada. `preferida` (chave explícita do cliente) vem antes das do ambiente;
    "" se não houver nenhuma disponível."""
    lista = ([preferida] if preferida else []) + [c for c in chaves() if c != preferida]
    with _lock:
        for c in lista:
            if c not in _esgotadas:
                return c
    return ""


def posicao(chave: str) -> str:
    """'N de M' para logs (nunca o valor)."""
    lista = chaves()
    n = lista.index(chave) + 1 if chave in lista else 0
    return f"{n or '?'} de {len(lista)}"


def marcar_esgotada(chave: str) -> None:
    if chave:
        with _lock:
            _esgotadas.add(chave)


def alguma_disponivel(preferida: Optional[str] = None) -> bool:
    return bool(atual(preferida))


def n_esgotadas() -> int:
    with _lock:
        return len(_esgotadas)


def resetar() -> None:
    """Esquece as chaves marcadas (testes; um processo novo também começa do zero)."""
    with _lock:
        _esgotadas.clear()


def _status(consultar_conta: bool) -> List[dict]:
    lista = chaves()
    out = []
    for i, c in enumerate(lista, 1):
        item = {"chave": f"{i} de {len(lista)}", "esgotada_neste_processo": c in _esgotadas}
        if consultar_conta:
            try:
                import httpx
                r = httpx.get("https://serpapi.com/account.json", params={"api_key": c}, timeout=15)
                d = r.json() if r.status_code == 200 else {}
                item["buscas_restantes"] = d.get("total_searches_left") if d else None
                item["http"] = r.status_code
            except Exception as e:  # nunca imprime a chave: só o tipo do erro
                item["erro"] = type(e).__name__
        out.append(item)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Chaves da SerpAPI configuradas (sem mostrar valores).")
    ap.add_argument("acao", choices=["status"])
    ap.add_argument("--conta", action="store_true", help="consulta buscas restantes de cada conta (não gasta busca)")
    a = ap.parse_args(argv)
    from . import config  # noqa: F401  (carrega o .env no ambiente)
    st = _status(a.conta)
    total = sum(int(s.get("buscas_restantes") or 0) for s in st)
    print(json.dumps({"n_chaves": len(st), "chaves": st,
                      **({"buscas_restantes_total": total} if a.conta else {})}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
