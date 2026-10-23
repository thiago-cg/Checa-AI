# API web do Checa AI para o Google Cloud Run (ver scripts/deploy_cloudrun.sh).

# Estágio só para extrair o modelo: o zip (~400 MB) não fica em nenhuma camada da imagem final.
FROM python:3.12-slim AS modelo
COPY modelo/bertimbau_v6.zip /tmp/
RUN python -m zipfile -e /tmp/bertimbau_v6.zip /modelo

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NLTK_DATA=/usr/share/nltk_data \
    # O disco do Cloud Run é efêmero: estado de execução vai para /tmp.
    TELEMETRIA_DIR=/tmp/runs \
    SERPAPI_USO_ARQ=/tmp/serpapi_uso.json \
    FACTCHECK_NLTK_DOWNLOAD=0 \
    # Detector BERTimbau v6 (run D1_dedup_s42), extraído no estágio "modelo".
    FAKE_MODEL_PATH=/app/modelo/bertimbau_v6

WORKDIR /app

# torch só de CPU (o índice padrão do pip traz a versão CUDA, bem maior); vem antes do
# requirements para nada puxar outra versão.
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.4"

COPY requirements-web.txt .
RUN pip install -r requirements-web.txt \
 && python -m nltk.downloader -d "$NLTK_DATA" rslp

# --chown no COPY (e não chown -R depois): o chown recursivo duplicaria os 435 MB do modelo numa camada nova.
RUN useradd --create-home app && chown app /app
COPY --chown=app --from=modelo /modelo/ modelo/
COPY --chown=app factcheck_mvp/ factcheck_mvp/
USER app

# O Cloud Run informa a porta em $PORT (8080 por padrão).
CMD exec uvicorn factcheck_mvp.api:app --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers --forwarded-allow-ips="*"
