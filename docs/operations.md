# Operations runbook

## Readiness and uptime

- Liveness: `GET /api/system/health` returns `{"status": "ok", "version": …}`. It is the `backend` container healthcheck.
- Readiness: `GET /api/system/readiness` checks PostgreSQL, Redis and a Celery worker (the worker ping is cached for 15 s). It returns 200 `{"status": "ready", …}` or 503 `{"status": "not_ready", "checks": {…}}`. Like the metrics it is internal: Traefik does not route it (404 from outside); the Blackbox exporter and `verify-deployment.sh` call `backend:8000` directly. Every failed check is logged (`readiness_*_failed`).
- Metrics: `GET /api/system/metrics` exposes Prometheus text metrics on the internal network only (404 through Traefik).
- Every container has a Docker healthcheck. Beat has no ping; it touches `/tmp/celerybeat-heartbeat` whenever the broker accepts one of its tasks, and `scripts/beat_healthcheck.py` turns the container unhealthy when that is older than 2 minutes.
- `scripts/verify-deployment.sh` checks the whole installation: containers, TLS endpoints, headers, worker, beat, migrations, backups and monitoring. It prints PASS/WARN/FAIL per check and exits non-zero on any FAIL.

## Logs

- API, worker and beat log to stdout; `docker compose logs <service>` shows them. In production every line is a JSON object (`event`, `level`, `logger`, `timestamp`, plus fields), including uvicorn, SQLAlchemy and Celery messages. `APP_ENV=development` prints a readable console format instead.
- The API writes one access-log line per request (`"event": "request"` with `method`, `path`, `status`, `duration_ms`); health, readiness and metrics probes only at DEBUG.
- Every line written while a request is handled carries its `request_id`, the same value the client receives in the `X-Request-ID` response header (and may send in the request). Search for it to follow one request: `docker compose logs backend | grep '"request_id": "<id>"'`.
- `LOG_LEVEL` (`.env`) sets the level for API, worker and beat; empty means INFO in production.

## Monitoring and alerts

Enable the `monitoring` compose profile (`COMPOSE_PROFILES=production,monitoring` in `.env`, then `docker compose up -d`). Prometheus scrapes:

- the API,
- the readiness endpoint through the Blackbox exporter,
- the backup service (`backup:9101`),
- the host through `node-exporter` (disk space of every real file system, memory, load; the host's `/` is mounted read-only),
- PostgreSQL through `postgres-exporter` (connections, database size, `pg_up`).

It evaluates `monitoring/alerts.yml`:

| Alert | Fires when |
|---|---|
| `ApiDown` | the API cannot be scraped for 2 min |
| `ReadinessFailing` | readiness is not 200 for 2 min |
| `HighServerErrorRate` | more than 5 % of requests return 5xx for 5 min |
| `RedisFailOpen` | a rate limit or the token deny-list let a request through because Redis was unreachable (`botball_redis_fail_open_total`) |
| `BackupFailed` | the last backup run failed |
| `BackupOffsiteCopyFailed` | the off-site copy of the last archive failed (only with `BACKUP_OFFSITE_TARGET`) |
| `BackupStale` | the last successful backup is older than 26 h |
| `BackupNeverSucceeded` | runs were recorded but none succeeded (1 h) |
| `BackupMonitoringDown` | the backup service is unreachable for 15 min |
| `DiskSpaceLow` / `DiskSpaceCritical` | a file system has less than 15 % (10 min) / 5 % (5 min) free |
| `ExporterDown` | node-exporter or postgres-exporter is not scraped for 5 min |
| `PostgresDown` | postgres-exporter cannot connect to the database for 1 min |
| `PostgresConnectionsHigh` | more than 80 % of `max_connections` are in use for 5 min |

`monitoring/alerts.test.yml` holds unit tests for the rules: `docker run --rm -v "$PWD/monitoring:/m:ro" --entrypoint promtool prom/prometheus:v3.5.5 test rules /m/alerts.test.yml`.

Alertmanager delivers alerts to `ALERT_WEBHOOK_URL` (Alertmanager webhook JSON, e.g. an ntfy topic) and/or `ALERT_EMAIL_TO`. SMTP comes from `ALERT_SMTP_*` and falls back to `SMTP_*`. `monitoring/alertmanager/render-config.sh` renders the configuration at container start. Without a receiver, alerts are only visible in the UIs, and Alertmanager logs a warning.

Prometheus and Alertmanager listen on `127.0.0.1` only:

```sh
ssh -L 9090:localhost:9090 -L 9093:localhost:9093 root@<server>
# http://localhost:9090/alerts, http://localhost:9093
```

Run the rule unit tests after changing `alerts.yml`:

```sh
docker run --rm -v "$PWD/monitoring:/m:ro" -w /m --entrypoint promtool prom/prometheus:v2.54.1 test rules alerts.test.yml
```

## Encrypted backups

### Key

Backups are encrypted with [age](https://age-encryption.org). Create the key pair on a trusted machine. `scripts/proxmox-setup.sh` does this for you and stores the identity in `/root/botball-backup-identity.txt`.

```sh
age-keygen -o botball-backup-identity.txt   # prints "Public key: age1…"
```

Put the public key into `.env` as `AGE_RECIPIENT`. Keep the identity file off the server, in a password manager or on an offline medium, with at least two copies. Without it no backup can be restored. The server never needs it, except temporarily for a restore.

### Schedule and failure handling

With the `production` profile the `backup` service runs `backend/scripts/backup_scheduler.py`:

- Every `BACKUP_INTERVAL_SECONDS` (default 24 h) it runs `backend/scripts/backup.sh`. The script dumps PostgreSQL (`pg_dump -Fc`), archives the upload directory together with a checksum manifest (`uploads.sha256`) and encrypts the archive to `botball-<UTC>.tar.gz.age` plus a `.sha256` file. Archives older than `BACKUP_RETENTION_DAYS` (30) are deleted.
- A failed run logs `BACKUP FAILED: <reason>`, removes the partial archive and is retried after `BACKUP_RETRY_SECONDS` (1 h).
- The outcome is written to `/backups/status/last-run.json`. The container healthcheck turns **unhealthy** when the last run failed or the last success is older than `BACKUP_MAX_AGE_HOURS` (26 h). The same data is exported as `botball_backup_*` metrics, which drive the alerts above.

```sh
make backup-now      # run a backup now (exit code = result)
make backup-status   # OK / UNHEALTHY: <reason>
docker compose logs backup
```

### Off-site copy

Archives are only useful when they survive the server. Set `BACKUP_OFFSITE_TARGET` in `.env` and the backup service copies every successful archive there right after writing it. The archives are encrypted, so any storage works. `scripts/proxmox-setup.sh` asks for the target and prepares the credentials.

| `BACKUP_OFFSITE_TARGET` | Copy with | Credentials in `BACKUP_OFFSITE_CONFIG_DIR` (default `/data/backup-offsite`, mounted read-only at `/offsite-config`) |
|---|---|---|
| `rsync:backup@nas.example.org:/srv/botball-backups` | rsync over SSH | `id_ed25519` (the setup generates it and prints the public key to authorize on the target) and `known_hosts` (the setup fetches it with `ssh-keyscan`; check the fingerprint). Host keys are checked strictly. |
| `rclone:b2:botball-backups` | `rclone copy` | `rclone.conf` with the remote, created with `rclone config` on any machine |
| `/mnt/offsite` | plain file copy | none; mount the directory (NFS, USB disk) into the `backup` container, e.g. in `docker-compose.override.yml`: `services: {backup: {volumes: ["/mnt/nas:/mnt/offsite"]}}` |

After changing `.env`, run `docker compose up -d backup`, then test the whole chain with `make backup-now` (backup plus copy; exit code 1 if either fails).

Failure handling:

- A failed copy does not undo the local backup (`botball_backup_last_run_success` stays 1). It is recorded separately in the status file: `botball_backup_offsite_last_success` drops to 0, `botball_backup_offsite_consecutive_failures` counts up, the alert `BackupOffsiteCopyFailed` fires and `make backup-status` reports `UNHEALTHY: off-site copy failed (<reason>)`.
- The scheduler retries only the copy after `BACKUP_RETRY_SECONDS` (1 h), without a new backup. A manual retry: `docker compose exec backup python scripts/backup_scheduler.py offsite`.
- One copy may take `BACKUP_OFFSITE_TIMEOUT_SECONDS` (1 h).

Only new archives are copied, and nothing is deleted on the target. Set the retention there (bucket lifecycle rule, cron job on the NAS). Also check the copy regularly: count the files and verify a checksum with `sha256sum -c`.

Without `BACKUP_OFFSITE_TARGET` you can still sync by hand or from a host cron job, e.g. `rsync -a /data/backups/ backup@nas.example.org:/srv/botball-backups/`. That needs `BACKUP_HOST_DIR=/data/backups` (the Proxmox setup sets it). Without `BACKUP_HOST_DIR` the archives live in the Docker volume `<project>_backups`; `docker volume inspect botballdashboard_backups --format '{{.Mountpoint}}'` shows the path.

### Restore test (monthly)

The restore test decrypts an archive, restores it into the isolated database `${POSTGRES_DB}_restore_test`, counts the events and verifies every upload file against the manifest. It never touches production data.

The containers run as the unprivileged user `app` (uid 10001), so the identity must be readable by that uid. Copy it to a temporary directory owned by it and remove the copy afterwards:

```sh
install -d -m 700 -o 10001 -g 10001 /data/restore-work
install -m 400 -o 10001 -g 10001 /path/to/botball-backup-identity.txt /data/restore-work/age-identity
docker compose run --rm --no-deps \
  -v /data/restore-work:/restore-work -e AGE_IDENTITY=/restore-work/age-identity \
  backup /app/scripts/restore-test.sh /backups/botball-YYYYMMDDTHHMMSSZ.tar.gz.age
rm -rf /data/restore-work
```

Expected output ends with `Uploads verified: N files match the manifest` and `Restore test succeeded`. Afterwards drop the test database: `docker compose exec db dropdb -U botball botball_restore_test`.

### Restore in production

`backend/scripts/restore.sh` replaces the database **and** the upload directory with the archive content. It refuses to run while anything is still connected to the database.

```sh
cd /opt/botballdashboard
make backup-now || true                               # safety copy of the current state
docker compose stop backend worker worker-ocr beat backup   # nothing may write during the restore
# The backend runs as uid 10001 on a read-only root filesystem: give it a
# disk-backed work directory (TMPDIR) and a copy of the identity it can read.
install -d -m 700 -o 10001 -g 10001 /data/restore-work
install -m 400 -o 10001 -g 10001 /path/to/botball-backup-identity.txt /data/restore-work/age-identity
docker compose run --rm --no-deps \
  -v /data/restore-work:/restore-work -e TMPDIR=/restore-work \
  -e AGE_IDENTITY=/restore-work/age-identity \
  -v /data/backups:/backups:ro \
  backend /app/scripts/restore.sh --yes /backups/botball-YYYYMMDDTHHMMSSZ.tar.gz.age
rm -rf /data/restore-work                             # also removes the identity copy
docker compose up -d                                  # backend migrates the restored DB to the current code
./scripts/verify-deployment.sh
```

Without `BACKUP_HOST_DIR`, use the named volume instead of `/data/backups`: `-v botballdashboard_backups:/backups:ro`. Archives copied back from off-site storage can be placed in any directory and mounted the same way; they must be readable by uid 10001. The work directory needs room for the decrypted archive (about the size of the uploads plus the database dump).

The restore:

1. checks the archive checksum,
2. decrypts the archive,
3. verifies the upload manifest,
4. drops and recreates the database and restores the dump,
5. replaces the upload directory.

If the archive is from an older release, the backend applies the newer migrations on start. For an archive from a newer release, first check out and build that release (see the update guide).

## Event rehearsal

Before a real event, create test teams and run through the full flow:

1. Admin setup
2. Schedule
3. Juror score
4. Ranking
5. Public scoreboard
6. Paper review
7. Print job

Then run the k6 test in `tests/load/event_live.js` with 30 scoring clients and 200 viewers.

The anonymized OCR reference photos are operational test data. Do not commit them if they contain names, e-mail addresses or handwritten personal notes. Keep the approved dataset in the protected CI fixture store and run the OCR acceptance suite before each real event. Every empty, implausible or low-confidence value must stay in `review` until a human confirms it.
