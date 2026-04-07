# syntax=docker/dockerfile:1.7

# ARG in COPY --from is not reliably expanded; pin via first FROM, then copy by stage name.
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.7
FROM ${UV_IMAGE} AS uv_bin

FROM python:3.13-slim AS builder

COPY --from=uv_bin /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

ENV UV_CACHE_DIR=/root/.cache/uv

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    DEBUG=false

RUN groupadd -r appuser && \
    useradd -r -g appuser -u 1000 appuser && \
    mkdir -p /app && \
    chown -R appuser:appuser /app

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

COPY --chown=appuser:appuser ./src ./src
COPY --chown=appuser:appuser ./alembic ./alembic
COPY --chown=appuser:appuser ./alembic.ini ./alembic.ini

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
