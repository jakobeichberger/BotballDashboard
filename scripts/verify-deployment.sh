#!/usr/bin/env bash
# =============================================================================
# BotballDashboard – verify a running installation
# =============================================================================
# Run on the Docker host after scripts/proxmox-setup.sh or scripts/update.sh:
#   /opt/botballdashboard/scripts/verify-deployment.sh
#
# Prints one PASS / WARN / FAIL line per check and exits 1 if any check FAILs
# (WARN = works, but something is disabled or should be looked at).
#
# Environment:
#   VERIFY_BASE_URL   default https://$DOMAIN (DOMAIN from .env, else localhost)
#   VERIFY_INSECURE   1 = skip TLS verification (automatic for localhost /
#                     *.local / *.test and an unset DOMAIN)
#   VERIFY_LOCAL      1 (default) = connect to 127.0.0.1 for $DOMAIN, so the
#                     check hits this host's Traefik regardless of DNS/NAT
#   COMPOSE_PROJECT_NAME / COMPOSE_FILE are honoured by docker compose.
# =============================================================================
set -uo pipefail

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${INSTALL_DIR}" || exit 2

passes=0
warns=0
fails=0
pass() { echo -e "\033[0;32mPASS\033[0m  $*"; passes=$((passes + 1)); }
warn() { echo -e "\033[1;33mWARN\033[0m  $*"; warns=$((warns + 1)); }
fail() { echo -e "\033[0;31mFAIL\033[0m  $*"; fails=$((fails + 1)); }

# Value of KEY from .env (handles "quoted" values written by proxmox-setup.sh).
env_value() {
  [[ -f .env ]] || return 0
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

has_service() {
  local wanted="$1" service
  for service in "${services[@]}"; do
    [[ "${service}" == "${wanted}" ]] && return 0
  done
  return 1
}

# Runs a command inside a service container, quietly.
in_service() {
  local service="$1"
  shift
  docker compose exec -T "${service}" "$@"
}

command -v docker >/dev/null || { fail "docker is not installed"; exit 1; }
command -v curl >/dev/null || { fail "curl is not installed"; exit 1; }

mapfile -t services < <(docker compose config --services 2>/dev/null)
if [[ ${#services[@]} -eq 0 ]]; then
  fail "docker compose config failed in ${INSTALL_DIR} (missing .env or invalid compose file?)"
  exit 1
fi

# ── 1. Containers running / healthy ─────────────────────────────────────────
echo "== Services (${#services[@]} in active profiles: ${services[*]})"
for service in backend worker worker-ocr beat frontend db redis traefik backup prometheus blackbox alertmanager; do
  if ! has_service "${service}"; then
    case "${service}" in
      backup) warn "backup: service not enabled (COMPOSE_PROFILES lacks \"production\") – NO BACKUPS are made" ;;
      prometheus|blackbox|alertmanager) ;;  # monitoring profile is optional
      *) fail "${service}: not defined in the compose configuration" ;;
    esac
    continue
  fi
  cid="$(docker compose ps -q "${service}" 2>/dev/null | head -n1)"
  if [[ -z "${cid}" ]]; then
    fail "${service}: no container (run: docker compose up -d)"
    continue
  fi
  read -r status health restarts < <(docker inspect --format \
    '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} {{.RestartCount}}' "${cid}")
  if [[ "${status}" != "running" ]]; then
    fail "${service}: container is ${status}"
  elif [[ "${health}" == "healthy" || "${health}" == "none" ]]; then
    pass "${service}: running (health: ${health}, restarts: ${restarts})"
  elif [[ "${health}" == "starting" ]]; then
    warn "${service}: running, healthcheck still starting"
  else
    reason="$(docker inspect --format '{{with .State.Health}}{{range .Log}}{{.Output}}{{end}}{{end}}' "${cid}" | tail -n1)"
    fail "${service}: ${health}${reason:+ – ${reason}}"
  fi
done

# ── 2. HTTP checks through Traefik ──────────────────────────────────────────
domain="$(env_value DOMAIN)"
domain="${domain:-localhost}"
base_url="${VERIFY_BASE_URL:-https://${domain}}"
curl_opts=(-sS --max-time 10)
if [[ "${VERIFY_INSECURE:-}" == "1" || "${domain}" == "localhost" || "${domain}" == *.local || "${domain}" == *.test ]]; then
  curl_opts+=(-k)
fi
if [[ "${VERIFY_LOCAL:-1}" == "1" && "${base_url}" == "https://${domain}" && "${domain}" != "localhost" ]]; then
  curl_opts+=(--resolve "${domain}:443:127.0.0.1")
fi
echo "== HTTP via ${base_url}"

http_status() { curl "${curl_opts[@]}" -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || echo 000; }

code="$(http_status "${base_url}/api/system/health")"
if [[ "${code}" == "200" ]]; then pass "/api/system/health: 200"; else fail "/api/system/health: HTTP ${code}"; fi

readiness="$(curl "${curl_opts[@]}" -w '\n%{http_code}' "${base_url}/api/system/readiness" 2>/dev/null || echo 000)"
code="$(tail -n1 <<<"${readiness}")"
if [[ "${code}" == "200" ]]; then
  pass "/api/system/readiness: 200 $(head -n1 <<<"${readiness}")"
else
  fail "/api/system/readiness: HTTP ${code} $(head -n1 <<<"${readiness}")"
fi

metrics="$(curl "${curl_opts[@]}" -w '\n%{http_code}' "${base_url}/api/system/metrics" 2>/dev/null || echo 000)"
code="$(tail -n1 <<<"${metrics}")"
if grep -q botball_http_requests_total <<<"${metrics}"; then
  fail "/api/system/metrics is publicly reachable through Traefik (HTTP ${code})"
elif [[ "${code}" == "404" ]]; then
  pass "/api/system/metrics not exposed through Traefik (404)"
else
  warn "/api/system/metrics returns HTTP ${code} (no metrics leaked, but expected 404)"
fi

check_headers() {
  local label="$1" url="$2" headers missing=()
  headers="$(curl "${curl_opts[@]}" -D - -o /dev/null "${url}" 2>/dev/null | tr -d '\r')"
  for header in Content-Security-Policy Strict-Transport-Security X-Frame-Options; do
    grep -qi "^${header}:" <<<"${headers}" || missing+=("${header}")
  done
  if [[ -z "${headers}" ]]; then
    fail "security headers on ${label}: no response"
  elif [[ ${#missing[@]} -eq 0 ]]; then
    pass "security headers on ${label}: CSP, HSTS, X-Frame-Options"
  else
    fail "security headers on ${label}: missing ${missing[*]}"
  fi
}
check_headers "/" "${base_url}/"
asset="$(curl "${curl_opts[@]}" "${base_url}/" 2>/dev/null | grep -oE '/assets/[^"]+\.js' | head -n1)"
if [[ -n "${asset}" ]]; then
  check_headers "${asset}" "${base_url}${asset}"
else
  fail "no hashed /assets/*.js found in index.html"
fi

# ── 3. Background processing ────────────────────────────────────────────────
echo "== Worker, beat, migrations"
if has_service worker && [[ -n "$(docker compose ps -q worker)" ]]; then
  # Output is captured first: `cmd | grep -q` fails under pipefail when grep
  # exits early and the producer gets SIGPIPE.
  # shellcheck disable=SC2016 # $HOSTNAME expands inside the container
  ping="$(in_service worker sh -c 'celery -A core.celery_app:celery_app inspect ping -d "celery@$HOSTNAME" --timeout 5' 2>/dev/null)"
  if grep -q pong <<<"${ping}"; then
    pass "Celery worker answers ping"
  else
    fail "Celery worker does not answer (docker compose logs worker)"
  fi
  vapid="$(env_value VAPID_PUBLIC_KEY)"
  # shellcheck disable=SC2016 # expands inside the container
  if in_service worker sh -c 'case "$VAPID_PRIVATE_KEY" in /*) test -r "$VAPID_PRIVATE_KEY";; *) test -n "$VAPID_PRIVATE_KEY";; esac' 2>/dev/null; then
    if [[ -n "${vapid}" ]]; then
      pass "VAPID private key readable in worker, public key set"
    else
      warn "VAPID private key readable in worker, but VAPID_PUBLIC_KEY is empty (push disabled in the frontend)"
    fi
  elif [[ -z "${vapid}" ]]; then
    warn "no VAPID key – push notifications disabled (make vapid-keys)"
  else
    fail "VAPID_PUBLIC_KEY is set but the private key is not readable in the worker"
  fi
else
  fail "worker is not running – push, printer polling and reminders stop"
fi

if has_service worker-ocr && [[ -n "$(docker compose ps -q worker-ocr)" ]]; then
  # shellcheck disable=SC2016 # $HOSTNAME expands inside the container
  ping="$(in_service worker-ocr sh -c 'celery -A core.celery_app:celery_app inspect ping -d "celery@$HOSTNAME" --timeout 5' 2>/dev/null)"
  if grep -q pong <<<"${ping}"; then
    pass "OCR worker answers ping"
  else
    fail "OCR worker does not answer (docker compose logs worker-ocr)"
  fi
else
  fail "worker-ocr is not running – score-sheet OCR stops"
fi

if has_service beat && [[ -n "$(docker compose ps -q beat)" ]]; then
  cmdline="$(in_service beat sh -c 'tr "\0" " " < /proc/1/cmdline' 2>/dev/null)"
  if grep -q "celery.* beat" <<<"${cmdline}"; then
    if grep -qi "beat: starting" <<<"$(docker compose logs --tail=500 beat 2>/dev/null)"; then
      pass "Celery beat running"
    else
      pass "Celery beat process running (start message already rotated out of the log)"
    fi
  else
    fail "beat container does not run celery beat"
  fi
else
  fail "beat is not running – no scheduled jobs (outbox, printer polling)"
fi

if [[ -n "$(docker compose ps -q backend 2>/dev/null)" ]]; then
  current="$(in_service backend alembic current 2>/dev/null | awk '$1 !~ /^INFO/ && NF {print $1}' | sort -u)"
  heads="$(in_service backend alembic heads 2>/dev/null | awk '$1 !~ /^INFO/ && NF {print $1}' | sort -u)"
  if [[ -z "${heads}" ]]; then
    fail "alembic heads could not be read in backend"
  elif [[ "${current}" == "${heads}" ]]; then
    pass "database migrations at head (${heads//$'\n'/, })"
  else
    fail "database at '${current:-none}', code expects '${heads//$'\n'/, }'"
  fi
fi

# ── 4. Backups ──────────────────────────────────────────────────────────────
echo "== Backups"
if has_service backup; then
  if [[ -z "$(env_value AGE_RECIPIENT)" ]]; then
    warn "AGE_RECIPIENT is empty – backups are DISABLED (every run fails). See docs/operations.md"
  elif [[ -z "$(docker compose ps -q backup)" ]]; then
    fail "backup container is not running"
  else
    result="$(in_service backup python scripts/backup_scheduler.py check 2>&1)"
    if [[ "${result}" == OK* ]]; then
      pass "last backup is fresh and succeeded"
    elif [[ "${result}" == *"no backup has run yet"* ]]; then
      warn "no backup has finished yet (first run starts with the container)"
    else
      fail "backup: ${result}"
    fi
  fi
else
  warn "backup service not enabled (COMPOSE_PROFILES=production) – NO BACKUPS"
fi

# ── 5. Monitoring (only with the "monitoring" profile) ──────────────────────
if has_service prometheus && [[ -n "$(docker compose ps -q prometheus)" ]]; then
  echo "== Monitoring"
  prom() { in_service prometheus wget -qO- "http://localhost:9090$1" 2>/dev/null; }
  targets="$(prom /api/v1/targets)"
  summary="$(python3 -c '
import json, sys
data = json.load(sys.stdin)["data"]["activeTargets"]
down = [t["labels"]["job"] + ":" + t.get("lastError", "") for t in data if t["health"] != "up"]
print(len(data), "; ".join(down))
' <<<"${targets}" 2>/dev/null)"
  count="${summary%% *}"
  down="${summary#* }"
  [[ "${down}" == "${summary}" ]] && down=""
  if [[ -z "${summary}" ]]; then
    fail "Prometheus API not reachable"
  elif [[ -z "${down}" ]]; then
    pass "Prometheus: all ${count} targets up"
  else
    fail "Prometheus targets down: ${down}"
  fi
  rules="$(prom /api/v1/rules | python3 -c '
import json, sys
groups = json.load(sys.stdin)["data"]["groups"]
rules = [r for g in groups for r in g["rules"]]
bad = [r["name"] for r in rules if r.get("health") not in ("ok", "unknown")]
firing = [r["name"] for r in rules if r.get("state") == "firing"]
print(len(rules), ",".join(bad), ",".join(firing), sep="|")
' 2>/dev/null)"
  IFS='|' read -r rule_count bad_rules firing <<<"${rules}"
  if [[ -z "${rules}" || "${rule_count:-0}" -eq 0 ]]; then
    fail "Prometheus has no alert rules loaded"
  elif [[ -n "${bad_rules}" ]]; then
    fail "alert rules with errors: ${bad_rules}"
  else
    pass "Prometheus: ${rule_count} alert rules loaded"
  fi
  [[ -n "${firing:-}" ]] && warn "alerts currently firing: ${firing}"
  probe="$(prom '/api/v1/query?query=probe_success' | python3 -c '
import json, sys
r = json.load(sys.stdin)["data"]["result"]
print(r[0]["value"][1] if r else "")
' 2>/dev/null)"
  if [[ "${probe}" == "1" ]]; then pass "Blackbox readiness probe succeeds"; else warn "Blackbox readiness probe: ${probe:-no data yet}"; fi
  if has_service alertmanager && in_service alertmanager wget -qO- http://localhost:9093/-/healthy >/dev/null 2>&1; then
    pass "Alertmanager healthy"
    if grep -q "no alert receiver configured" <<<"$(docker compose logs alertmanager 2>/dev/null)"; then
      warn "Alertmanager has no receiver (set ALERT_WEBHOOK_URL / ALERT_EMAIL_TO)"
    fi
  else
    fail "Alertmanager not healthy"
  fi
fi

echo ""
echo "Result: ${passes} passed, ${warns} warnings, ${fails} failed"
[[ ${fails} -eq 0 ]]
