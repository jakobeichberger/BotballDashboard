# Offene Punkte

Stand: 2026-07-15 · Branch `feature/detail-pages-and-review-workflow`

Ausgangslage war ein weitgehend **read-only** Frontend (ca. die Hälfte der API ungenutzt).
Aktuell: **86 / 98 Endpoints genutzt (12 offen)**. Dieses Dokument listet, was noch fehlt.

## ✅ In diesem Zweig erledigt (Kurzüberblick)
- Detailseiten (Team, Paper, Druckauftrag) + klickbare Navigation
- Team ↔ Saison-Zuweisungsmatrix
- Kompletter Paper-Review-Workflow (Reviewer-Formular, Reviewer-Zuweisung, Status, Upload, Finalisierung + Ranking)
- Team-Self-Service: Papers, Wertungen und Druckaufträge selbst einreichen (eigenes Team erzwungen)
- Vorbereitungs-/Übungspunkte (getrennt von der offiziellen Rangliste)
- Team-Selbstverwaltung (Team + Mitglieder bearbeiten)
- Admin-Settings: Saisons, Benutzer, Drucker, Ankündigungen, Filament-Spulen, Saison-Module
- Team-Create, Profilseite (Name/Sprache/Passwort), Druck-Kontingent-Anzeige
- 4 latente Berechtigungs-Bugs behoben (Migrationen 0010–0013: `papers:write`, `teams:admin`, `dashboard:write` waren nie geseedet)

---

## 🟡 Offen – sinnvoll umzusetzen

### Scoring
- [ ] **Einzelne Wertung bearbeiten** – `PATCH /scoring/matches/{id}`. Aktuell nur Erstellen/Bestätigen/Löschen; Korrektur nur über Löschen + Neu-Erfassen.
- [ ] **Bulk-Wertungserfassung** – `POST /scoring/seasons/{id}/matches/bulk`. Schnelleingabe mehrerer Matches (z. B. Score-Table). Einzeleingabe existiert.

### Saisons
- [ ] **Saison-Phasen verwalten** – anlegen/bearbeiten/aktivieren (`PUT /seasons/{id}/phases/{phase_id}/activate`). Aktuell keine Phasen-UI (Seeding/Elimination/Final).
- [ ] **Saison-Detailfelder bearbeiten** – Registrierungs-/Event-/Deadline-Daten. Bisher nur Anlegen/Aktivieren/Löschen.

### Benutzer & Rollen
- [ ] **Rollen bestehender Benutzer ändern** – nur Anlegen + Aktivieren/Deaktivieren vorhanden (`PATCH /auth/users/{id}` mit `role_ids` ungenutzt).
- [ ] **Eigene Rollen anlegen** – `POST /auth/roles` (Rollen-/Rechteverwaltung). Kein UI.

### Exports
- [ ] **matches.csv-Export** – `GET /exports/seasons/{id}/matches.csv`. Button fehlt in den Export-Buttons (Rangliste/Papers/Teams/3D-Druck vorhanden).

---

## 🔧 Offen – benötigt zusätzlich Backend-Arbeit
- [ ] **Wettbewerbsstufen (Competition Levels) verwalten** – werden nur gelesen; es gibt keinen Create/Update/Delete-Endpoint dafür.
- [ ] **Druck-Kontingente pro Team bearbeiten** – Kontingent wird angezeigt, aber es existiert kein Endpoint zum Setzen von `max_parts` / `max_grams` pro Team+Saison.

---

## ⚪ Bewusst nicht umgesetzt (redundant zu bereits Genutztem)
- `GET /scoring/seasons/{id}/ranking` – Basis-Rangliste; das Frontend nutzt `ranking/extended`.
- `PUT /scoring/seasons/{id}/{de|aerial|doc}-results/{team_id}` – Einzel-Varianten; die Bulk-`PUT`-Endpoints sind verdrahtet.
- `GET /papers/{id}/reviews` – Reviews sind bereits in der Paper-Antwort (`GET /papers/{id}`) enthalten.
- `GET /scoring/matches/{id}`, `GET /auth/users/{id}` – Einzelabrufe; die Listen-Endpoints werden verwendet.

---

## ⚠️ Bekannte Einschränkungen / Hinweise
- **`.local`-E-Mails**: `UserCreate.email` ist `EmailStr` und lehnt reservierte TLDs wie `.local` ab. Die Seed-Logins (`@test.local`) funktionieren nur, weil das Seed-Script die Schema-Validierung umgeht. Über das Anlege-Formular echte Domains verwenden.
- **Branch nicht gepusht**: Alles liegt lokal auf `feature/detail-pages-and-review-workflow` (10 Commits). Verifiziert via `tsc -b`, API-Stichproben und Browser-Checks – es wurden **keine automatisierten E2E-Tests** ergänzt.
- **Pytest-Suite** wurde für die neuen Endpoints/Migrationen (0010–0013) **nicht aktualisiert**.
- **Phasen im Seed**: Die Test-Saison hat Phasen (Seeding/Double-Elimination), aber ohne Verwaltungs-UI sind sie nicht editierbar.
