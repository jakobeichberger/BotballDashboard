.PHONY: up down dev migrate logs shell-backend shell-db build test lint update verify backup-now backup-status vapid-keys fernet-key lock-backend

# ── Production ────────────────────────────────────────────────
up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

# ── Development ───────────────────────────────────────────────
dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

dev-backend:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up db redis backend

dev-frontend:
	cd frontend && pnpm dev

# ── Database ──────────────────────────────────────────────────
migrate:
	docker compose exec backend alembic upgrade head

migrate-down:
	docker compose exec backend alembic downgrade -1

migrate-create:
	docker compose exec backend alembic revision --autogenerate -m "$(MSG)"

# ── Logs ──────────────────────────────────────────────────────
logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-db:
	docker compose logs -f db

# ── Shells ────────────────────────────────────────────────────
shell-backend:
	docker compose exec backend bash

shell-db:
	docker compose exec db psql -U botball botball

# ── Testing ───────────────────────────────────────────────────
test-backend:
	docker compose exec backend pytest -n auto

test-frontend:
	cd frontend && pnpm test

# ── Dependencies ──────────────────────────────────────────────
# Re-pin backend/requirements*.txt after changing pyproject.toml (needs uv:
# https://docs.astral.sh/uv/). The Docker images and CI install these files.
lock-backend:
	cd backend && uv pip compile pyproject.toml --universal --python-version 3.11 --custom-compile-command "make lock-backend" -o requirements.txt
	cd backend && uv pip compile pyproject.toml --extra dev --universal --python-version 3.11 --custom-compile-command "make lock-backend" -o requirements-dev.txt

# ── Linting ───────────────────────────────────────────────────
lint-backend:
	docker compose exec backend sh -c "ruff check . && mypy ."

lint-frontend:
	cd frontend && pnpm lint

# ── Utilities ─────────────────────────────────────────────────
vapid-keys:
	docker compose exec backend sh -c "mkdir -p /app/vapid && cd /app/vapid && vapid --gen >/dev/null && printf 'VAPID_PRIVATE_KEY=/app/vapid/private_key.pem\nVAPID_PUBLIC_KEY=' && vapid --applicationServerKey | sed -n 's/^Application Server Key = *//p'"

fernet-key:
	docker compose exec backend python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# ── Operations ────────────────────────────────────────────────
update:
	./scripts/update.sh

verify:
	./scripts/verify-deployment.sh

backup-now:
	docker compose exec backup python scripts/backup_scheduler.py once

backup-status:
	docker compose exec backup python scripts/backup_scheduler.py check
