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

### Docker & lokale Entwicklung
- `docker-compose.yml` startet: Backend, Frontend, PostgreSQL, (optional) OCR-Service
- Separate Container pro Modul möglich
- `.env`-Datei für lokale Konfiguration

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
