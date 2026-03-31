# Done – Erledigte Module

---

## [x] Modul 1: Infrastruktur & Projekt-Setup
**Abgeschlossen am:** 2026-03-31
**Beschreibung:**
- `docker-compose.yml` (Produktion: Traefik + SSL, PostgreSQL 16, Redis 7, Backend, Frontend)
- `docker-compose.dev.yml` (Hot-Reload-Überrides für Entwicklung)
- `backend/Dockerfile` (Multi-Stage: development / production target, poppler-utils für OCR)
- `frontend/Dockerfile` (Node 20 Builder → nginx alpine)
- `frontend/nginx.conf` (SPA-Fallback, gzip, Cache-Header)
- `.env.example` (alle Variablen dokumentiert)
- `Makefile` (up/dev/migrate/logs/shell-backend/shell-db/vapid-keys/fernet-key)
- `.gitignore`
- `backend/pyproject.toml` (FastAPI, SQLAlchemy 2.0, Alembic, JWT, Redis, aiosmtplib, pywebpush, cryptography, structlog, httpx)
- `frontend/package.json` (React 18, Vite, Tailwind, TanStack Query, Zustand, i18next, Zod, vite-plugin-pwa, recharts, lucide-react)
- Alembic-Setup: `alembic.ini`, `alembic/env.py` (async), `alembic/script.py.mako`

**Kommuniziert mit:** Alle Module (Basis)
**Notizen:** `migrate-then-start.sh` führt Migrationen automatisch vor dem Backend-Start aus.

---

## [x] Modul 2: Authentifizierung & Rechtesystem
**Abgeschlossen am:** 2026-03-31
**Beschreibung:**
- Modelle: `User`, `Role`, `Permission`, `RolePermission`, `UserRole`, `RefreshToken`, `PushSubscription`
- 5 System-Rollen mit Berechtigungen seeded: `admin`, `juror`, `reviewer`, `mentor`, `guest`
- JWT: Access Token (15 min) + Refresh Token (30 Tage, HttpOnly-Cookie)
- Token-Rotation bei jedem Refresh; Token-Widerruf beim Logout
- `require_permission()` und `require_any_permission()` FastAPI-Dependencies
- Web Push Subscriptions: pro Gerät, VAPID, pywebpush
- Passwort: bcrypt, Änderung mit Bestätigung des alten Passworts
- E-Mail + Sprache + Theme im User-Profil gespeichert
- Migration `0002` mit Seed-Daten

**Kommuniziert mit:** Allen Modulen (jeder API-Call prüft Token & Berechtigung)
**Notizen:** Superuser (`is_superuser=True`) hat automatisch alle Rechte ohne explizite Rollenzuweisung.

---

## [x] Modul 3: Saisonverwaltung
**Abgeschlossen am:** 2026-03-31
**Beschreibung:**
- Modelle: `Season`, `SeasonPhase`, `CompetitionLevel`
- ECER, GCER, Junior als Competition Levels seeded
- Phasentypen: seeding, double_seeding, elimination, final
- Pro Season: Deadline-Felder (Registration, Event, Paper, Print)
- Aktive Saison eindeutig (SET via `UPDATE ... SET is_active=false` dann gezielte Aktivierung)
- Migration `0003`

**Kommuniziert mit:** Teams (Registrierung), Scoring (Phasen), Paper Review (Season-FK), Printing (Season-FK)

---

## [x] Modul 4: Teamverwaltung
**Abgeschlossen am:** 2026-03-31
**Beschreibung:**
- Modelle: `Team`, `TeamMember`, `TeamSeasonRegistration`
- Teams können mehreren Saisons zugeordnet werden (Registrierungen mit Bestätigung)
- Mitglieder mit Rollen (`mentor` / `member`), optional mit User-Account verknüpft
- Filter nach Season und Competition Level
- Migration `0004`

**Kommuniziert mit:** Seasons (Registrierungen), Scoring (Matches), Paper Review (Papers), Printing (Druckjobs)

---

## [x] Modul 5: Scoring-Modul
**Abgeschlossen am:** 2026-03-31
**Beschreibung:**
- Modelle: `ScoringSchema` (Felder + Multiplikatoren), `Match` (raw_scores als JSONB), `Ranking`
- Score-Berechnung: `total = Σ(wert × multiplikator)` pro Feld
- Seed-Score-Formel: Durchschnitt der 2 besten Runs
- Ranking wird nach jedem Score-Eintrag automatisch neu berechnet und nummeriert
- Yellow-Card / Red-Card Flags pro Match
- Bulk-Score-Entry Endpunkt
- WebSocket Live-Scoreboard: `/api/scoring/scoreboard/ws` (kein Auth, public)
- Migration `0005`
- **Score-Sheet-Import (Sub-Modul):**
  - PDF-Upload → pdftotext → Regex-Parser → OCR-Kandidaten
  - Admin-UI: Felder bestätigen, Multiplikatoren editieren, auf ScoringSchema anwenden
  - Modell: `ScoreSheetTemplate` mit OCR-Status

**Kommuniziert mit:** Seasons (Phasen-FK), Teams (Match-FK), Frontend (WebSocket)
**Notizen:** Scoreboard-Endpunkt ist absichtlich ohne Auth für externe Scoreboards/Displays.

---

## [x] Modul 6: Paper-Review-Modul
**Abgeschlossen am:** 2026-03-31
**Beschreibung:**
- Modelle: `Paper`, `ReviewerAssignment`, `PaperReview`
- Paper-Status-Workflow: `draft → submitted → under_review → accepted / rejected / revision_requested`
- Bei `revision_requested` wird `revision_number` automatisch inkrementiert
- Mehrere Reviewer pro Paper möglich (keine Blind-Review – Reviewer sehen sich gegenseitig)
- Review-Kriterien: Content, Methodology, Presentation, Originality (0–10, Durchschnitt = total_score)
- Wenn alle zugewiesenen Reviewer eingereicht haben → Paper wechselt automatisch zu `under_review`
- PDF-Datei-Upload + Download-Endpunkt
- Migration `0006`

**Kommuniziert mit:** Seasons (Paper-FK), Teams (Paper-FK), Auth (Reviewer-Zuweisung)

---

## [x] Modul 7: 3D-Druck-Modul
**Abgeschlossen am:** 2026-03-31
**Beschreibung:**
- Modelle: `Printer`, `PrintJob`, `TeamSeasonPrintQuota`, `FilamentSpool`
- Drucker-Types: `bambu`, `octoprint`, `generic` (Adapter-Architektur vorbereitet)
- API-Keys Fernet-verschlüsselt in DB gespeichert (nie im Klartext in API-Responses)
- Quota-System: `soft_limit_parts` (Warnung) + `max_parts` (Hard-Stop, 409-Fehler)
- `used_parts` / `used_grams` werden nach Job-Abschluss automatisch aktualisiert
- Filament-Tracking: Spulen mit `initial_grams` / `remaining_grams`, `consume_filament()`-Endpunkt
- Druckjob-Status-Flow: `pending → approved → queued → printing → completed / failed / cancelled`
- Migration `0007`

**Kommuniziert mit:** Teams (Job-FK), Seasons (Job-FK)
**Notizen:** Fernet-Key via `PRINTER_CREDENTIAL_ENCRYPTION_KEY` in .env; `make fernet-key` zum Generieren.

---

## [x] Modul 8: Dashboard & Visualisierung
**Abgeschlossen am:** 2026-03-31
**Beschreibung:**
- Modell: `Announcement` (mit Audience-Filter: all/teams/reviewers/jurors/internal)
- Stats-Aggregations-Endpoint: Teams, Matches, Papers, Druckjobs pro Saison
- Dashboard-Frontend: Stat-Cards, aktive Season-Phasen-Übersicht
- Audit-Log-Tabelle (migriert in `0008`)
- Migration `0008`

**Kommuniziert mit:** Allen Modulen (Daten-Aggregation)

---

## [x] Modul 9: Mobile App / PWA
**Abgeschlossen am:** 2026-03-31
**Beschreibung:**
- `vite-plugin-pwa` mit Workbox (NetworkFirst für API, offline für statische Assets)
- Web App Manifest: Name, Icons, Theme-Color, `standalone` Display
- Web Push: VAPID-basiert, `usePushNotifications` Hook (subscribe/unsubscribe)
- Push-Subscriptions werden pro Gerät in DB gespeichert (`PushSubscription`-Modell)
- `core/notifications.py`: `send_push_notification()` über pywebpush
- Dark/Light/System Theme: Zustand-Store, speichert in localStorage, OS-Präferenz-Listener

**Kommuniziert mit:** Backend (Push-API), Browser Push API

---

## [x] Modul 11: Dokumentation
**Abgeschlossen am:** 2026-03-31
**Beschreibung:**
- Vollständige Benutzerhandbücher: Admin, Juror, Reviewer, Mentor, Gast
- Technische Dokumentation: Architektur, API-Referenz, Datenbankschema, Plugin-Dev-Guide, Deployment
- Installationsanleitungen: Quickstart, Proxmox-Setup, Konfigurationsreferenz, Update-Prozess
- README.md: Tech-Stack, Schnellstart, Architekturübersicht, API-Übersicht, Rollen-Tabelle

---

## [x] Modul 10: Testing
**Abgeschlossen am:** 2026-03-31
**Beschreibung:**
- `backend/tests/conftest.py`: SQLite in-memory (aiosqlite), `db`/`client`/`admin_token`/`season`/`team` Fixtures
- Unit-Tests (pytest-asyncio):
  - `test_scoring.py`: `TestComputeSeedScore` (8 Fälle), `TestComputeMatchTotal` (8 Fälle), `TestRankingLogic` (2 async)
  - `test_paper_review.py`: `TestPaperStatusTransitions` (6), `TestReviewerAssignment` (3), `TestReviewScores` (3)
  - `test_printing_quota.py`: `TestPrintQuota` (4), `TestFilamentTracking` (4), `TestCredentialEncryption` (2)
  - `test_auth.py`: `TestPasswordHashing` (4), `TestJWTTokens` (5), `TestUserCreation` (6)
- Integrationstests (httpx AsyncClient):
  - `test_auth_routes.py`: Login/Logout/Refresh/Protected (5+4+1)
  - `test_scoring_routes.py`: Match-CRUD (5+2)
  - `test_seasons_teams.py`: Seasons/Teams API (5+4)
- Frontend (Vitest + @testing-library/react + jsdom):
  - `authStore.test.ts` (7 Fälle), `themeStore.test.ts` (4 Fälle)
  - `LoginPage.test.tsx` (4 Fälle inkl. vi.mock für useAuth und react-router)
- CI/CD GitHub Actions:
  - `.github/workflows/ci.yml`: ruff lint, pytest+coverage, ESLint, vitest, Vite build check
  - `.github/workflows/deploy.yml`: Docker buildx → GHCR, SSH-Deploy via appleboy/ssh-action

**Kommuniziert mit:** Allen Modulen (Tests decken alle Kern-Flows ab)
**Notizen:** SQLite in-memory für Tests (kein echtes PostgreSQL in CI nötig); StaticPool für konsistente Verbindungen.

---

## [x] PDF- & CSV-Export
**Abgeschlossen am:** 2026-03-31
**Beschreibung:**
- `backend/modules/exports/pdf_builder.py`: reportlab A4-PDFs mit Logo-Header und alternierenden Zeilenfarben
  - `build_ranking_pdf()`, `build_paper_review_pdf()`, `build_print_report_pdf()`, `build_team_list_pdf()`
- `backend/modules/exports/routes.py`: 7 Export-Endpunkte:
  - `GET /exports/seasons/{id}/ranking.pdf` + `.csv`
  - `GET /exports/seasons/{id}/matches.csv`
  - `GET /exports/seasons/{id}/papers.pdf` + `.csv`
  - `GET /exports/seasons/{id}/printing.pdf`
  - `GET /exports/seasons/{id}/teams.pdf` + `.csv`
- `frontend/src/components/ExportButtons.tsx`: `ExportButton`, `RankingExportButtons`, `PaperExportButtons`, `PrintingExportButtons`, `TeamExportButtons`
- CSV-Export: UTF-8 mit BOM (Excel-kompatibel)
- Download via `api.get(url, { responseType: "blob" })` + `URL.createObjectURL` + hidden anchor

**Kommuniziert mit:** Scoring, Paper-Review, Printing, Teams, Seasons

---

## [x] Benutzerhandbuch & FAQ
**Abgeschlossen am:** 2026-03-31
**Beschreibung:**
- `docs/documentation/user-manual/index.md`: Übersicht, Navigation, Rollen, Export-Kurzanleitung
- `docs/documentation/user-manual/admin.md`: Benutzerverwaltung, Rechte, Saisons, alle Module, Exporte, Logs
- `docs/documentation/user-manual/juror.md`: Score-Eingabe, Korrektur, Cards, Rangliste, Export, Offline
- `docs/documentation/user-manual/reviewer.md`: Paper-Review-Workflow, Bewertungskategorien, KI-Policy
- `docs/documentation/user-manual/mentor.md`: Dashboard, Scoring, Paper einreichen, 3D-Druck, Limits
- `docs/documentation/user-manual/guest.md`: Öffentliches Scoreboard, PWA
- `docs/documentation/user-manual/faq.md`: 30+ Fragen zu allen Modulen (allgemein, Scoring, Paper, Druck, Benachrichtigungen, Admin)
