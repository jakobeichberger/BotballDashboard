#!/bin/sh
# Production restore: replaces the database AND the upload directory with the
# contents of a backup archive created by backup.sh.
#
# Stop every service that writes to the database or the uploads first
# (backend, worker, beat, backup), then run – see docs/operations.md. The
# container runs as uid 10001 on a read-only root: the identity must be
# readable by that uid, and TMPDIR must point to a disk-backed directory large
# enough for the decrypted archive:
#
#   docker compose run --rm --no-deps \
#     -v /data/restore-work:/restore-work -e TMPDIR=/restore-work \
#     -e AGE_IDENTITY=/restore-work/age-identity \
#     -v <backups volume or dir>:/backups:ro \
#     backend /app/scripts/restore.sh --yes /backups/botball-TIMESTAMP.tar.gz.age
set -eu

usage() {
  echo "Usage: $0 --yes /backups/botball-TIMESTAMP.tar.gz.age" >&2
  echo "Replaces database ${POSTGRES_DB:-?} and ${UPLOAD_DIR:-/app/uploads} with the backup." >&2
  exit 2
}

[ "$#" -eq 2 ] && [ "$1" = "--yes" ] || usage
archive="$2"
: "${AGE_IDENTITY:?AGE_IDENTITY must point to the private age identity file}"
: "${POSTGRES_DB:?}" "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}" "${POSTGRES_HOST:?}"
upload_dir="${UPLOAD_DIR:-/app/uploads}"
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
  pg psql --dbname="$target_db" --quiet --no-psqlrc --set=ON_ERROR_STOP=1 \
    --file="$sql" >/dev/null || return 1
  rm -f "$sql"
}

echo "==> Verifying and decrypting $archive"
if [ -f "${archive}.sha256" ]; then
  (cd "$(dirname "$archive")" && sha256sum -c "$(basename "$archive").sha256")
fi
age --decrypt --identity "$AGE_IDENTITY" --output "${work_dir}/backup.tar.gz" "$archive"
mkdir "${work_dir}/data"
tar -xzf "${work_dir}/backup.tar.gz" -C "${work_dir}/data"
[ -f "${work_dir}/data/database.dump" ] || { echo "ERROR: archive contains no database.dump" >&2; exit 1; }
if [ -f "${work_dir}/data/uploads.sha256" ]; then
  # sha256sum -c rejects an empty manifest; a backup without uploads has one.
  if [ -s "${work_dir}/data/uploads.sha256" ]; then
    (cd "${work_dir}/data" && sha256sum --quiet -c uploads.sha256)
  fi
fi
restored_uploads="${work_dir}/data/${upload_dir#/}"
[ -d "$restored_uploads" ] || { echo "ERROR: archive has no ${upload_dir#/} directory" >&2; exit 1; }

active="$(pg psql --dbname=postgres -tAc \
  "SELECT count(*) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();")"
if [ "$active" != "0" ]; then
  echo "ERROR: ${active} open connection(s) to ${POSTGRES_DB}." >&2
  echo "Stop backend, worker, beat and backup first: docker compose stop backend worker beat backup" >&2
  exit 1
fi

echo "==> Recreating database ${POSTGRES_DB}"
pg dropdb --maintenance-db=postgres "$POSTGRES_DB"
pg createdb --maintenance-db=postgres --owner="$POSTGRES_USER" "$POSTGRES_DB"
restore_dump "$POSTGRES_DB" "${work_dir}/data/database.dump"

echo "==> Replacing uploads in ${upload_dir}"
mkdir -p "$upload_dir"
find "$upload_dir" -mindepth 1 -delete
cp -a "${restored_uploads}/." "$upload_dir/"

echo "==> Restore finished: $(find "$upload_dir" -type f | wc -l) upload files."
echo "    Start the stack again (docker compose up -d); the backend runs pending migrations on start."
