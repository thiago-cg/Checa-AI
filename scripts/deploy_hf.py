"""Deploy da API web (e do bot do Telegram, por webhook) num Hugging Face Space do tipo Docker.

Usa o mesmo Dockerfile do Cloud Run. O Space recebe só o necessário para o build (Dockerfile,
requirements-web.txt, factcheck_mvp/, modelo/bertimbau_v6.zip) e um README.md com o cabeçalho que
o HF exige. As chaves do .env viram secrets do Space (nunca entram nos arquivos, que são públicos);
as configurações não secretas viram variables.

Uso (precisa de login no HF com permissão de escrita: `hf auth login` ou HF_TOKEN):
    python3 scripts/deploy_hf.py --space usuario/checa-ai
    python3 scripts/deploy_hf.py --space usuario/checa-ai --sem-webhook   # não mexe no bot

Space grátis é público (código e modelo visíveis) e dorme após ~48 h sem visitas.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Mesmas listas de scripts/deploy_cloudrun.sh (mantenha iguais).
SEGREDOS = (["TELEGRAM_TOKEN", "OPENROUTER_API_KEY", "GOOGLE_FACTCHECK_API_KEY", "SERPAPI_KEY", "SERPAPI_KEYS"]
            + [f"SERPAPI_KEY_{i}" for i in range(2, 21)])
CONFIG_PUBLICA = ["OPENROUTER_MODEL", "OPENROUTER_MODEL_JUIZ", "OPENROUTER_FALLBACK_MODEL",
                  "OPENROUTER_PROVIDER_ORDER", "OPENROUTER_REASONING_EFFORT", "OPENROUTER_RPM", "LLM_DAILY_CAP",
                  "SERPAPI_DAILY_CAP", "CACHE_SERPAPI_TTL", "SERP_ENGINE", "SERP_ESTRATEGIA", "INDICE_CHECAGENS",
                  "RELEVANCIA_MIN", "MAX_AFIRMACOES", "MAX_EVIDENCIAS"]

# app_port: o Dockerfile escuta em ${PORT:-8080} e o HF não define PORT.
README = """---
title: Checa AI
emoji: 🔎
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8080
pinned: false
---

Checa AI: estima a propensão de um texto ser desinformação, com as fontes consultadas.
"""


def _montar(destino: Path) -> None:
    """Copia para `destino` só o que o Dockerfile usa."""
    zip_modelo = RAIZ / "modelo" / "bertimbau_v6.zip"
    if not zip_modelo.exists():
        raise SystemExit(f"modelo ausente: {zip_modelo}")
    for nome in ("Dockerfile", "requirements-web.txt"):
        shutil.copy2(RAIZ / nome, destino / nome)
    shutil.copytree(RAIZ / "factcheck_mvp", destino / "factcheck_mvp",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (destino / "modelo").mkdir()
    shutil.copy2(zip_modelo, destino / "modelo" / zip_modelo.name)
    (destino / "README.md").write_text(README, encoding="utf-8")


def _registrar_webhook(token: str, url_space: str) -> None:
    """Mesmo registro de scripts/deploy_cloudrun.sh. Nunca imprime o token."""
    import httpx

    sys.path.insert(0, str(RAIZ))
    from factcheck_mvp.telegram_bot import segredo_webhook

    r = httpx.post(f"https://api.telegram.org/bot{token}/setWebhook", timeout=20,
                   data={"url": f"{url_space}/telegram/webhook", "secret_token": segredo_webhook(token),
                         "allowed_updates": '["message","callback_query"]'})
    if not r.json().get("ok"):
        raise SystemExit(f"setWebhook falhou (HTTP {r.status_code}): {r.json().get('description', '')}")
    print(f"webhook do Telegram -> {url_space}/telegram/webhook")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--space", required=True, help="usuario/nome do Space")
    ap.add_argument("--env-arq", default=str(RAIZ / ".env"))
    ap.add_argument("--sem-webhook", action="store_true", help="não registra o webhook do Telegram")
    args = ap.parse_args()

    from dotenv import dotenv_values
    from huggingface_hub import HfApi

    env = {k: v for k, v in dotenv_values(args.env_arq).items() if v}
    api = HfApi()
    api.create_repo(args.space, repo_type="space", space_sdk="docker", exist_ok=True)

    secrets = [n for n in SEGREDOS if n in env]
    if not secrets:
        raise SystemExit(f"Nenhuma chave encontrada em {args.env_arq}.")
    for nome in secrets:
        api.add_space_secret(args.space, nome, env[nome])
        print(f"secret {nome}")
    for nome in CONFIG_PUBLICA:
        if nome in env:
            api.add_space_variable(args.space, nome, env[nome])

    with tempfile.TemporaryDirectory() as tmp:
        _montar(Path(tmp))
        # delete_patterns: arquivo apagado do código local some também do Space.
        api.upload_folder(repo_id=args.space, repo_type="space", folder_path=tmp,
                          commit_message="deploy", delete_patterns=["factcheck_mvp/**"])

    url = (api.space_info(args.space).host or "").rstrip("/")
    print(f"URL: {url}  (o build leva alguns minutos; acompanhe na aba Logs do Space)")
    if env.get("TELEGRAM_TOKEN") and not args.sem_webhook and url:
        _registrar_webhook(env["TELEGRAM_TOKEN"], url)


if __name__ == "__main__":
    main()
