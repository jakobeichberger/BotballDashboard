#!/bin/bash
# Runs Alembic migrations then starts the FastAPI server.
# Used as the Docker ENTRYPOINT so the DB is always up-to-date before serving.

set -e

echo "==> Running database migrations..."
# Retry up to 15 times (45s) in case the DB container reports healthy before
# the init scripts have finished creating the target database.
for i in $(seq 1 15); do
    if alembic upgrade head 2>&1; then
        break
    fi
    if [ "$i" -eq 15 ]; then
        echo "ERROR: database still not ready after 15 attempts, giving up."
        exit 1
    fi
    echo "    attempt $i failed, retrying in 3s..."
    sleep 3
done

echo "==> Starting BotballDashboard API..."
# Client IPs come from X-Forwarded-For only for trusted proxies
# (FORWARDED_ALLOW_IPS; docker-compose.yml sets it for the Traefik setup).
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
    --no-access-log \
    --log-level warning
