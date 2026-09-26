#!/usr/bin/env bash
# =============================================================================
# BotballDashboard – update an existing installation (or roll it back)
# =============================================================================
# Run from anywhere on the host (as a user allowed to use Docker):
#   /opt/botballdashboard/scripts/update.sh            # follow the branch (main), rebuild, restart
#   /opt/botballdashboard/scripts/update.sh --no-pull  # rebuild the current checkout
#   /opt/botballdashboard/scripts/update.sh --ref v1.4 # check out a tag/branch/commit
#   /opt/botballdashboard/scripts/update.sh --rollback # back to the release before
#                                                      # the last update, no rebuild
# Options: --skip-backup (no backup before the migrations; not recommended).
#
# An update is
#   git pull → build images → verified backup → [PostgreSQL major upgrade]
#   → docker compose up -d (the backend runs the migrations on start)
# (a plain `docker compose pull` would only refresh postgres/redis/traefik).
#
# Backup: with the "production" profile a backup is taken and verified
# (backup_scheduler.py once --verify: restore test of the new archive, or its
# checksum without the restore-test key) after the build and BEFORE anything
# is migrated; the update stops if it fails. Its name goes into .deploy-state.
#
# Images: the application images are tagged with the commit they were built
# from (<prefix>-backend:<sha>, <prefix>-frontend:<sha>, see docker-compose.yml);
# the running release is tagged before the build, so --rollback only re-tags
# and starts the previous images. The five newest release tags are kept.
#
# Detached HEAD (after --ref <tag|commit>, a deploy from GitHub or a
# rollback): a plain update.sh cannot `git pull` there. It checks out the
# branch it follows – UPDATE_BRANCH, else the remote's default branch (main) –
# and pulls that, i.e. "update" always means "newest state of the branch".
# To stay on a fixed release use --ref <tag>; --no-pull rebuilds exactly the
# checked-out commit.
#
# Frontend build mode (FRONTEND_BUILD=auto|host|docker, default auto):
#   host    build dist/ with pnpm on the host and wrap it with
#           frontend/Dockerfile.prebuilt – needed on Proxmox LXC without
#           nesting, where esbuild cannot run inside `docker build`
#   docker  `docker compose build frontend` (multi-stage Dockerfile)
#   auto    host if pnpm is installed, otherwise docker
#
# Before updating, the current commit, Alembic revision and image tag are
# written to .deploy-state for a rollback (docs/documentation/installation/update.md).
# =============================================================================
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_SERVICES=(volume-permissions backup-permissions backend worker worker-ocr beat backup)
# Services that use the database or the backend image (stopped for a rollback).
APP_SERVICES=(backend worker worker-ocr beat backup)
KEEP_RELEASE_TAGS=5
PULL=true
REF=""
ROLLBACK=false
SKIP_BACKUP=false

info()    { echo -e "\033[0;36m[INFO]\033[0m  $*"; }
success() { echo -e "\033[0;32m[OK]\033[0m    $*"; }
warn()    { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
die()     { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-pull) PULL=false ;;
    --ref) REF="${2:?--ref needs a value}"; shift ;;
    --rollback) ROLLBACK=true ;;
    --skip-backup) SKIP_BACKUP=true ;;
    -h|--help) sed -n '2,43p' "${BASH_SOURCE[0]}"; exit 0 ;;
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

# Value of KEY in .deploy-state.
state_value() {
  [[ -f .deploy-state ]] || return 0
  sed -n "s/^$1=//p" .deploy-state | tail -n1
}

IMAGE_PREFIX="${BOTBALL_IMAGE_PREFIX:-$(env_value BOTBALL_IMAGE_PREFIX)}"
IMAGE_PREFIX="${IMAGE_PREFIX:-botballdashboard}"
BACKEND_IMAGE="${IMAGE_PREFIX}-backend"
FRONTEND_IMAGE="${IMAGE_PREFIX}-frontend"
export BOTBALL_IMAGE_PREFIX="${IMAGE_PREFIX}"

mapfile -t active_services < <(docker compose config --services)
is_active() {
  local service
  for service in "${active_services[@]}"; do [[ "${service}" == "$1" ]] && return 0; done
  return 1
}
running() { [[ -n "$(docker compose ps -q --status running "$1" 2>/dev/null)" ]]; }

# Tag the image a running service's container uses as <image>:<tag>, unless
# that tag exists already. Only a running container says for sure which
# image belongs to the running release (installations from before the fixed
# image names run <project>-backend:latest).
tag_running_image() {
  local service="$1" image="$2" tag="$3" cid id
  docker image inspect "${image}:${tag}" >/dev/null 2>&1 && return 0
  cid="$(docker compose ps -q --status running "${service}" 2>/dev/null | head -n1)"
  [[ -n "${cid}" ]] || return 1
  id="$(docker inspect --format '{{.Image}}' "${cid}" 2>/dev/null)" || return 1
  docker tag "${id}" "${image}:${tag}"
  info "Kept the running ${service} image as ${image}:${tag}"
}

# Tag the running release's images with PREVIOUS_IMAGE_TAG for --rollback.
remember_running_images() {
  local tag="$1"
  if tag_running_image backend "${BACKEND_IMAGE}" "${tag}" \
    && tag_running_image frontend "${FRONTEND_IMAGE}" "${tag}"; then
    echo "PREVIOUS_IMAGE_TAG=${tag}" >> .deploy-state
  else
    warn "backend/frontend not running – the previous images are not kept; a rollback needs a rebuild"
  fi
}

# Delete release tags beyond the newest KEEP_RELEASE_TAGS (never :local or
# the tags named in .deploy-state). Only the tag goes; a layer still used by
# another tag or a container stays.
prune_release_tags() {
  local image keep_a keep_b tag
  keep_a="$(state_value PREVIOUS_IMAGE_TAG)"
  keep_b="$(state_value CURRENT_IMAGE_TAG)"
  for image in "${BACKEND_IMAGE}" "${FRONTEND_IMAGE}"; do
    docker image ls --format '{{.CreatedAt}}\t{{.Tag}}' "${image}" \
      | sort -r | cut -f2 \
      | grep -Ev '^(local|<none>)$' \
      | tail -n +"$((KEEP_RELEASE_TAGS + 1))" \
      | while read -r tag; do
          [[ "${tag}" == "${keep_a}" || "${tag}" == "${keep_b}" ]] && continue
          docker image rm "${image}:${tag}" >/dev/null 2>&1 || true
        done
  done
}

wait_for_backend() {
  info "Waiting for the backend to become healthy..."
  local state=""
  for _ in $(seq 1 60); do
    state="$(docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q backend)" 2>/dev/null || true)"
    [[ "${state}" == "healthy" ]] && break
    sleep 5
  done
  if [[ "${state}" != "healthy" ]]; then
    docker compose logs --tail=40 backend
    die "backend is not healthy (state: ${state:-unknown}). Roll back: scripts/update.sh --rollback (docs/documentation/installation/update.md)"
  fi
  success "Backend healthy"
}

settle_and_verify() {
  # Give the other healthchecks (worker, backup) time to leave "starting" and
  # Prometheus one scrape interval, so the verification sees the settled state.
  local starting cid
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
}

# Verified backup of the running database before anything is migrated.
# Runs the NEW backend image (already built) next to the running stack.
pre_migration_backup() {
  local label="$1" output archive
  if [[ "${SKIP_BACKUP}" == "true" ]]; then
    warn "--skip-backup: no backup before ${label}"
    return 0
  fi
  if ! is_active backup; then
    warn "No backup service (COMPOSE_PROFILES lacks \"production\") – no backup before ${label}."
    warn "Take one yourself (see docs/operations.md) or enable the production profile."
    return 0
  fi
  if ! running db; then
    warn "The database is not running – no backup before ${label} (fresh installation?)."
    return 0
  fi
  info "Backup before ${label} (backup + restore test / checksum)..."
  # A new release may add volumes to the backup service (e.g. the
  # restore-test key); hand them to the app user first, as `up` would.
  docker compose run --rm --no-deps -T backup-permissions >/dev/null 2>&1 \
    || warn "backup-permissions failed – the backup may not reach every volume"
  if ! output="$(docker compose run --rm --no-deps -T backup \
      python scripts/backup_scheduler.py once --verify 2>&1)"; then
    echo "${output}" | tail -n 30 >&2
    die "the backup before ${label} failed – nothing was changed. Fix the backup (docs/operations.md) or re-run with --skip-backup."
  fi
  archive="$(sed -n 's/.*backup succeeded: //p' <<<"${output}" | tail -n1)"
  echo "PRE_UPDATE_BACKUP=${archive}" >> .deploy-state
  success "Verified backup: ${archive:-see docker compose logs backup}"
}

# ── Rollback ─────────────────────────────────────────────────────────────────
if [[ "${ROLLBACK}" == "true" ]]; then
  [[ -f .deploy-state ]] || die "no .deploy-state – nothing to roll back to"
  prev_commit="$(state_value PREVIOUS_COMMIT)"
  prev_revision="$(state_value PREVIOUS_ALEMBIC_REVISION)"
  prev_tag="$(state_value PREVIOUS_IMAGE_TAG)"
  [[ -n "${prev_commit}" && -n "${prev_tag}" ]] \
    || die ".deploy-state has no PREVIOUS_COMMIT/PREVIOUS_IMAGE_TAG (written by update.sh from this version on)"
  for image in "${BACKEND_IMAGE}" "${FRONTEND_IMAGE}"; do
    docker image inspect "${image}:${prev_tag}" >/dev/null 2>&1 \
      || die "image ${image}:${prev_tag} is gone – rebuild instead: git checkout ${prev_commit} && scripts/update.sh --no-pull"
  done
  # Everything that could stop the rollback half-way is checked before the
  # application is stopped.
  git cat-file -e "${prev_commit}^{commit}" 2>/dev/null \
    || die "commit ${prev_commit} is not in this checkout (git fetch origin)"
  git diff --quiet HEAD -- \
    || die "the checkout has local changes (git status); commit or stash them first"
  info "Rolling back to ${prev_commit:0:12} (images :${prev_tag}, alembic ${prev_revision:-unknown})"
  pre_migration_backup "the rollback"

  info "Stopping the application (database and Redis keep running)..."
  to_stop=()
  for service in "${APP_SERVICES[@]}"; do is_active "${service}" && to_stop+=("${service}"); done
  docker compose stop "${to_stop[@]}"

  if [[ -n "${prev_revision}" ]]; then
    # The downgrade needs the CURRENT release: only its code knows the newer
    # revisions and their downgrade() steps. It runs in a one-off container
    # while the backend is stopped, so no restart can upgrade it again.
    docker compose up -d db >/dev/null 2>&1 || true
    current_revision="$(docker compose run --rm --no-deps -T backend alembic current 2>/dev/null \
      | awk '/^[0-9a-f]+/ {print $1; exit}' || true)"
    if [[ -z "${current_revision}" ]]; then
      # E.g. a PostgreSQL major upgrade failed: the new server refuses the
      # old files, and no migration has run. If one had run, the old backend
      # fails its start visibly ("Can't locate revision") – no data is lost.
      warn "Cannot read the current Alembic revision (database not running?) – no downgrade"
    elif [[ "${current_revision}" != "${prev_revision}" ]]; then
      info "Migrating the database down: ${current_revision:-?} → ${prev_revision}"
      docker compose run --rm --no-deps -T backend alembic downgrade "${prev_revision}" \
        || die "alembic downgrade failed – the application is stopped. Restore the backup ($(state_value PRE_UPDATE_BACKUP)) or start the current release again: docker compose up -d"
    fi
  else
    warn "No previous Alembic revision recorded – the database is left as it is"
  fi

  # The previous release's compose file and scripts, then its images.
  git checkout --quiet "${prev_commit}"
  for image in "${BACKEND_IMAGE}" "${FRONTEND_IMAGE}"; do
    docker tag "${image}:${prev_tag}" "${image}:local"
  done
  mapfile -t active_services < <(docker compose config --services)
  info "Starting the previous release (no build)..."
  # Its migrate-then-start.sh runs `alembic upgrade head`; head of the old
  # code is the revision just migrated to, so nothing is upgraded again.
  docker compose up -d --no-build --remove-orphans
  {
    echo "ROLLED_BACK_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "CURRENT_COMMIT=${prev_commit}"
    echo "CURRENT_IMAGE_TAG=${prev_tag}"
  } >> .deploy-state
  wait_for_backend
  settle_and_verify
  success "Rolled back to $(git rev-parse --short HEAD) (detached HEAD; a later scripts/update.sh follows the branch again)"
  exit 0
fi

# ── 1. Remember the running version ──────────────────────────────────────────
# Skipped when this script restarted itself after step 2 (see there).
if [[ -z "${BOTBALL_UPDATE_RESTARTED:-}" ]]; then
  previous_commit="$(git rev-parse HEAD)"
  previous_tag="$(git rev-parse --short=12 HEAD)"
  previous_revision="$(docker compose exec -T backend alembic current 2>/dev/null \
    | awk '/^[0-9a-f]+/ {print $1; exit}' || true)"
  if [[ -z "${previous_revision}" && -f .deploy-state ]]; then
    # The backend is down, typically after an update that stopped half-way;
    # the version recorded before that update is the one to roll back to.
    info "Backend not running – keeping the rollback point in .deploy-state:"
    sed 's/^/        /' .deploy-state
  else
    {
      echo "PREVIOUS_COMMIT=${previous_commit}"
      echo "PREVIOUS_ALEMBIC_REVISION=${previous_revision}"
      echo "UPDATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > .deploy-state
    # Keep the running release's images under its commit for --rollback.
    remember_running_images "${previous_tag}"
    info "Current version: ${previous_commit:0:12} (alembic ${previous_revision:-unknown}) → saved to .deploy-state"
  fi
elif [[ -z "$(state_value PREVIOUS_IMAGE_TAG)" && -n "$(state_value PREVIOUS_COMMIT)" ]]; then
  # Restarted by an older update.sh, which wrote .deploy-state without image
  # tags; the old release is still running (nothing is built yet).
  remember_running_images "$(git rev-parse --short=12 "$(state_value PREVIOUS_COMMIT)")"
fi

# ── 2. Update the checkout ───────────────────────────────────────────────────
script_before="$(sha256sum "${BASH_SOURCE[0]}" | cut -d' ' -f1)"
if [[ -n "${REF}" ]]; then
  git fetch --tags origin
  git checkout "${REF}"
  if git symbolic-ref -q HEAD >/dev/null; then git pull --ff-only; fi
elif [[ "${PULL}" == "true" ]]; then
  if ! git symbolic-ref -q HEAD >/dev/null; then
    branch="${UPDATE_BRANCH:-$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)}"
    branch="${branch:-main}"
    info "Detached HEAD at $(git rev-parse --short HEAD) (after --ref, a GitHub deploy or a rollback)."
    info "Following branch '${branch}' again; use --ref <tag> to stay on a release, --no-pull to rebuild this commit."
    git fetch origin
    git checkout "${branch}"
  fi
  git pull --ff-only
fi
success "Checkout at $(git rev-parse --short HEAD): $(git log -1 --format=%s)"

# The rest of the update belongs to the new release: if the pull changed this
# script, continue with the new version (it may know steps the old one did
# not, such as a database migration).
if [[ -z "${BOTBALL_UPDATE_RESTARTED:-}" ]] \
  && [[ "$(sha256sum "${BASH_SOURCE[0]}" | cut -d' ' -f1)" != "${script_before}" ]]; then
  info "scripts/update.sh changed – continuing with the new version"
  restart_args=(--no-pull)
  [[ "${SKIP_BACKUP}" == "true" ]] && restart_args+=(--skip-backup)
  BOTBALL_UPDATE_RESTARTED=1 exec "${BASH_SOURCE[0]}" "${restart_args[@]}"
fi
mapfile -t active_services < <(docker compose config --services)

# ── 3. Build images ──────────────────────────────────────────────────────────
new_tag="$(git rev-parse --short=12 HEAD)"
if [[ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]]; then
  # Local modifications: the images are not exactly that commit.
  new_tag="${new_tag}-dirty"
fi
mode="${FRONTEND_BUILD:-auto}"
if [[ "${mode}" == "auto" ]]; then
  if command -v pnpm >/dev/null 2>&1; then mode=host; else mode=docker; fi
fi

info "Pulling base images (postgres, redis, traefik, monitoring)..."
docker compose pull --ignore-buildable --quiet || warn "some base images could not be pulled – using cached ones"

# Only build services that exist in the active profiles.
to_build=()
for service in "${BACKEND_SERVICES[@]}"; do
  is_active "${service}" && to_build+=("${service}")
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
  # Installations set up before the switch to Node.js 24 still have Node 22;
  # the build works for now, but re-run step 3 of proxmox-setup.sh to upgrade.
  node_major=$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)
  if [[ "${node_major:-0}" -lt 24 ]]; then
    warn "Node.js ${node_major:-?} on the host – the project targets Node.js 24 LTS (see docs/documentation/installation/update.md)"
  fi
  (
    cd frontend
    pnpm install --frozen-lockfile
    VITE_API_URL=/api VITE_VAPID_PUBLIC_KEY="$(cd .. && env_value VAPID_PUBLIC_KEY)" pnpm build
  )
  docker build --pull -f frontend/Dockerfile.prebuilt -t "${FRONTEND_IMAGE}:local" frontend \
    || docker build -f frontend/Dockerfile.prebuilt -t "${FRONTEND_IMAGE}:local" frontend
else
  info "Building frontend in Docker..."
  docker compose build --pull frontend || docker compose build frontend
fi
for image in "${BACKEND_IMAGE}" "${FRONTEND_IMAGE}"; do
  docker tag "${image}:local" "${image}:${new_tag}"
done
echo "CURRENT_IMAGE_TAG=${new_tag}" >> .deploy-state
success "Images built and tagged :${new_tag}"

# ── 4. Verified backup, then the PostgreSQL major version ────────────────────
# Nothing has touched the data yet; the running release keeps serving.
pre_migration_backup "the migrations"

# A new PostgreSQL major in docker-compose.yml needs the data dumped with the
# old server and restored into the new one. postgres-upgrade.sh does that with
# a row-count check, keeps the old files for a rollback and does nothing when
# the database is already on the right version.
pg_state=0
scripts/postgres-upgrade.sh --check || pg_state=$?
case "${pg_state}" in
  0) ;;
  3)
    info "The database has to move to a new PostgreSQL major version (application stops meanwhile)..."
    scripts/postgres-upgrade.sh --yes \
      || die "PostgreSQL upgrade failed – the old data is unchanged; see the messages above and docs/documentation/installation/update.md"
    ;;
  *) die "PostgreSQL data needs attention (see above); the running stack was left as it is" ;;
esac

# ── 5. Restart ───────────────────────────────────────────────────────────────
info "Starting the updated stack (migrations run on backend start)..."
docker compose up -d --remove-orphans
wait_for_backend
prune_release_tags
settle_and_verify
success "Update complete: $(git rev-parse --short HEAD) (images :${new_tag}; rollback: scripts/update.sh --rollback)"
