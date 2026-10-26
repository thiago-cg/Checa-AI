#!/usr/bin/env bash
# Deploy da API web (e do bot do Telegram, por webhook, se o ENV_ARQ tiver TELEGRAM_TOKEN) no
# Google Cloud Run, a partir do código local (o build roda no Cloud Build:
# não precisa de Docker instalado). Uso, da raiz do projeto:
#
#   PROJETO=meu-projeto-gcp scripts/deploy_cloudrun.sh
#
# Variáveis opcionais: SERVICO (checa-ai), REGIAO (southamerica-east1), ENV_ARQ (.env).
# As chaves do ENV_ARQ vão para o Secret Manager (uma versão nova a cada deploy) e nunca são
# impressas nem entram na imagem. Configurações não secretas da lista CONFIG_PUBLICA viram
# variáveis de ambiente do serviço.
set -euo pipefail

PROJETO="${PROJETO:?defina PROJETO=<id do projeto no Google Cloud>}"
SERVICO="${SERVICO:-checa-ai}"
REGIAO="${REGIAO:-southamerica-east1}"
ENV_ARQ="${ENV_ARQ:-.env}"

# Mesmas listas de scripts/deploy_hf.py (mantenha iguais).
SEGREDOS=(TELEGRAM_TOKEN OPENROUTER_API_KEY GOOGLE_FACTCHECK_API_KEY SERPAPI_KEY SERPAPI_KEYS)
for i in $(seq 2 20); do SEGREDOS+=("SERPAPI_KEY_$i"); done
# Fica de fora UNSLOTH_* (LLM local, inalcançável da nuvem) e LAYA_* (detector não instalado).
CONFIG_PUBLICA=(OPENROUTER_MODEL OPENROUTER_MODEL_JUIZ OPENROUTER_FALLBACK_MODEL OPENROUTER_PROVIDER_ORDER
                OPENROUTER_REASONING_EFFORT OPENROUTER_RPM LLM_DAILY_CAP SERPAPI_DAILY_CAP CACHE_SERPAPI_TTL
                SERP_ENGINE SERP_ESTRATEGIA INDICE_CHECAGENS RELEVANCIA_MIN MAX_AFIRMACOES MAX_EVIDENCIAS)

# Valor de NOME no ENV_ARQ (última ocorrência, sem aspas em volta); vazio se ausente.
valor() {
  [ -f "$ENV_ARQ" ] || return 0
  sed -n "s/^[[:space:]]*\(export[[:space:]]\{1,\}\)\{0,1\}$1=//p" "$ENV_ARQ" | tail -n1 \
    | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/"
}

gcloud config set project "$PROJETO" >/dev/null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com

NUM_PROJETO="$(gcloud projects describe "$PROJETO" --format='value(projectNumber)')"
CONTA_SERVICO="${NUM_PROJETO}-compute@developer.gserviceaccount.com"

set_secrets=()
for nome in "${SEGREDOS[@]}"; do
  v="$(valor "$nome")"
  [ -n "$v" ] || continue
  segredo="$(echo "$SERVICO-$nome" | tr '[:upper:]_' '[:lower:]-')"
  if ! gcloud secrets describe "$segredo" >/dev/null 2>&1; then
    gcloud secrets create "$segredo" --replication-policy=automatic >/dev/null
  fi
  printf '%s' "$v" | gcloud secrets versions add "$segredo" --data-file=- >/dev/null
  gcloud secrets add-iam-policy-binding "$segredo" --member="serviceAccount:$CONTA_SERVICO" \
    --role=roles/secretmanager.secretAccessor >/dev/null
  set_secrets+=("$nome=$segredo:latest")
  echo "segredo $nome -> $segredo"
done
[ ${#set_secrets[@]} -gt 0 ] || { echo "Nenhuma chave encontrada em $ENV_ARQ." >&2; exit 1; }

env_vars=()
for nome in "${CONFIG_PUBLICA[@]}"; do
  v="$(valor "$nome")"
  [ -n "$v" ] && env_vars+=("$nome=$v")
done

# --max-instances 1: limita o gasto (SerpAPI/OpenRouter) e mantém o limitador de taxa em memória
# coerente. --timeout 300: uma checagem pode levar até 180 s. --min-instances 0: dorme sem acesso.
# --memory 2Gi: torch + BERTimbau carregados ocupam ~1 GB além da API.
# --no-cpu-throttling: o webhook do Telegram responde na hora e a checagem segue em segundo plano;
# com a CPU limitada fora das requisições, ela pararia. A instância continua dormindo sem acesso.
args=(--source . --region "$REGIAO" --allow-unauthenticated
      --memory 2Gi --cpu 1 --timeout 300 --concurrency 4
      --min-instances 0 --max-instances 1 --no-cpu-throttling
      --set-secrets "$(IFS=,; echo "${set_secrets[*]}")")
[ ${#env_vars[@]} -gt 0 ] && args+=(--set-env-vars "^@^$(IFS=@; echo "${env_vars[*]}")")

gcloud run deploy "$SERVICO" "${args[@]}"
URL="$(gcloud run services describe "$SERVICO" --region "$REGIAO" --format='value(status.url)')"
echo "URL: $URL"

# Registra o webhook do bot. O segredo é o mesmo de telegram_bot.segredo_webhook (derivado do token).
# O token vai pelo stdin do curl (-K -), não pela linha de comando: não aparece em `ps` nem no log.
token="$(valor TELEGRAM_TOKEN)"
if [ -n "$token" ]; then
  segredo_tg="$(printf 'webhook:%s' "$token" | sha256sum | cut -c1-64)"
  printf 'url = "https://api.telegram.org/bot%s/setWebhook"\n' "$token" \
    | curl -fsS -K - --data-urlencode "url=$URL/telegram/webhook" \
        --data-urlencode "secret_token=$segredo_tg" \
        --data-urlencode 'allowed_updates=["message","callback_query"]' >/dev/null
  echo "webhook do Telegram -> $URL/telegram/webhook"
fi
