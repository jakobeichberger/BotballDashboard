#!/usr/bin/env bash
# =============================================================================
# BotballDashboard – move the database to the PostgreSQL major version of the
# compose file (docker-compose.yml, service "db")
# =============================================================================
# A new PostgreSQL major version cannot open the data files of an older one.
# This script moves the data with a dump and restore:
#
#   1. finds the old cluster in the "pgdata" volume (PostgreSQL <= 17 images
#      keep it at the top of the volume, 18+ images in <major>/docker),
#   2. stops every container that uses the volume (the application is down
#      from here on),
#   3. starts the OLD major on the old files in a temporary container without
#      network, dumps the database (pg_dump -Fc of the same major), checks the
#      dump and counts the rows of every table,
#   4. initialises the new major in a staging directory of the same volume
#      (<major>/botball-upgrade), restores the dump in one transaction,
#      compares the row counts table by table and runs ANALYZE,
#   5. only then renames the staging directory to <major>/docker, where the db
#      service finds it.
#
# The old cluster's files are left as they are (the old server is only started
# and cleanly stopped for the dump); nothing is deleted. If any step fails the
# staging directory is removed again and the old release can be started
# unchanged (see docs/documentation/installation/update.md).
#
# If the old cluster is started again after the migration (a rollback to the
# old release), its data and the migrated copy diverge. The script notices
# that (pg_control of the old cluster changed since the migration) and stops
# with a question instead of silently continuing with the older copy.
#
# Usage (from the installation directory, as a user allowed to use Docker):
#   scripts/postgres-upgrade.sh             # ask, then migrate if needed
#   scripts/postgres-upgrade.sh --yes       # no question (scripts/update.sh)
#   scripts/postgres-upgrade.sh --check     # exit 0: nothing to do, 3: migration
#                                           # needed, 4: decision needed (see above)
#   scripts/postgres-upgrade.sh --redo      # migrate the old cluster again; the
#                                           # existing new cluster is kept aside as
#                                           # <major>/docker.replaced-<time>
#   scripts/postgres-upgrade.sh --keep-new  # continue with the new cluster, ignore
#                                           # later changes in the old one
#   scripts/postgres-upgrade.sh --remove-old-data   # delete the old cluster
#                                           # after the new one has proven itself
#
# Environment:
#   PG_UPGRADE_DIR   where the dump, the row counts and a log are kept
#                    (default: <installation>/pg-upgrade, mode 700)
#   PG_UPGRADE_OLD_IMAGE  image for the old server (default: the db image with
#                    the old major, e.g. postgres:16-alpine)
#   COMPOSE_FILE / COMPOSE_PROFILES are honoured like for docker compose.
# =============================================================================
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPGRADE_DIR="${PG_UPGRADE_DIR:-${INSTALL_DIR}/pg-upgrade}"
VOLUME_ROOT=/var/lib/postgresql
MODE=migrate
ASSUME_YES=false

info()    { echo -e "\033[0;36m[INFO]\033[0m  $*"; }
success() { echo -e "\033[0;32m[OK]\033[0m    $*"; }
warn()    { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
die()     { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y) ASSUME_YES=true ;;
    --check) MODE=check ;;
    --remove-old-data) MODE=remove-old ;;
    --redo) MODE=redo ;;
    --keep-new) MODE=keep-new ;;
    -h|--help) sed -n '2,51p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

cd "${INSTALL_DIR}"

# ── Compose facts: db image, volume name, credentials ───────────────────────
compose_json="$(docker compose config --format json)" \
  || die "docker compose config failed – run from a complete checkout"
# compose_value image|volume|<db environment variable>
compose_value() {
  python3 -c '
import json, sys
c = json.load(sys.stdin)
db = c["services"]["db"]
env = db.get("environment") or {}
key = sys.argv[1]
if key == "image":
    print(db["image"])
elif key == "volume":
    print(c["volumes"]["pgdata"]["name"])
else:
    print(env.get(key) or "")
' "$1" <<<"${compose_json}"
}
NEW_IMAGE="$(compose_value image)"
VOLUME="$(compose_value volume)"
[[ -n "${NEW_IMAGE}" && -n "${VOLUME}" ]] || die "no db service / pgdata volume in the compose file"
PGUSER_NAME="$(compose_value POSTGRES_USER)"
PGUSER_NAME="${PGUSER_NAME:-postgres}"
PGDB_NAME="$(compose_value POSTGRES_DB)"
PGDB_NAME="${PGDB_NAME:-${PGUSER_NAME}}"
# Secrets and init options never go onto a command line; containers get them
# with -e NAME from this environment.
POSTGRES_PASSWORD="$(compose_value POSTGRES_PASSWORD)"
POSTGRES_INITDB_ARGS="$(compose_value POSTGRES_INITDB_ARGS)"
POSTGRES_HOST_AUTH_METHOD="$(compose_value POSTGRES_HOST_AUTH_METHOD)"
export POSTGRES_PASSWORD POSTGRES_INITDB_ARGS POSTGRES_HOST_AUTH_METHOD
export PGPASSWORD="${POSTGRES_PASSWORD}"

ensure_image() {
  docker image inspect "$1" >/dev/null 2>&1 && return 0
  info "Pulling $1..."
  docker pull --quiet "$1" >/dev/null || die "cannot pull $1"
}
ensure_image "${NEW_IMAGE}"
NEW_MAJOR="$(docker image inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${NEW_IMAGE}" \
  | sed -n 's/^PG_MAJOR=//p')"
[[ "${NEW_MAJOR}" =~ ^[0-9]+$ ]] || die "cannot read PG_MAJOR from ${NEW_IMAGE}"
# postgres:18-alpine → postgres:<old>-alpine for the old server (the image the
# installation ran so far, normally still on the host). PG_UPGRADE_OLD_IMAGE
# overrides it.
image_for_major() {
  if [[ -n "${PG_UPGRADE_OLD_IMAGE:-}" ]]; then echo "${PG_UPGRADE_OLD_IMAGE}"; return; fi
  sed -E "s/:[0-9]+(\.[0-9]+)*/:$1/" <<<"${NEW_IMAGE}"
}
NEW_DIR="${VOLUME_ROOT}/${NEW_MAJOR}/docker"
STAGING_DIR="${VOLUME_ROOT}/${NEW_MAJOR}/botball-upgrade"

# Runs a shell snippet as the postgres user in a throw-away container of the
# new image with the volume at /var/lib/postgresql (no network).
in_volume() {
  docker run --rm --network none --user postgres --entrypoint sh \
    -v "${VOLUME}:${VOLUME_ROOT}" "${NEW_IMAGE}" -c "$1"
}

# ── 1. What is in the volume? ────────────────────────────────────────────────
if ! docker volume inspect "${VOLUME}" >/dev/null 2>&1; then
  # Let compose create it with the configured driver options (bind mount on
  # Proxmox) – a plain `docker run -v` would create an empty local volume.
  docker compose create --no-recreate db >/dev/null 2>&1 || true
  if ! docker volume inspect "${VOLUME}" >/dev/null 2>&1; then
    success "No database volume yet – nothing to migrate"
    exit 0
  fi
fi

# One line per cluster: "<directory> <PG_VERSION>".
clusters="$(in_volume "
  for d in ${VOLUME_ROOT} ${VOLUME_ROOT}/*/docker; do
    [ -s \"\$d/PG_VERSION\" ] && echo \"\$d \$(cat \"\$d/PG_VERSION\")\"
  done
  exit 0")"
new_present=false
old_dir="" old_major=""
while read -r dir version; do
  [[ -n "${dir}" ]] || continue
  if [[ "${dir}" == "${NEW_DIR}" ]]; then
    new_present=true
  elif [[ "${version}" =~ ^[0-9]+$ ]] && (( version < NEW_MAJOR )); then
    if [[ -z "${old_major}" ]] || (( version > old_major )); then
      old_dir="${dir}" old_major="${version}"
    fi
  elif [[ "${version}" =~ ^[0-9]+$ ]] && (( version > NEW_MAJOR )); then
    die "the volume holds PostgreSQL ${version} data in ${dir}, newer than ${NEW_IMAGE} – downgrades are not supported"
  fi
done <<<"${clusters}"

if [[ "${MODE}" == "remove-old" ]]; then
  [[ "${new_present}" == "true" ]] || die "no PostgreSQL ${NEW_MAJOR} cluster in ${NEW_DIR} – refusing to delete anything"
  [[ -n "${old_dir}" ]] || { success "No old cluster left in volume ${VOLUME}"; exit 0; }
  warn "This permanently deletes the PostgreSQL ${old_major} cluster in ${old_dir} (volume ${VOLUME})."
  warn "After this a rollback to a release with PostgreSQL ${old_major} needs a backup."
  if [[ "${ASSUME_YES}" != "true" ]]; then
    read -rp "Type DELETE to continue: " answer
    [[ "${answer}" == "DELETE" ]] || die "aborted"
  fi
  if [[ "${old_dir}" == "${VOLUME_ROOT}" ]]; then
    # Old layout: the cluster IS the top of the volume. Keep the per-major
    # directories (18/, …) and lost+found, delete everything else.
    in_volume "cd ${VOLUME_ROOT} && find . -mindepth 1 -maxdepth 1 \
      ! -name lost+found ! -regex './[0-9][0-9]*' -exec rm -rf {} +"
  else
    in_volume "rm -rf '${old_dir%/docker}'"
  fi
  success "Old PostgreSQL ${old_major} data removed"
  exit 0
fi

# The migration records which old cluster it copied and the modification time
# of that cluster's pg_control after the dump. A different time later means the
# old server ran again (rollback) and may hold changes the copy lacks.
MARKER="${VOLUME_ROOT}/${NEW_MAJOR}/botball-upgrade.info"
pg_control_mtime() { in_volume "stat -c %Y '$1/global/pg_control'"; }
replace_new=false
if [[ "${new_present}" == "true" && -n "${old_dir}" ]]; then
  read -r rec_dir _rec_major rec_mtime rec_stamp < <(in_volume "cat '${MARKER}' 2>/dev/null; exit 0") || true
  current_mtime="$(pg_control_mtime "${old_dir}")"
  if [[ "${rec_dir:-}" == "${old_dir}" && -n "${rec_mtime:-}" && "${current_mtime}" != "${rec_mtime}" ]]; then
    case "${MODE}" in
      keep-new)
        in_volume "printf '%s %s %s %s\n' '${old_dir}' '${old_major}' '${current_mtime}' '${rec_stamp:-}' > '${MARKER}'"
        success "Continuing with the PostgreSQL ${NEW_MAJOR} data; later changes in the old cluster are ignored"
        exit 0 ;;
      redo) replace_new=true ;;
      *)
        echo -e "\033[0;31m[ERROR]\033[0m The PostgreSQL ${old_major} cluster in ${old_dir} was started again after it" >&2
        echo "  was migrated to PostgreSQL ${NEW_MAJOR} (${rec_stamp:-earlier}) – probably a rollback to the previous release." >&2
        echo "  Its data may now differ from the migrated copy in ${NEW_DIR}. Decide which one to keep:" >&2
        echo "    scripts/postgres-upgrade.sh --redo       migrate the PostgreSQL ${old_major} data again (newest if" >&2
        echo "                                             the rollback release was in use; the ${NEW_MAJOR} copy is kept aside)" >&2
        echo "    scripts/postgres-upgrade.sh --keep-new   keep the PostgreSQL ${NEW_MAJOR} data as it is" >&2
        echo "  then run scripts/update.sh again. See docs/documentation/installation/update.md." >&2
        exit 4 ;;
    esac
  fi
fi

if [[ "${new_present}" == "true" && "${replace_new}" != "true" ]]; then
  [[ "${MODE}" != "redo" ]] || [[ -z "${old_dir}" ]] || replace_new=true
fi
if [[ "${new_present}" == "true" && "${replace_new}" != "true" ]]; then
  if [[ -n "${old_dir}" ]]; then
    info "PostgreSQL ${NEW_MAJOR} is in use; the old PostgreSQL ${old_major} files are still in ${old_dir}"
    info "(rollback copy). Delete them with: scripts/postgres-upgrade.sh --remove-old-data"
  fi
  [[ "${MODE}" == "check" ]] || success "Database is on PostgreSQL ${NEW_MAJOR} – nothing to migrate"
  exit 0
fi
if [[ -z "${old_dir}" ]]; then
  [[ "${MODE}" == "check" ]] || success "No existing cluster – PostgreSQL ${NEW_MAJOR} initialises a new one"
  exit 0
fi
if [[ "${MODE}" == "check" ]]; then
  echo "PostgreSQL ${old_major} data in ${old_dir} must be migrated to ${NEW_MAJOR}"
  exit 3
fi
[[ "${MODE}" != "keep-new" ]] || die "no PostgreSQL ${NEW_MAJOR} cluster yet – nothing to keep"

OLD_IMAGE="$(image_for_major "${old_major}")"
info "Found PostgreSQL ${old_major} data in ${old_dir} (volume ${VOLUME})."
info "It will be migrated to PostgreSQL ${NEW_MAJOR} (${NEW_IMAGE}) with a dump and restore;"
info "the application is stopped meanwhile and the old files stay untouched."
if [[ "${replace_new}" == "true" ]]; then
  warn "The existing PostgreSQL ${NEW_MAJOR} cluster is replaced; it is kept as ${NEW_DIR}.replaced-<time>."
fi
if [[ "${ASSUME_YES}" != "true" ]]; then
  read -rp "Continue? (y/N): " answer
  [[ "${answer}" =~ ^[Yy]$ ]] || die "aborted – nothing was changed"
fi
ensure_image "${OLD_IMAGE}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 700 "${UPGRADE_DIR}"
dump_file="${UPGRADE_DIR}/${PGDB_NAME}-pg${old_major}-${stamp}.dump"
globals_file="${UPGRADE_DIR}/globals-pg${old_major}-${stamp}.sql"
counts_old="${UPGRADE_DIR}/rowcounts-pg${old_major}-${stamp}.txt"
counts_new="${UPGRADE_DIR}/rowcounts-pg${NEW_MAJOR}-${stamp}.txt"
OLD_CT="botball-pgupgrade-old-${stamp}"
NEW_CT="botball-pgupgrade-new-${stamp}"
committed=false

cleanup() {
  status=$?
  docker rm -f "${OLD_CT}" "${NEW_CT}" >/dev/null 2>&1 || true
  if [[ ${status} -ne 0 && "${committed}" != "true" ]]; then
    in_volume "rm -rf '${STAGING_DIR}'; rmdir '${VOLUME_ROOT}/${NEW_MAJOR}' 2>/dev/null; exit 0" \
      >/dev/null 2>&1 || true
    if [[ "${replace_new}" == "true" ]]; then
      # --redo: put the PostgreSQL <new> cluster that was set aside back.
      in_volume "if [ ! -e '${NEW_DIR}/PG_VERSION' ] && [ -d '${NEW_DIR}.replaced-${stamp}' ]; then
          rmdir '${NEW_DIR}' 2>/dev/null; mv '${NEW_DIR}.replaced-${stamp}' '${NEW_DIR}'; fi; exit 0" \
        >/dev/null 2>&1 || true
    fi
    echo >&2
    echo -e "\033[0;31m[ERROR]\033[0m PostgreSQL upgrade failed – see the messages above." >&2
    echo "  Your data is unchanged: the PostgreSQL ${old_major} files in ${old_dir}" >&2
    echo "  (volume ${VOLUME}) were not modified and the unfinished new cluster was removed." >&2
    echo "  Back to the previous release (docs/documentation/installation/update.md):" >&2
    echo "    git checkout \$(sed -n 's/^PREVIOUS_COMMIT=//p' .deploy-state) && ./scripts/update.sh --no-pull" >&2
    echo "  Or fix the cause and run: scripts/postgres-upgrade.sh" >&2
    echo "  Dump and row counts (if taken): ${UPGRADE_DIR}" >&2
  fi
  exit ${status}
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# SQL: "<schema>.<table> <exact row count>" for every table, plus the Alembic
# revision – the same text on both servers means the same data set.
count_sql="
SELECT format('%I.%I %s', table_schema, table_name,
       (xpath('/row/c/text()', query_to_xml(
          format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name),
          false, true, '')))[1]::text)
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND table_schema NOT IN ('pg_catalog', 'information_schema')
  AND table_schema NOT LIKE 'pg\\_%'
ORDER BY 1;"
revision_sql="SELECT CASE WHEN to_regclass('public.alembic_version') IS NULL THEN 'alembic_version -'
  ELSE (SELECT 'alembic_version ' || string_agg(version_num, ',' ORDER BY version_num) FROM alembic_version) END;"

# psql/pg_* inside a temporary server container, over TCP on 127.0.0.1 (the
# Unix socket is switched off: Proxmox LXC without nesting cannot create it).
pg_in() {
  local ct="$1"; shift
  docker exec -i -e PGPASSWORD "${ct}" "$@" --host=127.0.0.1 --username="${PGUSER_NAME}"
}
wait_ready() {
  local ct="$1"
  for _ in $(seq 1 90); do
    if docker exec "${ct}" pg_isready -q -h 127.0.0.1 -U "${PGUSER_NAME}" 2>/dev/null; then
      return 0
    fi
    [[ "$(docker inspect --format '{{.State.Running}}' "${ct}" 2>/dev/null)" == "true" ]] || break
    sleep 1
  done
  docker logs --tail 40 "${ct}" >&2 || true
  die "temporary PostgreSQL container ${ct} did not start"
}
stop_server() {
  # SIGINT (the images' STOPSIGNAL) = fast shutdown with a checkpoint.
  docker stop --time 300 "$1" >/dev/null
  [[ "$(docker inspect --format '{{.State.ExitCode}}' "$1")" == "0" ]] \
    || { docker logs --tail 20 "$1" >&2; die "PostgreSQL in $1 did not shut down cleanly"; }
  docker rm "$1" >/dev/null
}

# ── 2. Stop everything that uses the volume ──────────────────────────────────
info "Stopping the services that use the database..."
mapfile -t active < <(docker compose config --services)
to_stop=()
for service in backend worker worker-ocr beat backup postgres-exporter db; do
  for a in "${active[@]}"; do [[ "${a}" == "${service}" ]] && to_stop+=("${service}"); done
done
docker compose stop "${to_stop[@]}" >/dev/null
users="$(docker ps --quiet --filter "volume=${VOLUME}")"
[[ -z "${users}" ]] || die "containers still use volume ${VOLUME}: $(docker ps --filter "volume=${VOLUME}" --format '{{.Names}}' | tr '\n' ' ')– stop them first"
if [[ "${replace_new}" == "true" ]]; then
  in_volume "mv '${NEW_DIR}' '${NEW_DIR}.replaced-${stamp}'" || die "cannot move ${NEW_DIR} aside"
  info "Previous PostgreSQL ${NEW_MAJOR} cluster moved to ${NEW_DIR}.replaced-${stamp}"
fi

# Free space: the new cluster needs about as much as the old one.
old_kb="$(in_volume "du -sk '${old_dir}' | cut -f1")"
free_kb="$(in_volume "df -Pk ${VOLUME_ROOT} | awk 'NR==2 {print \$4}'")"
if [[ "${old_kb}" =~ ^[0-9]+$ && "${free_kb}" =~ ^[0-9]+$ ]] && (( free_kb < old_kb + 262144 )); then
  die "not enough space in volume ${VOLUME}: $((free_kb / 1024)) MB free, the new cluster needs about $((old_kb / 1024 + 256)) MB"
fi

# ── 3. Dump with the old major ───────────────────────────────────────────────
info "Starting PostgreSQL ${old_major} on the old files (temporary, no network)..."
if [[ "${old_dir}" == "${VOLUME_ROOT}" ]]; then
  # Old image layout: the volume is the data directory.
  old_mount="${VOLUME}:/var/lib/postgresql/data"
  old_pgdata=/var/lib/postgresql/data
else
  old_mount="${VOLUME}:${VOLUME_ROOT}"
  old_pgdata="${old_dir}"
fi
docker run -d --name "${OLD_CT}" --network none -e PGDATA="${old_pgdata}" \
  -v "${old_mount}" "${OLD_IMAGE}" \
  postgres -c listen_addresses=127.0.0.1 -c unix_socket_directories= >/dev/null
wait_ready "${OLD_CT}"

other_dbs="$(pg_in "${OLD_CT}" psql --dbname=postgres --no-psqlrc -tA -c \
  "SELECT string_agg(datname, ' ') FROM pg_database WHERE NOT datistemplate AND datname NOT IN ('postgres', '${PGDB_NAME}')")"
if [[ -n "${other_dbs}" ]]; then
  warn "Only database ${PGDB_NAME} is migrated. Also present (stay in the old cluster): ${other_dbs}"
fi

info "Dumping ${PGDB_NAME} with pg_dump ${old_major} → ${dump_file}"
( umask 077
  pg_in "${OLD_CT}" pg_dump --dbname="${PGDB_NAME}" --format=custom > "${dump_file}"
  pg_in "${OLD_CT}" pg_dumpall --globals-only --no-role-passwords > "${globals_file}" )
[[ -s "${dump_file}" ]] || die "the dump is empty"
docker exec -i "${OLD_CT}" pg_restore --list < "${dump_file}" > /dev/null \
  || die "the dump cannot be read back (pg_restore --list failed)"
( umask 077
  { pg_in "${OLD_CT}" psql --dbname="${PGDB_NAME}" --no-psqlrc -tA -v ON_ERROR_STOP=1 -c "${count_sql}"
    pg_in "${OLD_CT}" psql --dbname="${PGDB_NAME}" --no-psqlrc -tA -v ON_ERROR_STOP=1 -c "${revision_sql}"
  } > "${counts_old}" )
tables="$(grep -vc '^alembic_version ' "${counts_old}" || true)"
rows="$(awk '$1 != "alembic_version" {s += $2} END {print s + 0}' "${counts_old}")"
success "Dump written ($(du -h "${dump_file}" | cut -f1)): ${tables} tables, ${rows} rows, $(grep '^alembic_version ' "${counts_old}")"
stop_server "${OLD_CT}"
old_ctl_mtime="$(pg_control_mtime "${old_dir}")"

# ── 4. Restore into the new major (staging directory) ────────────────────────
info "Initialising PostgreSQL ${NEW_MAJOR} in ${STAGING_DIR}..."
in_volume "rm -rf '${STAGING_DIR}'"
# The image's own init functions (initdb with POSTGRES_USER/POSTGRES_PASSWORD,
# pg_hba.conf), without its temporary socket server and without the check
# that refuses to initialise next to old data – which is exactly our case.
docker run --rm --network none --user postgres --entrypoint bash \
  -e PGDATA="${STAGING_DIR}" -e POSTGRES_USER="${PGUSER_NAME}" -e POSTGRES_PASSWORD \
  -e POSTGRES_INITDB_ARGS -e POSTGRES_HOST_AUTH_METHOD \
  -v "${VOLUME}:${VOLUME_ROOT}" "${NEW_IMAGE}" -c '
    set -Eeo pipefail
    source /usr/local/bin/docker-entrypoint.sh
    docker_setup_env
    docker_create_db_directories
    docker_init_database_dir
    pg_setup_hba_conf postgres' > "${UPGRADE_DIR}/initdb-${stamp}.log" 2>&1 \
  || { cat "${UPGRADE_DIR}/initdb-${stamp}.log" >&2; die "initdb for PostgreSQL ${NEW_MAJOR} failed"; }

docker run -d --name "${NEW_CT}" --network none --user postgres -e PGDATA="${STAGING_DIR}" \
  -v "${VOLUME}:${VOLUME_ROOT}" "${NEW_IMAGE}" \
  postgres -c listen_addresses=127.0.0.1 -c unix_socket_directories= >/dev/null
wait_ready "${NEW_CT}"
pg_in "${NEW_CT}" psql --dbname=postgres --no-psqlrc -q -v ON_ERROR_STOP=1 \
  -v db="${PGDB_NAME}" <<<'CREATE DATABASE :"db";' \
  || die "cannot create database ${PGDB_NAME}"

info "Restoring with pg_restore ${NEW_MAJOR} (one transaction, stops at the first error)..."
# Rendered to a file first, so a pg_restore failure cannot turn into a
# silently partial restore (as in backend/scripts/restore.sh).
docker exec -i "${NEW_CT}" pg_restore --no-owner --file=/tmp/restore.sql < "${dump_file}" \
  || die "pg_restore could not read the dump"
pg_in "${NEW_CT}" psql --dbname="${PGDB_NAME}" --no-psqlrc --quiet -v ON_ERROR_STOP=1 \
  --single-transaction --file=/tmp/restore.sql >/dev/null \
  || die "restore into PostgreSQL ${NEW_MAJOR} failed"
docker exec "${NEW_CT}" rm -f /tmp/restore.sql
pg_in "${NEW_CT}" psql --dbname="${PGDB_NAME}" --no-psqlrc -q -c ANALYZE >/dev/null

( umask 077
  { pg_in "${NEW_CT}" psql --dbname="${PGDB_NAME}" --no-psqlrc -tA -v ON_ERROR_STOP=1 -c "${count_sql}"
    pg_in "${NEW_CT}" psql --dbname="${PGDB_NAME}" --no-psqlrc -tA -v ON_ERROR_STOP=1 -c "${revision_sql}"
  } > "${counts_new}" )
if ! diff -u "${counts_old}" "${counts_new}" >&2; then
  die "row counts differ between PostgreSQL ${old_major} and ${NEW_MAJOR} (diff above)"
fi
success "Verified: all ${tables} tables have the same row counts (${rows} rows), same Alembic revision"
stop_server "${NEW_CT}"

# ── 5. Commit: the db service uses <major>/docker from now on ────────────────
# A db container started before the migration leaves an empty <major>/docker
# behind (the image creates it before refusing to start); rmdir only removes
# it while empty.
in_volume "if [ -d '${NEW_DIR}' ]; then rmdir '${NEW_DIR}' || exit 1; fi
  printf '%s %s %s %s\n' '${old_dir}' '${old_major}' '${old_ctl_mtime}' '${stamp}' > '${MARKER}'
  mv '${STAGING_DIR}' '${NEW_DIR}'" \
  || die "cannot move ${STAGING_DIR} to ${NEW_DIR}"
committed=true
{
  echo "PostgreSQL ${old_major} → ${NEW_MAJOR} migration ${stamp}"
  echo "volume:        ${VOLUME}"
  echo "old cluster:   ${old_dir} (unchanged; delete with scripts/postgres-upgrade.sh --remove-old-data)"
  echo "new cluster:   ${NEW_DIR}"
  echo "dump:          ${dump_file}"
  echo "tables/rows:   ${tables}/${rows}"
} > "${UPGRADE_DIR}/upgrade-${stamp}.log"
success "PostgreSQL ${NEW_MAJOR} is ready in ${NEW_DIR}"
info "The old PostgreSQL ${old_major} files stay in ${old_dir} for a rollback; the dump is"
info "${dump_file}. Once the new version runs fine, free the space with"
info "  scripts/postgres-upgrade.sh --remove-old-data   and delete ${UPGRADE_DIR}."
