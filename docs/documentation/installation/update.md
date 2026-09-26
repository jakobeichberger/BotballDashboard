# Update-Anleitung

Ein Update tauscht nur die Programmteile aus (Backend-, Worker- und Frontend-Images). Datenbank, Uploads, Backups und Zertifikate liegen in Volumes bzw. unter `/data` und bleiben erhalten.

---

## Prinzip

`docker-compose.yml` baut die Anwendungs-Images **lokal** aus dem Checkout. Ein `docker compose pull` allein aktualisiert daher nur PostgreSQL, Redis, Traefik und die Monitoring-Images, aber nicht die Anwendung. Ein Update besteht immer aus:

```
1. Proxmox-Snapshot (von Hand, empfohlen)
2. git pull (neuer Code)
3. Images neu bauen und mit dem Commit taggen (backend, worker, worker-ocr, beat, backup, frontend)
4. verifiziertes Backup, bevor irgendetwas migriert wird
5. nur bei neuer PostgreSQL-Hauptversion: Daten umziehen (scripts/postgres-upgrade.sh)
6. docker compose up -d  → das Backend spielt beim Start ausstehende Migrationen ein
7. Prüfen (scripts/verify-deployment.sh)
```

Schritte 2–7 erledigt `scripts/update.sh`.

Beim Start führt das Backend `alembic upgrade head` aus (`migrate-then-start.sh`). Eine Prüfung, ob Code und Datenbankschema zueinander passen, gibt es darüber hinaus **nicht**. Wer älteren Code auf eine neuere Datenbank startet, bekommt Fehler zur Laufzeit. Deshalb gehört zum Rollback das Downgrade der Migrationen (siehe unten).

---

## Standard-Update (empfohlen)

```bash
cd /opt/botballdashboard
./scripts/update.sh
```

Das Skript:

1. speichert den laufenden Commit, die Alembic-Revision und das Image-Tag in `.deploy-state` (für den Rollback) und taggt die **laufenden** Images als `botballdashboard-backend:<commit>` bzw. `botballdashboard-frontend:<commit>`. Läuft das Backend gerade nicht (z. B. nach einem abgebrochenen Update), bleibt der bisherige Rollback-Punkt stehen,
2. holt mit `git pull --ff-only` den neuen Stand (`--ref v1.4` für einen Tag/Branch/Commit, `--no-pull` baut nur neu). Hat sich dabei `scripts/update.sh` selbst geändert, macht die neue Fassung weiter,
3. baut die Backend-Images (`backend`, `worker`, `worker-ocr`, `beat`, `backup` und die Init-Dienste `volume-permissions`/`backup-permissions` – alle ein Image `botballdashboard-backend:local`) mit aktuellen Basis-Images neu,
4. baut das Frontend: mit `pnpm` auf dem Host (wie beim Proxmox-Setup, `frontend/Dockerfile.prebuilt`), ohne `pnpm` per `docker compose build frontend`. Die Wahl lässt sich mit `FRONTEND_BUILD=host|docker` erzwingen. Beide neuen Images bekommen zusätzlich das Tag des neuen Commits; die fünf neuesten Release-Tags bleiben erhalten, ältere werden entfernt,
5. erstellt mit dem **neuen** Image ein **verifiziertes Backup**, während die alte Version noch läuft: `backup_scheduler.py once --verify` sichert und spielt das neue Archiv sofort testweise ein (Restore-Test mit dem Test-Schlüssel, siehe [Betrieb → Restore test](../../operations.md#restore-test-automatic-weekly); ohne Test-Schlüssel wird die Prüfsumme geprüft). Scheitert das, bricht das Update ab, bevor etwas migriert wird. Der Archivname steht danach als `PRE_UPDATE_BACKUP` in `.deploy-state`. Ohne Profil `production` (kein Backup-Dienst) oder ohne laufende Datenbank (Neuinstallation) gibt es eine Warnung statt eines Backups; `--skip-backup` überspringt es (nicht empfohlen),
6. zieht die Datenbank auf eine neue PostgreSQL-Hauptversion um, falls `docker-compose.yml` eine verlangt (`scripts/postgres-upgrade.sh`, siehe unten). Sonst passiert hier nichts,
7. startet mit `docker compose up -d --remove-orphans` neu und wartet auf das gesunde Backend,
8. führt `scripts/verify-deployment.sh` aus und endet mit Fehlercode, wenn eine Prüfung fehlschlägt.

**Detached HEAD.** Nach `--ref <tag|commit>`, einem Deploy aus GitHub (der einen Commit auscheckt) oder einem Rollback steht der Checkout auf keinem Branch. Ein einfaches `./scripts/update.sh` bricht dann nicht mehr in `git pull` ab: es meldet den Zustand, checkt den verfolgten Branch wieder aus (`UPDATE_BRANCH`, sonst den Standard-Branch des Remotes, also `main`) und holt dessen neuesten Stand – „Update“ heißt immer „neuester Stand des Branches“. Wer auf einem bestimmten Release bleiben will, nimmt `--ref <tag>`; `--no-pull` baut genau den ausgecheckten Commit neu.

Manuell entspricht das:

```bash
git pull --ff-only
docker compose build --pull volume-permissions backup-permissions backend worker worker-ocr beat backup
# Frontend: entweder im Container …
docker compose build --pull frontend
# … oder (Proxmox-LXC) auf dem Host:
(cd frontend && pnpm install --frozen-lockfile && VITE_API_URL=/api VITE_VAPID_PUBLIC_KEY=<aus .env> pnpm build)
docker build -f frontend/Dockerfile.prebuilt -t botballdashboard-frontend:local frontend
docker compose run --rm --no-deps backup-permissions
docker compose run --rm --no-deps backup python scripts/backup_scheduler.py once --verify
./scripts/postgres-upgrade.sh     # nur nötig bei neuer PostgreSQL-Hauptversion, sonst ohne Wirkung
docker compose up -d --remove-orphans
./scripts/verify-deployment.sh
```

Updates lassen sich auch aus GitHub starten: Actions → **Deploy** → *Run workflow*. Der Workflow löst den `ref` zu einem Commit auf und deployt nur, wenn für **genau diesen Commit** ein erfolgreicher Lauf des CI-Workflows existiert (CI wird von Hand gestartet: Actions → CI → *Run workflow*). Dann führt er per SSH `scripts/update.sh --ref <commit>` auf dem Server aus – mit demselben verifizierten Backup vor den Migrationen. Siehe [Deployment](../technical/deployment.md#deploy-aus-github).

---

## Versionshinweis: PostgreSQL 18, Redis 8 und Python 3.14 (2026-09)

| Komponente | vorher | jetzt |
|---|---|---|
| Datenbank | `postgres:16-alpine` | `postgres:18-alpine` (18.6) |
| Redis | `redis:7-alpine` | `redis:8-alpine` (8.10) |
| Backend-Image | `python:3.11-slim`, `postgresql-client` von Debian (17) | `python:3.14-slim` (Debian 13), `postgresql-client-18` von apt.postgresql.org |

### Ablauf

**Dieses eine Mal** den Code vorher holen, damit schon das neue `update.sh` läuft (das alte kennt den Datenbank-Umzug nicht):

```bash
cd /opt/botballdashboard
make backup-now                      # Backup von vor dem Umzug
pct snapshot 105 pre-pg18            # auf dem Proxmox-Host, ID anpassen
git pull --ff-only
./scripts/update.sh --no-pull
```

`update.sh` baut zuerst die Images (die Anwendung läuft währenddessen weiter) und ruft dann `scripts/postgres-upgrade.sh` auf. Das Skript

1. stoppt `backend`, `worker`, `worker-ocr`, `beat`, `backup`, `postgres-exporter` und `db`,
2. startet PostgreSQL 16 in einem temporären Container ohne Netzwerk auf den alten Dateien, erstellt einen Dump (`pg_dump -Fc` derselben Version), liest ihn zur Kontrolle zurück und zählt die Zeilen jeder Tabelle,
3. legt PostgreSQL 18 in einem Zwischenverzeichnis desselben Volumes an (gleicher Benutzer, gleiches Passwort, gleiche Locale wie eine Neuinstallation), spielt den Dump in **einer** Transaktion ein, vergleicht Tabelle für Tabelle die Zeilenzahlen und die Alembic-Revision und führt `ANALYZE` aus,
4. benennt das Zwischenverzeichnis erst danach in `18/docker` um. Danach startet `update.sh` den Stack wie gewohnt.

Die Ausgabe endet mit `Verified: all … tables have the same row counts`. Der Umzug dauert bei einer üblichen Veranstaltungsdatenbank Sekunden; so lange ist die Anwendung aus.

**Wo liegen die Daten?** Ab PostgreSQL 18 liegt der Cluster in einem Unterverzeichnis je Hauptversion. Das Volume `pgdata` (Proxmox: `/data/db`) ist deshalb jetzt unter `/var/lib/postgresql` eingebunden, nicht mehr unter `/var/lib/postgresql/data`:

```
/data/db/                      PostgreSQL 16 (alt, unverändert – Rollback-Kopie)
/data/db/18/docker/            PostgreSQL 18 (neu, in Betrieb)
/data/db/18/botball-upgrade.info   Vermerk des Umzugs
```

Dump, Zeilenzahlen, die Rollenliste (ohne Passwörter) und ein Protokoll liegen in `/opt/botballdashboard/pg-upgrade/` (Modus 700). Der Dump enthält die kompletten Daten; nach dem erfolgreichen Umzug wird er mit `age` an `AGE_RECIPIENT` **verschlüsselt** (`*.dump.age`) und die unverschlüsselte Datei gelöscht. Ohne `AGE_RECIPIENT` bleibt er unverschlüsselt (Modus 600), das Skript weist darauf hin. Platzbedarf im Volume: etwa die Größe der alten Datenbank plus 256 MB; in `pg-upgrade/` bis zur Größe der alten Datenbank (wird vor dem Dump geprüft, sonst `PG_UPGRADE_DIR` auf eine größere Platte legen).

**Aufräumen** nach einigen Tagen Betrieb, wenn kein Rollback mehr nötig ist:

```bash
./scripts/postgres-upgrade.sh --remove-old-data   # fragt nach „DELETE“; löscht alten Cluster und Dumps
```

### Wenn etwas schiefgeht

- **Der Umzug bricht ab** (z. B. Fehler beim Einspielen, abweichende Zeilenzahlen, zu wenig Platz): Das Skript entfernt das halbfertige Verzeichnis wieder. Die Dateien von PostgreSQL 16 sind unverändert. Entweder die Ursache beheben und `./scripts/postgres-upgrade.sh` erneut starten, oder zurück zur alten Version: `./scripts/update.sh --rollback` (Option 2 unten; startet die vorherigen Images ohne Neubau, PostgreSQL 16 auf den unveränderten Dateien).
- **Update mit dem alten `update.sh` gestartet** (ohne vorheriges `git pull`): Das alte Skript baut die neuen Images und startet sie. Der Datenbank-Container mit PostgreSQL 18 verweigert dann den Start, weil im Volume noch Daten von PostgreSQL 16 liegen („there appears to be PostgreSQL data in /var/lib/postgresql“). Es wird nichts verändert. `./scripts/update.sh --no-pull` erledigt den Umzug und startet alles.
- **Rollback nach dem Umzug** (Option 2 unten) startet wieder PostgreSQL 16 auf den alten Dateien. Alles, was seit dem Umzug in PostgreSQL 18 erfasst wurde, fehlt dort; wer das braucht, spielt vorher ein Backup ein (Option 3). Beim nächsten Update erkennt `postgres-upgrade.sh`, dass PostgreSQL 16 nach dem Umzug wieder lief, und fragt nach: `./scripts/postgres-upgrade.sh --redo` zieht den aktuellen Stand von PostgreSQL 16 erneut um (die bisherige 18er-Kopie bleibt als `18/docker.replaced-<Zeit>` erhalten), `--keep-new` arbeitet mit den 18er-Daten weiter. Bis dahin startet der Datenbank-Container nicht, damit die Anwendung nicht unbemerkt auf der veralteten Kopie läuft.
- **Redis beim Rollback:** Redis 8 schreibt seine Datei (`dump.rdb`) in einem Format, das Redis 7 nicht lesen kann („Can't handle RDB format version“). Vor dem Start der alten Version die Redis-Daten verwerfen: `docker compose stop redis && docker run --rm -v botballdashboard_redisdata:/data redis:7-alpine rm -f /data/dump.rdb`. Verloren gehen nur flüchtige Daten: Cache, Rate-Limit-Zähler, noch nicht abgearbeitete Celery-Aufträge und die Sperrliste widerrufener Access-Tokens (die ohnehin nach 15 Minuten ablaufen).

### Redis 8

Redis 8 liest die Daten von Redis 7 ohne Umwandlung; `update.sh` holt das neue Image mit `docker compose pull`. Die Anwendung nutzt nur Grundfunktionen (Pub/Sub für Live-Updates, Cache, Rate-Limits per Lua-Skript, Token-Sperrliste, Celery-Broker), der Client `redis-py` 8.1 unterstützt Redis 8. Das offizielle Image lädt zusätzlich die Module für JSON, Suche, Zeitreihen und Bloom-Filter; die Anwendung nutzt sie nicht, sie kosten einige MB Speicher.

Lizenz: Redis 8 steht wahlweise unter AGPLv3, RSALv2 oder SSPLv1 (Redis 7.2 und älter: BSD-3-Clause; das bisher genutzte 7.4: RSALv2 oder SSPLv1). Das Dashboard verwendet Redis unverändert als internen Dienst im eigenen Stack. Wer Redis verändert, weiterverteilt oder als Dienst für Dritte anbietet, prüft die Bedingungen der gewählten Lizenz.

### Python 3.14

Backend, Worker, Beat und Backup laufen mit Python 3.14 (vorher 3.11). Alle Abhängigkeiten sind auf ihrem neuesten stabilen Stand und haben Wheels für 3.14 (x86-64 und ARM64). Für den Betrieb ist nichts zu tun, `update.sh` baut die Images neu. Wer lokal ohne Docker entwickelt, braucht Python 3.14 (`uv python install 3.14`).

---

## Versionshinweis: Node.js 24 und neue Monitoring-Images (2026-09)

Das Frontend wird mit **Node.js 24 LTS** gebaut (Docker-Image `node:24-alpine`, CI, `proxmox-setup.sh`). Beim Bau im Container ist nichts zu tun. Auf Proxmox-LXC baut `update.sh` das Frontend auf dem Host. Dort bleibt das vorhandene Node 22 installiert, und `update.sh` gibt eine Warnung aus. Node 22 baut vorerst weiter. Upgrade auf dem Host:

```bash
curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
apt-get install -y nodejs
corepack enable && corepack prepare pnpm@10.29.3 --activate
node --version   # v24.x
```

Das Profil `monitoring` nutzt jetzt Prometheus v3.15.0, Alertmanager v0.34.1 und Blackbox-Exporter v0.28.0. Die Konfigurationen bleiben unverändert, die Daten in `prometheusdata` und `alertmanagerdata` werden weiterverwendet. `update.sh` lädt die neuen Images mit `docker compose pull`.

## Versionshinweis: Container ohne Root-Rechte (Security-Update 2026-09)

Ab diesem Stand laufen `backend`, `worker`, `worker-ocr`, `beat` und `backup` als unprivilegierter Benutzer `app` (**UID/GID 10001**) statt als `root`, ohne Linux-Capabilities (`cap_drop: ALL`), mit `no-new-privileges` und mit Speicherlimits (`*_MEM_LIMIT` in `.env`). `backend`, `worker`, `worker-ocr` und `beat` haben zusätzlich ein schreibgeschütztes Root-Dateisystem; beschreibbar sind nur ihre Volumes und `/tmp` (tmpfs).

Dateien, die ältere Versionen als `root` angelegt haben (Uploads, VAPID-Schlüssel, Backup-Archive, Off-site-Zugangsdaten), gehören danach dem falschen Benutzer. **Das erledigt der Start automatisch:** zwei einmalig laufende Init-Container stellen vor dem Start der Anwendung die Eigentümer um und beenden sich wieder:

| Dienst | Verzeichnisse | Profil |
|---|---|---|
| `volume-permissions` | Volumes `uploads` (`/app/uploads`), `vapid` (`/app/vapid`) | immer |
| `backup-permissions` | `BACKUP_HOST_DIR` bzw. Volume `backups` (`/backups`), `BACKUP_OFFSITE_CONFIG_DIR` (`/offsite-config`) | `production` |

Sie laufen als `root`, aber nur mit den Capabilities `CHOWN` und `DAC_READ_SEARCH`, ohne Netzwerk, und ändern nur Einträge, die noch nicht UID 10001 gehören (Symlinks selbst, nie ihr Ziel). Beim ersten Start nach dem Update steht im Log, wie viele Einträge umgestellt wurden (`docker compose logs volume-permissions backup-permissions`); jeder weitere Start ändert nichts. `scripts/update.sh` baut die beiden Dienste mit.

Wer lieber vorab und von Hand umstellt (z. B. vor dem ersten Start oder bei einem eigenen Compose-Setup ohne die Init-Dienste):

```bash
cd /opt/botballdashboard
docker compose stop backend worker worker-ocr beat backup
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

`update.sh` erstellt das verifizierte Backup selbst (Schritt 5 oben). Ein Proxmox-Snapshot sichert zusätzlich Code, Images und Daten in einem Schritt:

```bash
# Verschlüsseltes Backup (Datenbank + Uploads) von Hand, z. B. vor Arbeiten ohne update.sh
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

### Option 2: Vorherige Version starten, Daten behalten (ohne Neubau)

Nur möglich, wenn die neuen Migrationen ein funktionierendes `downgrade` haben. `.deploy-state` enthält den vorherigen Commit, die vorherige Alembic-Revision und das Image-Tag der vorherigen Version.

```bash
cd /opt/botballdashboard
cat .deploy-state          # PREVIOUS_COMMIT=…  PREVIOUS_ALEMBIC_REVISION=…  PREVIOUS_IMAGE_TAG=…
./scripts/update.sh --rollback
```

Das Skript

1. prüft, dass die vorherigen Images (`…-backend:<PREVIOUS_IMAGE_TAG>`, `…-frontend:<PREVIOUS_IMAGE_TAG>`) noch da sind, der Commit vorhanden ist und der Checkout keine lokalen Änderungen hat – erst danach wird etwas angehalten,
2. erstellt ein verifiziertes Backup des aktuellen Stands,
3. hält `backend`, `worker`, `worker-ocr`, `beat` und `backup` an (Datenbank und Redis laufen weiter),
4. rollt die Migrationen mit dem **aktuellen** Image in einem Einmal-Container zurück (`docker compose run --rm --no-deps backend alembic downgrade <PREVIOUS_ALEMBIC_REVISION>`). Nur der neue Code kennt die neuen Revisionen und ihre `downgrade()`-Schritte. Weil das Backend dabei angehalten ist, kann kein Neustart (Healthcheck, OOM, `restart: unless-stopped`) die Datenbank über `migrate-then-start.sh` wieder hochziehen,
5. checkt den vorherigen Commit aus (Compose-Datei und Skripte der alten Version), taggt die vorherigen Images wieder als `:local` und startet sie mit `docker compose up -d --no-build` – **ohne Neubau**, also auch ohne Netz und in Sekunden. Das alte Backend führt beim Start zwar `alembic upgrade head` aus, aber sein `head` ist genau die Revision, auf die gerade zurückgerollt wurde: es wird nichts erneut migriert,
6. wartet auf das gesunde Backend und führt `verify-deployment.sh` (der alten Version) aus.

Danach steht der Checkout auf einem detached HEAD; ein späteres `./scripts/update.sh` folgt wieder dem Branch (siehe oben).

Von Hand entspricht das (Tags aus `.deploy-state`, Image-Präfix `botballdashboard`):

```bash
docker compose stop backend worker worker-ocr beat backup
docker compose run --rm --no-deps backend alembic downgrade <PREVIOUS_ALEMBIC_REVISION>
git checkout <PREVIOUS_COMMIT>
docker tag botballdashboard-backend:<PREVIOUS_IMAGE_TAG> botballdashboard-backend:local
docker tag botballdashboard-frontend:<PREVIOUS_IMAGE_TAG> botballdashboard-frontend:local
docker compose up -d --no-build --remove-orphans
./scripts/verify-deployment.sh
```

**Nicht** `docker compose exec backend alembic downgrade …` im laufenden neuen Backend: startet dieser Container danach neu, spielt `migrate-then-start.sh` sofort wieder `upgrade head` ein.

Sind die vorherigen Images nicht mehr vorhanden (Installation älter als die Release-Tags, oder aufgeräumt), meldet `--rollback` das; dann alten Code auschecken und neu bauen: `git checkout <PREVIOUS_COMMIT> && ./scripts/update.sh --no-pull` (nach dem Downgrade wie oben).

Einschränkungen:
- Datenmigrationen oder gelöschte Spalten lassen sich per `downgrade` nicht immer verlustfrei umkehren. Im Zweifel Option 1 oder Option 3 verwenden.
- Ist das Backend nach dem Update gar nicht gestartet, wurden die Migrationen evtl. nur teilweise eingespielt: `docker compose run --rm backend alembic current` zeigt den Stand.
- Zurück über einen Wechsel der PostgreSQL- oder Redis-Hauptversion (z. B. auf einen Stand mit PostgreSQL 16 / Redis 7): siehe [Wenn etwas schiefgeht](#wenn-etwas-schiefgeht). Die alte PostgreSQL-Version startet auf ihren unveränderten Dateien, die Redis-Datei muss vorher weg.

### Option 3: Backup von vor dem Update wiederherstellen

Vorherige Version starten (Option 2 ohne den Downgrade-Schritt, oder alten Code auschecken und neu bauen), dann das Backup von vor dem Update einspielen – sein Name steht als `PRE_UPDATE_BACKUP` in `.deploy-state`, siehe [Betrieb → Wiederherstellung](../../operations.md#restore-in-production). Das Backend führt danach beim Start die Migrationen bis zum Stand des alten Codes aus.

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
[ ] Proxmox-Snapshot angelegt
[ ] ./scripts/update.sh ohne Fehler durchgelaufen (enthält das verifizierte Backup: "Verified backup: …")
[ ] verify-deployment.sh: keine FAIL-Zeile
[ ] Im Browser getestet → Login, Scoreboard, Live-Updates funktionieren
[ ] Snapshot nach 48 h löschen
```
