#!/usr/bin/env bash
# =============================================================================
# BotballDashboard – Proxmox One-Call Setup Script
# =============================================================================
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/jakobeichberger/BotballDashboard/main/scripts/proxmox-setup.sh | bash
#   or locally:
#   bash scripts/proxmox-setup.sh
#
# What this script does:
#   1.  Checks prerequisites (OS, root, network)
#   2.  Installs Docker + Docker Compose plugin
#   3.  Installs Node.js 20 + pnpm (needed to build the frontend on the host)
#   4.  Clones the repository (or updates if already cloned)
#   5.  Interactively generates a .env file with all required secrets
#   6.  Creates required data directories
#   7.  Builds the frontend on the host (esbuild/workbox run natively, no Docker)
#   8.  Builds the backend Docker image; the frontend nginx image just copies dist/
#   9.  Starts all services
#   10. Generates VAPID keys, rebuilds frontend with them, restarts nginx
#   11. Creates first admin user
#   12. Prints access info
#
# Tested on: Debian 12 (Bookworm) LXC container on Proxmox VE 8
#
# Note: The frontend is built directly on the host rather than inside a Docker
# build container. This avoids a socketpair()/ENOTCONN failure that occurs when
# esbuild (used by Vite + workbox-build) tries to spawn its child service daemon
# inside a Docker build container running in a Proxmox LXC without kernel
# nesting enabled.
# =============================================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── Config ────────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/jakobeichberger/BotballDashboard.git"
INSTALL_DIR="/opt/botballdashboard"
DATA_DIR="/data"
MIN_DOCKER_VERSION="24"
NODE_MAJOR="20"
PNPM_VERSION="10.29.3"
HEALTH_URL="http://localhost:8000/api/system/health"

# ── Helpers ───────────────────────────────────────────────────────────────────
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

header() {
  echo ""
  echo -e "${BOLD}${BLUE}══════════════════════════════════════════════${NC}"
  echo -e "${BOLD}${BLUE}  $*${NC}"
  echo -e "${BOLD}${BLUE}══════════════════════════════════════════════${NC}"
  echo ""
}

prompt() {
  local var_name="$1"
  local prompt_text="$2"
  local default="${3:-}"
  local secret="${4:-false}"

  if [[ -n "$default" ]]; then
    prompt_text="$prompt_text [${default}]"
  fi

  if [[ "$secret" == "true" ]]; then
    read -rsp "${prompt_text}: " value
    echo ""
  else
    read -rp "${prompt_text}: " value
  fi

  if [[ -z "$value" && -n "$default" ]]; then
    value="$default"
  fi
  printf -v "$var_name" '%s' "$value"
}

generate_secret() {
  local bytes="${1:-32}"
  python3 -c "import secrets; print(secrets.token_urlsafe(${bytes}))"
}

generate_fernet_key() {
  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
}

# ── Step 1: Prerequisite Checks ───────────────────────────────────────────────
check_prerequisites() {
  header "Step 1/10 – Checking Prerequisites"

  if [[ $EUID -ne 0 ]]; then
    die "This script must be run as root (or via sudo)."
  fi
  success "Running as root"

  if [[ ! -f /etc/debian_version ]]; then
    warn "This script is optimised for Debian/Ubuntu. Proceeding anyway..."
  else
    local debian_ver
    debian_ver=$(cat /etc/debian_version)
    success "Debian/Ubuntu detected (${debian_ver})"
  fi

  if ! curl -fsSL --max-time 5 https://github.com > /dev/null 2>&1; then
    die "No internet access. Please check network connectivity."
  fi
  success "Internet connectivity OK"

  local pkgs=()
  command -v git     &>/dev/null || pkgs+=(git)
  command -v curl    &>/dev/null || pkgs+=(curl)
  command -v python3 &>/dev/null || pkgs+=(python3)
  if [[ ${#pkgs[@]} -gt 0 ]]; then
    info "Installing missing packages: ${pkgs[*]}..."
    apt-get update -qq && apt-get install -y -q "${pkgs[@]}" > /dev/null
  fi
  success "git, curl, python3 available"
}

# ── Step 2: Install Docker ─────────────────────────────────────────────────────
install_docker() {
  header "Step 2/10 – Installing Docker"

  if command -v docker &>/dev/null; then
    local docker_ver
    docker_ver=$(docker version --format '{{.Server.Version}}' 2>/dev/null | cut -d. -f1)
    if [[ "${docker_ver:-0}" -ge "$MIN_DOCKER_VERSION" ]]; then
      success "Docker ${docker_ver} already installed"
      apt-get install -y -q python3-cryptography > /dev/null 2>&1 || true
      return 0
    else
      warn "Docker version too old (${docker_ver}). Upgrading..."
    fi
  fi

  info "Installing Docker via official install script..."
  curl -fsSL https://get.docker.com | sh

  systemctl enable --now docker > /dev/null 2>&1

  local installed_ver
  installed_ver=$(docker version --format '{{.Server.Version}}' 2>/dev/null | cut -d. -f1)
  success "Docker ${installed_ver} installed and running"

  info "Installing python3-cryptography for key generation..."
  apt-get install -y -q python3-cryptography > /dev/null 2>&1 || \
    pip3 install cryptography --quiet
  success "python3-cryptography available"
}

# ── Step 3: Install Node.js + pnpm ────────────────────────────────────────────
# The frontend is built on the LXC host so that esbuild and workbox-build can
# use their native binaries (socketpair IPC works fine outside Docker).
install_node() {
  header "Step 3/10 – Installing Node.js ${NODE_MAJOR} + pnpm ${PNPM_VERSION}"

  # ── Node.js ───────────────────────────────────────────────────────────────
  local node_ok=false
  if command -v node &>/dev/null; then
    local nv
    nv=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1)
    if [[ "${nv:-0}" -ge "${NODE_MAJOR}" ]]; then
      success "Node.js $(node --version) already installed"
      node_ok=true
    else
      warn "Node.js ${nv} too old (need ${NODE_MAJOR}+). Upgrading..."
    fi
  fi

  if [[ "${node_ok}" == "false" ]]; then
    info "Installing Node.js ${NODE_MAJOR} via NodeSource..."
    apt-get install -y -q ca-certificates gnupg > /dev/null
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - > /dev/null 2>&1
    apt-get install -y -q nodejs > /dev/null
    success "Node.js $(node --version) installed"
  fi

  # ── pnpm (via corepack) ───────────────────────────────────────────────────
  if command -v pnpm &>/dev/null; then
    local pv
    pv=$(pnpm --version 2>/dev/null)
    if [[ "${pv}" == "${PNPM_VERSION}" ]]; then
      success "pnpm ${pv} already installed"
      return 0
    fi
    info "pnpm ${pv} found, pinning to ${PNPM_VERSION}..."
  else
    info "Installing pnpm ${PNPM_VERSION} via corepack..."
  fi

  corepack enable
  corepack prepare "pnpm@${PNPM_VERSION}" --activate
  success "pnpm $(pnpm --version) installed"
}

# ── Step 4: Clone / Update Repository ────────────────────────────────────────
setup_repository() {
  header "Step 4/10 – Setting Up Repository"

  if [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "Repository already exists at ${INSTALL_DIR}. Pulling latest changes..."
    git -C "${INSTALL_DIR}" pull --ff-only
    success "Repository updated"
  else
    info "Cloning repository to ${INSTALL_DIR}..."
    git clone "${REPO_URL}" "${INSTALL_DIR}"
    success "Repository cloned"
  fi

  cd "${INSTALL_DIR}"
}

# ── Step 5: Generate .env ─────────────────────────────────────────────────────
configure_env() {
  header "Step 5/10 – Configuration"

  if [[ -f "${INSTALL_DIR}/.env" ]]; then
    echo -e "${YELLOW}A .env file already exists.${NC}"
    read -rp "Overwrite it? (y/N): " overwrite
    if [[ ! "${overwrite}" =~ ^[Yy]$ ]]; then
      success ".env kept as-is"
      return 0
    fi
  fi

  echo ""
  echo -e "${BOLD}Please provide the following configuration values.${NC}"
  echo -e "Secrets will be auto-generated where possible. Press Enter to accept defaults.\n"

  echo -e "${BOLD}--- Domain & URL ---${NC}"
  prompt DOMAIN        "Domain name (e.g. botball.yourschool.at)"
  prompt TRAEFIK_EMAIL "Admin email (for Let's Encrypt SSL notifications)"

  APP_BASE_URL="https://${DOMAIN}"
  ALLOWED_ORIGINS="https://${DOMAIN}"

  echo -e "\n${BOLD}--- Database ---${NC}"
  prompt POSTGRES_DB   "PostgreSQL database name" "botball"
  prompt POSTGRES_USER "PostgreSQL user"          "botball"
  local pg_pass_default
  pg_pass_default=$(generate_secret 16)
  prompt POSTGRES_PASSWORD "PostgreSQL password (leave empty to auto-generate)" ""
  if [[ -z "${POSTGRES_PASSWORD}" ]]; then
    POSTGRES_PASSWORD="${pg_pass_default}"
    info "Auto-generated PostgreSQL password: ${POSTGRES_PASSWORD}"
  fi
  DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}"

  echo -e "\n${BOLD}--- Email (SMTP) ---${NC}"
  echo -e "${YELLOW}Email is optional. Without it, password resets and notifications will be disabled.${NC}"
  read -rp "Configure SMTP email? (y/N): " use_smtp
  if [[ "${use_smtp}" =~ ^[Yy]$ ]]; then
    prompt SMTP_HOST     "SMTP host"          "mail.yourschool.at"
    prompt SMTP_PORT     "SMTP port"          "587"
    prompt SMTP_USER     "SMTP username / sender address"
    prompt SMTP_PASSWORD "SMTP password" "" "true"
    SMTP_FROM="BotballDashboard <${SMTP_USER}>"
    SMTP_TLS="true"

    echo ""
    read -rp "Do you have a SendGrid API key as fallback? (y/N): " use_sendgrid
    if [[ "${use_sendgrid}" =~ ^[Yy]$ ]]; then
      prompt SENDGRID_API_KEY "SendGrid API key" "" "true"
      SENDGRID_FROM="${SMTP_USER}"
    else
      SENDGRID_API_KEY=""
      SENDGRID_FROM="${SMTP_USER}"
    fi
  else
    warn "SMTP skipped – email features (password reset, notifications) will be disabled."
    SMTP_HOST=""
    SMTP_PORT="587"
    SMTP_USER=""
    SMTP_PASSWORD=""
    SMTP_FROM=""
    SMTP_TLS="false"
    SENDGRID_API_KEY=""
    SENDGRID_FROM=""
  fi

  echo -e "\n${BOLD}--- Secrets (auto-generated) ---${NC}"
  APP_SECRET_KEY=$(generate_secret 32)
  JWT_SECRET_KEY=$(generate_secret 32)
  PRINTER_CREDENTIAL_ENCRYPTION_KEY=$(generate_fernet_key)
  info "APP_SECRET_KEY              generated"
  info "JWT_SECRET_KEY              generated"
  info "PRINTER_ENCRYPTION_KEY      generated"

  # VAPID keys are generated later (step 9) via the running backend container.
  VAPID_PRIVATE_KEY="__VAPID_PLACEHOLDER__"
  VAPID_PUBLIC_KEY="__VAPID_PLACEHOLDER__"
  VAPID_ADMIN_EMAIL="${TRAEFIK_EMAIL}"

  echo -e "\n${BOLD}--- Admin Account (first login) ---${NC}"
  prompt ADMIN_EMAIL    "Admin email address"    "admin@${DOMAIN}"
  prompt ADMIN_NAME     "Admin display name"     "Administrator"
  while true; do
    prompt ADMIN_PASSWORD "Admin password (min. 8 chars)" "" "true"
    if [[ ${#ADMIN_PASSWORD} -lt 8 ]]; then
      warn "Password too short (min. 8 characters). Please try again."
    else
      break
    fi
  done

  cat > "${INSTALL_DIR}/.env" <<EOF
# Generated by proxmox-setup.sh on $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# ─────────────────────────────────────────────
# BotballDashboard – environment variables
# ─────────────────────────────────────────────

# ── Application ──────────────────────────────
APP_ENV=production
APP_SECRET_KEY=${APP_SECRET_KEY}
APP_BASE_URL=${APP_BASE_URL}
ALLOWED_ORIGINS=${ALLOWED_ORIGINS}

# ── Database ─────────────────────────────────
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
DATABASE_URL=${DATABASE_URL}

# ── Redis ────────────────────────────────────
REDIS_URL=redis://redis:6379/0

# ── JWT ──────────────────────────────────────
JWT_SECRET_KEY=${JWT_SECRET_KEY}
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# ── Email (primary SMTP) ──────────────────────
SMTP_HOST=${SMTP_HOST}
SMTP_PORT=${SMTP_PORT}
SMTP_USER=${SMTP_USER}
SMTP_PASSWORD=${SMTP_PASSWORD}
SMTP_FROM=${SMTP_FROM}
SMTP_TLS=${SMTP_TLS}

# ── Email fallback (SendGrid) ─────────────────
SENDGRID_API_KEY=${SENDGRID_API_KEY}
SENDGRID_FROM=${SENDGRID_FROM}

# ── Web Push ─────────────────────────────────
VAPID_PRIVATE_KEY=${VAPID_PRIVATE_KEY}
VAPID_PUBLIC_KEY=${VAPID_PUBLIC_KEY}
VAPID_ADMIN_EMAIL=${VAPID_ADMIN_EMAIL}

# ── 3D Print ─────────────────────────────────
PRINTER_CREDENTIAL_ENCRYPTION_KEY=${PRINTER_CREDENTIAL_ENCRYPTION_KEY}

# ── File uploads ─────────────────────────────
UPLOAD_DIR=/app/uploads
MAX_UPLOAD_SIZE_MB=20

# ── Traefik / SSL ─────────────────────────────
TRAEFIK_EMAIL=${TRAEFIK_EMAIL}
DOMAIN=${DOMAIN}
EOF

  chmod 600 "${INSTALL_DIR}/.env"
  success ".env written to ${INSTALL_DIR}/.env (permissions: 600)"
}

# ── Step 6: Create Data Directories ──────────────────────────────────────────
create_directories() {
  header "Step 6/10 – Creating Data Directories"

  mkdir -p "${DATA_DIR}/db"
  mkdir -p "${DATA_DIR}/uploads"
  mkdir -p "${DATA_DIR}/letsencrypt"

  # postgres:alpine runs as UID 70 inside the container. Pre-owning the bind-
  # mount directory to that UID lets PostgreSQL initialise without needing to
  # chown (which can fail in some container runtimes).
  if [[ -z "$(ls -A "${DATA_DIR}/db" 2>/dev/null)" ]]; then
    chown 70:70 "${DATA_DIR}/db"
    chmod 700   "${DATA_DIR}/db"
    info "Set ${DATA_DIR}/db ownership to postgres (uid 70)"
  else
    info "${DATA_DIR}/db is non-empty – preserving existing ownership"
  fi

  local acme_file="${DATA_DIR}/letsencrypt/acme.json"
  if [[ ! -f "${acme_file}" ]]; then
    touch "${acme_file}"
    chmod 600 "${acme_file}"
  fi

  success "Created: ${DATA_DIR}/db, ${DATA_DIR}/uploads, ${DATA_DIR}/letsencrypt"

  if grep -q "device: /data/db" "${INSTALL_DIR}/docker-compose.yml"; then
    success "docker-compose.yml already uses /data/db"
  else
    info "Patching docker-compose.yml to use /data/db..."
    sed -i 's|device: \./data|device: /data|g; s|device: ./data|device: /data|g' \
      "${INSTALL_DIR}/docker-compose.yml"
    success "docker-compose.yml patched to use ${DATA_DIR}/db"
  fi
}

# ── Step 7: Build Frontend on Host ────────────────────────────────────────────
# Building on the host avoids Docker's nested seccomp profile which blocks the
# socketpair() IPC call that esbuild and workbox-build use for their child
# service daemons when running inside a Docker build container on Proxmox LXC.
build_frontend() {
  header "Step 7/10 – Building Frontend (on host)"

  local frontend_dir="${INSTALL_DIR}/frontend"

  info "Installing frontend dependencies..."
  cd "${frontend_dir}"
  pnpm install --frozen-lockfile

  # Read VAPID public key from .env; use empty string if still a placeholder
  local vapid_pub=""
  if [[ -f "${INSTALL_DIR}/.env" ]]; then
    vapid_pub=$(grep -m1 '^VAPID_PUBLIC_KEY=' "${INSTALL_DIR}/.env" | cut -d= -f2-)
    if [[ "${vapid_pub}" == "__VAPID_PLACEHOLDER__" ]]; then
      vapid_pub=""
    fi
  fi

  info "Building frontend (VITE_API_URL=/api)..."
  VITE_API_URL=/api VITE_VAPID_PUBLIC_KEY="${vapid_pub}" pnpm build

  success "Frontend built → ${frontend_dir}/dist"
}

# ── Step 8: Build Docker Images ───────────────────────────────────────────────
build_images() {
  header "Step 8/10 – Building Docker Images"

  cd "${INSTALL_DIR}"

  info "Pulling base images..."
  docker compose pull --quiet traefik db redis 2>/dev/null || true

  # Frontend image just copies the pre-built dist/ into nginx (no build step).
  # Backend image is the only one that compiles code inside Docker.
  info "Building backend and frontend images..."
  docker compose build --no-cache

  success "All images built"
}

# ── Step 9: Start Services ────────────────────────────────────────────────────
start_services() {
  header "Step 9/10 – Starting Services"

  cd "${INSTALL_DIR}"

  # Remove any stale containers from previous runs (preserves volumes/data)
  info "Removing stale containers (if any)..."
  docker compose down --remove-orphans 2>/dev/null || true

  # Remove the old Docker volume registration so Compose doesn't ask
  # "volume exists but doesn't match configuration" interactively when the
  # pgdata volume driver_opts changed between runs (bind-mount ↔ named).
  # The actual data in /data/db is a bind mount and is NOT deleted by this.
  docker volume rm botballdashboard_pgdata 2>/dev/null || true

  # Start infrastructure first; bypass depends_on so the script controls ordering
  info "Starting infrastructure services (db, redis, traefik, frontend)..."
  docker compose up -d --no-deps db redis traefik frontend

  # Wait for db before even attempting to start the backend
  local pg_user
  pg_user=$(grep '^POSTGRES_USER=' .env | cut -d= -f2)

  info "Waiting for database to be healthy..."
  local retries=40
  until docker compose exec -T db pg_isready -h localhost -U "${pg_user}" -q 2>/dev/null; do
    retries=$((retries - 1))
    if [[ $retries -le 0 ]]; then
      error "Database did not become healthy in time. Logs:"
      docker compose logs db | tail -30
      die "Startup failed – see db logs above."
    fi
    sleep 3
  done
  success "Database is healthy"

  # Recovery: if the data directory was previously initialised without
  # POSTGRES_USER/POSTGRES_DB being created (e.g. from a failed run with
  # unix_socket_directories='' that prevented the init scripts from running)
  # we repair by connecting as the built-in postgres superuser which uses
  # trust auth from 127.0.0.1 regardless of POSTGRES_PASSWORD.
  local pg_db pg_pass
  pg_db=$(grep '^POSTGRES_DB=' .env | cut -d= -f2)
  pg_pass=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)

  # Ensure the application user exists
  local user_exists
  user_exists=$(docker compose exec -T db \
    psql -h localhost -U postgres -tAc \
    "SELECT 1 FROM pg_roles WHERE rolname='${pg_user}'" 2>/dev/null || true)
  if [[ "${user_exists}" != "1" ]]; then
    warn "User '${pg_user}' missing – creating..."
    docker compose exec -T db psql -h localhost -U postgres \
      -c "CREATE USER \"${pg_user}\" WITH SUPERUSER PASSWORD '${pg_pass}';" || true
    success "User '${pg_user}' created"
  fi

  # Ensure the application database exists
  local db_exists
  db_exists=$(docker compose exec -T db \
    psql -h localhost -U postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname='${pg_db}'" 2>/dev/null || true)
  if [[ "${db_exists}" != "1" ]]; then
    warn "Database '${pg_db}' missing – creating..."
    docker compose exec -T db psql -h localhost -U postgres \
      -c "CREATE DATABASE \"${pg_db}\" OWNER \"${pg_user}\";" || true
    success "Database '${pg_db}' created"
  fi

  info "Waiting for Redis..."
  local redis_retries=20
  until docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
    redis_retries=$((redis_retries - 1))
    [[ $redis_retries -le 0 ]] && { warn "Redis slow to respond – continuing"; break; }
    sleep 2
  done

  # Now start the backend (db + redis confirmed healthy)
  info "Starting backend service..."
  docker compose up -d --no-deps backend 2>&1 || true

  info "Waiting for backend API to respond..."
  local api_retries=30
  until curl -fsSL --max-time 3 "${HEALTH_URL}" > /dev/null 2>&1; do
    api_retries=$((api_retries - 1))
    if [[ $api_retries -le 0 ]]; then
      warn "Backend did not respond in time – check logs: docker compose logs backend"
      break
    fi
    sleep 3
  done
  if [[ $api_retries -gt 0 ]]; then
    success "Backend API is responding"
  fi

  success "All services started"
}

# ── Step 9b: Generate VAPID Keys + Rebuild Frontend ──────────────────────────
generate_vapid_keys() {
  info "Generating VAPID keys via backend container..."

  local vapid_out
  vapid_out=$(docker compose -f "${INSTALL_DIR}/docker-compose.yml" exec -T backend \
    python -c "
from pywebpush import Vapid
v = Vapid()
v.generate_keys()
priv = v.private_key_as_pem()
pub  = v.public_key_as_pem()
print(priv.decode().strip())
print('---')
print(pub.decode().strip())
" 2>/dev/null) || true

  if [[ -z "${vapid_out}" ]]; then
    warn "VAPID key generation failed – push notifications disabled."
    warn "Run later: cd ${INSTALL_DIR} && make vapid-keys"
    VAPID_PRIVATE_KEY=""
    VAPID_PUBLIC_KEY=""
    return
  fi

  VAPID_PRIVATE_KEY=$(echo "${vapid_out}" | awk '/^-----BEGIN/{p=1} p{print} /^-----END PRIVATE/{p=0}')
  VAPID_PUBLIC_KEY=$(echo "${vapid_out}"  | awk '/^-----BEGIN/{p=1} p{print} /^-----END PUBLIC/{p=0}')

  # Replace placeholder values in .env
  sed -i "s|VAPID_PRIVATE_KEY=__VAPID_PLACEHOLDER__|VAPID_PRIVATE_KEY=${VAPID_PRIVATE_KEY}|" \
    "${INSTALL_DIR}/.env"
  sed -i "s|VAPID_PUBLIC_KEY=__VAPID_PLACEHOLDER__|VAPID_PUBLIC_KEY=${VAPID_PUBLIC_KEY}|" \
    "${INSTALL_DIR}/.env"

  # Restart backend to pick up the new VAPID keys
  docker compose -f "${INSTALL_DIR}/docker-compose.yml" restart backend > /dev/null 2>&1

  # Rebuild the frontend with the real VAPID public key embedded, then restart nginx
  info "Rebuilding frontend with VAPID public key..."
  cd "${INSTALL_DIR}/frontend"
  VITE_API_URL=/api VITE_VAPID_PUBLIC_KEY="${VAPID_PUBLIC_KEY}" pnpm build
  docker compose -f "${INSTALL_DIR}/docker-compose.yml" build --no-cache frontend > /dev/null 2>&1
  docker compose -f "${INSTALL_DIR}/docker-compose.yml" up -d frontend > /dev/null 2>&1

  success "VAPID keys generated and frontend rebuilt with push notifications enabled"
}

# ── Step 9c: Create first Admin User ─────────────────────────────────────────
create_admin_user() {
  header "Creating Admin User"

  # ADMIN_EMAIL/PASSWORD/NAME are only set when configure_env() created a new
  # .env. If the user kept the existing .env they are unbound – skip silently.
  if [[ -z "${ADMIN_EMAIL:-}" ]]; then
    info "Existing .env kept – skipping admin user creation (already exists)."
    info "To create a new admin manually:"
    info "  cd ${INSTALL_DIR} && docker compose exec backend python scripts/create_admin.py --email you@example.com --password yourpassword"
    return 0
  fi

  info "Creating admin account: ${ADMIN_EMAIL}..."

  local output
  output=$(docker compose -f "${INSTALL_DIR}/docker-compose.yml" exec -T backend \
    python scripts/create_admin.py \
      --email    "${ADMIN_EMAIL}" \
      --password "${ADMIN_PASSWORD}" \
      --name     "${ADMIN_NAME}" 2>&1)

  if echo "${output}" | grep -q "\[OK\]"; then
    success "Admin user '${ADMIN_EMAIL}' created"
  elif echo "${output}" | grep -q "already exists"; then
    success "Admin user '${ADMIN_EMAIL}' already exists – skipped"
  else
    warn "Admin user creation returned unexpected output:"
    echo "${output}"
    warn "Create the admin user manually: cd ${INSTALL_DIR} && docker compose exec backend python scripts/create_admin.py --email admin@example.com --password yourpassword"
  fi
}

# ── Step 10: Post-install Info ────────────────────────────────────────────────
print_summary() {
  header "Step 10/10 – Setup Complete"

  # Save admin credentials before sourcing .env (they are not stored in .env)
  local _admin_email="${ADMIN_EMAIL:-}"
  local _admin_name="${ADMIN_NAME:-}"
  local _admin_password="${ADMIN_PASSWORD:-}"

  # shellcheck source=/dev/null
  source "${INSTALL_DIR}/.env"

  # Collect host IP addresses (exclude loopback and Docker bridge networks)
  local host_ips=()
  while IFS= read -r ip; do
    host_ips+=("$ip")
  done < <(ip -4 addr show scope global \
    | grep -oP '(?<=inet\s)\d+(\.\d+){3}' \
    | grep -v '^172\.' \
    | grep -v '^10\.0\.2\.' \
    || true)

  # Docker internal network of the db container
  local db_ip=""
  db_ip=$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
    botballdashboard-db-1 2>/dev/null || true)

  echo -e "${GREEN}${BOLD}BotballDashboard is up and running!${NC}"
  echo ""
  echo -e "  ${BOLD}Domain (HTTPS):${NC}  https://${DOMAIN}"
  echo -e "  ${BOLD}API / Swagger:${NC}   https://${DOMAIN}/api/docs"
  echo ""

  if [[ ${#host_ips[@]} -gt 0 ]]; then
    echo -e "  ${BOLD}Host IP(s):${NC}"
    for ip in "${host_ips[@]}"; do
      echo -e "    http://${ip}        ${YELLOW}← Traefik (redirects to HTTPS)${NC}"
      echo -e "    http://${ip}:8080   ${GREEN}← Direct nginx access (no DNS/SSL needed)${NC}"
    done
    echo ""
  fi

  if [[ -n "${db_ip}" ]]; then
    echo -e "  ${BOLD}Postgres (Docker-internal):${NC}"
    echo -e "    Host:  db  →  ${db_ip}"
    echo -e "    Port:  5432  (TCP only, Unix sockets disabled)"
    echo -e "    DB:    ${POSTGRES_DB}"
    echo -e "    User:  ${POSTGRES_USER}"
    echo ""
  fi

  echo -e "  ${BOLD}Install dir:${NC}     ${INSTALL_DIR}"
  echo -e "  ${BOLD}Data dir:${NC}        ${DATA_DIR}"
  echo ""
  echo -e "${BOLD}Useful commands:${NC}"
  echo -e "  cd ${INSTALL_DIR}"
  echo -e "  docker compose logs -f          # live logs"
  echo -e "  docker compose ps               # service status"
  echo -e "  docker compose down             # stop all"
  echo -e "  docker compose pull && docker compose up -d  # update"
  echo ""

  if [[ -z "${VAPID_PUBLIC_KEY:-}" ]]; then
    echo -e "${YELLOW}${BOLD}⚠  VAPID keys not set – push notifications disabled.${NC}"
    echo -e "   Run the following to generate them:"
    echo -e "   cd ${INSTALL_DIR} && make vapid-keys"
    echo -e "   Then add the output to ${INSTALL_DIR}/.env and restart: docker compose up -d backend"
    echo ""
  fi

  echo -e "${BOLD}First login:${NC}"
  echo -e "  URL:      http://$(echo "${host_ips[0]:-<server-ip>}"):8080"
  if [[ -n "${_admin_email}" ]]; then
    echo -e "  Name:     ${_admin_name}"
    echo -e "  Email:    ${_admin_email}"
    echo -e "  Password: ${BOLD}${_admin_password}${NC}"
  else
    echo -e "  ${YELLOW}Admin credentials: use the email/password you set during initial setup.${NC}"
  fi
  echo ""
  echo -e "${CYAN}Full documentation: https://github.com/jakobeichberger/BotballDashboard/blob/main/docs/documentation/user-manual/index.md${NC}"
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  echo ""
  echo -e "${BOLD}${BLUE}"
  echo "  ╔══════════════════════════════════════════════╗"
  echo "  ║     BotballDashboard – Proxmox Setup         ║"
  echo "  ║     One-call installer for Debian LXC        ║"
  echo "  ╚══════════════════════════════════════════════╝"
  echo -e "${NC}"

  check_prerequisites   # 1
  install_docker        # 2
  install_node          # 3  ← installs Node.js 20 + pnpm on the host
  setup_repository      # 4
  configure_env         # 5
  create_directories    # 6
  build_frontend        # 7  ← builds on host, esbuild/workbox run natively
  build_images          # 8  ← nginx image just copies dist/; backend compiled here
  start_services        # 9
  generate_vapid_keys   # 9b ← rebuilds frontend with real VAPID key
  create_admin_user     # 9c
  print_summary         # 10
}

main "$@"
