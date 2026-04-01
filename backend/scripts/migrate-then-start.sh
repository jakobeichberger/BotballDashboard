#!/bin/bash
# Runs Alembic migrations then starts the FastAPI server.
# Used as the Docker ENTRYPOINT so the DB is always up-to-date before serving.

set -e

echo "==> Running database migrations..."
alembic upgrade head

echo "==> Starting BotballDashboard API..."
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --no-access-log \
    --log-level warning
