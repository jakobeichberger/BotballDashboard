# Deployment & Betrieb

---

## Dienste (docker-compose.yml)

| Dienst | Image | Profil | Aufgabe |
|---|---|---|---|
| `traefik` | traefik:v3.7 | – | Reverse Proxy, HTTP→HTTPS, Let's Encrypt (TLS-Challenge) |
| `frontend` | `botballdashboard-frontend:local` (lokal gebaut) | – | nginx mit dem React-Build; unbekannte `/api/*`-Pfade → 404 |
| `backend` | `botballdashboard-backend:local` (lokal aus `backend/`) | – | FastAPI; `migrate-then-start.sh` führt `alembic upgrade head` aus und startet Uvicorn |
| `worker` | wie backend | – | Celery-Worker (Queues `default`, `periodic`): Web-Push-Outbox, Drucker-Polling, Erinnerungen |
| `worker-ocr` | wie backend | – | Celery-Worker (Queue `ocr`): Score-Sheet-OCR. Liest **keine** `.env`: nur Datenbank, Redis, Uploads (`SERVICE_SCOPE=ocr`), keine JWT-/App-/Drucker-/SMTP-Secrets |
| `beat` | wie backend | – | Celery-Beat: plant Outbox (10 s), Drucker (15 s), Paper-Fristen (1 h), Outbox-Aufräumen (täglich); jeder Auftrag verfällt nach seinem Intervall |
| `db` | postgres:18-alpine | – | Datenbank (Volume `pgdata` unter `/var/lib/postgresql`, Cluster in `18/docker`; optional Bind-Mount `/data/db`). Neue Hauptversion: `scripts/postgres-upgrade.sh` |
| `redis` | redis:8-alpine | – | Celery-Broker, Cache, Rate-Limits, Event-Streams, Token-Sperrliste; `maxmemory` (`REDIS_MAXMEMORY`, 256mb) mit `noeviction` |
| `backup` | wie backend | `production` | `backup_scheduler.py`: tägliche verschlüsselte Backups, wöchentlicher Restore-Test, Healthcheck, Metriken auf :9101 |
| `volume-permissions` | wie backend | – | Einmaliger Init-Container: übergibt `uploads` und `vapid` an UID 10001, beendet sich |
| `backup-permissions` | wie backend | `production` | Einmaliger Init-Container: dasselbe für Backup-Archive und Off-site-Zugangsdaten |
| `prometheus` | prom/prometheus:v3.15.0 | `monitoring` | Scrapt API, Probes, Backup-Dienst, sich selbst und Alertmanager, wertet `monitoring/alerts.yml` aus (127.0.0.1:9090) |
| `blackbox` | prom/blackbox-exporter:v0.28.0 | `monitoring` | HTTP-Probes auf `/api/system/readiness` (intern) und `https://$DOMAIN/` samt Zertifikat (über Traefik; `DOMAIN` zeigt im Container auf den Docker-Host) |
| `alertmanager` | prom/alertmanager:v0.34.1 | `monitoring` | Stellt Alarme per Webhook/E-Mail zu (127.0.0.1:9093); den `Watchdog` nur an `ALERT_HEARTBEAT_URL` |
| `node-exporter` | prom/node-exporter:v1.12.1 | `monitoring` | Host-Metriken (Plattenplatz, Speicher, Last) |
| `postgres-exporter` | prometheuscommunity/postgres-exporter:v0.20.1 | `monitoring` | PostgreSQL-Metriken (Verbindungen, Größe, Erreichbarkeit) als Rolle `botball_monitor` (nur `pg_monitor`) |
| `postgres-monitor-role` | postgres:18-alpine | `monitoring` | Einmaliger Init-Container: legt die Rolle `botball_monitor` an bzw. aktualisiert sie (Passwort im Volume `postgres-monitor-secret`) |

Profile werden über `COMPOSE_PROFILES` in `.env` aktiviert (z. B. `production,monitoring`). Alle Dienste schreiben Logs als `json-file` mit Rotation (`LOG_MAX_SIZE`, Standard 10 MB × `LOG_MAX_FILE` = 5 Dateien).

`backend`, `worker`, `worker-ocr`, `beat` und `backup` laufen als unprivilegierter Benutzer `app` (UID/GID 10001) ohne Linux-Capabilities (`cap_drop: ALL`), mit `no-new-privileges` und Speicherlimits (`BACKEND_MEM_LIMIT`, `WORKER_MEM_LIMIT`, `OCR_WORKER_MEM_LIMIT`, `BEAT_MEM_LIMIT`, `BACKUP_MEM_LIMIT`). `backend`, `worker`, `worker-ocr` und `beat` haben ein schreibgeschütztes Root-Dateisystem mit `/tmp` als tmpfs. Traefik lehnt API-Anfragen mit mehr als `API_MAX_BODY_BYTES` (Standard 102 MiB) ab; die genauen Grenzen pro Route setzt das Backend beim Einlesen durch. Umstellung bestehender Installationen: [Update-Anleitung](../installation/update.md#versionshinweis-container-ohne-root-rechte-security-update-2026-09).

Volumes: `pgdata`, `redisdata`, `uploads`, `vapid`, `letsencrypt`, `backups` (oder `BACKUP_HOST_DIR`), `backup-restore-test-key`, `prometheusdata`, `alertmanagerdata`, `postgres-monitor-secret`.

Images: alle Dienste aus `backend/` nutzen ein Image `botballdashboard-backend:local`, das Frontend `botballdashboard-frontend:local` (Präfix `BOTBALL_IMAGE_PREFIX`). `scripts/update.sh` taggt jede Version zusätzlich mit ihrem Commit; `update.sh --rollback` startet die vorherige Version ohne Neubau.

Traefik routet `Host($DOMAIN) && PathPrefix(/api)` an das Backend, aber **nicht** `/api/system/metrics`. Alles andere geht an das Frontend. Das Backend veröffentlicht keinen Port.

---

## Health, Readiness, Metriken

| Endpunkt | Antwort | Zweck |
|---|---|---|
| `GET /api/system/health` | `200 {"status": "ok", "version": "…"}` | Liveness: Prozess läuft. Healthcheck des `backend`-Containers. |
| `GET /api/system/readiness` | `200 {"status": "ready", "checks": {"postgresql": true, "redis": true, "worker": true}, "queues": {"default": true, "periodic": true, "ocr": true}}`, sonst `503` mit `"not_ready"` | Betriebsbereitschaft: jede Celery-Queue braucht einen lebenden Worker (alle Worker werden nach ihren Queues gefragt, nicht nur der erste, der antwortet). Prüft Prometheus per Blackbox. |
| `GET /api/system/metrics` | Prometheus-Textformat (`botball_http_requests_total`, `botball_http_request_duration_seconds`, `botball_celery_queue_consumers{queue}`, `botball_beat_last_heartbeat_timestamp_seconds`) | Nur intern (`backend:8000`). Über Traefik 404, die App lehnt Anfragen mit `X-Forwarded-For` ab. |

```bash
curl https://dashboard.meineschule.at/api/system/health
curl https://dashboard.meineschule.at/api/system/readiness
```

Worker und Backup haben eigene Healthchecks: Beide Worker (`worker`, `worker-ocr`) müssen auf `celery inspect ping` antworten. Der Backup-Dienst ist `unhealthy`, wenn der letzte Lauf fehlschlug oder älter als `BACKUP_MAX_AGE_HOURS` ist (Standard: Backup-Intervall + 2 h, also 26 h). Beat schreibt bei jedem Auftrag einen Heartbeat nach Redis; fehlt er länger als 5 min, feuert `BeatNotRunning`.

---

## Erstinstallation

- Proxmox-LXC: [Proxmox-Setup](../installation/proxmox-setup.md) (Skript, empfohlen)
- Beliebiger Docker-Host: [Quickstart](../installation/quickstart.md)

Danach prüfen:

```bash
./scripts/verify-deployment.sh
```

---

## Update

```bash
cd /opt/botballdashboard
./scripts/update.sh
```

`git pull` → alle lokalen Images neu bauen und mit dem Commit taggen → verifiziertes Backup → `docker compose up -d` (Migrationen) → Verifikation. Ein reines `docker compose pull` aktualisiert die Anwendung **nicht**, weil ihre Images lokal gebaut werden. Rollback ohne Neubau: `./scripts/update.sh --rollback`, siehe [Update-Anleitung](../installation/update.md#rollback-nach-fehlgeschlagenem-update).

### Deploy aus GitHub

`.github/workflows/deploy.yml` (nur manuell: Actions → **Deploy** → *Run workflow*, Eingabe `ref`) löst `ref` zu einem Commit auf und bricht ab, wenn es für **genau diesen Commit** keinen erfolgreichen Lauf des CI-Workflows gibt (CI läuft nur manuell: erst Actions → **CI** → *Run workflow* auf dem Ref, dann deployen). Danach verbindet er sich per SSH mit dem Server und führt `./scripts/update.sh --ref <commit>` aus – also mit verifiziertem Backup vor den Migrationen. Es gibt keine Container-Registry: Gebaut wird auf dem Server.

Der CI-Workflow prüft dafür unter anderem die Migrationen mit Daten (Round-Trip mit `seed_e2e.py`) und im Job „Deployment – update“ ein Update der vorherigen Version **mit Daten** auf diesen Commit per `update.sh` samt Rollback per `update.sh --rollback`.

Secrets im GitHub-Environment `production`:

| Secret | Inhalt |
|---|---|
| `DEPLOY_HOST` | Hostname/IP des Servers (LXC) |
| `DEPLOY_USER` | SSH-Benutzer mit Docker-Rechten |
| `DEPLOY_SSH_KEY` | privater Schlüssel eines eigenen Deploy-Keys (`ssh-keygen -t ed25519`), öffentlicher Teil in `~/.ssh/authorized_keys` |
| `DEPLOY_HOST_FINGERPRINT` | SHA256-Fingerprint des Host-Keys (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`) |
| `DEPLOY_PORT` | optional, Standard 22 |
| `DEPLOY_PATH` | optional, Standard `/opt/botballdashboard` |

Der Server braucht Lesezugriff auf das Repository (öffentlicher Clone oder Deploy-Key) und eine fertige `.env`. Ein Required Reviewer am Environment verhindert versehentliche Deploys.

---

## Monitoring und Alarme

Profil `monitoring` aktivieren (`COMPOSE_PROFILES=production,monitoring`, dann `docker compose up -d`).

| Alarm | Bedingung |
|---|---|
| `ApiDown` | Prometheus erreicht `backend:8000` 2 min nicht |
| `ReadinessFailing` | `/api/system/readiness` 2 min nicht 200 (DB, Redis oder eine Queue ohne Worker) |
| `WorkerQueueDown` | Queue `default`/`periodic` (Dienst `worker`) oder `ocr` (`worker-ocr`) 2 min ohne Worker |
| `BeatNotRunning` | Beat hat seit > 5 min (oder nie) einen Auftrag abgegeben |
| `SiteUnreachable` | `https://$DOMAIN/` bzw. `/api/system/health` über Traefik 3 min nicht erreichbar |
| `TLSCertificateExpiresSoon` / `…Critical` | Zertifikat läuft in < 14 / < 3 Tagen ab (Erneuerung scheitert) |
| `Watchdog` | feuert immer: Totmannschalter, geht nur an `ALERT_HEARTBEAT_URL` (externer Heartbeat-Dienst, z. B. healthchecks.io) |
| `AlertmanagerNotificationsFailing` | Alertmanager konnte Benachrichtigungen nicht zustellen |
| `HighServerErrorRate` | > 5 % 5xx-Antworten über 5 min (bei > 0,1 req/s) |
| `BackupFailed` | letzter Backup-Lauf fehlgeschlagen |
| `BackupStale` | letztes erfolgreiches Backup älter als Intervall + 2 h (bzw. `BACKUP_MAX_AGE_HOURS`) |
| `RestoreTestFailed` / `RestoreTestStale` | letzter Restore-Test fehlgeschlagen / zu lange her (wöchentlich automatisch; manuell 35 Tage) |
| `BackupNeverSucceeded` | Läufe aufgezeichnet, aber nie erfolgreich (1 h) |
| `BackupMonitoringDown` | Backup-Dienst 15 min nicht erreichbar (Profil `production` fehlt?) |

Zustellung: `monitoring/alertmanager/render-config.sh` erzeugt beim Start die Alertmanager-Konfiguration aus `ALERT_WEBHOOK_URL` (JSON-POST, z. B. ntfy) und/oder `ALERT_EMAIL_TO` (SMTP aus `ALERT_SMTP_*` bzw. `SMTP_*`). Ohne Empfänger sind Alarme nur in der Oberfläche sichtbar. Beim Start steht dann eine Warnung im Log.

Totmannschalter: Fällt Prometheus, Alertmanager oder der ganze Server aus, meldet niemand mehr etwas. Dafür geht der immer feuernde `Watchdog` jede Minute an `ALERT_HEARTBEAT_URL` – einen **externen** Heartbeat-Dienst (healthchecks.io mit Periode 1 min und Karenz 5 min, Uptime-Kuma-Push-Monitor o. Ä.), der alarmiert, wenn die Pings ausbleiben. Details: [Betrieb → Dead man's switch](../../operations.md#dead-mans-switch-external-receiver-needed).

Die Regeln sind getestet (`promtool test rules monitoring/alerts.test.yml`):

```bash
docker run --rm -v "$PWD/monitoring:/m:ro" -w /m --entrypoint promtool prom/prometheus:v3.15.0 test rules alerts.test.yml
```

Zugriff auf die Oberflächen: `ssh -L 9090:localhost:9090 -L 9093:localhost:9093 <server>`.

### Logs

```bash
docker compose logs --tail=100 -f            # alle Dienste
docker compose logs backend --tail=100 -f
docker compose logs backup                   # Backup-Läufe, "BACKUP FAILED: …"
```

---

## Backup & Restore

Der Dienst `backup` erstellt täglich `botball-<UTC-Zeit>.tar.gz.age` (+ `.sha256`) mit:

- Datenbank-Dump (`pg_dump -Fc`),
- dem Upload-Verzeichnis,
- einer Prüfsummenliste aller Uploads.

Die Archive sind mit `AGE_RECIPIENT` verschlüsselt. Ein fehlgeschlagener Lauf endet mit `BACKUP FAILED: <Grund>` und wird nach einer Stunde wiederholt. Er macht den Container `unhealthy` und löst `BackupFailed` aus.

Einmal pro Woche spielt der Dienst das neueste Archiv testweise in `${POSTGRES_DB}_restore_test` ein (in einer Transaktion) und prüft alle Uploads gegen die Prüfsummenliste. Dafür verschlüsselt `backup.sh` jedes Archiv zusätzlich an einen eigenen Test-Schlüssel des Servers (Volume `backup-restore-test-key`, nie neben den Archiven und nie außer Haus); `BACKUP_RESTORE_TEST_INTERVAL_SECONDS=0` schaltet das ab. Ergebnis und Alter: `botball_restore_test_*`, Alarme `RestoreTestFailed`/`RestoreTestStale`. Details und Abwägung: [Betrieb → Restore test](../../operations.md#restore-test-automatic-weekly).

```bash
make backup-now      # sofort sichern
make backup-status   # OK / UNHEALTHY: <Grund>
```

Wiederherstellung (Test und Produktion) sowie Kopie außer Haus: [Betrieb](../../operations.md#encrypted-backups). Kurzfassung für die Produktion:

`restore.sh` spielt den Dump zuerst in einer Transaktion in eine Staging-Datenbank ein und ersetzt die Produktionsdatenbank erst danach; scheitert das Einspielen, bleibt sie unverändert.

```bash
docker compose stop backend worker worker-ocr beat backup
# Die Container laufen als UID 10001 (schreibgeschütztes Root-Dateisystem):
# Arbeitsverzeichnis und eine für sie lesbare Kopie der Identität bereitstellen.
install -d -m 700 -o 10001 -g 10001 /data/restore-work
install -m 400 -o 10001 -g 10001 /pfad/zu/botball-backup-identity.txt /data/restore-work/age-identity
docker compose run --rm --no-deps \
  -v /data/restore-work:/restore-work -e TMPDIR=/restore-work \
  -e AGE_IDENTITY=/restore-work/age-identity \
  -v /data/backups:/backups:ro \
  backend /app/scripts/restore.sh --yes /backups/botball-YYYYMMDDTHHMMSSZ.tar.gz.age
rm -rf /data/restore-work
docker compose up -d
```

---

## SSL-Zertifikate

Traefik holt und erneuert Let's-Encrypt-Zertifikate automatisch (TLS-Challenge über Port 443, Erneuerung 30 Tage vor Ablauf). Sie liegen im Docker-Volume `letsencrypt` unter `/letsencrypt/acme.json` im Traefik-Container:

```bash
docker compose exec traefik cat /letsencrypt/acme.json | python3 -m json.tool | grep '"main"'
docker compose logs traefik | grep -i acme      # Fehler bei der Ausstellung
```

Erneuerung erzwingen: `docker compose restart traefik`. Solange kein Zertifikat ausgestellt ist (DNS falsch, Port 443 nicht erreichbar), liefert Traefik ein selbstsigniertes Standardzertifikat aus.

---

## Sicherheits-Hinweise für Produktion

```bash
# .env niemals committen (steht in .gitignore); Rechte 600
chmod 600 /opt/botballdashboard/.env

# Firewall: nur 80/443 öffentlich
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow from <verwaltungsnetz> to any port 22 proto tcp
ufw enable

# Betriebssystem aktuell halten; Anwendung: ./scripts/update.sh
apt update && apt upgrade -y
```
