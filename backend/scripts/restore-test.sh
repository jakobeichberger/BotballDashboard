#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /backups/botball-TIMESTAMP.tar.gz.age" >&2
  exit 2
fi
: "${AGE_IDENTITY:?AGE_IDENTITY must point to the private age identity file}"
archive="$1"
restore_db="${POSTGRES_DB}_restore_test"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
sha256sum -c "${archive}.sha256"
age --decrypt --identity "$AGE_IDENTITY" --output "${work_dir}/backup.tar.gz" "$archive"
tar -xzf "${work_dir}/backup.tar.gz" -C "$work_dir"
PGPASSWORD="${POSTGRES_PASSWORD}" dropdb --if-exists --host="${POSTGRES_HOST}" \
  --port="${POSTGRES_PORT:-5432}" --username="${POSTGRES_USER}" "$restore_db"
PGPASSWORD="${POSTGRES_PASSWORD}" createdb --host="${POSTGRES_HOST}" \
  --port="${POSTGRES_PORT:-5432}" --username="${POSTGRES_USER}" "$restore_db"
PGPASSWORD="${POSTGRES_PASSWORD}" pg_restore --host="${POSTGRES_HOST}" \
  --port="${POSTGRES_PORT:-5432}" --username="${POSTGRES_USER}" \
  --dbname="$restore_db" --exit-on-error "${work_dir}/database.dump"
PGPASSWORD="${POSTGRES_PASSWORD}" psql --host="${POSTGRES_HOST}" \
  --port="${POSTGRES_PORT:-5432}" --username="${POSTGRES_USER}" \
  --dbname="$restore_db" --command='SELECT COUNT(*) AS restored_events FROM events;'
echo "Restore test succeeded in database: $restore_db"
