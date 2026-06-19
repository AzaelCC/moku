# Build from the repository root:
# docker build -f apps/backend/Dockerfile -t moku-backend .

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    XDG_CACHE_HOME=/app/.cache \
    HF_HOME=/app/.cache/huggingface \
    HF_DATASETS_CACHE=/app/.cache/huggingface/datasets \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends --yes build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
COPY apps/backend/pyproject.toml apps/backend/pyproject.toml
COPY packages/moku-core/pyproject.toml packages/moku-core/pyproject.toml

RUN uv sync --frozen --no-dev --package moku-backend --all-extras \
    --no-install-package moku-backend \
    --no-install-package moku-core

COPY apps/backend/src apps/backend/src
COPY apps/backend/alembic apps/backend/alembic
COPY apps/backend/alembic.ini apps/backend/alembic.ini
COPY packages/moku-core/src packages/moku-core/src

RUN uv sync --frozen --no-dev --package moku-backend --all-extras --no-editable

RUN groupadd --system moku \
    && useradd --system --gid moku --home /app moku \
    && mkdir -p /app/.cache/huggingface/datasets \
    && chown -R moku:moku /app/.cache
USER moku

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=2).read()"

CMD ["uvicorn", "moku_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
