# BotballDashboard

Webbasierte Plattform für die Organisation und Auswertung von Botball-Turnieren. Saisons, Events, Teams, Wertung am Spieltisch, Brackets, Paper-Review und 3D-Druck laufen in einem System. Das Backend ist FastAPI, das Frontend React (PWA). Betrieben wird es selbst gehostet mit Docker Compose.

Stand: Migration `0034` · Änderungen: [CHANGELOG.md](CHANGELOG.md) · offene Aufgaben: [docs/todo.md](docs/todo.md)

---

## Funktionen

**Turnier**
- Eventzentriert: Eine Saison hält das Regelwerk, jedes Event (Regional, ECER, GCER) hat eigene Teams, Phasen, Zeitplan, Wertungen und Ranglisten. Die Oberfläche läuft unter `/events/:eventId/…`, dazu kommt ein Einrichtungsassistent unter `/setup`.
- Module pro Event schaltbar: Seeding, Double Elimination, Paper, Dokumentation, Aerial, 3D-Druck, Bot-Galerie.
- Zeitplan-Generator für Seeding, Double Seeding, Double-Elimination-Bracket (Loser-Bracket, Grand Final, Reset-Finale, automatisches Weiterrücken) und Alliance-Paare.
- Öffentliche Event-Seite `/public/<slug>` mit Freigaben pro Bereich, Live-Aktualisierung über WebSocket, Rotation, Vollbild und QR-Code.

**Wertung**
- Strukturierte Score-Sheets:
  - Bereiche, Multiplikatoren, Entweder-oder, Seiten A/B;
  - Vorlagen 2024/2025/2026;
  - Versionierung pro Event.
- Sonderregeln der Saison:
  - Tie-Breaker-Presets aus den Game Reviews, Finals-Replay;
  - Kontakt-Bonus, „Runde verloren";
  - Schiedsrichter-Checkliste.
- Seeding nach Game Review, Ränge je Kategorie. Gesamtwertung über eine sichere Formel-Engine mit Presets (ECER 2025, Regional 2026, GCER 2026, Aerial, JBC) und Vorschau mit echten Daten.
- Mobile Wertung mit Offline-Queue, Bestätigung durch die Jury, vollständiger Revisions-Historie und lokaler OCR von Score-Sheet-Fotos.
- Scouting (externe Teams, Beobachtungen, Gegner-Rangliste) und GCER-Qualifikation.

**Paper-Review**
- Ein Paper pro Team und Saison, PDF-Versionen mit Text-Diff.
- Offizielle und interne Deadlines mit Durchsetzung und Erinnerungen.
- Automatische Reviewer-Zuweisung, fünf Kriterien, Feedback für Teams, Formalabzug, Finalisierung zum Paper-Score.

**3D-Druck**
- Druckaufträge mit Datei-Upload.
- Kontingente pro Event und Team (Soft- und Hard-Limit).
- Bambu Lab (MQTT) und OctoPrint mit Live-Status, manuelle Drucker.
- Filament-Spulen, 3D-Druck-Checkliste pro Saison.

**Teams, Analyse, Konto**
- Teams mit Suche, Saison-Details, Kader, versionierten Dokumenten und Mehrjahres-Historie.
- Performance, Statistik mit Anomalie-Erkennung, rollenbezogene Dashboards.
- Deadline-Kalender mit iCal-Abo, Exporte als CSV und PDF.
- Web Push mit Kategorien, Benachrichtigungszentrale, E-Mail-Erinnerungen.
- Passwort-Reset, Theme und Sprache im Profil, DSGVO-Datenexport und Kontolöschung.

---

## Tech-Stack

| Schicht | Technologie |
|---|---|
| Backend | Python 3.11 · FastAPI · SQLAlchemy 2.0 async · Alembic · Pydantic v2 |
| Hintergrund | Celery-Worker und -Beat (OCR mit OpenCV/Tesseract, Drucker-Polling, Outbox, Erinnerungen) |
| Daten | PostgreSQL 16 · Redis 7 (Broker, Live-Stream, Rate-Limits, Token-Sperrliste) |
| Frontend | React 19 · TypeScript 7 · Vite 8 · Tailwind CSS 4 · TanStack Query · Zustand · Recharts |
| i18n | i18next (Deutsch/Englisch; noch nicht alle Seiten übersetzt) |
| PWA | vite-plugin-pwa (Workbox) · Web Push (pywebpush/VAPID) · IndexedDB-Offline-Queue |
| Auth | PyJWT (HS256) · bcrypt · Refresh-Token als HttpOnly-Cookie · rollenbasierte Rechte mit Team-Scoping |
| E-Mail | SMTP, SendGrid als Rückfall |
| Betrieb | Docker Compose · Traefik (Let's Encrypt) · Prometheus · Alertmanager · verschlüsselte Backups (age) |

---

## Schnellstart

### Proxmox / Debian LXC

Auf einem frischen **Debian-12-LXC-Container**:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/jakobeichberger/BotballDashboard/main/scripts/proxmox-setup.sh)
```

Das Skript macht Folgendes:

- installiert Docker, Node.js und pnpm und klont das Repository;
- fragt die `.env` ab (Domain, SMTP optional, Monitoring optional) und erzeugt alle Secrets, auch den Fernet-Schlüssel und das age-Schlüsselpaar für Backups;
- baut die Images und startet **alle** Dienste: Traefik, Backend, Worker, Beat, Frontend, PostgreSQL, Redis, Backup, optional Prometheus und Alertmanager;
- legt die VAPID-Schlüssel und den ersten Admin an und prüft die Installation mit `scripts/verify-deployment.sh`.

Updates: `./scripts/update.sh` (git pull → Images neu bauen → `up -d` → Prüfung). Details: [Proxmox-Setup](docs/documentation/installation/proxmox-setup.md), [Update](docs/documentation/installation/update.md).

### Manuelle Installation (Produktion)

```bash
cp .env.example .env
# Pflicht: APP_SECRET_KEY, JWT_SECRET_KEY, POSTGRES_PASSWORD (je ≥ 24 Zeichen),
# PRINTER_CREDENTIAL_ENCRYPTION_KEY (Fernet), DOMAIN, APP_BASE_URL, ALLOWED_ORIGINS,
# TRAEFIK_EMAIL, AGE_RECIPIENT (Backups) – die Befehle zum Erzeugen stehen in .env.example

make up          # docker compose up -d --build (inkl. Traefik, Worker, Beat, Backup)
make verify      # scripts/verify-deployment.sh
make update      # später: git pull + Images neu bauen + up -d + Prüfung
```

In Produktion verweigert das Backend den Start mit Standard-Secrets oder einem ungültigen Fernet-Schlüssel. Den ersten Admin legst du mit `docker compose exec -e ADMIN_PASSWORD='…' backend python scripts/create_admin.py --email … --name …` an. Danach führt `/` zum Einrichtungsassistenten. Siehe [Quickstart](docs/documentation/installation/quickstart.md) und [Konfiguration](docs/documentation/installation/configuration.md).

### Entwicklung

```bash
make dev         # Stack ohne Traefik, Hot-Reload für Backend und Frontend
```

Eine `.env` ist nicht nötig, `docker-compose.dev.yml` setzt `APP_ENV=development` und die Dev-Zugangsdaten. Wer `.env.example` für die Entwicklung kopiert, setzt `COMPOSE_PROFILES=` leer, sonst startet auch der Backup-Dienst.

- Frontend: http://localhost:5173
- API und Swagger UI: http://localhost:8000/api/docs (nur im Dev-Modus)
- Login: `admin@dev.local` / `admin1234` (wird beim Start angelegt)

Ohne Docker: im Backend `pip install -r requirements-dev.txt` (die gepinnten Versionen aus `make lock-backend`), dann `alembic upgrade head` und `uvicorn main:app --reload`; im Frontend (Node.js 22) `pnpm install` und `pnpm dev`. Tests:

```bash
cd backend && pytest -q -n auto && ruff check . && ruff format --check . && mypy .
cd frontend && pnpm lint && pnpm exec tsc --noEmit && pnpm test && pnpm build
```

### Pre-commit-Hooks

```bash
pipx install pre-commit      # oder: pip install pre-commit
pre-commit install
pre-commit run --all-files
```

Die Hooks sind ruff (check und format) für `backend/`, eslint für `frontend/src` (vorher `pnpm install` in `frontend/`), shellcheck und ein YAML-Check.

### Make-Befehle

| Befehl | Beschreibung |
|---|---|
| `make up` / `make down` | Produktion starten / stoppen |
| `make dev` | Entwicklungsmodus |
| `make migrate` / `make migrate-down` | Migrationen anwenden / eine zurück |
| `make migrate-create MSG="name"` | Neue Migration erzeugen |
| `make logs` | Live-Logs |
| `make shell-backend` / `make shell-db` | Shell im Backend / psql |
| `make test-backend` / `make test-frontend` | Tests |
| `make vapid-keys` / `make fernet-key` | Schlüssel erzeugen |
| `make update` / `make verify` | Update / Installation prüfen |
| `make backup-now` / `make backup-status` | Backup sofort / Backup-Status |

---

## Architektur

Modularer Monolith mit statischen Registries: `backend/core/modules.py` für die Router, `frontend/src/core/plugins.ts` für Routen, Navigation und Rechte. Laufzeit-Plugins gibt es bewusst nicht.

```
Traefik ─┬─ /api → backend (FastAPI) ─┬─ PostgreSQL
         │                             └─ Redis ─ worker / beat (Celery)
         └─ /    → frontend (nginx, SPA/PWA)
```

- `backend/modules/`: `auth`, `seasons`, `events`, `teams`, `scoring` (inkl. `score_sheets`), `paper_review`, `printing`, `dashboard`, `exports`, `bots`.
- Live-Daten über Redis Pub/Sub, veröffentlicht nach dem Commit, an `WS /api/v1/public/events/{slug}/ws`.
- Benachrichtigungen über eine transaktionale Outbox, die der Worker zustellt.
- Einheitliches Fehlerformat `{code, message, fieldErrors, requestId}`.

Details: [Architektur](docs/documentation/technical/architecture.md) · [Modul-Registry](docs/documentation/technical/plugins.md) · [Datenbank](docs/documentation/technical/database.md) (68 Tabellen, ERD, Migrationen `0001`–`0034`) · [API-Referenz](docs/documentation/technical/api-reference.md).

---

## Rollen

| Rolle | Rechte (Migrationen `0002`–`0017`) |
|---|---|
| **admin** | alle |
| **juror** | `scoring:read/write/admin` · `events:read/write` · `teams:read` · `seasons:read` · `dashboard:read` |
| **reviewer** | `papers:read/review` · `teams:read` · `seasons:read` · `events:read` · `dashboard:read` |
| **mentor** | `teams:read/write` · `scoring:read/write` · `papers:read/write` · `printing:read/write` · `seasons:read` · `events:read` · `dashboard:read`. Schreibrechte nur fürs eigene Team. |
| **guest** | `scoring:read` · `teams:read` · `seasons:read` · `events:read` · `dashboard:read` |

Admins können Rechte ändern und eigene Rollen anlegen. Vollständige Matrix und Restrisiken: [docs/SECURITY.md](docs/SECURITY.md).

---

## Dokumentation

| Dokument | Inhalt |
|---|---|
| [docs/documentation/index.md](docs/documentation/index.md) | Einstieg in die Gesamtdokumentation |
| [Quickstart](docs/documentation/installation/quickstart.md) · [Konfiguration](docs/documentation/installation/configuration.md) · [Anforderungen](docs/documentation/installation/requirements.md) | Installation |
| [Proxmox-Setup](docs/documentation/installation/proxmox-setup.md) · [Update](docs/documentation/installation/update.md) · [Deployment](docs/documentation/technical/deployment.md) · [Betrieb](docs/operations.md) | Betrieb, Backups, Monitoring |
| [Benutzerhandbuch](docs/documentation/user-manual/index.md) | Grundlagen für alle Rollen |
| [Admin](docs/documentation/user-manual/admin.md) · [Juror](docs/documentation/user-manual/juror.md) · [Reviewer](docs/documentation/user-manual/reviewer.md) · [Mentor](docs/documentation/user-manual/mentor.md) · [Gast](docs/documentation/user-manual/guest.md) · [FAQ](docs/documentation/user-manual/faq.md) | Handbücher |
| [Architektur](docs/documentation/technical/architecture.md) · [API](docs/documentation/technical/api-reference.md) · [Datenbank](docs/documentation/technical/database.md) · [Modul-Registry](docs/documentation/technical/plugins.md) | Technik |
| [SECURITY.md](docs/SECURITY.md) · [todo.md](docs/todo.md) · [done.md](docs/done.md) · [OPEN_ITEMS.md](docs/OPEN_ITEMS.md) · [audit-2026-09.md](docs/audit-2026-09.md) | Sicherheit und Projektstand |
| [docs/modules/](docs/modules/) | Ursprüngliche Modul-Spezifikationen (01–11) |
| [docs/schulung/](docs/schulung/README.md) | Schulung „Von der Frage zum Auftrag“: Arbeiten mit KI-Agenten, 60 Minuten mit Live-Demo (Gamedoc 2027 in die App übernehmen) |

### Referenzdokumente

| Datei | Beschreibung |
|---|---|
| [`docs/assets/README.md`](docs/assets/README.md) | Quellen und Nutzungshinweis aller Referenzdokumente |
| [`docs/assets/2026-Botball-Game-Review-v1.4.pdf`](docs/assets/2026-Botball-Game-Review-v1.4.pdf) | Game Review 2026 (v1.4) |
| [`docs/assets/2026-Botball-Seeding-Score-Sheet.pdf`](docs/assets/2026-Botball-Seeding-Score-Sheet.pdf) · [`2026-Botball-Scoring-Examples.pdf`](docs/assets/2026-Botball-Scoring-Examples.pdf) | Score-Sheet und Scoring Examples 2026 |
| [`docs/assets/2026 ECER Amendments v1.0.pdf`](<docs/assets/2026 ECER Amendments v1.0.pdf>) | ECER Amendments 2026 (ERAA) |
| `docs/assets/2026-Botball-Period-{1,2,3}-Documentation.pdf` · [`2026-Botball-Onsite-Documentation.pdf`](docs/assets/2026-Botball-Onsite-Documentation.pdf) | Dokumentations-Bewertungsbögen 2026 (P1 /100, P2 /95, P3 /100, Onsite /100) |
| [`docs/assets/aerial-junior-rulebook-2026-en-v1.pdf`](docs/assets/aerial-junior-rulebook-2026-en-v1.pdf) | Aerial Junior Rulebook 2026 |
| [`docs/assets/Results 2026.xlsx`](<docs/assets/Results 2026.xlsx>) | Ergebnisse ECER 2026 (Referenz für die Vorlagen 2026 und den Ergebnis-Export) |
| [`docs/assets/2026 Botball Game Review v1.3.pdf`](<docs/assets/2026 Botball Game Review v1.3.pdf>) | Game Review 2026, frühere Fassung v1.3 |
| [`docs/assets/2026 Call for Papers v1.0.pdf`](<docs/assets/2026 Call for Papers v1.0.pdf>) | Call for Papers 2026 |
| [`docs/assets/2025 Botball Game Review v1.2.pdf`](<docs/assets/2025 Botball Game Review v1.2.pdf>) | Game Review 2025 |
| [`docs/assets/2025 Call for Papers v1.0.pdf`](<docs/assets/2025 Call for Papers v1.0.pdf>) | Call for Papers 2025 |
| [`docs/assets/Results 2025.xlsx`](<docs/assets/Results 2025.xlsx>) | Ergebnisse ECER 2025 (Referenz für die Formel-Engine) |
