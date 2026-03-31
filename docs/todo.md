# Todo – Offene Aufgaben

## Implementierungsstand

Alle Kern- und Plugin-Module sind vollständig implementiert. Ausstehend ist ausschließlich das Testing-Modul sowie optionale Erweiterungen.

---

## [ ] Modul 10: Testing & CI/CD

### Backend (pytest)
- [ ] `pytest.ini` / `pyproject.toml` Test-Konfiguration
- [ ] `tests/conftest.py`: async Test-DB (SQLite in-memory oder PostgreSQL via testcontainers)
- [ ] Unit-Tests: Scoring-Berechnungen
  - `compute_match_total()` mit verschiedenen Schemata
  - `compute_seed_score()` (avg top-2)
  - Ranking-Neuberechnung nach Match-Änderung
- [ ] Unit-Tests: Paper-Review-Workflow
  - Statusübergänge (draft → submitted → under_review usw.)
  - Reviewer-Zuweisung + automatischer Statuswechsel
- [ ] Unit-Tests: 3D-Druck-Quota
  - Soft-Limit (Warnung) / Hard-Limit (ConflictError)
  - Filament-Verbrauch-Tracking
- [ ] Integrationstests: Auth-Flow
  - Login → Access Token → Refresh → Logout → Token ungültig
  - Passwort-Änderung invalidiert alte Tokens
- [ ] Integrationstests: vollständiger Scoring-Workflow
  - Season anlegen → Team registrieren → Matches eintragen → Ranking prüfen
- [ ] Integrationstests: alle API-Endpunkte (Smoke-Tests)

### Frontend (Vitest)
- [ ] `vitest.config.ts` Setup
- [ ] Unit-Tests: Zustand Stores (authStore, themeStore)
- [ ] Unit-Tests: `useAuth` Hook (Login, Token-Refresh-Logik)
- [ ] Komponenten-Tests: LoginPage, Layout, ScoreboardPage

### E2E (Playwright)
- [ ] Playwright installieren und konfigurieren
- [ ] E2E: Login → Dashboard → Scoreboard
- [ ] E2E: Score-Eingabe → Rangliste aktualisiert sich
- [ ] E2E: Paper-Upload → Review-Workflow

### CI/CD
- [ ] `.github/workflows/ci.yml`: Lint + Tests bei jedem Push
- [ ] `.github/workflows/deploy.yml`: Automatisches Deployment bei Push auf `main`
- [ ] Pre-commit Hooks: ruff + mypy (Backend), ESLint (Frontend)

---

## Optionale Erweiterungen (Backlog)

### Backend
- [ ] Passwort-Reset per E-Mail (Token-basiert)
- [ ] Bambu Lab MQTT-Adapter (Echtzeit-Druckerstatus)
- [ ] OctoPrint REST-Adapter
- [ ] Celery-Worker für Hintergrundaufgaben (E-Mail-Versand, OCR-Jobs)
- [ ] PDF-Export: Ranking, Paper-Bewertungsübersicht
- [ ] CSV/Excel-Export für alle Tabellen
- [ ] Mehrjahresvergleich (Season-übergreifende Statistiken)
- [ ] DSGVO: Daten-Export + Account-Löschung pro User

### Frontend
- [ ] Score-Eingabe-Formular (dynamisch aus ScoringSchema)
- [ ] Paper-Upload-Formular mit Drag & Drop
- [ ] 3D-Druck-Anfrage-Formular für Teams
- [ ] Echtzeitstatus-Anzeige Drucker (WebSocket)
- [ ] Mehrjahres-Vergleichsdiagramm (recharts)
- [ ] Offline-Modus mit Sync-Queue (IndexedDB)
- [ ] Admin: Rollen-Management-UI
- [ ] Admin: Saison-Management-UI
- [ ] Scoreboard-externe-Ansicht (Vollbild, keine Sidebar)

### Infrastruktur
- [ ] Automatische DB-Backups (cron in Docker oder Proxmox-Backup)
- [ ] Monitoring: Uptime Kuma oder Grafana
- [ ] Log-Rotation und Log-Archivierung
- [ ] Rate-Limiting auf Auth-Endpunkten
