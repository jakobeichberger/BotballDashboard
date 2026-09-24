# BotballDashboard

Webbasierte Plattform zur vollständigen Verwaltung und Auswertung des Botball-Wettbewerbs – Teams, Saisons, Scoring, Paper-Review und 3D-Druck in einem System.

---

## Status: Implementiert ✓

| # | Modul | Typ | Status |
|---|---|---|---|
| 01 | [Infrastruktur](docs/modules/01-infrastruktur.md) | Basis | ✅ Implementiert |
| 02 | [Auth & Rechtesystem](docs/modules/02-auth.md) | Kern | ✅ Implementiert |
| 03 | [Saisonverwaltung](docs/modules/03-saisonverwaltung.md) | Kern | ✅ Implementiert |
| 04 | [Teamverwaltung](docs/modules/04-teamverwaltung.md) | Kern | ✅ Implementiert |
| 05 | [Scoring-Modul](docs/modules/05-scoring.md) | Modul | ✅ Implementiert |
| 06 | [Paper-Review-Modul](docs/modules/06-paper-review.md) | Modul | ✅ Implementiert |
| 07 | [3D-Druck-Modul](docs/modules/07-3d-druck.md) | Modul | ✅ Implementiert |
| 08 | [Dashboard & Visualisierung](docs/modules/08-dashboard.md) | Kern | ✅ Implementiert |
| 09 | [Mobile App / PWA](docs/modules/09-mobile-pwa.md) | Frontend | ✅ Implementiert |
| 10 | [Testing](docs/modules/10-testing.md) | Querschnitt | ✅ Implementiert |
| 11 | [Dokumentation](docs/modules/11-dokumentation.md) | Querschnitt | ✅ Implementiert |
| – | [PDF- & CSV-Export](docs/modules/) | Feature | ✅ Implementiert |

---

## Tech-Stack

| Schicht | Technologie |
|---|---|
| **Backend** | Python 3.11 · FastAPI · SQLAlchemy 2.0 async · Alembic |
| **Datenbank** | PostgreSQL 16 · Redis 7 |
| **Frontend** | React 18 · TypeScript · Vite · Tailwind CSS (dark mode) |
| **State / Data** | Zustand · TanStack Query · Zod · React Hook Form |
| **i18n** | i18next (DE + EN, 1-Klick-Wechsel) |
| **PWA** | vite-plugin-pwa · Web Push API (pywebpush) |
| **Auth** | JWT (15 min Access · 30 d Refresh HttpOnly Cookie) · RBAC |
| **Infrastruktur** | Docker Compose · Traefik (SSL/Let's Encrypt) · Proxmox |
| **E-Mail** | SMTP (primär) · SendGrid (Fallback) |
| **3D-Druck** | Bambu Lab · OctoPrint · Fernet-verschlüsselte API-Keys |

---

## Schnellstart

### Proxmox / Debian LXC – One-Call Setup

Auf einem frischen **Debian 12 LXC-Container** genügt ein einziger Befehl:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/jakobeichberger/BotballDashboard/main/scripts/proxmox-setup.sh)
```

Das Script erledigt automatisch:
- Docker-, Node.js- und pnpm-Installation
- Repository klonen
- Interaktive `.env`-Konfiguration (Domain, DB, SMTP optional, Monitoring optional). Alle Secrets werden erzeugt, auch der Fernet-Schlüssel und das age-Schlüsselpaar für Backups.
- Datenverzeichnisse `/data/db` und `/data/backups` anlegen
- Images bauen und **alle** Dienste starten: Traefik, Backend, Worker, Beat, Frontend, DB, Redis, Backup, optional Prometheus/Alertmanager
- VAPID-Schlüssel, erster Admin, `scripts/verify-deployment.sh`

> SMTP-Konfiguration ist **optional** – bei Bedarf kann sie übersprungen werden.

Updates: `./scripts/update.sh` (git pull → Images neu bauen → `up -d` → Prüfung). Details: [Proxmox-Setup](docs/documentation/installation/proxmox-setup.md), [Update](docs/documentation/installation/update.md).

---

### Manuelle Installation

#### Voraussetzungen
- Docker & Docker Compose
- (Optional) pnpm 10 für lokale Frontend-Entwicklung

#### Produktion

```bash
cp .env.example .env
# Pflicht: APP_SECRET_KEY, JWT_SECRET_KEY, POSTGRES_PASSWORD (je ≥ 24 Zeichen),
# PRINTER_CREDENTIAL_ENCRYPTION_KEY (Fernet), DOMAIN, APP_BASE_URL, ALLOWED_ORIGINS,
# TRAEFIK_EMAIL, AGE_RECIPIENT (Backups) – Befehle zum Erzeugen stehen in .env.example

make up          # baut und startet alle Container inkl. Traefik und Backup
make verify      # scripts/verify-deployment.sh
make update      # späteres Update: git pull + Images neu bauen + up -d
```

Siehe [Quickstart](docs/documentation/installation/quickstart.md).

#### Entwicklung

```bash
make dev         # Backend + DB + Redis + Frontend mit Hot-Reload
```

Für die Entwicklung ist keine `.env` nötig (`docker-compose.dev.yml` setzt `APP_ENV=development` und Dev-Zugangsdaten). `.env.example` ist die Produktionsvorlage: Wer sie für die Entwicklung kopiert, setzt `COMPOSE_PROFILES=` leer, sonst startet auch der Backup-Dienst.

#### Pre-commit-Hooks

```bash
pipx install pre-commit      # oder: pip install pre-commit
pre-commit install           # ab jetzt vor jedem Commit
pre-commit run --all-files   # einmalig alles prüfen
```

`.pre-commit-config.yaml` führt ruff (check + format) für `backend/`, eslint für `frontend/src` (vorher `pnpm install` in `frontend/`), shellcheck für die Shell-Skripte und einen YAML-Check aus. Das sind dieselben Prüfungen wie in der CI.

Danach erreichbar:
- Frontend: http://localhost:5173
- Backend API + Swagger: http://localhost:8000/api/docs

**Standard-Login (Dev):**

| | |
|---|---|
| E-Mail | `admin@dev.local` |
| Passwort | `admin1234` |

> Der Dev-Admin wird beim ersten Start automatisch angelegt.

### Nützliche Make-Befehle

| Befehl | Beschreibung |
|---|---|
| `make up` | Produktion starten |
| `make down` | Alle Container stoppen |
| `make dev` | Entwicklungsmodus |
| `make migrate` | DB-Migrationen ausführen |
| `make migrate-create MSG="name"` | Neue Migration generieren |
| `make logs` | Live-Logs aller Container |
| `make shell-backend` | Shell im Backend-Container |
| `make shell-db` | psql in der Datenbank |
| `make vapid-keys` | VAPID-Schlüsselpaar generieren |
| `make fernet-key` | Fernet-Key für Drucker-Credentials |
| `make update` | Update: git pull, Images neu bauen, neu starten, prüfen |
| `make verify` | Installation prüfen (PASS/WARN/FAIL) |
| `make backup-now` / `make backup-status` | Backup sofort erstellen / Backup-Status |

---

## Architektur

```
KERN
├── Auth               (User, Role, Permission, Refresh-Cookie)
├── Saison             (jährliches Regelwerk und Scoring-Vorlagen)
├── Event              (Teams, Phasen, Zeitplan, Freigaben, Zeitzone)
└── Turnier            (Schedule, Bracket, Match, ScoreRevision, Ranking)

STATISCHE MODULE
├── Scoring            (dynamische Schemas, mobile Eingabe, Audit)
│   └── Score-Sheets   (lokale OpenCV/Tesseract-Pipeline, Pflicht-Review)
├── Paper-Review       (Auslastung, Fristen, Erinnerungen, Statushistorie)
└── 3D-Druck           (OctoPrint/Bambu, Zustandsautomat, Worker-Polling)

ÜBERGREIFEND
├── Public Live        (Rangliste, Zeitplan, Ansagen, QR, Redis Pub/Sub)
├── Dashboard          (rechtebezogene Widgets, Notification-Outbox)
└── Betrieb            (Readiness, Prometheus, Backups, strukturierte Logs)
```

**Modul-Mechanismus:** Die Anwendung ist ein statischer modularer Monolith. Backend- und Frontend-Register werden beim Build kompiliert; installierbare Laufzeit-Plugins gibt es bewusst nicht.

---

## Datenbank-Migrationen

Migrationen laufen automatisch beim Container-Start via `scripts/migrate-then-start.sh`.

| Migration | Inhalt |
|---|---|
| `0001` | Score-Sheet-Templates (OCR-Pipeline) |
| `0002` | Auth: User, Role, Permission, Token, PushSubscription (5 Rollen seeded) |
| `0003` | Seasons: Season, SeasonPhase, CompetitionLevel (ECER/GCER/Junior seeded) |
| `0004` | Teams: Team, TeamMember, TeamSeasonRegistration |
| `0005` | Scoring: ScoringSchema, Match, Ranking |
| `0006` | Paper Review: Paper, ReviewerAssignment, PaperReview |
| `0007` | 3D-Druck: Printer, PrintJob, TeamSeasonPrintQuota, FilamentSpool |
| `0008` | Dashboard: Announcement, AuditLog |
| `0009` | Wettbewerbsmodule und Kategorien |
| `0010` | Events, Registrierungen, Phasen, Zeitplan, Revisionen und Datenmigration |
| `0011` | Lokale Score-Sheet-Scans und OCR-Review |
| `0012` | Paper-/Print-Workflows, Notification-Outbox und Constraints |

---

## API-Übersicht

Alle Endpunkte unter `/api/`. Swagger UI unter `/api/docs` (nur im Dev-Modus).

| Bereich | Präfix | Authentifizierung |
|---|---|---|
| Auth | `/api/auth/` | Teils öffentlich |
| Events | `/api/v1/events/{eventId}/` | Eventbezogene Permissions |
| Öffentliche Events | `/api/v1/public/events/{slug}/` | Nur Lesen, ohne Login |
| Saisons | `/api/seasons/` | JWT erforderlich |
| Teams | `/api/teams/` | `teams:read/write` |
| Scoring | `/api/scoring/` | `scoring:read/write/admin` |
| Score-Sheets | `/api/scoring/score-sheets` | `scoring:admin` |
| Paper Review | `/api/papers/` | `papers:read/review/admin` |
| 3D-Druck | `/api/printing/` | `printing:read/write/admin` |
| Dashboard | `/api/dashboard/` | `dashboard:read` |
| Live-Kanal | `/api/v1/public/events/{slug}/ws` | Öffentlich, Redis Pub/Sub |

---

## Rollen & Berechtigungen

| Rolle | Permissions |
|---|---|
| **admin** | Alle Berechtigungen |
| **juror** | scoring:read/write/admin · teams:read · dashboard:read |
| **reviewer** | papers:read/review · teams:read · dashboard:read |
| **mentor** | teams:read · scoring:read · papers:read · printing:read/write |
| **guest** | scoring:read · dashboard:read · seasons:read |

---

## Vollständige Dokumentation

| Dokument | Beschreibung |
|---|---|
| [docs/documentation/installation/quickstart.md](docs/documentation/installation/quickstart.md) | Schnellstart-Anleitung |
| [docs/documentation/installation/configuration.md](docs/documentation/installation/configuration.md) | Alle .env-Variablen |
| [scripts/proxmox-setup.sh](scripts/proxmox-setup.sh) | One-Call Proxmox Installer |
| [docs/documentation/installation/proxmox-setup.md](docs/documentation/installation/proxmox-setup.md) | Proxmox-Setup: LXC, Skript, Test auf dem eigenen Server |
| [docs/documentation/installation/update.md](docs/documentation/installation/update.md) | Update und Rollback |
| [docs/documentation/technical/deployment.md](docs/documentation/technical/deployment.md) | Dienste, Health/Readiness, Deploy-Workflow, Monitoring |
| [docs/documentation/technical/architecture.md](docs/documentation/technical/architecture.md) | Systemarchitektur |
| [docs/documentation/technical/database.md](docs/documentation/technical/database.md) | Datenbankschema |
| [docs/documentation/technical/api-reference.md](docs/documentation/technical/api-reference.md) | API-Referenz |
| [docs/documentation/technical/plugins.md](docs/documentation/technical/plugins.md) | Statische Modul-Registry |
| [docs/operations.md](docs/operations.md) | Readiness, Alarme, Backups (außer Haus, Wiederherstellung) und Event-Probelauf |
| [docs/documentation/user-manual/admin.md](docs/documentation/user-manual/admin.md) | Handbuch: Admin |
| [docs/documentation/user-manual/juror.md](docs/documentation/user-manual/juror.md) | Handbuch: Juror |
| [docs/documentation/user-manual/reviewer.md](docs/documentation/user-manual/reviewer.md) | Handbuch: Reviewer |
| [docs/documentation/user-manual/mentor.md](docs/documentation/user-manual/mentor.md) | Handbuch: Mentor |

---

## Referenzdokumente

| Datei | Beschreibung |
|---|---|
| [`docs/assets/2026 Botball Game Review v1.3.pdf`](<docs/assets/2026 Botball Game Review v1.3.pdf>) | Game Review 2026 |
| [`docs/assets/2026 Call for Papers v1.0.pdf`](<docs/assets/2026 Call for Papers v1.0.pdf>) | Call for Papers 2026 |
| [`docs/assets/2025 Botball Game Review v1.2.pdf`](<docs/assets/2025 Botball Game Review v1.2.pdf>) | Game Review 2025 |
| [`docs/assets/2025 Call for Papers v1.0.pdf`](<docs/assets/2025 Call for Papers v1.0.pdf>) | Call for Papers 2025 |
