# Quickstart-Guide

Schnellinstallation des BotballDashboard mit Docker Compose auf einem Linux-Server. Für eine Debian-LXC auf Proxmox gibt es ein Setup-Skript, siehe [Proxmox-Setup](proxmox-setup.md).

---

## Voraussetzungen

- Linux-Server mit Docker 24+ und dem Compose-Plugin (`docker compose version`)
- Git, Python 3 (für die Schlüssel-Befehle unten), `age` für Backup-Schlüssel (`apt install age`)
- Eine Domain, deren DNS-Eintrag auf den Server zeigt, und offene Ports 80/443. Traefik holt das Let's-Encrypt-Zertifikat automatisch.

---

## 1. Repository klonen

```bash
git clone https://github.com/jakobeichberger/BotballDashboard.git /opt/botballdashboard
cd /opt/botballdashboard
```

---

## 2. Konfiguration erstellen

```bash
cp .env.example .env
```

Diese Werte **müssen** in `.env` gesetzt werden. Mit `APP_ENV=production` startet das Backend sonst nicht. Den Grund zeigt `docker compose logs backend`.

| Variable | Wert |
|---|---|
| `APP_SECRET_KEY` | Zufallswert, mindestens 24 Zeichen |
| `JWT_SECRET_KEY` | anderer Zufallswert, mindestens 24 Zeichen |
| `POSTGRES_PASSWORD` | Zufallswert, mindestens 24 Zeichen |
| `PRINTER_CREDENTIAL_ENCRYPTION_KEY` | Fernet-Schlüssel (Befehl unten) |
| `DOMAIN` | z. B. `dashboard.meineschule.at` |
| `APP_BASE_URL`, `ALLOWED_ORIGINS` | `https://dashboard.meineschule.at` |
| `TRAEFIK_EMAIL` | Kontaktadresse für Let's Encrypt |
| `AGE_RECIPIENT` | öffentlicher Backup-Schlüssel (`age1…`). Ohne ihn schlägt jedes Backup fehl. |

Werte erzeugen:

```bash
# Secrets (dreimal ausführen: APP_SECRET_KEY, JWT_SECRET_KEY, POSTGRES_PASSWORD)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Fernet-Schlüssel für PRINTER_CREDENTIAL_ENCRYPTION_KEY
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"

# Backup-Schlüsselpaar: die Datei ist der PRIVATE Schlüssel (für die Wiederherstellung).
# Aufbewahrung sicher und nicht auf diesem Server; die ausgegebene Zeile "Public key: age1…"
# kommt nach AGE_RECIPIENT.
age-keygen -o botball-backup-identity.txt
```

`SMTP_*` ist optional. Ist `SMTP_HOST` leer, verschickt das Dashboard keine E-Mails.

> Vollständige Referenz: [Konfigurationsreferenz](configuration.md)

---

## 3. System starten

```bash
docker compose up -d --build
```

`.env.example` setzt `COMPOSE_PROFILES=production`. Damit startet neben `traefik`, `db`, `redis`, `backend`, `worker`, `worker-ocr`, `beat` und `frontend` auch der Backup-Dienst `backup`. Monitoring (Prometheus, Blackbox, Alertmanager) kommt mit `COMPOSE_PROFILES=production,monitoring` dazu.

Beim ersten Start spielt das Backend automatisch alle Datenbank-Migrationen ein (Alembic). Standardrollen und Berechtigungen werden dabei angelegt.

Status prüfen:

```bash
docker compose ps                  # alle Dienste "running", backend/worker/worker-ocr/db/redis "healthy"
./scripts/verify-deployment.sh     # PASS/WARN/FAIL je Prüfung
```

---

## 4. Admin-Benutzer erstellen

```bash
docker compose exec -e ADMIN_PASSWORD='sicheres_passwort' backend \
  python scripts/create_admin.py --email admin@meineschule.at --name Administrator
```

---

## 5. Im Browser öffnen

```
https://dashboard.meineschule.at
```

Login mit den soeben erstellten Admin-Zugangsdaten.

---

## 6. Erste Schritte nach der Installation

1. **Saison anlegen:** Einstellungen → Saisons (`/settings/seasons`)
2. **Event anlegen:** Event-Setup (`/setup`) – Saison wählen, Event erstellen und Teams registrieren
3. **Benutzer anlegen:** Einstellungen → Benutzer (`/settings/users`). Der Admin legt jedes Konto mit E-Mail, Name, Startpasswort und Rollen an und gibt das Passwort persönlich weiter. Einladungs-Links gibt es nicht.
4. **Drucker konfigurieren:** Einstellungen → Drucker (`/settings/printers`)
5. **Scoring-Schema einstellen:** im Event unter Event-Verwaltung bzw. Wertung → Score-Sheets

Detaillierte Anleitung: [Admin-Handbuch](../user-manual/admin.md)

---

## System stoppen

```bash
docker compose down
```

> **Wichtig:** `docker compose down` löscht **nicht** die Datenbank. Die Volumes (`pgdata`, `uploads`, `backups`, …) bleiben erhalten. `docker compose down -v` löscht sie. Das ist nur für eine komplette Neuinstallation gedacht.

---

## Nächste Schritte

- [Proxmox-Setup](proxmox-setup.md): Installation per Skript auf einer Proxmox-LXC
- [Konfigurationsreferenz](configuration.md): alle Einstellungen
- [Update-Anleitung](update.md): System aktuell halten
- [Betrieb](../../operations.md): Backups, Wiederherstellung, Monitoring
