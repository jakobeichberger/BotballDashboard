#!/usr/bin/env bash
# =============================================================================
# BotballDashboard – update an existing installation
# =============================================================================
# Run from anywhere on the host (as a user allowed to use Docker):
#   /opt/botballdashboard/scripts/update.sh            # pull main, rebuild, restart
#   /opt/botballdashboard/scripts/update.sh --no-pull  # rebuild the current checkout
#   /opt/botballdashboard/scripts/update.sh --ref v1.4 # check out a tag/branch/commit
#
# The compose file builds all application images locally, so an update is
#   git pull → build images → docker compose up -d
# (a plain `docker compose pull` would only refresh postgres/redis/traefik).
#
# Frontend build mode (FRONTEND_BUILD=auto|host|docker, default auto):
#   host    build dist/ with pnpm on the host and wrap it with
#           frontend/Dockerfile.prebuilt – needed on Proxmox LXC without
#           nesting, where esbuild cannot run inside `docker build`
#   docker  `docker compose build frontend` (multi-stage Dockerfile)
#   auto    host if pnpm is installed, otherwise docker
#
# Before updating, the current commit and Alembic revision are written to
# .deploy-state for a rollback (see docs/documentation/installation/update.md).
# Database migrations run automatically when the backend container starts.
# =============================================================================
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_IMAGE="botballdashboard-frontend:local"
BACKEND_SERVICES=(volume-permissions backup-permissions backend worker worker-ocr beat backup)
PULL=true
REF=""

info()    { echo -e "\033[0;36m[INFO]\033[0m  $*"; }
success() { echo -e "\033[0;32m[OK]\033[0m    $*"; }
warn()    { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
die()     { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-pull) PULL=false ;;
    --ref) REF="${2:?--ref needs a value}"; shift ;;
    -h|--help) sed -n '2,25p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

cd "${INSTALL_DIR}"
[[ -f .env ]] || die "${INSTALL_DIR}/.env missing – run scripts/proxmox-setup.sh or copy .env.example first."

# Value of KEY from .env (handles "quoted" values written by proxmox-setup.sh).
env_value() {
  python3 - "$1" <<'PYEOF'
import json, re, sys
key = sys.argv[1]
for line in open(".env"):
    m = re.match(rf"^{re.escape(key)}\s*=\s*(.*)$", line.rstrip("\n"))
    if m:
        v = m.group(1).strip()
        if len(v) >= 2 and v[0] == v[-1] == '"':
            try:
                v = json.loads(v)
            except ValueError:
                v = v[1:-1]
        elif len(v) >= 2 and v[0] == v[-1] == "'":
            v = v[1:-1]
        print(v)
        break
PYEOF
}

# ── 1. Remember the running version ──────────────────────────────────────────
previous_commit="$(git rev-parse HEAD)"
previous_revision="$(docker compose exec -T backend alembic current 2>/dev/null \
  | awk '/^[0-9a-f]+/ {print $1; exit}' || true)"
{
  echo "PREVIOUS_COMMIT=${previous_commit}"
  echo "PREVIOUS_ALEMBIC_REVISION=${previous_revision}"
  echo "UPDATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > .deploy-state
info "Current version: ${previous_commit:0:12} (alembic ${previous_revision:-unknown}) → saved to .deploy-state"

# ── 2. Update the checkout ───────────────────────────────────────────────────
if [[ -n "${REF}" ]]; then
  git fetch --tags origin
  git checkout "${REF}"
  if git symbolic-ref -q HEAD >/dev/null; then git pull --ff-only; fi
elif [[ "${PULL}" == "true" ]]; then
  git pull --ff-only
fi
success "Checkout at $(git rev-parse --short HEAD): $(git log -1 --format=%s)"

# ── 3. Build images ──────────────────────────────────────────────────────────
mode="${FRONTEND_BUILD:-auto}"
if [[ "${mode}" == "auto" ]]; then
  if command -v pnpm >/dev/null 2>&1; then mode=host; else mode=docker; fi
fi

info "Pulling base images (postgres, redis, traefik, monitoring)..."
docker compose pull --ignore-buildable --quiet || warn "some base images could not be pulled – using cached ones"

# Only build services that exist in the active profiles.
mapfile -t active_services < <(docker compose config --services)
to_build=()
for service in "${BACKEND_SERVICES[@]}"; do
  for active in "${active_services[@]}"; do
    [[ "${service}" == "${active}" ]] && to_build+=("${service}")
  done
done
info "Building ${to_build[*]}..."
# --pull refreshes the base images (security updates); fall back to the cached
# base image when the registry is unreachable or rate-limited.
if ! docker compose build --pull "${to_build[@]}"; then
  warn "build with --pull failed – retrying with cached base images"
  docker compose build "${to_build[@]}"
fi

if [[ "${mode}" == "host" ]]; then
  info "Building frontend on the host (pnpm)..."
  (
    cd frontend
    pnpm install --frozen-lockfile
    VITE_API_URL=/api VITE_VAPID_PUBLIC_KEY="$(cd .. && env_value VAPID_PUBLIC_KEY)" pnpm build
  )
  docker build --pull -f frontend/Dockerfile.prebuilt -t "${FRONTEND_IMAGE}" frontend \
    || docker build -f frontend/Dockerfile.prebuilt -t "${FRONTEND_IMAGE}" frontend
else
  info "Building frontend in Docker..."
  docker compose build --pull frontend || docker compose build frontend
fi
success "Images built"

# ── 4. Restart ───────────────────────────────────────────────────────────────
info "Starting the updated stack (migrations run on backend start)..."
docker compose up -d --remove-orphans

info "Waiting for the backend to become healthy..."
for _ in $(seq 1 60); do
  state="$(docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q backend)" 2>/dev/null || true)"
  [[ "${state}" == "healthy" ]] && break
  sleep 5
done
if [[ "${state:-}" != "healthy" ]]; then
  docker compose logs --tail=40 backend
  die "backend is not healthy (state: ${state:-unknown}). Roll back: see docs/documentation/installation/update.md"
fi
success "Backend healthy"

# Give the other healthchecks (worker, backup) time to leave "starting" and
# Prometheus one scrape interval, so the verification sees the settled state.
for _ in $(seq 1 24); do
  starting=0
  for cid in $(docker compose ps -q); do
    [[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "${cid}")" == "starting" ]] \
      && starting=1
  done
  [[ ${starting} -eq 0 ]] && break
  sleep 5
done
sleep 20

if [[ -x scripts/verify-deployment.sh ]]; then
  info "Running scripts/verify-deployment.sh..."
  scripts/verify-deployment.sh || die "verification failed – see FAIL lines above"
fi
success "Update complete: $(git rev-parse --short HEAD)"
