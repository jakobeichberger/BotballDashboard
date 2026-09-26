# Konfigurationsreferenz

Die Konfiguration steht in der `.env`-Datei im Projektverzeichnis. Docker Compose liest sie für die Variablen in `docker-compose.yml` und reicht sie per `env_file` an die Container weiter. Vorlage ist `.env.example`, das Proxmox-Setup-Skript erzeugt die Datei vollständig.

Im Produktionsmodus (`APP_ENV=production`, ebenso `APP_ENV=test`; alles außer `development`) startet das Backend nicht, solange eine dieser Bedingungen zutrifft:

- `APP_SECRET_KEY`, `JWT_SECRET_KEY` oder `POSTGRES_PASSWORD` ist kürzer als 24 Zeichen oder enthält `change-me`/`placeholder`.
- `PRINTER_CREDENTIAL_ENCRYPTION_KEY` ist kein gültiger Fernet-Schlüssel.
- `APP_BASE_URL` oder `ALLOWED_ORIGINS` enthält noch `example.com`.

Die Fehlermeldung in `docker compose logs backend` nennt die betroffenen Variablen und die Befehle zum Erzeugen.

## Compose-Profile

| Variable | Standard (.env.example) | Beschreibung |
|---|---|---|
| `COMPOSE_PROFILES` | `production` | `production` startet den Backup-Dienst, `monitoring` Prometheus, Blackbox-Exporter und Alertmanager. Beispiel: `production,monitoring` |

Ohne Profil laufen `traefik`, `db`, `redis`, `backend`, `worker`, `worker-ocr`, `beat` und `frontend`.

## Anwendung und Domain

| Variable | Standard | Beschreibung |
|---|---|---|
| `APP_ENV` | `production` | `development`, `test` oder `production` (andere Werte werden abgelehnt); nur `development` überspringt die Prüfung der Secrets |
| `APP_SECRET_KEY` | – (Pflicht) | Zufälliges Secret, mindestens 24 Zeichen |
| `APP_BASE_URL` | – (Pflicht) | Öffentliche HTTPS-URL |
| `ALLOWED_ORIGINS` | – (Pflicht) | Komma-getrennte erlaubte CORS-Origins |
| `DOMAIN` | – (Pflicht) | Hostname für die Traefik-Router |
| `TRAEFIK_EMAIL` | – (Pflicht) | E-Mail für Let's Encrypt |
| `FORWARDED_ALLOW_IPS` | `*` | Proxys, deren `X-Forwarded-For` Uvicorn vertraut. Das Backend ist nur über Traefik erreichbar. |

## PostgreSQL

| Variable | Standard | Beschreibung |
|---|---|---|
| `POSTGRES_HOST` | `db` | Datenbank-Host |
| `POSTGRES_PORT` | `5432` | Datenbank-Port |
| `POSTGRES_DB` | `botball` | Datenbankname |
| `POSTGRES_USER` | `botball` | Datenbankbenutzer |
| `POSTGRES_PASSWORD` | – (Pflicht) | Mindestens 24 Zeichen |
| `POSTGRES_UNIX_SOCKET_DIRECTORIES` | nicht gesetzt | Nur für Proxmox-LXC ohne Nesting: leer setzen, dann nur TCP. Rolle und Datenbank legt dann das Setup-Skript an. |
| `PGDATA_DRIVER_OPT_TYPE` | leer | Für den Bind-Mount: `none` |
| `PGDATA_DRIVER_OPT_O` | leer | Für den Bind-Mount: `bind` |
| `PGDATA_DRIVER_OPT_DEVICE` | leer | Beispielsweise `/data/db`. Alle drei leer: benanntes Volume `pgdata` |
| `DB_POOL_SIZE` | `5` | Verbindungen im Pool jedes API-Prozesses (die Worker öffnen Verbindungen pro Task) |
| `DB_MAX_OVERFLOW` | `10` | Zusätzliche Verbindungen bei Last |
| `DB_POOL_RECYCLE_SECONDS` | `1800` | Ältere Verbindungen werden vor der Nutzung ersetzt; tote Verbindungen fängt zusätzlich ein Ping ab |
| `DB_ECHO` | `false` | Jedes SQL-Statement loggen (nur zur Fehlersuche, langsam) |

Das Backend setzt die Verbindungs-URL aus den Einzelwerten zusammen. `DATABASE_URL` wird **nicht** gelesen.

## Redis und Authentifizierung

| Variable | Standard | Beschreibung |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379/0` | Redis für Celery, Rate-Limits, Events und den Ranglisten-Cache |
| `CACHE_BACKEND` | `redis` | Cache für berechnete Ranglisten und Ergebnisse: `redis`, `memory` (ein Prozess) oder `none` |
| `RANKING_CACHE_TTL_SECONDS` | `120` | Höchstalter eines Cache-Eintrags. Live-Wertungen verwerfen ihn sofort; die TTL begrenzt nur Änderungen ohne Live-Ereignis (z. B. ein umbenanntes Team) |
| `JWT_SECRET_KEY` | – (Pflicht) | Eigenes zufälliges JWT-Secret, mindestens 24 Zeichen |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Lebensdauer des Access-Tokens |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Lebensdauer des Refresh-Tokens |

Secrets erzeugen:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## E-Mail

| Variable | Standard | Beschreibung |
|---|---|---|
| `SMTP_HOST` | leer | SMTP-Server. Leer: kein SMTP-Versand |
| `SMTP_PORT` | `587` | SMTP-Port |
| `SMTP_USER` | leer | SMTP-Benutzer |
| `SMTP_PASSWORD` | leer | SMTP-Passwort |
| `SMTP_FROM` | `BotballDashboard <noreply@example.com>` | Absender |
| `SMTP_TLS` | `true` | STARTTLS verwenden |
| `SENDGRID_API_KEY` | leer | Optionaler Fallback, wenn SMTP fehlschlägt |
| `SENDGRID_FROM` | leer | SendGrid-Absender |

Derzeit verschickt das Dashboard nur eine Mitteilung beim Anlegen eines Kontos. Alertmanager kann dieselben SMTP-Daten für Alarm-Mails nutzen.

## Web Push

| Variable | Standard | Beschreibung |
|---|---|---|
| `VAPID_PRIVATE_KEY` | `/app/vapid/private_key.pem` | Pfad zum privaten Schlüssel im Volume `vapid` (Backend und Worker) |
| `VAPID_PUBLIC_KEY` | leer | Application Server Key, wird ins Frontend eingebaut |
| `VAPID_ADMIN_EMAIL` | – | Kontaktadresse für VAPID-Claims |

`make vapid-keys` erzeugt das Schlüsselpaar und gibt den öffentlichen Schlüssel aus. Danach `VAPID_PUBLIC_KEY` in `.env` eintragen und `./scripts/update.sh --no-pull` ausführen, damit das Frontend neu gebaut wird. Das Proxmox-Setup erledigt das automatisch.

## Drucker und Dateien

| Variable | Standard | Beschreibung |
|---|---|---|
| `PRINTER_CREDENTIAL_ENCRYPTION_KEY` | – (Pflicht in Produktion) | Fernet-Schlüssel für gespeicherte Drucker-Zugangsdaten. Nicht mehr ändern, sobald Drucker gespeichert sind. |
| `UPLOAD_DIR` | `/app/uploads` | Upload-Verzeichnis im Container (Volume `uploads`) |
| `MAX_UPLOAD_SIZE_MB` | `20` | Maximale Uploadgröße (Paper, Dokumente, Bilder, Score-Sheets) |
| `PRINT_UPLOAD_MAX_MB` | `100` | Maximale Größe von Druckdateien (STL, 3MF, OBJ, G-Code) |

Das Backend prüft beide Grenzen selbst: Anfragen an `/api/printing/jobs/{id}/file` dürfen bis `PRINT_UPLOAD_MAX_MB` groß sein, alle anderen bis `MAX_UPLOAD_SIZE_MB` (jeweils + 1 MB für den Multipart-Overhead). Gezählt werden die tatsächlich empfangenen Bytes, auch bei Anfragen ohne `Content-Length` (chunked). Traefik (`docker-compose.yml`) lehnt API-Anfragen über `API_MAX_BODY_BYTES` ab (Standard 106954752 = 102 MiB); wer `PRINT_UPLOAD_MAX_MB` erhöht, erhöht diesen Wert mit. Steht ein anderer Reverse Proxy vor der API, muss er mindestens den größeren Wert + 1 MB durchlassen, bei nginx z. B. `client_max_body_size 101m;` im `location /api/`-Block. Das `client_max_body_size 21m` in `frontend/nginx.conf` betrifft nur den Frontend-Container, der keine API-Anfragen annimmt.

Fernet-Schlüssel erzeugen (beide Befehle liefern dasselbe Format):

```bash
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
make fernet-key   # bei laufendem Stack
```

## Backups (Profil `production`)

| Variable | Standard | Beschreibung |
|---|---|---|
| `AGE_RECIPIENT` | – (Pflicht für Backups) | Öffentlicher age-Schlüssel (`age1…`). Leer: jeder Backup-Lauf schlägt fehl, der Container wird `unhealthy`. |
| `BACKUP_HOST_DIR` | Volume `backups` | Host-Verzeichnis für die Archive, z. B. `/data/backups` (erleichtert die Kopie außer Haus) |
| `BACKUP_INTERVAL_SECONDS` | `86400` | Abstand zwischen erfolgreichen Backups |
| `BACKUP_RETRY_SECONDS` | `3600` | Neuer Versuch nach einem Fehlschlag |
| `BACKUP_RETENTION_DAYS` | `30` | Ältere Archive werden gelöscht |
| `BACKUP_MAX_AGE_HOURS` | Intervall in Stunden + 2 (26) | Healthcheck wird `unhealthy` und `BackupStale` feuert, wenn das letzte erfolgreiche Backup älter ist |
| `BACKUP_RESTORE_TEST_INTERVAL_SECONDS` | `604800` (wöchentlich) | Automatischer Restore-Test mit eigenem Test-Schlüssel des Servers; `0` = nur manuelle Tests (dann alle 35 Tage erwartet) |

Details zu Schlüssel, Kopie außer Haus und Wiederherstellung: [Betrieb](../../operations.md).

## Alarme (Profil `monitoring`)

| Variable | Standard | Beschreibung |
|---|---|---|
| `ALERT_WEBHOOK_URL` | leer | Alertmanager sendet Alarme als JSON-POST dorthin (z. B. ntfy-Topic) |
| `ALERT_EMAIL_TO` | leer | Empfänger für Alarm-Mails |
| `ALERT_EMAIL_FROM` | `SMTP_FROM` | Absender |
| `ALERT_SMTP_SMARTHOST` | `SMTP_HOST:SMTP_PORT` | SMTP-Server für Alarm-Mails |
| `ALERT_SMTP_USER` / `ALERT_SMTP_PASSWORD` | `SMTP_USER` / `SMTP_PASSWORD` | SMTP-Anmeldung |
| `ALERT_SMTP_REQUIRE_TLS` | `SMTP_TLS` | STARTTLS |
| `ALERT_HEARTBEAT_URL` | leer | Totmannschalter: der immer feuernde `Watchdog` geht jede Minute als POST dorthin – an einen externen Heartbeat-Dienst (healthchecks.io, Uptime-Kuma-Push), der alarmiert, wenn er ausbleibt |

Ohne Empfänger sind Alarme nur in der Oberfläche von Prometheus (`:9090/alerts`) und Alertmanager (`:9093`) sichtbar.

## Redis, Images, Monitoring-Rolle

| Variable | Standard | Beschreibung |
|---|---|---|
| `REDIS_MAXMEMORY` | `256mb` | Speichergrenze von Redis (Richtlinie `noeviction`: bei vollem Speicher schlagen Schreibvorgänge fehl, statt Celery-Aufträge zu verwerfen) |
| `REDIS_MEM_LIMIT` | `768m` | Container-Limit von Redis (mit Reserve für Snapshots) |
| `BOTBALL_IMAGE_PREFIX` | `botballdashboard` | Präfix der lokal gebauten Images (`<prefix>-backend:local`, `<prefix>-frontend:local`) |
| `POSTGRES_MONITOR_USER` | `botball_monitor` | Login-Rolle des postgres-exporters (nur `pg_monitor`, wird automatisch angelegt) |
| `SERVICE_SCOPE` | `full` | Nicht ändern; `worker-ocr` setzt selbst `ocr` |

## Container-Logs

| Variable | Standard | Beschreibung |
|---|---|---|
| `LOG_MAX_SIZE` | `10m` | Größe einer Logdatei (Docker `json-file`) |
| `LOG_MAX_FILE` | `5` | Anzahl rotierter Dateien je Container |
