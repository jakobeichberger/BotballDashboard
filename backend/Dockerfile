# syntax=docker/dockerfile:1
FROM python:3.14-slim AS base

# Major version of the PostgreSQL client tools (pg_dump, pg_restore, psql) for
# backup.sh, restore.sh and restore-test.sh. It must match the server image in
# docker-compose.yml (postgres:18-alpine): a newer pg_restore writes settings
# an older server rejects, an older pg_dump refuses a newer server. Debian's
# own postgresql-client follows the Debian release (17 in trixie), so the
# client comes from the PostgreSQL project's apt repository (apt.postgresql.org).
ARG PG_MAJOR=18

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
       https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    libglib2.0-0 \
    libgl1 \
    postgresql-client-${PG_MAJOR} \
    age \
    rsync \
    openssh-client \
    rclone \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/* \
    && pg_dump --version | grep -q " ${PG_MAJOR}\."

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
