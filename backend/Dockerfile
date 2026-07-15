# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Dependencies ──────────────────────────────────────────────
FROM base AS deps
COPY pyproject.toml .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && pip install .

# ── Development target ────────────────────────────────────────
FROM deps AS development
# watchfiles for --reload, plus the test/lint toolchain (mirrors the
# [project.optional-dependencies] dev group) so `make test-backend` and
# `make lint-backend` work out-of-the-box inside the container.
RUN pip install \
    watchfiles \
    pytest==8.2.0 \
    pytest-asyncio==0.23.6 \
    pytest-cov==5.0.0 \
    aiosqlite==0.20.0 \
    factory-boy==3.3.0 \
    ruff==0.4.4 \
    mypy==1.10.0
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Production target ─────────────────────────────────────────
FROM deps AS production
COPY . .
RUN chmod +x scripts/migrate-then-start.sh
EXPOSE 8000
CMD ["./scripts/migrate-then-start.sh"]
