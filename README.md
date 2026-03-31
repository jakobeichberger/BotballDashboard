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
| 05 | [Scoring-Modul](docs/modules/05-scoring.md) | Plugin | ✅ Implementiert |
| 06 | [Paper-Review-Modul](docs/modules/06-paper-review.md) | Plugin | ✅ Implementiert |
| 07 | [3D-Druck-Modul](docs/modules/07-3d-druck.md) | Plugin | ✅ Implementiert |
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
- Docker-Installation
- Repository klonen
- Interaktive `.env`-Konfiguration (Domain, DB, SMTP optional, Secrets auto-generiert)
- Datenverzeichnisse anlegen
- Images bauen & Services starten
- Health-Checks und Zusammenfassung

> SMTP-Konfiguration ist **optional** – bei Bedarf kann sie übersprungen werden.

---

### Manuelle Installation

#### Voraussetzungen
- Docker & Docker Compose
- (Optional) pnpm 9+ für lokale Frontend-Entwicklung

#### Produktion

```bash
cp .env.example .env
# .env anpassen (Passwörter, DOMAIN, SMTP optional, VAPID-Keys)

make up          # startet alle Container inkl. Traefik
make migrate     # ggf. Migrationen manuell anstoßen (läuft automatisch beim Start)
```

#### Entwicklung

```bash
cp .env.example .env
# .env.example zeigt alle benötigten Variablen

make dev         # Backend + DB + Redis + Frontend mit Hot-Reload
```

Danach erreichbar:
- Frontend: http://localhost:5173
- Backend API + Swagger: http://localhost:8000/api/docs

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

---

## Architektur

```
KERN
├── Auth               (User, Role, Permission, JWT, RefreshToken, PushSubscription)
├── Saisonverwaltung   (Season, SeasonPhase, CompetitionLevel)
└── Teamverwaltung     (Team, TeamMember, TeamSeasonRegistration)

PLUGINS
├── Scoring            (ScoringSchema, Match, Ranking, WebSocket-Scoreboard)
│   └── Score-Sheets   (PDF-Import, OCR-Pipeline, Feldbestätigung)
├── Paper-Review       (Paper, ReviewerAssignment, PaperReview, Datei-Upload)
└── 3D-Druck           (Printer, PrintJob, TeamSeasonPrintQuota, FilamentSpool)

ÜBERGREIFEND
├── Dashboard          (Announcements, Stats-Widgets)
├── Frontend Shell     (Layout, Sidebar, Auth-Context, Theme, i18n)
└── PWA                (Service Worker, Web Push Subscriptions)
```

**Plugin-Mechanismus:** Jedes Modul registriert sich über ein `manifest.json` (Backend) und eine `PluginDefinition` (Frontend). Neue Module können hinzugefügt werden ohne den Kern zu verändern.

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

---

## API-Übersicht

Alle Endpunkte unter `/api/`. Swagger UI unter `/api/docs` (nur im Dev-Modus).

| Bereich | Präfix | Authentifizierung |
|---|---|---|
| Auth | `/api/auth/` | Teils öffentlich |
| Saisons | `/api/seasons/` | JWT erforderlich |
| Teams | `/api/teams/` | `teams:read/write` |
| Scoring | `/api/scoring/` | `scoring:read/write/admin` |
| Score-Sheets | `/api/scoring/score-sheets` | `scoring:admin` |
| Paper Review | `/api/papers/` | `papers:read/review/admin` |
| 3D-Druck | `/api/printing/` | `printing:read/write/admin` |
| Dashboard | `/api/dashboard/` | `dashboard:read` |
| Scoreboard WS | `/api/scoring/scoreboard/ws` | Öffentlich |

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
| [docs/documentation/installation/proxmox-setup.md](docs/documentation/installation/proxmox-setup.md) | Proxmox + Docker Setup (manuell) |
| [docs/documentation/technical/architecture.md](docs/documentation/technical/architecture.md) | Systemarchitektur |
| [docs/documentation/technical/database.md](docs/documentation/technical/database.md) | Datenbankschema |
| [docs/documentation/technical/api-reference.md](docs/documentation/technical/api-reference.md) | API-Referenz |
| [docs/documentation/technical/plugins.md](docs/documentation/technical/plugins.md) | Plugin-Entwicklung |
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
