"""Provedor da busca web (BUSCA_PROVEDOR): interface comum e fábrica dos clientes.

`serpapi` (SerpAPIClient, pago por busca) e `ddgs` (DDGSClient, metasearch sem chave) têm a mesma
superfície pública: `buscar_ex(params) -> ResultadoBusca` e `buscar(params) -> payload`. Este módulo
só importa `config` e `telemetria`, para que `serpapi_layer` e `ddgs_layer` possam herdar de `ClienteBusca` sem ciclo.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from . import config, telemetria

PROVEDORES = ("serpapi", "ddgs")


class ClienteBusca:
    """Base dos clientes de busca. Subclasses implementam `buscar_ex`; `buscar` devolve só o payload.

    O agente usa `buscar_ex` (motivo por chamada) quando o cliente NÃO sobrescreveu `buscar`; fakes de
    teste que sobrescrevem só `buscar` continuam sendo chamados por ele.
    """

    def buscar(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.buscar_ex(params).payload

    def buscar_ex(self, params: Dict[str, Any]) -> Any:  # ResultadoBusca (serpapi_layer)
        raise NotImplementedError


def provedor_configurado() -> str:
    """BUSCA_PROVEDOR normalizado. Valor desconhecido cai no serpapi com fallback registrado."""
    bruto = str(getattr(config, "BUSCA_PROVEDOR", "serpapi") or "serpapi").strip().lower()
    if bruto not in PROVEDORES:
        telemetria.fallback("busca", f"BUSCA_PROVEDOR desconhecido ({bruto}): usando serpapi")
        return "serpapi"
    return bruto


def cliente_padrao() -> ClienteBusca:
    """Cliente do provedor configurado (SerpAPIClient ou DDGSClient). Nunca levanta."""
    if provedor_configurado() == "ddgs":
        from .ddgs_layer import DDGSClient
        return DDGSClient()
    from .serpapi_layer import SerpAPIClient
    return SerpAPIClient()
