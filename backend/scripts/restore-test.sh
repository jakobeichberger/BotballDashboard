#!/bin/sh
# Verifies a backup archive without touching production data:
#   1. checks the archive checksum,
#   2. decrypts it with the private age identity,
#   3. restores the database into the isolated ${POSTGRES_DB}_restore_test DB,
#   4. verifies every upload file against the manifest written by backup.sh.
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
pg pg_restore --dbname="$restore_db" --exit-on-error --no-owner "${work_dir}/data/database.dump"
pg psql --dbname="$restore_db" --command='SELECT COUNT(*) AS restored_events FROM events;'

if [ -f "${work_dir}/data/uploads.sha256" ]; then
  upload_count="$(wc -l < "${work_dir}/data/uploads.sha256")"
  (cd "${work_dir}/data" && sha256sum --quiet -c uploads.sha256)
  echo "Uploads verified: ${upload_count} files match the manifest"
else
  # Archives from before the manifest was introduced only carry the files.
  upload_count="$(find "${work_dir}/data" -path '*/uploads/*' -type f | wc -l)"
  echo "WARNING: archive has no upload manifest; found ${upload_count} upload files" >&2
fi

echo "Restore test succeeded in database: $restore_db"
