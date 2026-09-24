#!/usr/bin/env bash
# =============================================================================
# BotballDashboard – Proxmox One-Call Setup Script
# =============================================================================
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/jakobeichberger/BotballDashboard/main/scripts/proxmox-setup.sh | bash
#   or locally:
#   bash scripts/proxmox-setup.sh
#
# Run it INSIDE the Debian LXC/VM that will host the stack (not on the
# Proxmox node itself).
#
# What this script does:
#   1.  Checks prerequisites (OS, root, network) and installs git/curl/python3/age
#   2.  Installs Docker + Docker Compose plugin
#   3.  Installs Node.js 20 + pnpm (needed to build the frontend on the host)
#   4.  Clones the repository (or updates if already cloned)
#   5.  Interactively generates .env with all secrets (APP/JWT secrets, DB
#       password, Fernet key, age backup key pair, compose profiles, alerts)
#   6.  Creates the data directories (/data/db, /data/backups)
#   7.  Builds the frontend on the host (esbuild/workbox run natively, no Docker)
#   8.  Builds the backend image (backend, worker, beat, backup) and wraps dist/
#       into the nginx frontend image
#   9.  Starts db/redis, repairs the DB role if needed, then starts the whole
#       stack: traefik, backend, worker, beat, frontend, backup (profile
#       "production") and optionally prometheus/blackbox/alertmanager
#       (profile "monitoring")
#   10. Generates VAPID keys, rebuilds the frontend with them
#   11. Creates the first admin user
#   12. Runs scripts/verify-deployment.sh and prints access info
#
# Updates afterwards: scripts/update.sh (git pull + rebuild + up -d).
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
REPO_BRANCH="main"
INSTALL_DIR="/opt/botballdashboard"
DATA_DIR="/data"
MIN_DOCKER_VERSION="24"
NODE_MAJOR="20"
PNPM_VERSION="10.29.3"
# Private key that decrypts the backups. It must be copied OFF this machine.
BACKUP_IDENTITY_FILE="/root/botball-backup-identity.txt"

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
    local show_pw="n"
    read -rp "  Passwort beim Tippen anzeigen? (j/N): " show_pw
    if [[ "${show_pw}" =~ ^[Jj]$ ]]; then
      read -rp "${prompt_text}: " value
    else
      read -rsp "${prompt_text}: " value
      echo ""
    fi
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
  # A Fernet key is 32 random bytes, urlsafe-base64 encoded – no need for the
  # cryptography package on the host.
  python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
}

# Value of KEY from ${INSTALL_DIR}/.env (handles JSON-quoted values).
env_value() {
  python3 - "${INSTALL_DIR}/.env" "$1" <<'PYEOF'
import json, re, sys
path, key = sys.argv[1], sys.argv[2]
try:
    lines = open(path).read().splitlines()
except FileNotFoundError:
    sys.exit(0)
for line in lines:
    m = re.match(rf"^{re.escape(key)}\s*=\s*(.*)$", line)
    if m:
        v = m.group(1).strip()
        if len(v) >= 2 and v[0] == v[-1] == '"':
            try:
                v = json.loads(v)
            except ValueError:
                v = v[1:-1]
        print(v)
        break
PYEOF
}

# Sets KEY=VALUE in ${INSTALL_DIR}/.env (JSON-quoted), replacing or appending.
set_env_value() {
  python3 - "${INSTALL_DIR}/.env" "$1" "$2" <<'PYEOF'
from pathlib import Path
import json
import sys

path, key, value = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
line_value = f"{key}={json.dumps(value)}"
lines = path.read_text().splitlines() if path.exists() else []
for index, line in enumerate(lines):
    if line.startswith(f"{key}="):
        lines[index] = line_value
        break
else:
    lines.append(line_value)
path.write_text("\n".join(lines) + "\n")
PYEOF
}

# Creates (or reuses) the age key pair for backups and prints the public key.
# Returns non-zero when age-keygen is unavailable.
ensure_backup_keypair() {
  command -v age-keygen &>/dev/null || return 1
  if [[ ! -f "${BACKUP_IDENTITY_FILE}" ]]; then
    (umask 077 && age-keygen -o "${BACKUP_IDENTITY_FILE}" 2>/dev/null) || return 1
  fi
  age-keygen -y "${BACKUP_IDENTITY_FILE}"
}

# Adds settings introduced after the first installation to a kept .env.
ensure_env_defaults() {
  local env_file="${INSTALL_DIR}/.env"
  if ! grep -q '^COMPOSE_PROFILES=' "${env_file}"; then
    set_env_value COMPOSE_PROFILES "production"
    info "Added COMPOSE_PROFILES=production to .env (enables the backup service)"
  fi
  if ! grep -q '^POSTGRES_UNIX_SOCKET_DIRECTORIES=' "${env_file}"; then
    # Installs from before this setting always ran PostgreSQL TCP-only.
    set_env_value POSTGRES_UNIX_SOCKET_DIRECTORIES ""
  fi
  if ! grep -q '^BACKUP_HOST_DIR=' "${env_file}"; then
    set_env_value BACKUP_HOST_DIR "${DATA_DIR}/backups"
  fi
  if [[ -z "$(env_value AGE_RECIPIENT)" ]]; then
    local recipient
    if recipient=$(ensure_backup_keypair); then
      set_env_value AGE_RECIPIENT "${recipient}"
      warn "Generated a backup key pair: ${BACKUP_IDENTITY_FILE} – copy it OFF this machine."
    else
      warn "AGE_RECIPIENT is empty – backups will FAIL until you set it (see docs/operations.md)."
    fi
  fi
  local name value
  for name in APP_SECRET_KEY JWT_SECRET_KEY POSTGRES_PASSWORD; do
    value=$(env_value "${name}")
    if [[ ${#value} -lt 24 ]]; then
      warn "${name} is shorter than 24 characters – the backend refuses to start in production."
    fi
  done
  local printer_key
  printer_key=$(env_value PRINTER_CREDENTIAL_ENCRYPTION_KEY)
  if ! python3 -c "import base64,sys; sys.exit(len(base64.urlsafe_b64decode(sys.argv[1])) != 32)" "${printer_key}" 2>/dev/null; then
    warn "PRINTER_CREDENTIAL_ENCRYPTION_KEY is not a valid Fernet key – the backend refuses to start in production."
    warn "Only generate a new one if no printer credentials are stored yet: make fernet-key"
  fi
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
  command -v git        &>/dev/null || pkgs+=(git)
  command -v curl       &>/dev/null || pkgs+=(curl)
  command -v python3    &>/dev/null || pkgs+=(python3)
  # age-keygen creates the backup encryption key pair (Debian 12: package "age").
  command -v age-keygen &>/dev/null || pkgs+=(age)
  if [[ ${#pkgs[@]} -gt 0 ]]; then
    info "Installing missing packages: ${pkgs[*]}..."
    if ! { apt-get update -qq && apt-get install -y -q "${pkgs[@]}" > /dev/null; }; then
      warn "Could not install all of: ${pkgs[*]}"
    fi
  fi
  if ! command -v git &>/dev/null || ! command -v python3 &>/dev/null; then
    die "git and python3 are required."
  fi
  success "git, curl, python3 available"
  if command -v age-keygen &>/dev/null; then
    success "age available (backup encryption)"
  else
    warn "age is not installed – no backup key pair can be generated here."
  fi
}

# ── Step 2: Install Docker ─────────────────────────────────────────────────────
install_docker() {
  header "Step 2/10 – Installing Docker"

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

  systemctl enable --now docker > /dev/null 2>&1

  local installed_ver
  installed_ver=$(docker version --format '{{.Server.Version}}' 2>/dev/null | cut -d. -f1)
  success "Docker ${installed_ver} installed and running"
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
    git -C "${INSTALL_DIR}" fetch origin
    git -C "${INSTALL_DIR}" checkout "${REPO_BRANCH}"
    git -C "${INSTALL_DIR}" pull origin "${REPO_BRANCH}"
    success "Repository updated (branch: ${REPO_BRANCH})"
  else
    info "Cloning repository (branch: ${REPO_BRANCH}) to ${INSTALL_DIR}..."
    git clone -b "${REPO_BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
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
      ensure_env_defaults
      success ".env kept (missing new settings added)"
      return 0
    fi
  elif [[ -f "${DATA_DIR}/db/PG_VERSION" ]]; then
    # PostgreSQL data directory exists but .env is gone → the new .env will
    # get a freshly generated password that does not match the running DB.
    # The start_services() ALTER USER step will re-synchronise the password,
    # but warn the user so they understand what is happening.
    warn "Existing PostgreSQL data found at ${DATA_DIR}/db but no .env present."
    warn "A new password will be generated and the DB password will be updated automatically."
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
  # 32 bytes → 43 characters; the backend refuses production secrets < 24 chars.
  pg_pass_default=$(generate_secret 32)
  while true; do
    prompt POSTGRES_PASSWORD "PostgreSQL password (min. 24 chars, leave empty to auto-generate)" ""
    if [[ -z "${POSTGRES_PASSWORD}" ]]; then
      POSTGRES_PASSWORD="${pg_pass_default}"
      info "Auto-generated PostgreSQL password (stored in .env)"
      break
    fi
    [[ ${#POSTGRES_PASSWORD} -ge 24 ]] && break
    warn "Too short – the backend refuses passwords under 24 characters in production."
  done

  echo -e "\n${BOLD}--- Email (SMTP) ---${NC}"
  echo -e "${YELLOW}Email is optional. Without it the dashboard sends no e-mails (e.g. account notifications, alert mails).${NC}"
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
    warn "SMTP skipped – the dashboard will not send e-mails. Configure SMTP_* in .env later if needed."
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
  info "PRINTER_ENCRYPTION_KEY      generated (Fernet)"

  echo -e "\n${BOLD}--- Backups (encrypted with age) ---${NC}"
  echo -e "Backups are encrypted with an age public key. The matching private key"
  echo -e "(identity) is needed to restore and must be stored OFF this server."
  prompt AGE_RECIPIENT "Existing age public key (age1..., leave empty to generate a new key pair)" ""
  BACKUPS_ENABLED=true
  if [[ -z "${AGE_RECIPIENT}" ]]; then
    if AGE_RECIPIENT=$(ensure_backup_keypair); then
      info "Backup key pair generated: ${BACKUP_IDENTITY_FILE}"
      warn "Copy ${BACKUP_IDENTITY_FILE} to a password manager / offline medium and"
      warn "then delete it from this server – without it backups cannot be restored."
    else
      AGE_RECIPIENT=""
      BACKUPS_ENABLED=false
      warn "age-keygen unavailable – BACKUPS ARE DISABLED. Set AGE_RECIPIENT in .env and"
      warn "add \"production\" to COMPOSE_PROFILES later (see docs/operations.md)."
    fi
  elif [[ ! "${AGE_RECIPIENT}" =~ ^age1[0-9a-z]+$ ]]; then
    die "'${AGE_RECIPIENT}' is not an age public key (age1...)."
  fi

  echo -e "\n${BOLD}--- Monitoring (optional) ---${NC}"
  echo -e "Prometheus + Alertmanager: alerts for API down, readiness, 5xx rate and failed/stale backups."
  read -rp "Enable monitoring? (y/N): " use_monitoring
  ALERT_WEBHOOK_URL=""
  ALERT_EMAIL_TO=""
  local profiles=()
  [[ "${BACKUPS_ENABLED}" == "true" ]] && profiles+=(production)
  if [[ "${use_monitoring}" =~ ^[Yy]$ ]]; then
    profiles+=(monitoring)
    prompt ALERT_WEBHOOK_URL "Alert webhook URL (e.g. https://ntfy.sh/<topic>, empty = none)" ""
    if [[ -n "${SMTP_HOST}" ]]; then
      prompt ALERT_EMAIL_TO "Alert e-mail recipient (empty = none)" ""
    fi
    if [[ -z "${ALERT_WEBHOOK_URL}" && -z "${ALERT_EMAIL_TO}" ]]; then
      warn "No alert receiver – alerts are only visible in Prometheus/Alertmanager (SSH tunnel)."
    fi
  fi
  COMPOSE_PROFILES=$(IFS=,; echo "${profiles[*]}")

  # The private key is stored in a Docker volume; only the browser public key
  # is kept in .env and embedded into the frontend build.
  VAPID_PRIVATE_KEY="/app/vapid/private_key.pem"
  VAPID_PUBLIC_KEY=""
  VAPID_ADMIN_EMAIL="${TRAEFIK_EMAIL}"

  echo -e "\n${BOLD}--- Admin Account (first login) ---${NC}"
  prompt ADMIN_EMAIL    "Admin email address"    "admin@${DOMAIN}"
  prompt ADMIN_NAME     "Admin display name"     "Administrator"
  while true; do
    prompt ADMIN_PASSWORD "Admin password (min. 8 chars)" "" "true"
    if [[ ${#ADMIN_PASSWORD} -lt 8 ]]; then
      warn "Password too short (min. 8 characters). Please try again."
      continue
    fi
    prompt ADMIN_PASSWORD_CONFIRM "Admin password (repeat)" "" "true"
    if [[ "${ADMIN_PASSWORD}" != "${ADMIN_PASSWORD_CONFIRM}" ]]; then
      warn "Passwords do not match. Please try again."
    else
      break
    fi
  done

  # Wrap password values in JSON-style double quotes so that special
  # characters (#, $, @, ", etc.) are preserved when dotenv/pydantic reads them.
  # json.dumps() adds surrounding "..." and escapes internal " and \ correctly.
  _q() { python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$1"; }

  cat > "${INSTALL_DIR}/.env" <<EOF
# Generated by proxmox-setup.sh on $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# ─────────────────────────────────────────────
# BotballDashboard – environment variables
# See .env.example for every option.
# ─────────────────────────────────────────────

# ── Compose profiles ─────────────────────────
# production = backup service, monitoring = Prometheus/Alertmanager
COMPOSE_PROFILES=${COMPOSE_PROFILES}

# ── Application ──────────────────────────────
APP_ENV=production
APP_SECRET_KEY=$(_q "${APP_SECRET_KEY}")
APP_BASE_URL=${APP_BASE_URL}
ALLOWED_ORIGINS=${ALLOWED_ORIGINS}

# ── Database ─────────────────────────────────
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=$(_q "${POSTGRES_PASSWORD}")

# TCP only: Unix sockets cannot be created in an unprivileged LXC without
# nesting. start_services() creates the role/database over TCP instead.
POSTGRES_UNIX_SOCKET_DIRECTORIES=

# pgdata bind-mount (production only – dev uses plain named volume when these are empty)
PGDATA_DRIVER_OPT_TYPE=none
PGDATA_DRIVER_OPT_O=bind
PGDATA_DRIVER_OPT_DEVICE=${DATA_DIR}/db

# ── Redis ────────────────────────────────────
REDIS_URL=redis://redis:6379/0

# ── JWT ──────────────────────────────────────
JWT_SECRET_KEY=$(_q "${JWT_SECRET_KEY}")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30
TOKEN_DENYLIST_BACKEND=redis

# ── Email (primary SMTP) ──────────────────────
SMTP_HOST=${SMTP_HOST}
SMTP_PORT=${SMTP_PORT}
SMTP_USER=${SMTP_USER}
SMTP_PASSWORD=$(_q "${SMTP_PASSWORD}")
SMTP_FROM=$(_q "${SMTP_FROM}")
SMTP_TLS=${SMTP_TLS}

# ── Email fallback (SendGrid) ─────────────────
SENDGRID_API_KEY=$(_q "${SENDGRID_API_KEY}")
SENDGRID_FROM=${SENDGRID_FROM}

# ── Web Push ─────────────────────────────────
VAPID_PRIVATE_KEY=$(_q "${VAPID_PRIVATE_KEY}")
VAPID_PUBLIC_KEY=$(_q "${VAPID_PUBLIC_KEY}")
VAPID_ADMIN_EMAIL=${VAPID_ADMIN_EMAIL}

# ── 3D Print ─────────────────────────────────
PRINTER_CREDENTIAL_ENCRYPTION_KEY=$(_q "${PRINTER_CREDENTIAL_ENCRYPTION_KEY}")

# ── File uploads ─────────────────────────────
UPLOAD_DIR=/app/uploads
MAX_UPLOAD_SIZE_MB=20
PRINT_UPLOAD_MAX_MB=100

# ── Traefik / SSL ─────────────────────────────
TRAEFIK_EMAIL=${TRAEFIK_EMAIL}
DOMAIN=${DOMAIN}

# ── Backups ──────────────────────────────────
# Private key for restores: ${BACKUP_IDENTITY_FILE} (keep a copy off-site!)
AGE_RECIPIENT=${AGE_RECIPIENT}
BACKUP_HOST_DIR=${DATA_DIR}/backups

# ── Alerts (monitoring profile) ──────────────
ALERT_WEBHOOK_URL=$(_q "${ALERT_WEBHOOK_URL}")
ALERT_EMAIL_TO=${ALERT_EMAIL_TO}
EOF

  chmod 600 "${INSTALL_DIR}/.env"
  success ".env written to ${INSTALL_DIR}/.env (permissions: 600)"
}

# ── Step 6: Create Data Directories ──────────────────────────────────────────
create_directories() {
  header "Step 6/10 – Creating Data Directories"

  mkdir -p "${DATA_DIR}/db"
  # Encrypted backup archives (BACKUP_HOST_DIR); sync this directory off-site.
  mkdir -p "${DATA_DIR}/backups"
  chmod 700 "${DATA_DIR}/backups"

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

  # Uploads, VAPID keys and Let's Encrypt certificates live in Docker named
  # volumes (uploads, vapid, letsencrypt); they are included in backups
  # (uploads) or re-creatable (certificates, VAPID via make vapid-keys).
  success "Created: ${DATA_DIR}/db, ${DATA_DIR}/backups"
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
    vapid_pub="${vapid_pub%\"}"
    vapid_pub="${vapid_pub#\"}"
  fi

  info "Building frontend (VITE_API_URL=/api)..."
  VITE_API_URL=/api VITE_VAPID_PUBLIC_KEY="${vapid_pub}" pnpm build

  success "Frontend built → ${frontend_dir}/dist"
}

# ── Step 8: Build Docker Images ───────────────────────────────────────────────
build_images() {
  header "Step 8/10 – Building Docker Images"

  cd "${INSTALL_DIR}"

  info "Pulling base images (postgres, redis, traefik, monitoring)..."
  docker compose pull --ignore-buildable --quiet 2>/dev/null || true

  # backend, worker, beat and backup all run the backend image; build every
  # one that is part of the active profiles (COMPOSE_PROFILES in .env).
  local services=() service
  for service in $(docker compose config --services); do
    case "${service}" in
      backend|worker|beat|backup) services+=("${service}") ;;
    esac
  done
  info "Building backend image for: ${services[*]}..."
  # --pull refreshes base images; fall back to cached ones if the registry is
  # unreachable or rate-limited.
  docker compose build --pull "${services[@]}" || docker compose build "${services[@]}"
  info "Building frontend image from the host-built dist/..."
  docker build --pull -f frontend/Dockerfile.prebuilt \
    -t botballdashboard-frontend:local frontend \
    || docker build -f frontend/Dockerfile.prebuilt -t botballdashboard-frontend:local frontend

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
  # Only for the bind mount – removing a plain named volume would delete data.
  if [[ "$(env_value PGDATA_DRIVER_OPT_TYPE)" == "none" ]]; then
    docker volume rm botballdashboard_pgdata 2>/dev/null || true
  fi

  # Start infrastructure first; bypass depends_on so the script controls ordering
  info "Starting infrastructure services (db, redis)..."
  docker compose up -d --no-deps db redis

  # Wait for db before even attempting to start the backend
  local pg_user
  pg_user=$(env_value POSTGRES_USER)

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
  # Use Python to parse the quoted password value from .env correctly.
  # Simple cut/grep fails when the value is JSON-quoted ("...") or contains = signs.
  pg_pass=$(python3 - <<'PYEOF'
import json, re, sys
with open(".env") as f:
    for line in f:
        m = re.match(r'^POSTGRES_PASSWORD\s*=\s*(.*)', line.rstrip('\n'))
        if m:
            v = m.group(1).strip()
            if v.startswith('"') and v.endswith('"'):
                try:
                    v = json.loads(v)
                except Exception:
                    v = v[1:-1]
            elif v.startswith("'") and v.endswith("'"):
                v = v[1:-1]
            print(v)
            sys.exit(0)
PYEOF
)

  # Helper: run psql via localhost (127.0.0.1) inside the db container.
  # The PostgreSQL Docker image generates pg_hba.conf with:
  #   host  all  all  127.0.0.1/32  trust
  # so connections from inside the container to localhost use TRUST auth –
  # no password required. This lets us repair the DB regardless of what
  # password the data directory was originally initialised with.
  _psql() { docker compose exec -T db psql -h localhost -U "${pg_user}" "$@"; }

  # Ensure the application user exists (needed when data dir was pre-existing
  # from a failed init that never created the role).
  local user_exists
  user_exists=$(_psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${pg_user}'" 2>/dev/null || true)
  if [[ "${user_exists}" != "1" ]]; then
    warn "User '${pg_user}' missing – creating..."
    _psql -c "CREATE USER \"${pg_user}\" WITH SUPERUSER PASSWORD '${pg_pass}';" 2>/dev/null || true
    success "User '${pg_user}' created"
  fi

  # ALWAYS synchronise the password to match .env.
  # If the data directory is from a previous install with a different password
  # the backend would fail to authenticate.  Trust auth (127.0.0.1) lets us
  # reset it without knowing the old password.
  info "Synchronising database password..."
  if _psql -c "ALTER USER \"${pg_user}\" WITH PASSWORD '${pg_pass}';" 2>/dev/null; then
    success "Database password synchronised"
  else
    warn "Password sync failed – check DB logs if backend cannot connect"
  fi

  # Ensure the application database exists
  local db_exists
  db_exists=$(_psql -tAc "SELECT 1 FROM pg_database WHERE datname='${pg_db}'" 2>/dev/null || true)
  if [[ "${db_exists}" != "1" ]]; then
    warn "Database '${pg_db}' missing – creating..."
    _psql -c "CREATE DATABASE \"${pg_db}\" OWNER \"${pg_user}\";" 2>/dev/null || true
    success "Database '${pg_db}' created"
  fi

  info "Waiting for Redis..."
  local redis_retries=20
  until docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
    redis_retries=$((redis_retries - 1))
    [[ $redis_retries -le 0 ]] && { warn "Redis slow to respond – continuing"; break; }
    sleep 2
  done

  # db + redis are healthy: start everything in the active profiles –
  # traefik, backend, worker, beat, frontend, backup ("production") and
  # prometheus/blackbox/alertmanager ("monitoring").
  info "Starting all services (profiles: $(env_value COMPOSE_PROFILES))..."
  docker compose up -d --remove-orphans

  info "Waiting for the backend to become healthy (up to 5 min – migrations run on first boot)..."
  if wait_for_backend 60; then
    success "Backend API is healthy"
  else
    warn "Backend is not healthy yet. Last 30 lines of backend logs:"
    docker compose logs --tail=30 backend
    warn "Setup continues – check again with: docker compose ps"
  fi

  docker compose ps
  success "Services started"
}

# Polls the backend container's healthcheck; $1 = attempts (5 s apart).
wait_for_backend() {
  local attempts="$1" state=""
  for _ in $(seq 1 "${attempts}"); do
    state=$(docker inspect --format '{{.State.Health.Status}}' \
      "$(docker compose ps -q backend)" 2>/dev/null || true)
    [[ "${state}" == "healthy" ]] && return 0
    sleep 5
  done
  return 1
}

# ── Step 9b: Generate VAPID Keys + Rebuild Frontend ──────────────────────────
generate_vapid_keys() {
  info "Generating VAPID keys via backend container..."

  local vapid_out
  cd "${INSTALL_DIR}"
  # Re-running the setup must not replace existing keys – that would silently
  # invalidate every browser push subscription.
  if [[ -n "$(env_value VAPID_PUBLIC_KEY)" ]] \
    && docker compose exec -T backend test -f /app/vapid/private_key.pem 2>/dev/null; then
    VAPID_PUBLIC_KEY=$(env_value VAPID_PUBLIC_KEY)
    success "VAPID keys already present – kept"
    return
  fi
  # `vapid --applicationServerKey` prints "Application Server Key = <key>".
  vapid_out=$(docker compose exec -T backend \
    sh -c "mkdir -p /app/vapid && cd /app/vapid && vapid --gen >/dev/null && vapid --applicationServerKey" \
    2>/dev/null | sed -n 's/^Application Server Key = *//p' | tr -d '[:space:]') || true

  if [[ -z "${vapid_out}" ]]; then
    warn "VAPID key generation failed – push notifications disabled."
    warn "Run later: cd ${INSTALL_DIR} && make vapid-keys"
    VAPID_PRIVATE_KEY=""
    VAPID_PUBLIC_KEY=""
    return
  fi

  VAPID_PUBLIC_KEY="${vapid_out}"

  python3 - "${INSTALL_DIR}/.env" "${VAPID_PUBLIC_KEY}" <<'PYEOF'
from pathlib import Path
import json
import sys

path = Path(sys.argv[1])
value = json.dumps(sys.argv[2])
lines = path.read_text().splitlines()
for index, line in enumerate(lines):
    if line.startswith("VAPID_PUBLIC_KEY="):
        lines[index] = f"VAPID_PUBLIC_KEY={value}"
        break
else:
    lines.append(f"VAPID_PUBLIC_KEY={value}")
path.write_text("\n".join(lines) + "\n")
PYEOF

  # Recreate backend + worker so they pick up VAPID_PUBLIC_KEY from .env
  # (`restart` would keep the old environment).
  (cd "${INSTALL_DIR}" && docker compose up -d backend worker > /dev/null 2>&1)

  # Rebuild the frontend with the real VAPID public key embedded, then restart nginx
  info "Rebuilding frontend with VAPID public key..."
  cd "${INSTALL_DIR}/frontend"
  VITE_API_URL=/api VITE_VAPID_PUBLIC_KEY="${VAPID_PUBLIC_KEY}" pnpm build
  docker build -f Dockerfile.prebuilt -t botballdashboard-frontend:local . > /dev/null 2>&1
  (cd "${INSTALL_DIR}" && docker compose up -d --force-recreate frontend > /dev/null 2>&1)
  cd "${INSTALL_DIR}"

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

  # Pass password via env var to avoid shell interpolation of special characters
  # (e.g. $, !, spaces) that would corrupt the value if passed as a CLI argument.
  local output
  output=$(ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
    docker compose exec -T \
      -e ADMIN_PASSWORD \
      backend \
    python scripts/create_admin.py \
      --email "${ADMIN_EMAIL}" \
      --name  "${ADMIN_NAME}" 2>&1)

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

# ── Step 9d: Verify ──────────────────────────────────────────────────────────
verify_deployment() {
  header "Verifying the installation"
  cd "${INSTALL_DIR}"
  # A fresh Let's Encrypt certificate can take a minute; a failed check here
  # does not abort the setup – rerun the script later.
  if ! ./scripts/verify-deployment.sh; then
    warn "Some checks failed (see FAIL lines). Rerun later: ${INSTALL_DIR}/scripts/verify-deployment.sh"
  fi
}

# ── Step 10: Post-install Info ────────────────────────────────────────────────
print_summary() {
  header "Step 10/10 – Setup Complete"

  # Admin credentials are not stored in .env; they only exist in this run.
  local _admin_email="${ADMIN_EMAIL:-}"
  local _admin_name="${ADMIN_NAME:-}"
  local _admin_password="${ADMIN_PASSWORD:-}"

  # Read values with env_value instead of `source .env`: sourcing would expand
  # $ and backticks inside generated passwords.
  local DOMAIN POSTGRES_DB POSTGRES_USER VAPID_PUBLIC_KEY AGE_RECIPIENT COMPOSE_PROFILES
  DOMAIN=$(env_value DOMAIN)
  POSTGRES_DB=$(env_value POSTGRES_DB)
  POSTGRES_USER=$(env_value POSTGRES_USER)
  VAPID_PUBLIC_KEY=$(env_value VAPID_PUBLIC_KEY)
  AGE_RECIPIENT=$(env_value AGE_RECIPIENT)
  COMPOSE_PROFILES=$(env_value COMPOSE_PROFILES)

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
  echo -e "  ${BOLD}API health:${NC}      https://${DOMAIN}/api/system/health"
  echo ""

  if [[ ${#host_ips[@]} -gt 0 ]]; then
    echo -e "  ${BOLD}Host IP(s):${NC}"
    for ip in "${host_ips[@]}"; do
      echo -e "    http://${ip}        ${YELLOW}← Traefik (redirects to HTTPS)${NC}"
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
  echo -e "  docker compose down             # stop all (data is kept)"
  echo -e "  ./scripts/update.sh              # update: git pull + rebuild images + up -d"
  echo -e "  ./scripts/verify-deployment.sh   # check services, TLS, headers, backups"
  echo ""

  if [[ -z "${VAPID_PUBLIC_KEY:-}" ]]; then
    echo -e "${YELLOW}${BOLD}⚠  VAPID keys not set – push notifications disabled.${NC}"
    echo -e "   Run the following to generate them:"
    echo -e "   cd ${INSTALL_DIR} && make vapid-keys"
    echo -e "   Put the printed VAPID_PUBLIC_KEY into ${INSTALL_DIR}/.env and run ./scripts/update.sh --no-pull"
    echo ""
  fi

  echo -e "${BOLD}Backups:${NC}"
  if [[ -n "${AGE_RECIPIENT}" && ",${COMPOSE_PROFILES}," == *",production,"* ]]; then
    echo -e "  Daily encrypted backups → ${DATA_DIR}/backups (status: docker compose ps backup)"
    if [[ -f "${BACKUP_IDENTITY_FILE}" ]]; then
      echo -e "  ${YELLOW}${BOLD}Private key: ${BACKUP_IDENTITY_FILE}${NC}"
      echo -e "  ${YELLOW}Copy it off this server (password manager/offline) and delete it here.${NC}"
      echo -e "  ${YELLOW}Without it no backup can be restored.${NC}"
    fi
    echo -e "  Copy ${DATA_DIR}/backups off-site regularly – see docs/operations.md."
  else
    echo -e "  ${RED}${BOLD}⚠  Backups are DISABLED${NC} (AGE_RECIPIENT or the \"production\" profile missing)."
    echo -e "  See docs/operations.md → Encrypted backups."
  fi
  if [[ ",${COMPOSE_PROFILES}," == *",monitoring,"* ]]; then
    echo -e "  Monitoring: ssh -L 9090:localhost:9090 -L 9093:localhost:9093 root@<host>"
  fi
  echo ""

  echo -e "${BOLD}First login:${NC}"
  echo -e "  URL:      https://${DOMAIN}"
  if [[ -n "${_admin_email}" ]]; then
    echo -e "  Name:     ${_admin_name}"
    echo -e "  Email:    ${_admin_email}"
    # Use printf %s so backslash sequences inside the password are never interpreted
    printf "  Password: ${BOLD}%s${NC}\n" "${_admin_password}"
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
  verify_deployment     # 9d
  print_summary         # 10
}

main "$@"
