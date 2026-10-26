"""API compartilhada Telegram <-> futura web (RNF05). Tipada pelos schemas."""
from __future__ import annotations

import asyncio
import hmac
import html
import json
import logging
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from . import config, llm_openrouter
from .catalogo import Catalogo
from .indice import Indice
from .pipeline import Pipeline
from .schemas import EntradaConsulta, RelatorioChecagem
from .serpapi_layer import SerpAPIClient

try:
    from .telegram_bot import (LINK_SEM_TEXTO_MSG, _texto_link, _urls_nao_analisadas,
                               classificar_entrada, entrada_de_link, formatar)
except Exception:  # telegram opcional p/ API/web (bot não quebra API)
    def classificar_entrada(texto: str) -> EntradaConsulta:  # type: ignore
        t = (texto or "").strip()
        if t.startswith(("http://", "https://", "www.")):
            return EntradaConsulta(tipo="link", conteudo=t[:2000])
        if len(t) <= 140 and "\n" not in t:
            return EntradaConsulta(tipo="titulo", conteudo=t)
        return EntradaConsulta(tipo="texto", conteudo=t[:20000])

    def formatar(rel) -> str:  # type: ignore
        return f"{rel.header or rel.propensao} {rel.why_1linha or rel.justificativa}"

    def _urls_nao_analisadas(rel) -> set:  # type: ignore
        try:
            dec = getattr(rel, "decisao", None) or {}
            return {n.get("url") for n in dec.get("nao_analisadas", []) or [] if n.get("url")}
        except Exception:
            return set()

    _texto_link = None  # type: ignore
    entrada_de_link = None  # type: ignore
    LINK_SEM_TEXTO_MSG = "Não consegui ler esse link. Cole aqui o título e o texto da notícia."

log = logging.getLogger("factcheck.api")

_tg = None  # Application do bot em modo webhook (None = desligado)


@asynccontextmanager
async def _ciclo(_app):
    """Com TELEGRAM_WEBHOOK=1 e token, o bot roda neste processo: o Telegram entrega cada
    atualização em POST /telegram/webhook e o Application a processa em segundo plano."""
    global _tg
    if config.TELEGRAM_WEBHOOK and config.TELEGRAM_TOKEN:
        try:
            from .telegram_bot import construir_app
            tg = construir_app(webhook=True)
            await tg.initialize()
            await tg.start()
            _tg = tg
            log.info("bot do Telegram no ar (webhook)")
        except Exception:
            log.exception("bot do Telegram não subiu; a API segue sem ele")
    if _tg is not None and config.TELEGRAM_WEBHOOK_URL:
        try:
            from .telegram_bot import registrar_webhook
            await registrar_webhook(_tg.bot, config.TELEGRAM_WEBHOOK_URL)
        except Exception:
            log.exception("falha ao registrar o webhook do Telegram")
    try:
        yield
    finally:
        if _tg is not None:
            await _tg.stop()
            await _tg.shutdown()
            _tg = None


app = FastAPI(title="Checa AI", version="0.2.0", lifespan=_ciclo)

_pipe: Pipeline | None = None
_lock = threading.Lock()
_hits: defaultdict = defaultdict(list)  # ip -> [timestamps] rate-limit simples


def pipeline() -> Pipeline:
    global _pipe
    if _pipe is None:
        with _lock:
            if _pipe is None:
                try:
                    catalogo = Catalogo.carregar()
                except RuntimeError as e:
                    log.error("catálogo indisponível: %s", e)
                    raise HTTPException(status_code=503, detail="catálogo indisponível, tente mais tarde")
                # Índice de checagens (ClaimReview/RSS): atalho opcional atrás de INDICE_CHECAGENS
                idx_ver = Indice.de_checagens()
                idx_not = Indice()
                _pipe = Pipeline(catalogo, idx_ver, idx_not, SerpAPIClient())
    return _pipe


@app.get("/saude")
def saude():
    p = pipeline()
    return {"ok": True, "portais": len(p.catalogo), "vereditos": len(p.idx_ver),
            "noticias": len(p.idx_not), "serpapi": p.serpapi.ativo,
            "serpapi_engine": p.serpapi.engine_default,
            "serpapi_estrategia": getattr(config, "SERP_ESTRATEGIA", "agente"),
            "serpapi_uso_hoje": p.serpapi.uso_hoje,
            "serpapi_cap": getattr(config, "SERPAPI_DAILY_CAP", 100),
            "openrouter": llm_openrouter.status_chave(),
            "versao": "mvp-0.2.0"}


@app.get("/portais")
def portais():
    p = pipeline()
    # Sem `responsavel` (nomes da equipe) na resposta pública.
    return [{"id": x["id"], "nome": x["nome"], "tipo": x["tipo"],
             "homepage": x["homepage"]} for x in p.catalogo.portais]


def _rate_ok(request: Request | None) -> bool:
    """Rate-limit por IP (sliding window 60s); True = pode prosseguir.

    Evita SerpAPI+LLM sem throttle; poda o mapa quando cresce demais
    (bot traffic não vira vazamento de memória).
    """
    try:
        limite = getattr(config, "API_RATE_LIMIT_PER_MIN", 30) or 30
        if limite <= 0 or request is None or not getattr(request, "client", None):
            return True
        ip = getattr(request.client, "host", "unknown") or "unknown"
        agora = time.time()
        if len(_hits) > 1000:  # evict: entradas sem hit recente
            for k in [k for k, v in _hits.items()
                      if not v or agora - v[-1] >= 120][: len(_hits) - 1000]:
                _hits.pop(k, None)
        janela = [t for t in _hits.get(ip, []) if agora - t < 60]
        if len(janela) >= limite:
            return False
        janela.append(agora)
        _hits[ip] = janela[-limite:]
        return True
    except Exception:
        return True


async def _ler_link(entrada: EntradaConsulta) -> EntradaConsulta | None:
    """Link -> texto da página (mesma regra do bot: só portais do catálogo, anti-SSRF).

    Retorna a entrada pronta para o pipeline, ou None se o link não pôde ser lido —
    aí, como no bot, pede-se o texto em vez de checar só o endereço."""
    if entrada.tipo != "link":
        return entrada
    if _texto_link is None:
        return None
    texto = await asyncio.to_thread(_texto_link, entrada.conteudo, pipeline().catalogo)
    if not texto:
        return None
    # "Hoje" da matéria = data da própria página; sem data, E4 desligado (A5).
    return entrada_de_link(entrada.conteudo, texto)


def _log_timeout() -> None:
    """Linha no log do servidor (Render/Cloud Run) para achar o trace do run cortado."""
    from . import telemetria
    log.warning("checagem cortada após %s s (CHECAGEM_TIMEOUT_S); run=%s",
                config.CHECAGEM_TIMEOUT_S, telemetria.ultimo_run_id())


def _checar_rate(request: Request) -> None:
    if not _rate_ok(request):
        raise HTTPException(status_code=429, detail="muitas checagens; tente de novo em instantes")


async def _checagem(entrada: EntradaConsulta, progresso=None) -> RelatorioChecagem:
    """Checagem com teto de tempo; toda falha sai como HTTPException com mensagem para a pessoa.
    `progresso`: callback async com os avisos do pipeline (os mesmos que o bot mostra)."""
    try:
        async with asyncio.timeout(config.CHECAGEM_TIMEOUT_S):
            pronta = await _ler_link(entrada)
            if pronta is None:
                raise HTTPException(status_code=422, detail=LINK_SEM_TEXTO_MSG)
            from .agregador import preparar_para_pessoa
            if progresso is None:
                rel = await pipeline().executar(pronta)
            else:
                rel = await pipeline().executar(pronta, progresso=progresso)
            return preparar_para_pessoa(rel)
    except (asyncio.TimeoutError, TimeoutError):
        _log_timeout()
        raise HTTPException(status_code=504, detail="checagem excedeu o tempo; tente um texto mais curto")
    except HTTPException:
        raise
    except Exception:
        log.exception("falha no pipeline")  # detalhe só no servidor, nunca no cliente
        raise HTTPException(status_code=502, detail="falha temporária, tente de novo em instantes")


@app.post("/checar", response_model=RelatorioChecagem)
async def checar(entrada: EntradaConsulta, request: Request):
    _checar_rate(request)
    return await _checagem(entrada)


@app.post("/checar-html", response_class=HTMLResponse)
async def checar_html(entrada: EntradaConsulta, request: Request):
    """Mesma checagem do /checar, devolvendo o bloco do relatório já montado (o JS da página só o
    insere): um desenho só para a página, com o raciocínio filtrado (C1) e as fontes fora do tema."""
    rel = await checar(entrada, request)
    return HTMLResponse(_relatorio_html(entrada.conteudo, rel))


@app.post("/checar-stream")
async def checar_stream(entrada: EntradaConsulta, request: Request):
    """O /checar-html com a etapa real: NDJSON com uma linha {"etapa"} por aviso do pipeline e, no
    fim, {"html"} (o bloco do relatório) ou {"erro", "status"}. A página mostra o que está rodando."""
    _checar_rate(request)  # antes do stream: o 429 sai como resposta HTTP normal
    fila: asyncio.Queue = asyncio.Queue()

    async def progresso(msg: str) -> None:
        await fila.put({"etapa": msg})

    async def rodar() -> None:
        try:
            rel = await _checagem(entrada, progresso)
            await fila.put({"html": _relatorio_html(entrada.conteudo, rel)})
        except HTTPException as e:
            await fila.put({"erro": e.detail, "status": e.status_code})
        except Exception:
            log.exception("falha ao montar o relatório")
            await fila.put({"erro": "falha temporária, tente de novo em instantes", "status": 502})
        finally:
            await fila.put(None)

    async def linhas():
        tarefa = asyncio.create_task(rodar())
        try:
            while (item := await fila.get()) is not None:
                yield json.dumps(item, ensure_ascii=False) + "\n"
        finally:
            tarefa.cancel()  # a pessoa fechou a página: não segue gastando busca e LLM

    # X-Accel-Buffering: proxies (Render, nginx) não seguram as linhas até o fim.
    return StreamingResponse(linhas(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _descontos_html(decisao: dict | None) -> str:
    """E4 Task 6 (web): cada fonte com desconto por data, com os dias além da janela, r e bits.
    Os bits ficam só aqui (o bot não os mostra: técnico demais). A URL vem escapada."""
    itens = []
    for x in (decisao or {}).get("descontos_temporais") or []:
        url = str(x.get("url") or "")
        if not url:
            continue
        bits = x.get("bits_descartados")
        bits_txt = f"{float(bits):.2f}" if isinstance(bits, (int, float)) else "?"
        itens.append(f"<li>{html.escape(url)} — {x.get('dias_alem_da_janela', '?')} dias além da janela de "
                     f"{x.get('janela', '?')} · r={x.get('r', '?')} · {bits_txt} bit(s) descartado(s)</li>")
    if not itens:
        return ""
    return ("<p><b>Fontes com desconto por data</b> (publicadas antes do período do texto):</p>"
            f"<ul>{''.join(itens)}</ul>")


def _link_html(url: str) -> str:
    """I3: âncora clicável só para http(s). Outro esquema (javascript:, data:, vbscript:…) ou URL
    malformada vira texto escapado: o navegador não executa nada vindo da fonte."""
    from .agregador import texto_de_linha
    u = texto_de_linha(url)
    try:
        esquema = urlparse(u).scheme.lower()
    except ValueError:
        esquema = ""
    if esquema in ("http", "https"):
        # Visual de botão inline do Telegram: largura total, fundo translúcido, ↗ no canto.
        return (f"<a href=\"{html.escape(u)}\" target='_blank' rel='noopener' "
                f"class='relative block w-full mt-3 py-2 px-8 rounded-lg text-center text-sm font-medium "
                f"bg-sky-500/10 hover:bg-sky-500/20 active:bg-sky-500/30 text-sky-700 dark:text-sky-300 "
                f"transition-colors no-underline'>"
                f"Acessar fonte original"
                f"<span class='absolute top-1 right-2 text-[10px] opacity-70'>↗</span></a>")
    return f"<span class='text-xs text-slate-500'>{html.escape(u[:80])}</span>"


def _relatorio_html(entrada_txt: str, rel: RelatorioChecagem) -> str:
    """Bloco do relatório (o mesmo para /checar-web e para o JS da página, via /checar-html)."""
    from .agregador import (NOMES_ETAPAS, STATUS_ETAPA, data_publicacao_exibida, direcoes_por_url,
                            linha_raciocinio, passos_para_pessoa, postura_legivel, rotulo_selo,
                            texto_de_linha)
    from .confiabilidade import ROTULO
    esc = html.escape
    from .agregador import preparar_para_pessoa
    preparar_para_pessoa(rel)
    direcoes = direcoes_por_url(rel.decisao)
    nao_lidas = _urls_nao_analisadas(rel)
    uteis = [f for f in rel.fontes if f.relevante is not False]
    # Fora do tema segundo o juiz: listadas à parte (acessadas, mas não são evidência).
    fora = [f for f in rel.fontes if f.relevante is False]
    cor = {"contesta o que o texto afirma": "#f87171", "confirma o que o texto afirma": "#4ade80"}
    # E4: mesma regra do bot (ver telegram_bot.formatar): `decisao` validado pelo schema, sem try.
    _dec = rel.decisao or {}
    _descontadas = {x.get("url") for x in _dec.get("descontos_temporais", []) or [] if x.get("url")}

    def _cartao(f) -> str:
        post = postura_legivel(f, direcoes)
        if bool(getattr(f, "corpo_lido", False)) and f.url not in nao_lidas:
            leitura = "📄 texto lido"
        else:
            leitura = "📰 só manchete — não analisada integralmente"
        _r = getattr(f, "relevancia_temporal", None)
        _linha_data = ""
        if (_r is not None and _r < 1.0) or (f.url in _descontadas):
            _dtxt = data_publicacao_exibida(getattr(f, "data_pub", None), getattr(f, "data_pub_precisao", None),
                                            getattr(f, "data_pub_bruta", None))
            if _dtxt:
                _linha_data = f"<br/>📅 {esc(_dtxt)} · anterior ao período do texto"
            else:
                _linha_data = "<br/>📅 anterior ao período do texto"
        _rac = linha_raciocinio(getattr(f, "raciocinio", None))
        _html_rac = f"<span class='text-slate-500 dark:text-slate-400 block mt-1'>{esc(_rac)}</span><br/>" if _rac else ""
        _cit = texto_de_linha(f.quote)[:300]
        _tit = texto_de_linha(f.titulo)[:200]
        if _cit and " ".join(_cit.lower().split()) == " ".join(_tit.lower().split()):
            _cit = ""  # trecho igual ao título não se repete
        return (f"<div class='p-4 rounded-xl bg-slate-50 dark:bg-slate-950/70 border border-slate-200 dark:border-slate-800 my-3 text-sm'>"
                f"<b>{esc(texto_de_linha(f.portal_nome) or 'web')}</b> "
                f"<span style='color:{cor.get(post, '#94a3b8')}'>{esc(post)}</span>"
                f"{' · ' + esc(texto_de_linha(rotulo_selo(f))) if f.selo_visivel else ''}"
                f" · {leitura}"
                f"{' · ' + esc(ROTULO[f.confiabilidade]) if f.confiabilidade in ROTULO else ''}<br/>"
                f"{esc(texto_de_linha(f.titulo)[:200])}<br/>"
                f"{'<i>“' + esc(_cit) + '”</i><br/>' if _cit else ''}"
                f"{_html_rac}"
                f"{_linha_data}"
                f"<br/>{_link_html(f.url)}</div>")

    fontes = "".join(_cartao(f) for f in uteis)
    outras = (f"<h3 class='text-base font-bold text-slate-900 dark:text-white mt-6 mb-2'>Outras fontes acessadas ({len(fora)})</h3>"
              f"<p class='text-sm text-slate-500 dark:text-slate-400'>Estas páginas foram lidas, mas não tratam do assunto; não entram na estimativa.</p>"
              f"{''.join(_cartao(f) for f in fora)}") if fora else ""
    passos = passos_para_pessoa(rel)
    if passos:  # passo a passo com os números do caso; sem decisão detalhada, a lista curta de etapas
        etapas = "".join(
            f"<li class='pl-1'><b class='text-slate-900 dark:text-white'>{esc(p['titulo'])}</b>"
            f"<p class='mt-0.5'>{esc(p['texto'])}</p>"
            + (f"<ul class='list-disc pl-5 mt-1 space-y-0.5'>{''.join(f'<li>{esc(i)}</li>' for i in p['itens'])}</ul>"
               if p["itens"] else "")
            + "</li>" for p in passos)
        etapas = f"<ol class='list-decimal pl-5 mt-2 space-y-3 text-slate-700 dark:text-slate-300'>{etapas}</ol>"
    else:
        etapas = ("<ul class='mt-2 space-y-1 text-slate-700 dark:text-slate-300'>"
                  + "".join(f"<li>{esc(t)}</li>" for t in rel.etapas_pessoa) + "</ul>")
    etapas_tecnicas = "".join(f"<li>{STATUS_ETAPA.get(e.status, '')} <b>{esc(NOMES_ETAPAS.get(e.nome, e.nome))}</b>: "
                              f"{esc(e.detalhe)}</li>" for e in rel.etapas)
    lims = "".join(f"<li>{esc(l)}</li>" for l in rel.limitacoes_pessoa[:5])
    guia = "".join(f"<li>{esc(p)}</li>" for p in rel.perguntas_guia)
    aviso = ("<p class='text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 p-2.5 rounded-lg my-2'>"
             "<i>Não encontrado na base de checagens; resultado de outras fontes</i></p>"
             if rel.onde_encontrado == "web" else "")

    rel_bloco = (
        f"<div class='bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/90 rounded-2xl p-6 sm:p-8 shadow-sm shadow-sm relative transition-colors'>"
        f"<div class='flex flex-wrap items-center justify-between pb-6 border-b border-slate-200 dark:border-slate-800 gap-4'>"
        f"<div>"
        f"<h4 class='text-lg font-bold text-slate-900 dark:text-white mt-0.5'>Resultado da checagem</h4></div>"
        f"</div>"
        f"<div class='mt-6 p-4 rounded-xl bg-slate-50 dark:bg-slate-950/70 border border-slate-200 dark:border-slate-800'>"
        f"<span class='text-xs text-slate-500 block mb-1'>Conteúdo submetido para análise:</span>"
        f"<p class='text-sm text-slate-700 dark:text-slate-300 italic '>“{esc(entrada_txt)}”</p></div>"
        f"<h2 class='text-xl font-bold text-slate-900 dark:text-white mt-6'>{esc(rel.header or rel.propensao)}</h2>"
        f"<p class='resumo text-slate-700 dark:text-slate-300 leading-relaxed my-3'>{esc(rel.resumo_pessoa)}</p>"
        f"{aviso}"
        f"<h3 class='text-base font-bold text-slate-900 dark:text-white mt-6 mb-2'>O que as fontes dizem ({len(uteis)})</h3>"
        f"{fontes or '<p class=\"text-sm text-slate-500 dark:text-slate-400 italic\">Não encontramos fontes que tratem do assunto. Na dúvida, não compartilhe.</p>'}"
        f"{outras}"
        f"<h3 class='text-base font-bold text-slate-900 dark:text-white mt-6 mb-2'>Para avaliar você mesmo</h3><ul class='list-disc pl-5 text-sm text-slate-700 dark:text-slate-300 space-y-1'>{guia}</ul>"
        f"<details class='mt-6 p-4 rounded-xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 text-sm'><summary class='font-bold cursor-pointer text-petroleo-600 dark:text-petroleo-300'>Como chegamos aqui</summary>{etapas}"
        f"<details class=\"tecnico mt-3 text-xs text-slate-500 dark:text-slate-400\"><summary class='cursor-pointer'>Detalhes técnicos</summary><ul class='mt-2 space-y-1'>{etapas_tecnicas}</ul>"
        f"{_descontos_html(rel.decisao)}</details></details>"
        f"{'<h3 class=' + chr(39) + 'text-base font-bold text-slate-900 dark:text-white mt-6 mb-2' + chr(39) + '>Limitações desta análise</h3><ul class=' + chr(39) + 'list-disc pl-5 text-sm text-slate-600 dark:text-slate-400 space-y-1' + chr(39) + '>' + lims + '</ul>' if lims else ''}"
        f"</div>"
    )
    return rel_bloco


def _render_html(entrada_txt: str, rel: RelatorioChecagem | None = None, erro_msg: str = "") -> str:
    from pathlib import Path
    esc = html.escape
    tmpl_path = Path(__file__).resolve().parent / "templates" / "index.html"
    template = tmpl_path.read_text(encoding="utf-8") if tmpl_path.exists() else ""

    if rel:
        rel_bloco = _relatorio_html(entrada_txt, rel)
    else:
        rel_bloco = (
            f"<div class='bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/90 rounded-2xl p-6 sm:p-8 shadow-sm shadow-sm relative transition-colors'>"
            f"<div class='flex flex-wrap items-center justify-between pb-6 border-b border-slate-200 dark:border-slate-800 gap-4'>"
            f"<div>"
            f"<h4 class='text-lg font-bold text-slate-900 dark:text-white mt-0.5'>Resultado da checagem</h4></div>"
            f"<div><span class='px-2.5 py-1 rounded bg-amber-500/10 border border-amber-500/30 text-amber-600 dark:text-amber-400 text-xs font-semibold'>Exemplo Demonstrativo</span></div>"
            f"</div>"
            f"<div class='mt-6 p-4 rounded-xl bg-slate-50 dark:bg-slate-950/70 border border-slate-200 dark:border-slate-800'>"
            f"<span class='text-xs text-slate-500 block mb-1'>Conteúdo de demonstração:</span>"
            f"<p class='text-sm text-slate-700 dark:text-slate-300 italic '>“ATENÇÃO: Banco Central vai bloquear chaves PIX que não pagarem taxa de recadastramento até hoje às 23:59. Acesse o link oficial para regularizar...”</p></div>"
            f"<div class='mt-6 space-y-3'>"
            f"<h2 class='text-xl font-bold text-slate-900 dark:text-white'>🟡 Propensão média de ser fake news</h2>"
            f"<p class='text-petroleo-600 dark:text-petroleo-300 font-semibold'><b>Fontes independentes esclarecem a questão cadastral.</b></p>"
            f"<p class='text-slate-700 dark:text-slate-300 leading-relaxed'>O Banco Central e agências de checagem catalogadas confirmam que não há qualquer taxa associada à manutenção ou regularização de chaves PIX.</p>"
            f"</div>"
            f"<div class='mt-8 pt-6 border-t border-slate-200 dark:border-slate-800'>"
            f"<h3 class='text-xs text-slate-500 dark:text-slate-400 block mb-3 uppercase tracking-wider font-semibold'>Checagens Correspondentes Encontradas:</h3>"
            f"<div class='space-y-3'>"
            f"<div class='p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950/50 border border-slate-200 dark:border-slate-800 flex items-start justify-between gap-4'>"
            f"<div><div class='flex items-center gap-2 mb-1'><span class='text-xs font-bold text-slate-900 dark:text-white'>Agência Lupa</span><span class='text-[10px] text-slate-500 '>Desmentido catalogado</span></div>"
            f"<p class='text-xs text-slate-700 dark:text-slate-300'>Selo da Lupa: FALSO — O Banco Central esclarece que não cobra taxas para o PIX.</p></div>"
            f"<span class='text-xs text-petroleo-600 dark:text-petroleo-300 font-medium'>Auditado</span></div>"
            f"<div class='p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950/50 border border-slate-200 dark:border-slate-800 flex items-start justify-between gap-4'>"
            f"<div><div class='flex items-center gap-2 mb-1'><span class='text-xs font-bold text-slate-900 dark:text-white'>Aos Fatos</span><span class='text-[10px] text-slate-500 '>Desmentido catalogado</span></div>"
            f"<p class='text-xs text-slate-700 dark:text-slate-300'>Site clone simula página governamental para capturar credenciais bancárias.</p></div>"
            f"<span class='text-xs text-petroleo-600 dark:text-petroleo-300 font-medium'>Auditado</span></div>"
            f"</div></div>"
            f"</div>"
        )

    msg_erro = f"<div class='p-3.5 rounded-xl bg-red-950/60 border border-red-800/70 text-red-200 text-xs my-2'><b>{esc(erro_msg)}</b></div>" if erro_msg else ""

    if template:
        html_out = template
        html_out = html_out.replace("{{ CONTEUDO }}", esc(entrada_txt))
        html_out = html_out.replace("{{ MENSAGEM_ERRO_HTML }}", msg_erro)
        html_out = html_out.replace("{{ RELATORIO_HTML }}", rel_bloco)
        return html_out

    # Fallback caso o arquivo de template não seja encontrado
    return (f"<html><head><meta charset='utf-8'><title>Checa AI</title></head><body>"
            f"<h1>Checa AI</h1>{msg_erro}{rel_bloco}</body></html>")


@app.get("/", response_class=HTMLResponse)
def home():
    return _render_html("")


@app.post("/checar-web", response_class=HTMLResponse)
async def checar_web(request: Request, conteudo: str = Form(...)):
    if not _rate_ok(request):
        return HTMLResponse(_render_html(conteudo, erro_msg="Muitas checagens; tente de novo em instantes."), status_code=429)
    try:
        entrada = classificar_entrada(conteudo)
    except Exception:
        return HTMLResponse(_render_html(conteudo, erro_msg="Entrada inválida."), status_code=400)
    try:
        async with asyncio.timeout(config.CHECAGEM_TIMEOUT_S):
            pronta = await _ler_link(entrada)
            if pronta is None:
                return HTMLResponse(_render_html(conteudo, erro_msg=LINK_SEM_TEXTO_MSG), status_code=422)
            rel = await pipeline().executar(pronta)
        from .agregador import preparar_para_pessoa
        return HTMLResponse(_render_html(conteudo, preparar_para_pessoa(rel)))
    except (asyncio.TimeoutError, TimeoutError):
        _log_timeout()
        return HTMLResponse(_render_html(conteudo, erro_msg="A checagem excedeu o tempo; tente um texto mais curto."),
                            status_code=504)
    except Exception:
        log.exception("falha no pipeline web")
        return HTMLResponse(_render_html(conteudo, erro_msg="Falha no pipeline web"), status_code=502)


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Recebe a atualização e responde na hora; a checagem (que pode levar minutos) roda depois,
    no Application. Só aceita quem manda o segredo registrado no setWebhook."""
    if _tg is None:
        raise HTTPException(status_code=404)
    from telegram import Update
    from .telegram_bot import segredo_webhook
    recebido = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "").encode()
    if not hmac.compare_digest(recebido, segredo_webhook(config.TELEGRAM_TOKEN).encode()):
        raise HTTPException(status_code=403)
    try:
        update = Update.de_json(await request.json(), _tg.bot)
    except Exception:
        raise HTTPException(status_code=400)
    await _tg.update_queue.put(update)
    return {"ok": True}


@app.get("/progresso.json")
def progresso_json():
    # Endpoint público: retorna só subconjunto seguro (sem notas internas).
    try:
        import json
        from pathlib import Path
        arq = Path(__file__).resolve().parent.parent / "PROGRESSO.json"
        if arq.exists():
            bruto = json.loads(arq.read_text(encoding="utf-8"))
            return {"loop": bruto.get("loop"), "status": bruto.get("status"),
                    "versao": bruto.get("versao")}
    except Exception:
        pass
    return {"loop": 1, "status": "em andamento"}
