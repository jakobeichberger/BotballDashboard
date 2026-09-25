# Proxmox-Setup

Installation des BotballDashboard in einer Debian-12-LXC (oder VM) auf Proxmox VE mit `scripts/proxmox-setup.sh`. Alle Dienste laufen per Docker Compose **in derselben LXC**.

```
Proxmox-Host
└── LXC botball (Debian 12, Docker)
    ├── traefik        Reverse Proxy, Let's Encrypt (Ports 80/443)
    ├── frontend       nginx mit dem React-Build
    ├── backend        FastAPI (führt beim Start die Migrationen aus)
    ├── worker         Celery: OCR, Web Push, Drucker-Polling
    ├── beat           Celery-Zeitplan (Outbox, Drucker, Paper-Fristen)
    ├── db, redis      PostgreSQL 16 (/data/db), Redis 7
    ├── backup         verschlüsselte Backups nach /data/backups   (Profil production)
    └── prometheus, blackbox, alertmanager                      (Profil monitoring, optional)
```

---

## 1. LXC anlegen (auf dem Proxmox-Host)

Über die WebUI oder per CLI, z. B.:

```bash
pveam update && pveam download local debian-12-standard_12.7-1_amd64.tar.zst
pct create 105 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname botball --cores 4 --memory 8192 --swap 1024 \
  --rootfs local-lvm:40 --mp0 local-lvm:50,mp=/data \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --features nesting=1,keyctl=1 --unprivileged 1 --onboot 1
pct start 105
```

- Den genauen Vorlagennamen zeigt `pveam available | grep debian-12`.
- `nesting=1,keyctl=1`: Docker braucht beides in einer LXC.
- `/data` als eigenes Volume (`mp0`) nimmt Datenbank und Backups auf. So lässt es sich getrennt sichern und vergrößern.
- DNS-Eintrag der Domain auf die öffentliche IP setzen und die Ports 80/443 zur LXC weiterleiten. Let's Encrypt prüft über Port 443.

## 2. Setup-Skript ausführen (in der LXC, als root)

```bash
pct enter 105     # oder per SSH in die LXC
apt-get update && apt-get install -y curl
bash <(curl -fsSL https://raw.githubusercontent.com/jakobeichberger/BotballDashboard/main/scripts/proxmox-setup.sh)
```

Was das Skript macht:

| Schritt | Inhalt |
|---|---|
| 1 | Prüft root/Netz, installiert `git`, `curl`, `python3`, `age` |
| 2 | Installiert Docker + Compose-Plugin (get.docker.com) |
| 3 | Installiert Node.js 24 und pnpm 10.29.3 (Frontend-Build auf dem Host) |
| 4 | Klont das Repository nach `/opt/botballdashboard` (bzw. `git pull`) |
| 5 | Fragt Domain, Let's-Encrypt-Mail, DB-Name/-User, optional SMTP, Backup-Schlüssel, Monitoring und Admin-Konto ab und schreibt `.env` (Rechte 600). Erzeugt automatisch `APP_SECRET_KEY`, `JWT_SECRET_KEY`, ein 43-stelliges `POSTGRES_PASSWORD` (falls keines eingegeben), einen Fernet-Schlüssel für `PRINTER_CREDENTIAL_ENCRYPTION_KEY` und – ohne eigenen Schlüssel – ein age-Schlüsselpaar für Backups (`/root/botball-backup-identity.txt`). Setzt `COMPOSE_PROFILES` (`production`, optional `monitoring`). |
| 6 | Legt `/data/db` (UID 70) und `/data/backups` an |
| 7 | Baut das Frontend auf dem Host (`pnpm build`) |
| 8 | Baut das Backend-Image für `backend`, `worker`, `worker-ocr`, `beat`, `backup` und das nginx-Frontend-Image (`frontend/Dockerfile.prebuilt`) |
| 9 | Startet `db` und `redis`, legt Rolle/Datenbank bei Bedarf über TCP an, gleicht das DB-Passwort mit `.env` ab und startet dann **alle** Dienste der aktiven Profile. Wartet auf den Healthcheck des Backends. |
| 10 | Erzeugt VAPID-Schlüssel (bestehende bleiben erhalten), baut das Frontend damit neu |
| 11 | Legt den ersten Admin an (`scripts/create_admin.py`) |
| 12 | Führt `scripts/verify-deployment.sh` aus und zeigt Zugangsdaten und Hinweise |

Hinweise:
- **SMTP ist optional.** Ohne SMTP verschickt das Dashboard keine E-Mails.
- **Backup-Schlüssel:** Die Datei `/root/botball-backup-identity.txt` ist der private Schlüssel. Ohne sie lassen sich die Backups nicht entschlüsseln. Kopiere sie in einen Passwortmanager oder auf ein Offline-Medium und lösche sie anschließend auf dem Server. Ist `age` nicht installierbar, schaltet das Skript die Backups ab und sagt das deutlich.
- **PostgreSQL läuft nur über TCP** (`POSTGRES_UNIX_SOCKET_DIRECTORIES=` in `.env`), weil unprivilegierte LXC ohne Nesting keine Unix-Sockets anlegen können. Deshalb legt das Skript Rolle und Datenbank selbst an.
- Erneut ausführen ist gefahrlos. Wer `.env` behält, bekommt fehlende neue Einstellungen ergänzt, und das Skript warnt bei zu kurzen Secrets oder einem ungültigen Fernet-Schlüssel.

## 3. Updates

```bash
cd /opt/botballdashboard
./scripts/update.sh          # git pull → Images neu bauen → up -d → verify
```

Details, Rollback und manuelle Variante: [Update-Anleitung](update.md). Updates aus GitHub: Workflow **Deploy** ([Deployment](../technical/deployment.md#deploy-aus-github)).

## 4. Proxmox-Snapshots und Backups

- Vor jedem Update einen Snapshot anlegen: `pct snapshot 105 pre-update-$(date +%Y%m%d)`.
- Die Anwendung sichert täglich Datenbank und Uploads verschlüsselt nach `/data/backups`. Diese Archive außer Haus kopieren, siehe [Betrieb → Encrypted backups](../../operations.md#encrypted-backups).
- Zusätzlich ein Proxmox-Backup (vzdump) der LXC auf ein anderes Storage, z. B. wöchentlich über *Datacenter → Backup*.

## 5. Firewall

```
Extern erreichbar:   80, 443
Nur SSH-Tunnel:      9090 (Prometheus), 9093 (Alertmanager) – lauschen auf 127.0.0.1
Intern (Docker):     5432, 6379, 8000 – nicht veröffentlicht
SSH:                 22 nur aus dem Verwaltungsnetz
```

## 6. Monitoring

Mit dem Profil `monitoring` überwacht Prometheus:

- die API (`/api/system/metrics`),
- die Readiness (`/api/system/readiness`, per Blackbox),
- den Backup-Dienst.

Alertmanager meldet Ausfälle an `ALERT_WEBHOOK_URL` und/oder `ALERT_EMAIL_TO`:

- API nicht erreichbar,
- Readiness schlägt fehl,
- 5xx-Rate > 5 %,
- Backup fehlgeschlagen, veraltet oder nie gelaufen.

```bash
ssh -L 9090:localhost:9090 -L 9093:localhost:9093 root@botball   # dann http://localhost:9090/alerts
```

---

## Auf dem eigenen Server testen

So prüfst du eine Installation auf deinem Proxmox-Host vollständig. Alle Befehle laufen in der LXC als root.

### A. Neuinstallation

1. LXC wie in Abschnitt 1 anlegen, DNS und Port-Weiterleitung setzen.
2. Setup-Skript ausführen (Abschnitt 2). Bei *Enable monitoring?* mit `y` antworten, damit auch die Monitoring-Prüfungen laufen. Für Alarme optional eine ntfy-URL als Webhook angeben.
3. Am Ende läuft `verify-deployment.sh` automatisch. Erwartet wird `Result: … 0 failed`. Normale Warnungen direkt nach der Installation:
   - `no backup has finished yet`
   - `healthcheck still starting`
   - `Alertmanager has no receiver`
4. Backup einmal auslösen und den Wiederherstellungstest fahren:
   ```bash
   cd /opt/botballdashboard
   make backup-now
   # Die Container laufen als UID 10001: Identität für sie lesbar bereitstellen.
   install -d -m 700 -o 10001 -g 10001 /data/restore-work
   install -m 400 -o 10001 -g 10001 /root/botball-backup-identity.txt /data/restore-work/age-identity
   docker compose run --rm --no-deps \
     -v /data/restore-work:/restore-work -e AGE_IDENTITY=/restore-work/age-identity \
     backup /app/scripts/restore-test.sh /backups/$(ls /data/backups | grep '\.age$' | tail -n1)
   rm -rf /data/restore-work
   ```
   Erwartet: `Uploads verified: … files match the manifest` und `Restore test succeeded`.
5. Im Browser `https://<domain>` öffnen und mit dem Admin-Konto anmelden. Dann unter Einstellungen → Saisons eine Saison und unter `/setup` ein Event anlegen.

### B. Update

```bash
cd /opt/botballdashboard
./scripts/update.sh            # oder: ./scripts/update.sh --ref <branch/tag>
```

Das Skript endet mit `Update complete`, nachdem `verify-deployment.sh` ohne FAIL durchgelaufen ist. `cat .deploy-state` zeigt den vorherigen Commit und die Migration für einen eventuellen Rollback.

### C. Prüfung jederzeit

```bash
/opt/botballdashboard/scripts/verify-deployment.sh
```

| Prüfung | Erwartung |
|---|---|
| Container | alle Dienste der aktiven Profile `running`, mit Healthcheck `healthy` |
| `/api/system/health`, `/api/system/readiness` über `https://$DOMAIN` | 200, Readiness `{"status":"ready",…}` |
| `/api/system/metrics` über Traefik | 404 (Metriken nur intern) |
| Security-Header auf `/` und einem `/assets/*.js` | CSP, HSTS, X-Frame-Options vorhanden |
| Worker, Beat | Celery-Ping beantwortet, Beat-Prozess läuft |
| Migrationen | `alembic current` = `alembic heads` |
| Backup | letztes Backup erfolgreich und < 26 h alt; ohne `AGE_RECIPIENT` WARN „backups are DISABLED“ |
| VAPID | privater Schlüssel im Worker lesbar |
| Monitoring (nur mit Profil) | alle Prometheus-Targets `up`, 7 Alarmregeln geladen, Alertmanager gesund |

Für den Test ohne echtes Zertifikat (z. B. `DOMAIN=localhost` oder `*.test`) prüft das Skript TLS automatisch ohne Zertifikatsprüfung (`curl -k`). `VERIFY_INSECURE=1` erzwingt das. Mit `VERIFY_LOCAL=1` (Standard) verbindet es sich für `$DOMAIN` mit `127.0.0.1`, prüft also Traefik auf diesem Host unabhängig von DNS/NAT.
