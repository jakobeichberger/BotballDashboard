# Deployment & Betrieb

---

## Dienste (docker-compose.yml)

| Dienst | Image | Profil | Aufgabe |
|---|---|---|---|
| `traefik` | traefik:v2.11 | – | Reverse Proxy, HTTP→HTTPS, Let's Encrypt (TLS-Challenge) |
| `frontend` | `botballdashboard-frontend:local` (lokal gebaut) | – | nginx mit dem React-Build; unbekannte `/api/*`-Pfade → 404 |
| `backend` | lokal aus `backend/` | – | FastAPI; `migrate-then-start.sh` führt `alembic upgrade head` aus und startet Uvicorn |
| `worker` | wie backend | – | Celery-Worker (Queues `default`, `periodic`): Web-Push-Outbox, Drucker-Polling, Erinnerungen |
| `worker-ocr` | wie backend | – | Celery-Worker (Queue `ocr`): Score-Sheet-OCR |
| `beat` | wie backend | – | Celery-Beat: plant Outbox (10 s), Drucker (15 s), Paper-Fristen (1 h), Outbox-Aufräumen (täglich); jeder Auftrag verfällt nach seinem Intervall |
| `db` | postgres:16-alpine | – | Datenbank (Volume `pgdata`, optional Bind-Mount `/data/db`) |
| `redis` | redis:7-alpine | – | Celery-Broker, Rate-Limits, Event-Streams |
| `backup` | wie backend | `production` | `backup_scheduler.py`: tägliche verschlüsselte Backups, Healthcheck, Metriken auf :9101 |
| `prometheus` | prom/prometheus:v2.54.1 | `monitoring` | Scrapt API, Readiness-Probe und Backup-Dienst, wertet `monitoring/alerts.yml` aus (127.0.0.1:9090) |
| `blackbox` | prom/blackbox-exporter:v0.25.0 | `monitoring` | HTTP-Probe auf `/api/system/readiness` |
| `alertmanager` | prom/alertmanager:v0.27.0 | `monitoring` | Stellt Alarme per Webhook/E-Mail zu (127.0.0.1:9093) |

Profile werden über `COMPOSE_PROFILES` in `.env` aktiviert (z. B. `production,monitoring`). Alle Dienste schreiben Logs als `json-file` mit Rotation (`LOG_MAX_SIZE`, Standard 10 MB × `LOG_MAX_FILE` = 5 Dateien).

Volumes: `pgdata`, `redisdata`, `uploads`, `vapid`, `letsencrypt`, `backups` (oder `BACKUP_HOST_DIR`), `prometheusdata`, `alertmanagerdata`.

Traefik routet `Host($DOMAIN) && PathPrefix(/api)` an das Backend, aber **nicht** `/api/system/metrics`. Alles andere geht an das Frontend. Das Backend veröffentlicht keinen Port.

---

## Health, Readiness, Metriken

| Endpunkt | Antwort | Zweck |
|---|---|---|
| `GET /api/system/health` | `200 {"status": "ok", "version": "…"}` | Liveness: Prozess läuft. Healthcheck des `backend`-Containers. |
| `GET /api/system/readiness` | `200 {"status": "ready", "checks": {"postgresql": true, "redis": true, "worker": true}}`, sonst `503` mit `"not_ready"` und den fehlgeschlagenen Checks | Betriebsbereitschaft inkl. Celery-Worker. Prüft Prometheus per Blackbox. |
| `GET /api/system/metrics` | Prometheus-Textformat (`botball_http_requests_total`, `botball_http_request_duration_seconds`) | Nur intern (`backend:8000`). Über Traefik 404, die App lehnt Anfragen mit `X-Forwarded-For` ab. |

```bash
curl https://dashboard.meineschule.at/api/system/health
curl https://dashboard.meineschule.at/api/system/readiness
```

Worker und Backup haben eigene Healthchecks: Beide Worker (`worker`, `worker-ocr`) müssen auf `celery inspect ping` antworten. Der Backup-Dienst ist `unhealthy`, wenn der letzte Lauf fehlschlug oder älter als 26 h ist.

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

`git pull` → alle lokalen Images neu bauen → `docker compose up -d` → Verifikation. Ein reines `docker compose pull` aktualisiert die Anwendung **nicht**, weil ihre Images lokal gebaut werden. Rollback: [Update-Anleitung](../installation/update.md#rollback-nach-fehlgeschlagenem-update).

### Deploy aus GitHub

`.github/workflows/deploy.yml` (nur manuell: Actions → **Deploy** → *Run workflow*, Eingabe `ref`) verbindet sich per SSH mit dem Server und führt `./scripts/update.sh --ref <ref>` aus. Es gibt keine Container-Registry: Gebaut wird auf dem Server.

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
| `ReadinessFailing` | `/api/system/readiness` 2 min nicht 200 (DB, Redis oder Worker fehlt) |
| `HighServerErrorRate` | > 5 % 5xx-Antworten über 5 min (bei > 0,1 req/s) |
| `BackupFailed` | letzter Backup-Lauf fehlgeschlagen |
| `BackupStale` | letztes erfolgreiches Backup > 26 h alt |
| `BackupNeverSucceeded` | Läufe aufgezeichnet, aber nie erfolgreich (1 h) |
| `BackupMonitoringDown` | Backup-Dienst 15 min nicht erreichbar (Profil `production` fehlt?) |

Zustellung: `monitoring/alertmanager/render-config.sh` erzeugt beim Start die Alertmanager-Konfiguration aus `ALERT_WEBHOOK_URL` (JSON-POST, z. B. ntfy) und/oder `ALERT_EMAIL_TO` (SMTP aus `ALERT_SMTP_*` bzw. `SMTP_*`). Ohne Empfänger sind Alarme nur in der Oberfläche sichtbar. Beim Start steht dann eine Warnung im Log.

Die Regeln sind getestet (`promtool test rules monitoring/alerts.test.yml`):

```bash
docker run --rm -v "$PWD/monitoring:/m:ro" -w /m --entrypoint promtool prom/prometheus:v2.54.1 test rules alerts.test.yml
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

```bash
make backup-now      # sofort sichern
make backup-status   # OK / UNHEALTHY: <Grund>
```

Wiederherstellung (Test und Produktion) sowie Kopie außer Haus: [Betrieb](../../operations.md#encrypted-backups). Kurzfassung für die Produktion:

```bash
docker compose stop backend worker worker-ocr beat backup
docker compose run --rm --no-deps \
  -v /pfad/zu/botball-backup-identity.txt:/run/age-identity:ro -e AGE_IDENTITY=/run/age-identity \
  -v /data/backups:/backups:ro \
  backend /app/scripts/restore.sh --yes /backups/botball-YYYYMMDDTHHMMSSZ.tar.gz.age
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
