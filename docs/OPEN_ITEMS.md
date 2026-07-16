# Offene Punkte

Stand: 2026-07-15 · Branch `feature/detail-pages-and-review-workflow` (gepusht)

Ausgangslage war ein weitgehend **read-only** Frontend (ca. die Hälfte der API ungenutzt).
Aktuell: **98 / 106 Endpoints genutzt** — die verbleibenden sind redundante
Alternativen zu bereits verdrahteten Endpoints. Es gibt keine substanziell
offenen Features mehr.

## ✅ Umgesetzt
- Detailseiten (Team, Paper, Druckauftrag) + klickbare Navigation
- Team ↔ Saison-Zuweisungsmatrix
- Kompletter Paper-Review-Workflow (Reviewer-Formular, Zuweisung, Status, Upload, Finalisierung + Ranking)
- Team-Self-Service: Papers, Wertungen und Druckaufträge selbst einreichen (eigenes Team erzwungen)
- Vorbereitungs-/Übungspunkte (getrennt von der offiziellen Rangliste)
- Team-Selbstverwaltung (Team + Mitglieder bearbeiten)
- **Saison-Deadlines & Events**: pro Saison beliebige Deadlines/Events anlegen/löschen, Termin-Felder editieren, Phasen aktivieren
- Admin-Settings: Benutzer (inkl. Rollen bearbeiten), Saisons (CRUD), Saison-Details, Saison-Module, **Wettbewerbsstufen (CRUD)**, Drucker, Filament-Spulen, Ankündigungen
- Team anlegen, Profilseite (Name/Sprache/Passwort), **Druck-Kontingent anzeigen + bearbeiten**
- Einzelne Wertung bearbeiten, `matches.csv`-Export
- **Benutzerdefinierte Rollen** anlegen (`GET /auth/permissions` + `POST /auth/roles`) mit Rechte-Auswahl
- **Bot-Galerie** (`/bots`, Migration 0015): Roboter eigener **und externer** Teams mit Funktionsweise, Antrieb, Sensorik, Saison und Bild (Magic-Byte-validiert). Mentoren pflegen die Bots ihres Teams, externe Bots sind Organisator-Sache.
- 4 latente Berechtigungs-Bugs behoben (Migrationen 0010–0014)
- **Dependabot: alle Alerts behoben** — Frontend `pnpm audit` meldet „No known vulnerabilities" (axios/vitest/vite/react-router/postcss + pnpm-overrides für Transitives), Backend cryptography 48.0.1, aiosmtplib 5.1.1, pytest 9.0.3
- **Login-Bug behoben**: zwei Logins desselben Users in derselben Sekunde erzeugten ein identisches Refresh-JWT → Hash-Kollision → **409**. Refresh-Tokens haben jetzt eine `jti`.
- **Tests**: **587 Backend**, **94 Frontend-Unit**, **11 Playwright-E2E**

## 🟢 Keine substanziell offenen Features mehr
Alle ursprünglich offenen Punkte sind abgearbeitet.

## 🐞 Bekannte Bugs (bestehend, bewusst nicht in diesem Branch gefixt)
- [ ] **Doppelte Ränge bei gemischten Wettbewerbsstufen** – `scoring/service.py::_refresh_ranks` filtert nur nach `competition_level_id`, wenn dieses gesetzt ist. `Ranking.competition_level_id` wird zudem nur beim Anlegen der Zeile gesetzt. Folge: Ein Team ohne Stufe und eines mit Stufe können beide **Rang 1** haben, und die Reihenfolge hängt davon ab, welches Match zuletzt erfasst wurde. Braucht eine Produktentscheidung: Ist die Rangliste **global** oder **pro Stufe**? (Aktuell nutzt die Erfassung durchgängig `competition_level_id=None`, daher im Alltag unauffällig.)
- [ ] **Race beim Quota-Upsert** – `team_season_print_quotas` hat nur einen **nicht-eindeutigen** Index auf `(team_id, season_id)` (Migration 0007). `_get_or_create_quota` macht check-then-insert; zwei parallele Requests können zwei Zeilen anlegen, danach wirft `scalar_one_or_none()` dauerhaft `MultipleResultsFound` (500). Verschärfend: `GET /printing/quotas` legt Zeilen an. Fix wäre ein Unique-Constraint per Migration + Upsert.

## ⚪ Bewusst nicht umgesetzt (redundant zu bereits Genutztem)
- `GET /scoring/seasons/{id}/ranking` – Basis-Rangliste; Frontend nutzt `ranking/extended`.
- `POST /scoring/seasons/{id}/matches/bulk` – Bulk-Eingabe; Einzeleingabe ist verdrahtet.
- `PUT /scoring/seasons/{id}/{de|aerial|doc}-results/{team_id}` – Einzel-Varianten; Bulk-`PUT` ist verdrahtet.
- `GET /scoring/matches/{id}` – Einzelabruf; die Bearbeitung nutzt die Listendaten.
- `GET /papers/{id}/reviews` – Reviews sind bereits in `GET /papers/{id}` enthalten.
- `GET /auth/users/{id}` – Einzelabruf; die Benutzerliste wird verwendet.

## ⚠️ Bekannte Einschränkungen / Hinweise
- **`.local`-E-Mails**: `UserCreate.email` (`EmailStr`) lehnt reservierte TLDs wie `.local` ab. Die Seed-Logins (`@test.local`) funktionieren nur, weil das Seed-Script die Validierung umgeht. Im Formular echte Domains verwenden.
- **E2E-Tests ausführen**: Der Playwright-Suite braucht den laufenden Dev-Stack (`make dev`) **mit Seed-Daten**, weil sie gegen die echten Test-Logins prüft:
  ```bash
  cd frontend && pnpm install && npx playwright install chromium
  pnpm test:e2e            # bzw. npx playwright test --ui
  ```
  Die Specs laufen gegen `http://localhost:5173` (überschreibbar via `E2E_BASE_URL`).
- **Tests**: 587 Backend · 94 Frontend-Unit · 11 E2E. Die E2E-Suite läuft noch **nicht in CI** (bräuchte dort Stack + Seed).
