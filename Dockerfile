FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        postgresql-client \
        tini \
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
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
