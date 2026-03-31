# Modul 01 – Projekt-Setup & Infrastruktur

**Status:** [ ] Offen  
**Typ:** Basis (kein Plugin)  
**Kommuniziert mit:** Allen anderen Modulen

---

## Beschreibung

Grundgerüst des gesamten Projekts. Definiert Tech-Stack, Verzeichnisstruktur, lokale Entwicklungsumgebung, CI/CD und den Plugin-Mechanismus über den sich alle Fachmodule beim Kern registrieren.

---

## Features

### Monorepo-Struktur
- `/core` – Kern (Auth, Team-, Saisonverwaltung)
- `/modules/scoring` – Scoring-Plugin
- `/modules/paper-review` – Paper-Review-Plugin
- `/modules/print` – 3D-Druck-Plugin
- `/frontend` – React-Anwendung
- `/docs` – Dokumentation & Modul-Beschreibungen

### Plugin-Registry
- Jedes Modul liefert ein `manifest.json` mit: Name, Version, API-Routen, UI-Komponenten, benötigte Rollen
- Kern liest beim Start alle Manifeste ein und registriert die Module
- Module können aktiviert/deaktiviert werden (pro Saison konfigurierbar)

### Datenbank-Migrationsstrategie (Zero Data Loss bei Updates)

Das System ist so aufgebaut, dass bei jedem Upgrade **nur die Programmkomponenten aktualisiert werden** – die Datenbank und ihre Daten bleiben immer erhalten:

- **Migrations-Tool:** Alembic (Python) oder Django Migrations – jede Schemaänderung wird als versioniertes Migrationsskript gespeichert
- **Beim Deployment:** Migrations werden automatisch vor dem Start der neuen Version ausgeführt (`migrate → then start`)
- **Keine destruktiven Migrationen:** Spalten/Tabellen werden nie gelöscht ohne vorherige Deprecation-Phase (erst umbenennen, dann in nächster Version löschen)
- **Rollback-fähig:** Jede Migration hat eine `upgrade()`- und `downgrade()`-Funktion
- **Daten-Backups:** Vor jedem Deployment wird automatisch ein Datenbank-Dump erstellt
- **Docker-Strategie:** Datenbank läuft in einem separaten Container mit persistentem Volume – ein `docker-compose pull && docker-compose up` aktualisiert nur Backend/Frontend, das DB-Volume bleibt unangetastet
- **Versionierung:** Backend-Version und DB-Schema-Version werden in der DB gespeichert (`schema_version`-Tabelle) → Inkompatibilitäten werden beim Start erkannt und verhindert

```yaml
# docker-compose.yml Prinzip
services:
  db:
    image: postgres:16
    volumes:
      - db_data:/var/lib/postgresql/data   # persistentes Volume
  backend:
    image: botballdashboard-backend:latest
    command: ["migrate-then-start"]        # Migrationen vor Start
volumes:
  db_data:  # bleibt bei docker-compose up/pull erhalten
```

### Docker & lokale Entwicklung
- `docker-compose.yml` startet: Backend, Frontend, PostgreSQL, (optional) OCR-Service
- Separate Container pro Modul möglich
- `.env`-Datei für lokale Konfiguration
- Datenbank-Volume wird nie automatisch gelöscht

### CI/CD (GitHub Actions)
- Linting & Formatting bei jedem Push
- Automatische Tests bei Pull Requests
- Build & Deploy bei Merge in `main`

### Mehrsprachigkeit (i18n)

- **Sprachen:** Deutsch und Englisch
- **Umschaltung:** Ein-Klick-Sprachumschalter in der Navigation (DE | EN)
- **Technologie:** i18next (React) – alle UI-Texte als Übersetzungs-Keys
- Sprachpräferenz wird im User-Profil gespeichert (persistent nach Login)
- Fallback auf Englisch wenn Übersetzung fehlt
- **Scope:** Gesamte UI (alle Module, Fehlermeldungen, E-Mail-Vorlagen)

### Dark / Light Mode

- Systemeinstellung wird automatisch erkannt (`prefers-color-scheme`)
- Manueller Umschalter in der Navigation (Sonne/Mond-Icon)
- Einstellung wird im User-Profil gespeichert (persistent)
- Tailwind CSS `dark:`-Klassen für alle Komponenten

### Responsive Design (alle Geräte)
Die Website muss auf allen Geräteklassen gut nutzbar sein:

| Gerät | Breite | Anforderungen |
|---|---|---|
| Handy | < 640px | Touch-optimiert, große Buttons, vertikales Layout |
| Tablet | 640–1024px | Angepasstes Grid, gut lesbare Tabellen |
| Laptop | 1024–1440px | Volle Funktionalität, mehrspaltige Layouts |
| Desktop/PC | > 1440px | Optimale Nutzung des Bildschirmplatzes |

- CSS Framework mit eingebautem Breakpoint-System (z.B. Tailwind CSS)
- Alle Formulare (Score-Eingabe, Paper-Upload, Review) touch-freundlich
- Tabellen bei kleinen Screens horizontal scrollbar oder in Card-Layout umgebrochen
- Navigation: Hamburger-Menü auf Mobile, Sidebar auf Desktop
- Schriftgrößen und Abstände responsive skaliert
- Getestet auf: Chrome/Safari Mobile, Chrome/Firefox Desktop

### Tech-Stack-Entscheidungen

**Backend-Framework: FastAPI**
- Modernes Python-Framework mit nativer async-Unterstützung
- Automatische OpenAPI/Swagger-Docs aus dem Code generiert
- Typ-Validierung via Pydantic (saubere Datenmodelle, weniger Boilerplate)
- Besser geeignet für reine API-Server als Django (kein ORM-Overhead, keine Template-Engine nötig)
- Alembic als Migrations-Tool (funktioniert problemlos mit FastAPI + SQLAlchemy)

**Monorepo-Setup: Einfaches pnpm Workspaces**
- Kein Turborepo/Nx-Overhead für diesen Projektumfang
- `pnpm workspaces` für Frontend-Pakete
- Python-Backend als separates Package im selben Repo
- Shared Types zwischen Frontend und Backend via OpenAPI-Codegen (FastAPI → TypeScript-Typen)

**Deployment: Self-hosted auf Proxmox**
- Proxmox-VM mit Docker + Docker Compose
- Jeder Service als eigener Container: Backend, Frontend (Nginx), PostgreSQL, (optional OCR-Service)
- Persistente Volumes für DB und Uploads bleiben bei Updates erhalten
- Proxmox-Snapshot vor jedem Deployment als zusätzliche Sicherheit
- Reverse Proxy: Traefik oder Nginx Proxy Manager (beide Proxmox-kompatibel)
- Empfehlung: eigene Proxmox-LXC für DB (leichter als VM, persistentes Storage)

### Code-Qualität
- Linter: ESLint (Frontend), Ruff (Backend)
- Formatter: Prettier (Frontend), Black (Backend)
- Pre-commit Hooks

---

## Schnittstellen zu anderen Modulen

| Richtung | Modul | Art |
|---|---|---|
| → | Alle Module | Plugin-Registry API |
| → | Alle Module | Docker-Netzwerk |
| → | Alle Module | Shared Environment Variables |

---

## Entschiedene Tech-Stack-Fragen
- [x] **Backend-Framework:** FastAPI (async, Pydantic, automatische OpenAPI-Docs)
- [x] **Monorepo-Tool:** pnpm Workspaces (kein Turborepo/Nx-Overhead nötig)
- [x] **Hosting:** Self-hosted auf Proxmox (Docker Compose, Traefik als Reverse Proxy)
