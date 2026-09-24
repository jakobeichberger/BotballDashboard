#!/bin/sh
# Creates an age-encrypted backup of the PostgreSQL database and the upload
# directory: ${BACKUP_DIR}/botball-<UTC timestamp>.tar.gz.age (+ .sha256).
#
# The archive contains:
#   database.dump         pg_dump --format=custom
#   uploads.sha256        checksum manifest of every upload file
#   app/uploads/...       the upload directory (path relative to /)
#
# Any failure exits non-zero with a "BACKUP FAILED" line on stderr and removes
# the partial archive. backup_scheduler.py turns that into an unhealthy
# container and a Prometheus signal.
set -eu

log() { echo "[backup $(date -u +%H:%M:%SZ)] $*"; }
fail() { reported=1; echo "BACKUP FAILED: $*" >&2; exit 1; }

[ -n "${AGE_RECIPIENT:-}" ] || fail "AGE_RECIPIENT is empty. Generate a key pair with age-keygen and put the public key (age1...) into .env – see docs/operations.md."
for var in POSTGRES_HOST POSTGRES_USER POSTGRES_DB POSTGRES_PASSWORD UPLOAD_DIR; do
  eval "value=\${${var}:-}"
  # shellcheck disable=SC2154 # assigned by eval above
  [ -n "$value" ] || fail "$var is not set"
done
for tool in pg_dump age tar sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || fail "required tool '$tool' is not installed"
done

backup_dir="${BACKUP_DIR:-/backups}"
retention_days="${BACKUP_RETENTION_DAYS:-30}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="${backup_dir}/botball-${timestamp}.tar.gz.age"
upload_rel="${UPLOAD_DIR#/}"
work_dir="$(mktemp -d)"

cleanup() {
  status=$?
  rm -rf "$work_dir"
  if [ "$status" -ne 0 ]; then
    rm -f "$archive" "${archive}.sha256"
    [ -n "${reported:-}" ] || echo "BACKUP FAILED: exit code $status (see messages above)" >&2
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

mkdir -p "$backup_dir" || fail "cannot create $backup_dir"
[ -d "$UPLOAD_DIR" ] || fail "upload directory $UPLOAD_DIR does not exist"

log "dumping database ${POSTGRES_DB}@${POSTGRES_HOST}"
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump --host="${POSTGRES_HOST}" \
  --port="${POSTGRES_PORT:-5432}" --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" --format=custom --file="${work_dir}/database.dump" \
  || fail "pg_dump failed"

log "writing upload manifest"
# Checksums relative to / so restore-test.sh can verify the extracted copy.
(cd / && find "$upload_rel" -type f -exec sha256sum {} +) > "${work_dir}/uploads.sha256" \
  || fail "cannot read $UPLOAD_DIR"

log "creating archive"
tar -C / -czf "${work_dir}/backup.tar.gz" "$upload_rel" \
  -C "$work_dir" database.dump uploads.sha256 \
  || fail "tar failed"

log "encrypting to $archive"
age --recipient "$AGE_RECIPIENT" --output "$archive" "${work_dir}/backup.tar.gz" \
  || fail "age encryption failed (is AGE_RECIPIENT a valid age1... public key?)"
[ -s "$archive" ] || fail "encrypted archive is empty"
(cd "$backup_dir" && sha256sum "$(basename "$archive")") > "${archive}.sha256" \
  || fail "cannot write checksum"

find "$backup_dir" -maxdepth 1 -name 'botball-*.tar.gz.age' -type f -mtime +"$retention_days" -delete
find "$backup_dir" -maxdepth 1 -name 'botball-*.tar.gz.age.sha256' -type f -mtime +"$retention_days" -delete

log "uploads: $(wc -l < "${work_dir}/uploads.sha256") files"
echo "Encrypted backup created: $archive"
