# syntax=docker/dockerfile:1
FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    libglib2.0-0 \
    libgl1 \
    postgresql-client \
    age \
    rsync \
    openssh-client \
    rclone \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged runtime user. The uid/gid are fixed (10001) so that volume and
# host-directory ownership is predictable; compose's volume-permissions and
# backup-permissions services hand existing volumes over to it (see
# docs/documentation/installation/update.md).
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /home/app --create-home \
       --shell /usr/sbin/nologin app

WORKDIR /app

# ── Dependencies ──────────────────────────────────────────────
# requirements.txt pins every package (generated from pyproject.toml with
# `make lock-backend`), so an image build installs exactly what CI tested.
FROM base AS deps
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && pip install -r requirements.txt

# ── Development target ────────────────────────────────────────
FROM deps AS development
# The pinned test/lint toolchain; uvicorn[standard] already brings watchfiles
# for --reload.
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Production target ─────────────────────────────────────────
FROM deps AS production
COPY . .
# The code stays root-owned (read-only for the app); only the directories the
# app writes to belong to it. New named volumes mounted there inherit this
# ownership.
RUN chmod +x scripts/*.sh \
    && mkdir -p /app/uploads /app/vapid /backups \
    && chown app:app /app/uploads /app/vapid /backups
USER app
EXPOSE 8000
CMD ["./scripts/migrate-then-start.sh"]
