#!/bin/sh
# Verifies a backup archive without touching production data:
#   1. checks the archive checksum,
#   2. decrypts it with the private age identity,
#   3. restores the database into the isolated ${POSTGRES_DB}_restore_test DB,
#   4. verifies every upload file against the manifest written by backup.sh.
# RESTORE_TEST_DROP_DB=1 drops the test database again after a success (the
# weekly automatic test in backup_scheduler.py does that).
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

pg() {
  tool="$1"
  shift
  PGPASSWORD="${POSTGRES_PASSWORD}" "$tool" --host="${POSTGRES_HOST}" \
    --port="${POSTGRES_PORT:-5432}" --username="${POSTGRES_USER}" "$@"
}

# pg_restore of a newer major version than the server writes settings the
# server does not know (pg_restore 17 → "SET transaction_timeout", rejected by
# PostgreSQL 16). Render the archive to SQL first, drop those lines, then load
# it with psql, stopping at the first error. Rendering to a file (not a pipe)
# keeps a pg_restore failure from turning into a silently partial restore.
# The image ships the client tools of the server major (PG_MAJOR in
# backend/Dockerfile); the filter stays as a guard for a mismatched setup.
restore_dump() {
  target_db="$1"
  dump="$2"
  sql="${work_dir}/restore.sql"
  pg_restore --no-owner --file="$sql" "$dump" || return 1
  sed -i '/^SET transaction_timeout = /d' "$sql" || return 1
  # One transaction: an error anywhere leaves the target database empty
  # instead of half restored.
  pg psql --dbname="$target_db" --quiet --no-psqlrc --set=ON_ERROR_STOP=1 \
    --single-transaction --file="$sql" >/dev/null || return 1
  rm -f "$sql"
}

if [ -f "${archive}.sha256" ]; then
  (cd "$(dirname "$archive")" && sha256sum -c "$(basename "$archive").sha256")
else
  echo "WARNING: no checksum file next to $archive – skipping checksum check" >&2
fi
age --decrypt --identity "$AGE_IDENTITY" --output "${work_dir}/backup.tar.gz" "$archive"
mkdir "${work_dir}/data"
tar -xzf "${work_dir}/backup.tar.gz" -C "${work_dir}/data"

pg dropdb --if-exists "$restore_db"
pg createdb "$restore_db"
restore_dump "$restore_db" "${work_dir}/data/database.dump"
# An archive of a database without the application schema (taken before
# the first migration) restores fine but has no events table to count.
if [ "$(pg psql --dbname="$restore_db" -tAc "SELECT to_regclass('public.events') IS NOT NULL")" = "t" ]; then
  pg psql --dbname="$restore_db" --command='SELECT COUNT(*) AS restored_events FROM events;'
else
  echo "NOTE: the archive holds no application schema (backup of an empty database)"
fi

if [ -f "${work_dir}/data/uploads.sha256" ]; then
  upload_count="$(wc -l < "${work_dir}/data/uploads.sha256")"
  # sha256sum -c rejects an empty manifest; a backup without uploads has one.
  if [ -s "${work_dir}/data/uploads.sha256" ]; then
    (cd "${work_dir}/data" && sha256sum --quiet -c uploads.sha256)
  fi
  echo "Uploads verified: ${upload_count} files match the manifest"
else
  # Archives from before the manifest was introduced only carry the files.
  upload_count="$(find "${work_dir}/data" -path '*/uploads/*' -type f | wc -l)"
  echo "WARNING: archive has no upload manifest; found ${upload_count} upload files" >&2
fi

if [ "${RESTORE_TEST_DROP_DB:-0}" = "1" ]; then
  # The scheduled test (backup_scheduler.py) does not keep the copy around.
  pg dropdb --if-exists "$restore_db"
  echo "Restore test succeeded (test database $restore_db dropped again)"
else
  echo "Restore test succeeded in database: $restore_db"
fi
