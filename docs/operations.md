# Operations runbook

## Readiness and uptime

- Liveness: `GET /api/system/health`
- Readiness: `GET /api/system/readiness` checks PostgreSQL, Redis, and a Celery worker.
- Metrics: `GET /api/system/metrics` exposes Prometheus text metrics.
- Prometheus probes readiness through Blackbox Exporter. Alert externally when the probe fails for two minutes.

## Encrypted backups

Set `AGE_RECIPIENT` to the offline backup public key. The backup container runs `backend/scripts/backup.sh` daily and stores encrypted PostgreSQL plus upload archives in the `backups` volume. Copy that volume to separate storage.

Every month, mount the private identity as `AGE_IDENTITY` and run:

```sh
backend/scripts/restore-test.sh /backups/botball-YYYYMMDDTHHMMSSZ.tar.gz.age
```

The script restores to the isolated `${POSTGRES_DB}_restore_test` database and verifies the `events` table. It never overwrites the production database.

Start scheduled encrypted backups only with the production profile:

```sh
docker compose --profile production up -d backup prometheus blackbox
```

## Event rehearsal

Before a real event, create test teams and perform the full Admin setup → schedule → juror score → ranking → public scoreboard → paper review → print job flow. Then run the k6 test in `tests/load/event_live.js` with 30 scoring clients and 200 viewers.

The anonymized OCR reference photos are operational test data and must not be committed if they contain names, e-mail addresses or handwritten personal notes. Place the approved dataset in the protected CI fixture store and run the OCR acceptance suite before each real event; every empty, implausible or low-confidence value must remain in `review` until a human confirms it.
