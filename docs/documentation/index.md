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
| [Gast-Ansicht](user-manual/guest.md) | Öffentliche Rangliste & Scoreboard |

### Technische Dokumentation
| Dokument | Beschreibung |
|---|---|
| [Systemarchitektur](technical/architecture.md) | Überblick, Komponenten, Plugin-System |
| [API-Referenz](technical/api-reference.md) | Alle REST-Endpunkte |
| [Datenbankschema](technical/database.md) | Modelle, Relationen, Migrationen |
| [Plugin-Entwicklung](technical/plugins.md) | Eigene Module entwickeln |
| [Deployment & Betrieb](technical/deployment.md) | Produktion, Monitoring, Backup |

---

## Schnellzugriff nach Aufgabe

| Ich möchte … | → |
|---|---|
| Das System zum ersten Mal installieren | [Quickstart-Guide](installation/quickstart.md) |
| Das System auf Proxmox installieren | [Proxmox-Setup](installation/proxmox-setup.md) |
| Das System aktualisieren | [Update-Anleitung](installation/update.md) |
| Einen neuen Benutzer anlegen | [Admin-Handbuch → Benutzerverwaltung](user-manual/admin.md#benutzerverwaltung) |
| Eine neue Saison erstellen | [Admin-Handbuch → Saisonverwaltung](user-manual/admin.md#saisonverwaltung) |
| Scores eingeben | [Juror-Handbuch](user-manual/juror.md) |
| Ein Paper reviewen | [Reviewer-Handbuch](user-manual/reviewer.md) |
| Druckjobs verwalten | [Admin-Handbuch → 3D-Druck](user-manual/admin.md#3d-druck) |
| Die API nutzen | [API-Referenz](technical/api-reference.md) |
| Ein Plugin entwickeln | [Plugin-Entwicklung](technical/plugins.md) |

---

## Versions-Information

| | |
|---|---|
| Aktuellste Version | _wird nach erstem Release ergänzt_ |
| Backend | FastAPI (Python) |
| Frontend | React + Tailwind CSS |
| Datenbank | PostgreSQL 16 |
| Deployment | Docker Compose auf Proxmox |
