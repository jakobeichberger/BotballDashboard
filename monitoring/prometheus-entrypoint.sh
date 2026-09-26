#!/bin/sh
# Entrypoint of the prometheus service (busybox sh): writes the targets of the
# external probe (job "botball-external" in prometheus.yml) from DOMAIN, then
# starts Prometheus with the arguments from docker-compose.yml.
#
# The Blackbox exporter resolves DOMAIN to the Docker host (extra_hosts in
# docker-compose.yml), so the probe goes through the published ports, Traefik,
# its certificate and the frontend/API router exactly like a visitor's
# request, independent of DNS and NAT hairpinning. Without DOMAIN the job has
# no targets.
set -eu

targets=/prometheus/external-targets.json
if [ -n "${DOMAIN:-}" ]; then
  printf '[{"targets": ["https://%s/", "https://%s/api/system/health"]}]\n' \
    "$DOMAIN" "$DOMAIN" > "${targets}.tmp"
else
  echo "WARNING: DOMAIN is empty - no external probe of Traefik/frontend." >&2
  echo "[]" > "${targets}.tmp"
fi
mv "${targets}.tmp" "$targets"

exec /bin/prometheus "$@"
