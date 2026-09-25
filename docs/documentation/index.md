# BotballDashboard – Dokumentation

Vollständige Dokumentation des BotballDashboard-Systems. Enthält Installationsanleitungen, Konfigurationsreferenz, Benutzerhandbuch und technische Dokumentation.

---

## Inhaltsverzeichnis

### Installation & Setup
| Dokument | Beschreibung |
|---|---|
| [Systemanforderungen](installation/requirements.md) | Hardware, Software, Netzwerk |
| [Quickstart-Guide](installation/quickstart.md) | Schnellinstallation mit Docker Compose |
| [Proxmox-Setup](installation/proxmox-setup.md) | Installation auf Proxmox-VM/LXC |
| [Konfigurationsreferenz](installation/configuration.md) | Alle `.env`-Variablen und Einstellungen |
| [Update-Anleitung](installation/update.md) | System aktualisieren ohne Datenverlust |

### Benutzerhandbuch
| Dokument | Zielgruppe |
|---|---|
| [Übersicht & Rollen](user-manual/index.md) | Alle Benutzer |
| [Admin-Handbuch](user-manual/admin.md) | System-Admins |
| [Juror-Handbuch](user-manual/juror.md) | Schiedsrichter / Score-Eingabe |
| [Reviewer-Handbuch](user-manual/reviewer.md) | Paper-Reviewer |
| [Mentor-Handbuch](user-manual/mentor.md) | Team-Betreuer |
| [Gast-Ansicht](user-manual/guest.md) | Öffentliche Event-Seite, Gast-Konto |
| [FAQ](user-manual/faq.md) | Alle Benutzer |

### Technische Dokumentation
| Dokument | Beschreibung |
|---|---|
| [Systemarchitektur](technical/architecture.md) | Dienste, Worker/Beat, Live-Stream, Modul-Aktivierung, Formel-Engine |
| [API-Referenz](technical/api-reference.md) | Alle REST-Endpunkte mit Rechten, Fehlerformat, Rate-Limits |
| [Datenbankschema](technical/database.md) | Alle Tabellen, ERD, Migrationen |
| [Statische Modul-Registry](technical/plugins.md) | Module konsistent erweitern |
| [Deployment & Betrieb](technical/deployment.md) | Produktion, Monitoring, Backup |

---

## Schnellzugriff nach Aufgabe

| Ich möchte … | → |
|---|---|
| Das System zum ersten Mal installieren | [Quickstart-Guide](installation/quickstart.md) |
| Das System auf Proxmox installieren | [Proxmox-Setup](installation/proxmox-setup.md) |
| Das System aktualisieren | [Update-Anleitung](installation/update.md) |
| Einen neuen Benutzer anlegen | [Admin-Handbuch → Benutzer](user-manual/admin.md#benutzer) |
| Eine neue Saison erstellen | [Admin-Handbuch → Saisons](user-manual/admin.md#saisons) |
| Ein Event einrichten | [Admin-Handbuch → Events einrichten](user-manual/admin.md#events-einrichten) |
| Scores eingeben | [Juror-Handbuch](user-manual/juror.md) |
| Ein Paper reviewen | [Reviewer-Handbuch](user-manual/reviewer.md) |
| Druckjobs verwalten | [Admin-Handbuch → 3D-Druck](user-manual/admin.md#3d-druck) |
| Die API nutzen | [API-Referenz](technical/api-reference.md) |
| Ein Modul erweitern | [Statische Modul-Registry](technical/plugins.md) |

---

## Versions-Information

| | |
|---|---|
| Änderungen | [CHANGELOG.md](../../CHANGELOG.md) |
| Datenbank-Stand | Migration `0029` |
| Backend | FastAPI (Python 3.11), Celery-Worker und -Beat |
| Frontend | React 18 + Vite + Tailwind CSS, PWA |
| Datenbank | PostgreSQL 16, Redis 7 |
| Deployment | Docker Compose auf Proxmox |
