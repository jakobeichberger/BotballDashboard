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
#   1. Checks prerequisites (OS, root, network)
#   2. Installs Docker + Docker Compose plugin
#   3. Clones the repository (or updates if already cloned)
#   4. Interactively generates a .env file with all required secrets
#   5. Creates required data directories
#   6. Pulls/builds Docker images
#   7. Starts all services
#   8. Waits for health checks and prints access info
#
# Tested on: Debian 12 (Bookworm) LXC container on Proxmox VE 8
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
  # Generate a cryptographically random secret of given byte length (default 32)
  local bytes="${1:-32}"
  python3 -c "import secrets; print(secrets.token_urlsafe(${bytes}))"
}

generate_fernet_key() {
  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
}

# ── Step 1: Prerequisite Checks ───────────────────────────────────────────────
check_prerequisites() {
  header "Step 1/8 – Checking Prerequisites"

  # Root check
  if [[ $EUID -ne 0 ]]; then
    die "This script must be run as root (or via sudo)."
  fi
  success "Running as root"

  # OS check
  if [[ ! -f /etc/debian_version ]]; then
    warn "This script is optimised for Debian/Ubuntu. Proceeding anyway..."
  else
    local debian_ver
    debian_ver=$(cat /etc/debian_version)
    success "Debian/Ubuntu detected (${debian_ver})"
  fi

  # Network check
  if ! curl -fsSL --max-time 5 https://github.com > /dev/null 2>&1; then
    die "No internet access. Please check network connectivity."
  fi
  success "Internet connectivity OK"

  # Required packages: git, curl, python3
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
  header "Step 2/8 – Installing Docker"

  if command -v docker &>/dev/null; then
    local docker_ver
    docker_ver=$(docker version --format '{{.Server.Version}}' 2>/dev/null | cut -d. -f1)
    if [[ "${docker_ver:-0}" -ge "$MIN_DOCKER_VERSION" ]]; then
      success "Docker ${docker_ver} already installed"
      return 0
    else
      warn "Docker version too old (${docker_ver}). Upgrading..."
    fi
  fi

  info "Installing Docker via official install script..."
  curl -fsSL https://get.docker.com | sh

  # Enable and start Docker
  systemctl enable --now docker > /dev/null 2>&1

  # Verify
  local installed_ver
  installed_ver=$(docker version --format '{{.Server.Version}}' 2>/dev/null | cut -d. -f1)
  success "Docker ${installed_ver} installed and running"

  # Install cryptography lib for Fernet key generation
  info "Installing python3-cryptography for key generation..."
  apt-get install -y -q python3-cryptography > /dev/null 2>&1 || \
    pip3 install cryptography --quiet
  success "python3-cryptography available"
}

# ── Step 3: Clone / Update Repository ────────────────────────────────────────
setup_repository() {
  header "Step 3/8 – Setting Up Repository"

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

# ── Step 4: Generate .env ─────────────────────────────────────────────────────
configure_env() {
  header "Step 4/8 – Configuration"

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

  # ── Domain & URL ──────────────────────────────────────────────────────────
  echo -e "${BOLD}--- Domain & URL ---${NC}"
  prompt DOMAIN        "Domain name (e.g. botball.yourschool.at)"
  prompt TRAEFIK_EMAIL "Admin email (for Let's Encrypt SSL notifications)"

  APP_BASE_URL="https://${DOMAIN}"
  ALLOWED_ORIGINS="https://${DOMAIN}"

  # ── Database ──────────────────────────────────────────────────────────────
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

  # ── SMTP ──────────────────────────────────────────────────────────────────
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

  # ── Auto-generated secrets ────────────────────────────────────────────────
  echo -e "\n${BOLD}--- Secrets (auto-generated) ---${NC}"
  APP_SECRET_KEY=$(generate_secret 32)
  JWT_SECRET_KEY=$(generate_secret 32)
  PRINTER_CREDENTIAL_ENCRYPTION_KEY=$(generate_fernet_key)
  info "APP_SECRET_KEY              generated"
  info "JWT_SECRET_KEY              generated"
  info "PRINTER_ENCRYPTION_KEY      generated"

  # ── VAPID Keys – generated after Docker images are built ─────────────────
  # (stored as placeholders here; filled in by generate_vapid_keys() later)
  VAPID_PRIVATE_KEY="__VAPID_PLACEHOLDER__"
  VAPID_PUBLIC_KEY="__VAPID_PLACEHOLDER__"
  VAPID_ADMIN_EMAIL="${TRAEFIK_EMAIL}"

  # ── Admin account ─────────────────────────────────────────────────────────
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

  # ── Write .env ────────────────────────────────────────────────────────────
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

# ── Step 5: Create Data Directories ──────────────────────────────────────────
create_directories() {
  header "Step 5/8 – Creating Data Directories"

  mkdir -p "${DATA_DIR}/db"
  mkdir -p "${DATA_DIR}/uploads"
  mkdir -p "${DATA_DIR}/letsencrypt"

  # acme.json must exist with exact permissions for Traefik
  local acme_file="${DATA_DIR}/letsencrypt/acme.json"
  if [[ ! -f "${acme_file}" ]]; then
    touch "${acme_file}"
    chmod 600 "${acme_file}"
  fi

  success "Created: ${DATA_DIR}/db, ${DATA_DIR}/uploads, ${DATA_DIR}/letsencrypt"

  # Patch docker-compose.yml to use absolute /data paths (idempotent)
  if grep -q "device: /data/db" "${INSTALL_DIR}/docker-compose.yml"; then
    success "docker-compose.yml already uses /data/db"
  else
    info "Patching docker-compose.yml to use /data/db..."
    sed -i 's|device: \./data|device: /data|g; s|device: ./data|device: /data|g' \
      "${INSTALL_DIR}/docker-compose.yml"
    success "docker-compose.yml patched to use ${DATA_DIR}/db"
  fi
}

# ── Step 6: Pull / Build Images ───────────────────────────────────────────────
build_images() {
  header "Step 6/8 – Building Docker Images"

  cd "${INSTALL_DIR}"

  info "Pulling base images..."
  docker compose pull --quiet traefik db redis 2>/dev/null || true

  info "Building backend and frontend images..."
  docker compose build --no-cache

  success "All images built"
}

# ── Step 7: Start Services ────────────────────────────────────────────────────
start_services() {
  header "Step 7/8 – Starting Services"

  cd "${INSTALL_DIR}"

  docker compose up -d

  info "Waiting for database to be healthy..."
  local retries=30
  until docker compose exec -T db pg_isready -U "$(grep POSTGRES_USER .env | cut -d= -f2)" -q 2>/dev/null; do
    retries=$((retries - 1))
    if [[ $retries -le 0 ]]; then
      error "Database did not become healthy in time."
      docker compose logs db | tail -20
      die "Startup failed."
    fi
    sleep 2
  done
  success "Database is healthy"

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

# ── Step 7b: Generate VAPID Keys (via running backend container) ──────────────
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

  # Restart backend to pick up new VAPID keys
  docker compose -f "${INSTALL_DIR}/docker-compose.yml" restart backend > /dev/null 2>&1

  success "VAPID keys generated and applied"
}


# ── Step 7c: Create first Admin User ─────────────────────────────────────────
create_admin_user() {
  header "Creating Admin User"

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


# ── Step 8: Post-install Info ─────────────────────────────────────────────────
print_summary() {
  header "Step 8/8 – Setup Complete"

  # Reload .env to get domain
  # shellcheck source=/dev/null
  source "${INSTALL_DIR}/.env"

  echo -e "${GREEN}${BOLD}BotballDashboard is up and running!${NC}"
  echo ""
  echo -e "  ${BOLD}URL:${NC}           https://${DOMAIN}"
  echo -e "  ${BOLD}API / Swagger:${NC} https://${DOMAIN}/api/docs"
  echo -e "  ${BOLD}Install dir:${NC}   ${INSTALL_DIR}"
  echo -e "  ${BOLD}Data dir:${NC}      ${DATA_DIR}"
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
  echo -e "  URL:      https://${DOMAIN}"
  echo -e "  Email:    ${ADMIN_EMAIL}"
  echo -e "  Password: ${BOLD}(the password you set during setup)${NC}"
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

  check_prerequisites
  install_docker
  setup_repository
  configure_env
  create_directories
  build_images
  start_services
  generate_vapid_keys
  create_admin_user
  print_summary
}

main "$@"
