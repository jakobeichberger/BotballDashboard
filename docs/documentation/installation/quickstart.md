# Quickstart-Guide

Schnellinstallation des BotballDashboard mit Docker Compose. Für Produktionsumgebungen auf Proxmox siehe [Proxmox-Setup](proxmox-setup.md).

---

## Voraussetzungen

- Linux-Server mit Docker + Docker Compose installiert
- Git
- Domain oder IP-Adresse
- (Optional) SSL-Zertifikat (Let's Encrypt via Traefik wird automatisch eingerichtet)

---

## 1. Repository klonen

```bash
git clone https://github.com/jakobeichberger/botballdashboard.git
cd botballdashboard
```

---

## 2. Konfiguration erstellen

```bash
cp .env.example .env
```

Pflichtfelder in `.env` anpassen:

```env
# Datenbank
POSTGRES_PASSWORD=sicheres_passwort_hier

# Sicherheit
SECRET_KEY=zufaelliger_langer_schluessel_min_32_zeichen
JWT_SECRET=weiterer_zufaelliger_schluessel

# Domain
DOMAIN=dashboard.meineschule.at
PUBLIC_SCOREBOARD_DOMAIN=scoreboard.meineschule.at   # optional

# E-Mail (SMTP)
SMTP_HOST=mail.meineschule.at
SMTP_PORT=587
SMTP_USER=dashboard@meineschule.at
SMTP_PASSWORD=smtp_passwort
SMTP_FROM=BotballDashboard <dashboard@meineschule.at>
```

> Vollständige Referenz aller Konfigurationsoptionen: [Konfigurationsreferenz](configuration.md)

---

## 3. System starten

```bash
docker compose up -d
```

Beim ersten Start werden automatisch:
- Datenbank-Schema erstellt (Alembic Migrations)
- Initiale Daten eingespielt (Rollen, Standard-Einstellungen)

Status prüfen:

```bash
docker compose ps
docker compose logs backend --tail=50
```

---

## 4. Admin-Benutzer erstellen

```bash
docker compose exec backend python manage.py create-admin \
  --email admin@meineschule.at \
  --password sicheres_passwort
```

---

## 5. Im Browser öffnen

```
https://dashboard.meineschule.at
```

Login mit den soeben erstellten Admin-Zugangsdaten.

---

## 6. Erste Schritte nach der Installation

1. **Saison anlegen:** Admin → Saisonverwaltung → Neue Saison
2. **Teams registrieren:** Admin → Teams → Team hinzufügen
3. **Benutzer einladen:** Admin → Benutzer → Benutzer einladen
4. **Drucker konfigurieren:** Admin → 3D-Drucker → Drucker hinzufügen
5. **Scoring-Schema einstellen:** Admin → Scoring → Schema bearbeiten

Detaillierte Anleitung: [Admin-Handbuch](../user-manual/admin.md)

---

## System stoppen

```bash
docker compose down
```

> **Wichtig:** `docker compose down` löscht **nicht** die Datenbank. Das persistente Volume `db_data` bleibt erhalten. Nur `docker compose down -v` würde Volumes löschen — das sollte nur bei einer kompletten Neuinstallation gemacht werden.

---

## Nächste Schritte

- [Proxmox-Setup](proxmox-setup.md) – für Produktivbetrieb auf Proxmox
- [Konfigurationsreferenz](configuration.md) – alle Einstellungsoptionen
- [Update-Anleitung](update.md) – System aktuell halten
