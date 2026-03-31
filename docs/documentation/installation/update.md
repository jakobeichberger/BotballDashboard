# Update-Anleitung

Das BotballDashboard ist so gebaut, dass Updates **ohne Datenverlust** durchgeführt werden können. Nur die Programmkomponenten (Backend, Frontend) werden aktualisiert — Datenbank und Uploads bleiben immer erhalten.

---

## Prinzip: Migrate → Then Start

```
1. Proxmox-Snapshot erstellen (Sicherheit)
2. Neues Docker-Image pullen
3. Datenbank-Migrationen automatisch ausführen
4. Neue Version starten
```

Das Backend führt beim Start automatisch alle ausstehenden Datenbankmigrationen aus (`migrate-then-start`-Strategie). Das System prüft ob Backend-Version und DB-Schema-Version kompatibel sind und verhindert einen Start bei Inkompatibilität.

---

## Standard-Update (empfohlen)

```bash
# 1. In das Projektverzeichnis wechseln
cd /opt/botballdashboard

# 2. Neueste Änderungen holen
git pull origin main

# 3. Neue Images bauen/pullen und starten
docker compose pull
docker compose up -d

# 4. Logs prüfen
docker compose logs backend --tail=50
```

Der Befehl `docker compose up -d` startet automatisch nur die Container neu, deren Image sich geändert hat. Das DB-Volume `db_data` wird dabei **nie** angefasst.

---

## Vor einem Update: Snapshot & Backup

```bash
# Datenbank-Backup (manuell vor dem Update)
docker compose exec db pg_dump -U botball botball_db \
  | gzip > /data/backups/pre-update-$(date +%Y%m%d-%H%M).sql.gz

# Proxmox-Snapshot (über Proxmox-WebUI oder CLI)
pvesh create /nodes/proxmox/qemu/100/snapshot \
  --snapname "pre-update-$(date +%Y%m%d)" \
  --description "Before update to $(git log -1 --format='%h %s')"
```

---

## Rollback nach fehlgeschlagenem Update

### Option 1: Proxmox-Snapshot wiederherstellen (einfachste Methode)

```bash
# Über Proxmox WebUI: VM → Snapshots → Snapshot auswählen → Rollback
# Oder via CLI:
pvesh create /nodes/proxmox/qemu/100/snapshot/pre-update-20240315/rollback
```

### Option 2: Datenbank-Rollback + altes Docker-Image

```bash
# Alte Datenbankversion wiederherstellen
gunzip < /data/backups/pre-update-20240315.sql.gz \
  | docker compose exec -T db psql -U botball botball_db

# Altes Docker-Image starten (Tag aus Git-History)
git checkout v1.2.3
docker compose up -d
```

---

## Datenbank-Migrationen manuell ausführen

Normalerweise werden Migrationen automatisch beim Start ausgeführt. Falls manuell nötig:

```bash
docker compose exec backend alembic upgrade head
```

Migrationshistorie anzeigen:
```bash
docker compose exec backend alembic history
docker compose exec backend alembic current
```

Downgrade (eine Version zurück):
```bash
docker compose exec backend alembic downgrade -1
```

---

## Schema-Versionscheck

Das System speichert Backend-Version und DB-Schema-Version in der `schema_version`-Tabelle. Bei Inkompatibilität wird der Start mit einer klaren Fehlermeldung abgebrochen:

```
ERROR: Backend v2.0.0 requires DB schema v10, but current schema is v8.
       Run migrations first: docker compose exec backend alembic upgrade head
```

---

## Update-Checkliste

```
[ ] Proxmox-Snapshot angelegt
[ ] Datenbank-Backup erstellt
[ ] git pull ausgeführt
[ ] docker compose pull ausgeführt
[ ] docker compose up -d ausgeführt
[ ] docker compose logs backend geprüft → keine Fehler
[ ] Im Browser getestet → Login funktioniert
[ ] Backup-Snapshot kann gelöscht werden (nach 48h)
```
