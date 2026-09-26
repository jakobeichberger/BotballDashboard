# Operations runbook

## Readiness and uptime

- Liveness: `GET /api/system/health` returns `{"status": "ok", "version": …}`. It is the `backend` container healthcheck.
- Readiness: `GET /api/system/readiness` checks PostgreSQL, Redis and that **every Celery queue** (`default`, `periodic`, `ocr`) has a live worker. It asks all workers for their queues (`inspect active_queues`, cached for 15 s), so a dead `worker` is noticed even while `worker-ocr` answers. It returns 200 `{"status": "ready", "checks": {…}, "queues": {"default": true, "periodic": true, "ocr": true}}` or 503 `{"status": "not_ready", …}`; `checks.worker` is true only when every queue has a consumer. Like the metrics it is internal: Traefik does not route it (404 from outside); the Blackbox exporter and `verify-deployment.sh` call `backend:8000` directly. Every failed check is logged (`readiness_*_failed`).
- Metrics: `GET /api/system/metrics` exposes Prometheus text metrics on the internal network only (404 through Traefik), including `botball_celery_queue_consumers{queue}` and the beat heartbeat (`botball_beat_last_heartbeat_timestamp_seconds`, `botball_beat_heartbeat_known`).
- Every container has a Docker healthcheck. Beat has no ping; it touches `/tmp/celerybeat-heartbeat` whenever the broker accepts one of its tasks, and `scripts/beat_healthcheck.py` turns the container unhealthy when that is older than 2 minutes. Beat writes the same heartbeat to Redis (`botball:beat:heartbeat`, at most every 5 s), which the API exports for the `BeatNotRunning` alert – a container that is merely "unhealthy" alerts nobody.
- `scripts/verify-deployment.sh` checks the whole installation: containers, TLS endpoints, headers, worker, beat, migrations, backups and monitoring. It prints PASS/WARN/FAIL per check and exits non-zero on any FAIL.

## Logs

- API, worker and beat log to stdout; `docker compose logs <service>` shows them. In production every line is a JSON object (`event`, `level`, `logger`, `timestamp`, plus fields), including uvicorn, SQLAlchemy and Celery messages. `APP_ENV=development` prints a readable console format instead.
- The API writes one access-log line per request (`"event": "request"` with `method`, `path`, `status`, `duration_ms`); health, readiness and metrics probes only at DEBUG.
- Every line written while a request is handled carries its `request_id`, the same value the client receives in the `X-Request-ID` response header (and may send in the request). Search for it to follow one request: `docker compose logs backend | grep '"request_id": "<id>"'`.
- `LOG_LEVEL` (`.env`) sets the level for API, worker and beat; empty means INFO in production.

## Monitoring and alerts

Enable the `monitoring` compose profile (`COMPOSE_PROFILES=production,monitoring` in `.env`, then `docker compose up -d`). Prometheus scrapes:

- the API (including queue consumers and the beat heartbeat),
- the readiness endpoint through the Blackbox exporter,
- `https://${DOMAIN}/` and `https://${DOMAIN}/api/system/health` through the Blackbox exporter, the way a visitor reaches them: the blackbox container resolves `DOMAIN` to the Docker host (`extra_hosts: host-gateway`), so the probe goes through the published ports, Traefik, its certificate and the frontend/API routers without depending on DNS or NAT hairpinning. `monitoring/prometheus-entrypoint.sh` writes these targets from `DOMAIN` at start. The probe also yields `probe_ssl_earliest_cert_expiry`. Whether the site is reachable **from the internet** (DNS, firewall, port forwarding) is up to the external heartbeat/uptime service below,
- the backup service (`backup:9101`, backups and restore tests),
- the host through `node-exporter` (disk space of every real file system, memory, load; the host's `/` is mounted read-only),
- PostgreSQL through `postgres-exporter` (connections, database size, `pg_up`), logged in as the `pg_monitor` role `botball_monitor` (see "Hardening"),
- Prometheus and Alertmanager themselves (failed notifications).

It evaluates `monitoring/alerts.yml`:

| Alert | Fires when |
|---|---|
| `ApiDown` | the API cannot be scraped for 2 min |
| `ReadinessFailing` | readiness is not 200 for 2 min |
| `WorkerQueueDown` | a Celery queue (`default`, `periodic` → service `worker`; `ocr` → `worker-ocr`) has no consumer for 2 min |
| `BeatNotRunning` | beat has handed no task to the broker for more than 5 min, or never (5 min) |
| `SiteUnreachable` | the probe of `https://${DOMAIN}/` or `/api/system/health` through Traefik fails for 3 min |
| `TLSCertificateExpiresSoon` / `TLSCertificateExpiryCritical` | the served certificate expires in less than 14 days (1 h) / 3 days (10 min); Traefik renews 30 days ahead, so the renewal is failing |
| `Watchdog` | always firing: the dead man's switch, delivered only to `ALERT_HEARTBEAT_URL` |
| `AlertmanagerNotificationsFailing` | Alertmanager could not deliver notifications of one integration in the last 15 min |
| `HighServerErrorRate` | more than 5 % of requests return 5xx for 5 min |
| `RedisFailOpen` | a rate limit or the token deny-list let a request through because Redis was unreachable (`botball_redis_fail_open_total`) |
| `BackupFailed` | the last backup run failed |
| `BackupOffsiteCopyFailed` | the off-site copy of the last archive failed (only with `BACKUP_OFFSITE_TARGET`) |
| `BackupStale` | the last successful backup is older than `BACKUP_MAX_AGE_HOURS`, by default the backup interval + 2 h (26 h for daily backups); exported as `botball_backup_max_age_seconds`, so a longer `BACKUP_INTERVAL_SECONDS` causes no false alarms |
| `RestoreTestFailed` | the last restore test failed |
| `RestoreTestStale` | no successful restore test for two weekly runs + 1 day (automatic), or 35 days (manual only) |
| `BackupNeverSucceeded` | runs were recorded but none succeeded (1 h) |
| `BackupMonitoringDown` | the backup service is unreachable for 15 min |
| `DiskSpaceLow` / `DiskSpaceCritical` | a file system has less than 15 % (10 min) / 5 % (5 min) free |
| `ExporterDown` | node-exporter or postgres-exporter is not scraped for 5 min |
| `PostgresDown` | postgres-exporter cannot connect to the database for 1 min |
| `PostgresConnectionsHigh` | more than 80 % of `max_connections` are in use for 5 min |

`monitoring/alerts.test.yml` holds unit tests for the rules: `docker run --rm -v "$PWD/monitoring:/m:ro" --entrypoint promtool prom/prometheus:v3.15.0 test rules /m/alerts.test.yml`.

Alertmanager delivers alerts to `ALERT_WEBHOOK_URL` (Alertmanager webhook JSON, e.g. an ntfy topic) and/or `ALERT_EMAIL_TO`. SMTP comes from `ALERT_SMTP_*` and falls back to `SMTP_*`. `monitoring/alertmanager/render-config.sh` renders the configuration at container start. Without a receiver, alerts are only visible in the UIs, and Alertmanager logs a warning.

### Dead man's switch (external receiver needed)

Alerts need a running Prometheus, Alertmanager and host. If one of them dies, nothing alerts – unless something **outside** the server expects a regular sign of life. The `Watchdog` alert is always firing; Alertmanager routes it (and only it) to `ALERT_HEARTBEAT_URL` and repeats it every minute. Point that URL at an external heartbeat service that raises an alarm when the pings stop:

- [healthchecks.io](https://healthchecks.io) (hosted or self-hosted): create a check with period 1 minute and grace 5 minutes, set `ALERT_HEARTBEAT_URL=https://hc-ping.com/<uuid>`, and configure its notifications (e-mail, ntfy, Signal, …). Any HTTP POST counts as a ping.
- Uptime Kuma: a "Push" monitor with heartbeat interval 60 s; its push URL is `ALERT_HEARTBEAT_URL`.
- Anything else that accepts an HTTP POST and alerts on silence (Cronitor, Better Stack heartbeats, a monitoring server of the school).

Run the external service somewhere else than this server. Most of them can also check `https://<domain>/api/system/health` from the internet, which covers what the internal probe cannot (DNS, firewall, port forwarding). Without `ALERT_HEARTBEAT_URL`, Alertmanager logs a warning at start and `verify-deployment.sh` warns.

Prometheus and Alertmanager listen on `127.0.0.1` only:

```sh
ssh -L 9090:localhost:9090 -L 9093:localhost:9093 root@<server>
# http://localhost:9090/alerts, http://localhost:9093
```

Run the rule unit tests after changing `alerts.yml`:

```sh
docker run --rm -v "$PWD/monitoring:/m:ro" -w /m --entrypoint promtool prom/prometheus:v3.15.0 test rules alerts.test.yml
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
- The outcome is written to `/backups/status/last-run.json`. The container healthcheck turns **unhealthy** when the last run failed or the last success is older than `BACKUP_MAX_AGE_HOURS` (default: the interval in hours + 2, i.e. 26 h for daily backups). The same data is exported as `botball_backup_*` metrics (including `botball_backup_max_age_seconds`), which drive the alerts above.
- `backup.sh` reads the dump back (`pg_restore --list`) before it archives it, so a truncated dump fails the backup instead of a later restore.

```sh
make backup-now      # run a backup now (exit code = result)
docker compose exec backup python scripts/backup_scheduler.py once --verify
                     # backup + restore test of that archive (what update.sh runs)
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

### Restore test (automatic, weekly)

The restore test decrypts an archive, restores it in one transaction into the isolated database `${POSTGRES_DB}_restore_test`, counts the events and verifies every upload file against the manifest. It never touches production data.

**Automatic.** Every `BACKUP_RESTORE_TEST_INTERVAL_SECONDS` (default 604800 = weekly) the backup service restore-tests the newest archive and drops the test database again. The operator's age identity stays off the server, so the service keeps a **separate test key**: on first start it creates `/restore-test-key/identity.txt` in its own volume (`backup-restore-test-key`, owned by uid 10001, mode 600) and `backup.sh` encrypts every archive to both `AGE_RECIPIENT` and this key. The test key is never written next to the archives and never copied off-site. Only archives made after the key exists can be tested; the first test runs right after the first such backup (e.g. the verified backup of `update.sh`), not a whole interval later.

Trade-off: whoever has root on the server can decrypt the archives with the test key. That person can read the live database anyway; what the key adds is access to older archives (data deleted since) and to off-site copies *together with* server access. Off-site copies alone stay protected. If that is not acceptable, set `BACKUP_RESTORE_TEST_INTERVAL_SECONDS=0`: no test key, no second recipient, and restore tests are manual (below), expected every 35 days (`BACKUP_RESTORE_TEST_MAX_AGE_DAYS`).

The result goes to `/backups/status/restore-test.json` and the metrics `botball_restore_test_*`; the alerts `RestoreTestFailed` and `RestoreTestStale` fire on a failure or when the last success is too old (two automatic runs + 1 day, or 35 days for manual tests). `verify-deployment.sh` reports the last result. The automatic test needs free space for the decrypted archive in the backup container and room for a second copy of the database for a moment.

**Manual (with the operator's identity).** Run it through the scheduler so the result is recorded. The containers run as the unprivileged user `app` (uid 10001), so the identity must be readable by that uid. Copy it to a temporary directory owned by it and remove the copy afterwards:

```sh
install -d -m 700 -o 10001 -g 10001 /data/restore-work
install -m 400 -o 10001 -g 10001 /path/to/botball-backup-identity.txt /data/restore-work/age-identity
docker compose run --rm --no-deps \
  -v /data/restore-work:/restore-work -e AGE_IDENTITY=/restore-work/age-identity \
  backup python scripts/backup_scheduler.py restore-test /backups/botball-YYYYMMDDTHHMMSSZ.tar.gz.age
rm -rf /data/restore-work
```

Expected output ends with `Uploads verified: N files match the manifest` and `Restore test succeeded`. This also proves that the operator's identity matches `AGE_RECIPIENT`, which the automatic test cannot. A manual test keeps its database for inspection; drop it afterwards: `docker compose exec db dropdb -U botball botball_restore_test`. (`backup /app/scripts/restore-test.sh <archive>` still works but records nothing.)

### Restore in production

`backend/scripts/restore.sh` replaces the database **and** the upload directory with the archive content. It refuses to run while anything is still connected to the database (sessions of the read-only monitoring role `botball_monitor` do not count; they are ended when the database is dropped).

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
4. restores the dump into the staging database `${POSTGRES_DB}_restoring` in **one transaction** that stops at the first error; if that fails, the staging database is dropped and the production database is left exactly as it was,
5. only then drops the production database and renames the staging copy to it,
6. replaces the upload directory.

The staging copy needs room for a second copy of the database for a moment.

If the archive is from an older release, the backend applies the newer migrations on start. For an archive from a newer release, first check out and build that release (see the update guide).

Archives made while the server still ran PostgreSQL 16 restore into PostgreSQL 18 without changes: `pg_restore` reads dumps of older servers. The backend image carries the client tools of the server's major version (`PG_MAJOR` in `backend/Dockerfile`, from apt.postgresql.org), because a newer `pg_restore` writes settings an older server rejects and an older `pg_dump` refuses a newer server. Change both together.

## PostgreSQL major upgrade

A new PostgreSQL major version cannot read the data files of the previous one. When `docker-compose.yml` moves to a new major (16 → 18 in September 2026), `scripts/update.sh` calls `scripts/postgres-upgrade.sh`, which moves the data with a dump and restore. It can also be run by hand from the installation directory.

What it does:

1. Finds the old cluster in the `pgdata` volume (or `/data/db` on Proxmox). Images up to 17 keep it at the top of the volume, images from 18 on in `<major>/docker`; the volume is therefore mounted at `/var/lib/postgresql` now.
2. Stops `backend`, `worker`, `worker-ocr`, `beat`, `backup`, `postgres-exporter` and `db`, and checks that no container uses the volume any more. The application is down from here on (a few seconds for a typical event database).
3. Starts the old major (`postgres:16-alpine`) on the old files in a temporary container without network, dumps the database with `pg_dump -Fc` of the same major, reads the dump back (`pg_restore --list`) and counts the rows of every table.
4. Initialises the new major in the staging directory `18/botball-upgrade` of the same volume with the image's own init code (same user, password, locale and `pg_hba.conf` as a fresh install), restores the dump in one transaction that stops at the first error, compares the row counts of every table and the Alembic revision, and runs `ANALYZE`.
5. Only then renames the staging directory to `18/docker`, where the `db` service finds it.

Dump, row counts, the role list (`pg_dumpall --globals-only`, without passwords) and a log are kept in `pg-upgrade/` of the installation directory (`PG_UPGRADE_DIR`, mode 700). The dump is a full copy of the data (e-mail addresses, password hashes): after the successful migration it is **encrypted with age to `AGE_RECIPIENT`** (`*.dump.age`, with `age` from the host or from the backend image, no network) and the plain file is deleted. Without `AGE_RECIPIENT` it stays unencrypted (mode 600) and the script says so. `--remove-old-data` deletes the old cluster **and** the dumps (logs and row counts stay). Only the database `POSTGRES_DB` is migrated; other databases in the old cluster (e.g. `botball_restore_test`) are listed and stay behind. Free space needed in the volume: about the size of the old cluster plus 256 MB; in `PG_UPGRADE_DIR` up to the size of the old cluster (checked before the dump; set `PG_UPGRADE_DIR` to a larger disk if needed).

The old cluster's files stay where they are; the old server is only started and cleanly stopped for the dump. If a step fails, the staging directory is removed and the previous release can be started unchanged. Free the space after a few days:

```sh
scripts/postgres-upgrade.sh --remove-old-data   # asks for DELETE; removes the old cluster and the dumps;
                                                # afterwards a rollback needs a backup
```

Safety nets:

- The PostgreSQL 18 image refuses to start while old data lies in the volume and no `18/docker` exists (for example when the update is run with an older `update.sh`, or with a plain `docker compose up`). Nothing is changed; run `scripts/update.sh --no-pull` or `scripts/postgres-upgrade.sh`.
- If the old release runs again on the old cluster after the migration (rollback), the migrated copy is out of date. The `db` service then refuses to start and `postgres-upgrade.sh` asks for a decision: `--redo` migrates the old cluster again (the existing 18 cluster is kept as `18/docker.replaced-<time>`), `--keep-new` continues with the 18 data.
- `scripts/postgres-upgrade.sh --check` only reports: exit code 0 (nothing to do), 3 (migration needed) or 4 (decision needed).

Before the upgrade take a backup and, on Proxmox, a snapshot (see the update guide). The migration itself was tested with an existing PostgreSQL 16 installation (bind mount, TCP-only as on Proxmox, and a named volume): 69 tables and about 20 000 rows with identical counts, Alembic at head, logins, sequences, backup and restore test on the new server.

## Hardening of the stack

- **worker-ocr** does not read `.env`. It gets only the database, Redis, upload and log settings (`docker-compose.yml`), with `SERVICE_SCOPE=ocr`, which lets the settings start without the secrets the `ocr` queue never uses (JWT, app secret, printer key, SMTP, push). A compromised poppler/tesseract/OpenCV decode therefore cannot read those secrets. The code path is guarded by `backend/tests/unit/test_ops_hardening.py`.
- **postgres-exporter** logs in as `botball_monitor` (`POSTGRES_MONITOR_USER`), a login role that is only a member of the built-in `pg_monitor` role (no superuser, no CREATE*, at most 3 connections). The one-shot service `postgres-monitor-role` (profile `monitoring`) creates or updates it on every `docker compose up`, for new and existing installations; the generated password lives in the volume `postgres-monitor-secret`, readable only by the exporter's user. The application's superuser password no longer reaches the exporter.
- **Redis** is the Celery broker, the cache, the rate-limit store and the token deny-list in one instance. It runs with `--maxmemory ${REDIS_MAXMEMORY:-256mb} --maxmemory-policy noeviction` and a container limit `REDIS_MEM_LIMIT` (768m, room for snapshots). `noeviction` is the only policy that is safe for the broker: an eviction policy would silently drop queued tasks or revoked tokens. When the limit is reached, writes fail instead (cache misses, rate limits fail open → alert `RedisFailOpen`, task enqueueing errors in the logs). The cached payloads expire after `RANKING_CACHE_TTL_SECONDS` and the API validates cache keys, so the cache cannot grow without bound. Raise `REDIS_MAXMEMORY` together with `REDIS_MEM_LIMIT` if needed.
- **Images** carry fixed names (`${BOTBALL_IMAGE_PREFIX:-botballdashboard}-backend:local`, `-frontend:local`); `update.sh` also tags each release with its commit for rollbacks without a rebuild (see the update guide).

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
