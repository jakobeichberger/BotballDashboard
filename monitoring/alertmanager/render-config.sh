#!/bin/sh
# Entrypoint of the alertmanager service (busybox sh): renders the Alertmanager
# configuration from environment variables, then starts Alertmanager.
#
#   ALERT_WEBHOOK_URL       POST alerts as Alertmanager webhook JSON (e.g. ntfy,
#                           a chat bridge or your own endpoint)
#   ALERT_EMAIL_TO          send alert e-mails to this address (comma-separated ok)
#   ALERT_EMAIL_FROM        sender (defaults to SMTP_FROM)
#   ALERT_SMTP_SMARTHOST    host:port (defaults to SMTP_HOST:SMTP_PORT)
#   ALERT_SMTP_USER / ALERT_SMTP_PASSWORD / ALERT_SMTP_REQUIRE_TLS
#
# Without any receiver the alerts are only visible in Prometheus (:9090/alerts)
# and Alertmanager (:9093); a warning is logged at start.
set -eu

config=/tmp/alertmanager.yml

# printf, not echo: some shells' echo would interpret backslashes in values.
line() {
  printf '%s\n' "$*"
}

# YAML double-quoted scalar.
q() {
  printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"
}

smarthost="${ALERT_SMTP_SMARTHOST:-}"
if [ -z "$smarthost" ] && [ -n "${SMTP_HOST:-}" ]; then
  smarthost="${SMTP_HOST}:${SMTP_PORT:-587}"
fi

{
  line "route:"
  line "  receiver: default"
  line "  group_by: [alertname]"
  line "  group_wait: 30s"
  line "  group_interval: 5m"
  line "  repeat_interval: 4h"
  line "receivers:"
  line "  - name: default"
} > "$config"

receivers=0
if [ -n "${ALERT_WEBHOOK_URL:-}" ]; then
  {
    line "    webhook_configs:"
    line "      - url: $(q "$ALERT_WEBHOOK_URL")"
    line "        send_resolved: true"
  } >> "$config"
  receivers=$((receivers + 1))
fi

if [ -n "${ALERT_EMAIL_TO:-}" ]; then
  if [ -z "$smarthost" ] || [ -z "${ALERT_EMAIL_FROM:-}" ]; then
    echo "WARNING: ALERT_EMAIL_TO is set but no SMTP host (ALERT_SMTP_SMARTHOST/SMTP_HOST) or sender (ALERT_EMAIL_FROM/SMTP_FROM) – e-mail alerts disabled." >&2
  else
    {
      line "    email_configs:"
      line "      - to: $(q "$ALERT_EMAIL_TO")"
      line "        from: $(q "$ALERT_EMAIL_FROM")"
      line "        smarthost: $(q "$smarthost")"
      if [ -n "${ALERT_SMTP_USER:-}" ]; then
        line "        auth_username: $(q "$ALERT_SMTP_USER")"
        line "        auth_password: $(q "${ALERT_SMTP_PASSWORD:-}")"
      fi
      line "        require_tls: ${ALERT_SMTP_REQUIRE_TLS:-true}"
      line "        send_resolved: true"
    } >> "$config"
    receivers=$((receivers + 1))
  fi
fi

if [ "$receivers" -eq 0 ]; then
  echo "WARNING: no alert receiver configured (set ALERT_WEBHOOK_URL and/or ALERT_EMAIL_TO in .env). Alerts are only visible in the Prometheus/Alertmanager UI." >&2
fi

exec /bin/alertmanager --config.file="$config" --storage.path=/alertmanager "$@"
