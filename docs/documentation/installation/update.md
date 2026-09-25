# Update-Anleitung

Ein Update tauscht nur die Programmteile aus (Backend-, Worker- und Frontend-Images). Datenbank, Uploads, Backups und Zertifikate liegen in Volumes bzw. unter `/data` und bleiben erhalten.

---

## Prinzip

`docker-compose.yml` baut die Anwendungs-Images **lokal** aus dem Checkout. Ein `docker compose pull` allein aktualisiert daher nur PostgreSQL, Redis, Traefik und die Monitoring-Images, aber nicht die Anwendung. Ein Update besteht immer aus:

```
1. Backup + Proxmox-Snapshot
2. git pull (neuer Code)
3. Images neu bauen (backend, worker, beat, backup, frontend)
4. docker compose up -d  → das Backend spielt beim Start ausstehende Migrationen ein
5. Prüfen (scripts/verify-deployment.sh)
```

Beim Start führt das Backend `alembic upgrade head` aus (`migrate-then-start.sh`). Eine Prüfung, ob Code und Datenbankschema zueinander passen, gibt es darüber hinaus **nicht**. Wer älteren Code auf eine neuere Datenbank startet, bekommt Fehler zur Laufzeit. Deshalb gehört zum Rollback das Downgrade der Migrationen (siehe unten).

---

## Standard-Update (empfohlen)

```bash
cd /opt/botballdashboard
./scripts/update.sh
```

Das Skript:

1. speichert den laufenden Commit und die Alembic-Revision in `.deploy-state` (für den Rollback),
2. holt mit `git pull --ff-only` den neuen Stand (`--ref v1.4` für einen Tag/Branch, `--no-pull` baut nur neu),
3. baut die Backend-Images (`backend`, `worker`, `beat`, `backup` und die Init-Dienste `volume-permissions`/`backup-permissions`) mit aktuellen Basis-Images neu,
4. baut das Frontend: mit `pnpm` auf dem Host (wie beim Proxmox-Setup, `frontend/Dockerfile.prebuilt`), ohne `pnpm` per `docker compose build frontend`. Die Wahl lässt sich mit `FRONTEND_BUILD=host|docker` erzwingen.
5. startet mit `docker compose up -d --remove-orphans` neu und wartet auf das gesunde Backend,
6. führt `scripts/verify-deployment.sh` aus und endet mit Fehlercode, wenn eine Prüfung fehlschlägt.

Manuell entspricht das:

```bash
git pull --ff-only
docker compose build --pull volume-permissions backup-permissions backend worker beat backup
# Frontend: entweder im Container …
docker compose build --pull frontend
# … oder (Proxmox-LXC) auf dem Host:
(cd frontend && pnpm install --frozen-lockfile && VITE_API_URL=/api VITE_VAPID_PUBLIC_KEY=<aus .env> pnpm build)
docker build -f frontend/Dockerfile.prebuilt -t botballdashboard-frontend:local frontend
docker compose up -d --remove-orphans
./scripts/verify-deployment.sh
```

Updates lassen sich auch aus GitHub starten: Actions → **Deploy** → *Run workflow* (per SSH wird `scripts/update.sh --ref <ref>` auf dem Server ausgeführt, siehe [Deployment](../technical/deployment.md#deploy-aus-github)).

---

## Versionshinweis: Container ohne Root-Rechte (Security-Update 2026-09)

Ab diesem Stand laufen `backend`, `worker`, `beat` und `backup` als unprivilegierter Benutzer `app` (**UID/GID 10001**) statt als `root`, ohne Linux-Capabilities (`cap_drop: ALL`), mit `no-new-privileges` und mit Speicherlimits (`*_MEM_LIMIT` in `.env`). `backend`, `worker` und `beat` haben zusätzlich ein schreibgeschütztes Root-Dateisystem; beschreibbar sind nur ihre Volumes und `/tmp` (tmpfs).

Dateien, die ältere Versionen als `root` angelegt haben (Uploads, VAPID-Schlüssel, Backup-Archive, Off-site-Zugangsdaten), gehören danach dem falschen Benutzer. **Das erledigt der Start automatisch:** zwei einmalig laufende Init-Container stellen vor dem Start der Anwendung die Eigentümer um und beenden sich wieder:

| Dienst | Verzeichnisse | Profil |
|---|---|---|
| `volume-permissions` | Volumes `uploads` (`/app/uploads`), `vapid` (`/app/vapid`) | immer |
| `backup-permissions` | `BACKUP_HOST_DIR` bzw. Volume `backups` (`/backups`), `BACKUP_OFFSITE_CONFIG_DIR` (`/offsite-config`) | `production` |

Sie laufen als `root`, aber nur mit den Capabilities `CHOWN` und `DAC_READ_SEARCH`, ohne Netzwerk, und ändern nur Einträge, die noch nicht UID 10001 gehören (Symlinks selbst, nie ihr Ziel). Beim ersten Start nach dem Update steht im Log, wie viele Einträge umgestellt wurden (`docker compose logs volume-permissions backup-permissions`); jeder weitere Start ändert nichts. `scripts/update.sh` baut die beiden Dienste mit.

Wer lieber vorab und von Hand umstellt (z. B. vor dem ersten Start oder bei einem eigenen Compose-Setup ohne die Init-Dienste):

```bash
cd /opt/botballdashboard
docker compose stop backend worker beat backup
# Named Volumes (Projektname ggf. anpassen: docker volume ls)
docker run --rm -v botballdashboard_uploads:/v alpine chown -R 10001:10001 /v
docker run --rm -v botballdashboard_vapid:/v alpine chown -R 10001:10001 /v
docker run --rm -v botballdashboard_backups:/v alpine chown -R 10001:10001 /v   # ohne BACKUP_HOST_DIR
# Host-Verzeichnisse (Proxmox-Setup)
chown -R 10001:10001 /data/backups /data/backup-offsite
docker compose up -d
```

Zu beachten:

- **SSH-Schlüssel für die Off-site-Kopie** (`id_ed25519`) muss dem Benutzer 10001 gehören und darf nur für ihn lesbar sein (`chmod 600`); das stellt `backup-permissions` sicher. Wird der Schlüssel später auf dem Host neu erzeugt (`scripts/proxmox-setup.sh`), korrigiert der nächste `docker compose up -d` den Eigentümer.
- **Wiederherstellung und Restore-Test** laufen ebenfalls als Benutzer 10001; die age-Identität und das Arbeitsverzeichnis müssen für ihn lesbar sein. Die geänderten Befehle stehen in [Betrieb → Restore](../../operations.md#restore-in-production).
- **Eigene Bind-Mounts** unter `/app/uploads` oder `/backups` (z. B. in einer `docker-compose.override.yml`) müssen ebenfalls UID 10001 gehören.
- **Rollback** auf eine ältere Version (Option 2/3 unten) braucht keinen Rückbau: deren Container laufen als `root` und können die umgestellten Dateien weiter lesen und schreiben.
- Die Entwicklungsumgebung (`docker-compose.dev.yml`) startet das Backend weiterhin als `root` auf dem eingebundenen Quellcode.

---

## Vor einem Update: Backup und Snapshot

```bash
# Verschlüsseltes Backup (Datenbank + Uploads) sofort erstellen
make backup-now            # = docker compose exec backup python scripts/backup_scheduler.py once

# Proxmox-Snapshot der LXC/VM (auf dem Proxmox-Host; ID anpassen)
pct snapshot 105 pre-update-$(date +%Y%m%d)        # LXC
# qm snapshot 105 pre-update-$(date +%Y%m%d)       # VM
```

---

## Rollback nach fehlgeschlagenem Update

### Option 1: Proxmox-Snapshot zurückspielen (einfachste Methode)

```bash
pct rollback 105 pre-update-20260315      # LXC   (qm rollback … für eine VM)
```

Setzt Code, Images **und** Daten auf den Stand des Snapshots zurück. Alles, was seit dem Snapshot erfasst wurde, geht dabei verloren.

### Option 2: Alten Code wiederherstellen, Daten behalten

Nur möglich, wenn die neuen Migrationen ein funktionierendes `downgrade` haben. `.deploy-state` enthält den vorherigen Commit und die vorherige Alembic-Revision.

```bash
cd /opt/botballdashboard
cat .deploy-state          # PREVIOUS_COMMIT=…  PREVIOUS_ALEMBIC_REVISION=…

# 1. Migrationen zurückrollen, SOLANGE der neue Code läuft:
#    Nur der neue Code kennt die neuen Revisionen und ihre downgrade()-Schritte.
docker compose exec backend alembic downgrade <PREVIOUS_ALEMBIC_REVISION>

# 2. Alten Code auschecken und die Images NEU BAUEN – ein bloßes
#    `docker compose up -d` würde die neuen Images weiterverwenden.
git checkout <PREVIOUS_COMMIT>
./scripts/update.sh --no-pull

# 3. Später zurück auf den Branch:  git checkout main
```

Einschränkungen:
- Datenmigrationen oder gelöschte Spalten lassen sich per `downgrade` nicht immer verlustfrei umkehren. Im Zweifel Option 1 oder Option 3 verwenden.
- Ist das Backend nach dem Update gar nicht gestartet, wurden die Migrationen evtl. nur teilweise eingespielt: `docker compose run --rm backend alembic current` zeigt den Stand.

### Option 3: Backup von vor dem Update wiederherstellen

Alten Code auschecken und neu bauen (Schritt 2 oben), dann das Backup von vor dem Update einspielen, siehe [Betrieb → Wiederherstellung](../../operations.md#restore-in-production). Das Backend führt danach beim Start die Migrationen bis zum Stand des alten Codes aus.

---

## Datenbank-Migrationen manuell ausführen

Normalerweise laufen die Migrationen automatisch beim Start. Falls manuell nötig:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current   # aktueller Stand
docker compose exec backend alembic heads     # Stand, den der Code erwartet
docker compose exec backend alembic history
```

---

## Update-Checkliste

```
[ ] make backup-now erfolgreich
[ ] Proxmox-Snapshot angelegt
[ ] ./scripts/update.sh ohne Fehler durchgelaufen
[ ] verify-deployment.sh: keine FAIL-Zeile
[ ] Im Browser getestet → Login, Scoreboard, Live-Updates funktionieren
[ ] Snapshot nach 48 h löschen
```
