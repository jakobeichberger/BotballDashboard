#!/bin/sh
# One-shot entrypoint of the postgres-monitor-role service (profile
# "monitoring", postgres image): creates or updates the login role that
# postgres-exporter uses, so the exporter no longer connects as the
# application's superuser (POSTGRES_USER).
#
#   - role MONITOR_ROLE (default botball_monitor): LOGIN, member of the
#     built-in pg_monitor role only (read statistics and settings), no
#     superuser, no CREATEDB/CREATEROLE, at most 3 connections;
#   - its password is generated once and kept in /secret/password (volume
#     postgres-monitor-secret), readable only by SECRET_OWNER (the exporter
#     image's user) and root; every run sets the password from that file.
#
# Runs on every `docker compose up` before postgres-exporter starts, so new
# and existing installations get the role without a manual step. Connects
# with the application's credentials (PGUSER/PGPASSWORD/PGHOST/PGDATABASE).
set -eu

role="${MONITOR_ROLE:-botball_monitor}"
secret=/secret/password
owner="${SECRET_OWNER:-65534}"

if [ ! -s "$secret" ]; then
  umask 077
  # 48 hex characters; no quoting issues anywhere.
  head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n' > "${secret}.tmp"
  # Owner: the exporter; group root, so this script (root, but without
  # DAC_OVERRIDE/FOWNER) can still read it on later runs. chmod first: once
  # the file belongs to the exporter, root may no longer change its mode.
  chmod 440 "${secret}.tmp"
  chown "${owner}:0" "${secret}.tmp"
  mv "${secret}.tmp" "$secret"
  echo "postgres-monitor-role: generated a new password for ${role}"
fi
password="$(cat "$secret")"

for _ in $(seq 1 30); do
  pg_isready -q && break
  sleep 2
done

# psql variables (:'name' / :"name") quote the values; they are interpolated
# in input read from stdin, not in -c.
psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 \
  --set=role="$role" --set=password="$password" --set=db="${PGDATABASE}" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role') \gexec
ALTER ROLE :"role" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
  NOBYPASSRLS CONNECTION LIMIT 3 PASSWORD :'password';
GRANT pg_monitor TO :"role";
GRANT CONNECT ON DATABASE :"db" TO :"role";
SQL
echo "postgres-monitor-role: ${role} is ready (pg_monitor)"
