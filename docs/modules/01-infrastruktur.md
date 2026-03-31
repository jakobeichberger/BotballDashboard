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

### Code-Qualität
- Linter: ESLint (Frontend), Ruff/Flake8 (Backend)
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

## Offene Fragen
- [ ] Monorepo-Tool: Turborepo, Nx oder einfaches Workspace-Setup?
- [ ] Backend-Framework: Django REST Framework oder FastAPI?
