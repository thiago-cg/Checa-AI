# API web do Checa AI para o Google Cloud Run (ver scripts/deploy_cloudrun.sh).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NLTK_DATA=/usr/share/nltk_data \
    # O disco do Cloud Run é efêmero: estado de execução vai para /tmp.
    TELEMETRIA_DIR=/tmp/runs \
    SERPAPI_USO_ARQ=/tmp/serpapi_uso.json \
    FACTCHECK_NLTK_DOWNLOAD=0

WORKDIR /app

COPY requirements-web.txt .
RUN pip install -r requirements-web.txt \
 && python -m nltk.downloader -d "$NLTK_DATA" rslp

COPY factcheck_mvp/ factcheck_mvp/

RUN useradd --create-home app && chown -R app /app
USER app

# O Cloud Run informa a porta em $PORT (8080 por padrão).
CMD exec uvicorn factcheck_mvp.api:app --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers --forwarded-allow-ips="*"
