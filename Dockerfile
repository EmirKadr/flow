FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

# Microsoft ODBC Driver 18 krävs för att prata med Azure SQL via pyodbc.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        gnupg \
        ca-certificates \
        libgomp1 \
        tini \
        unixodbc \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc \
         | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -sSL https://packages.microsoft.com/config/debian/12/prod.list \
         -o /etc/apt/sources.list.d/mssql-release.list \
    && sed -i 's|https://|[signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://|' \
         /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 flow

WORKDIR /repo

COPY app/requirements.txt /repo/app/requirements.txt
RUN pip install --no-cache-dir -r /repo/app/requirements.txt

COPY --chown=flow:flow app/ /repo/app/
COPY --chown=flow:flow data/ /repo/data/
COPY --chown=flow:flow warehouse_tools/ /repo/warehouse_tools/

USER flow
WORKDIR /repo/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "python -m backend.prestart && exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
