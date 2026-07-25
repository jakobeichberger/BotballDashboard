#!/bin/sh
set -eu

: "${AGE_RECIPIENT:?AGE_RECIPIENT must contain the backup encryption recipient}"
backup_dir="${BACKUP_DIR:-/backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
work_dir="$(mktemp -d)"
archive="${backup_dir}/botball-${timestamp}.tar.gz.age"
trap 'rm -rf "$work_dir"' EXIT
mkdir -p "$backup_dir"
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump --host="${POSTGRES_HOST}" \
  --port="${POSTGRES_PORT:-5432}" --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" --format=custom --file="${work_dir}/database.dump"
tar -C / -czf "${work_dir}/backup.tar.gz" "${UPLOAD_DIR#/}" -C "$work_dir" database.dump
age --recipient "$AGE_RECIPIENT" --output "$archive" "${work_dir}/backup.tar.gz"
sha256sum "$archive" > "${archive}.sha256"
find "$backup_dir" -name 'botball-*.tar.gz.age' -type f -mtime +30 -delete
find "$backup_dir" -name 'botball-*.tar.gz.age.sha256' -type f -mtime +30 -delete
echo "Encrypted backup created: $archive"
