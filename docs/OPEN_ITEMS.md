# Offene Punkte

Stand: 2026-07-15 · Branch `feature/detail-pages-and-review-workflow` (gepusht)

Ausgangslage war ein weitgehend **read-only** Frontend (ca. die Hälfte der API ungenutzt).
Aktuell: **96 / 105 Endpoints genutzt** — die 9 verbleibenden sind fast alle redundante
Alternativen zu bereits verdrahteten Endpoints.

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
- 4 latente Berechtigungs-Bugs behoben (Migrationen 0010–0014)

## 🟡 Offen – sinnvoll umzusetzen
- [ ] **Eigene Rollen/Rechte anlegen** – `POST /auth/roles`. Rollen sind aktuell fix (admin/juror/reviewer/mentor/guest); es gibt kein UI, um benutzerdefinierte Rollen mit eigener Rechte-Auswahl zu erstellen.

## ⚪ Bewusst nicht umgesetzt (redundant zu bereits Genutztem)
- `GET /scoring/seasons/{id}/ranking` – Basis-Rangliste; Frontend nutzt `ranking/extended`.
- `POST /scoring/seasons/{id}/matches/bulk` – Bulk-Eingabe; Einzeleingabe ist verdrahtet.
- `PUT /scoring/seasons/{id}/{de|aerial|doc}-results/{team_id}` – Einzel-Varianten; Bulk-`PUT` ist verdrahtet.
- `GET /scoring/matches/{id}` – Einzelabruf; die Bearbeitung nutzt die Listendaten.
- `GET /papers/{id}/reviews` – Reviews sind bereits in `GET /papers/{id}` enthalten.
- `GET /auth/users/{id}` – Einzelabruf; die Benutzerliste wird verwendet.

## ⚠️ Bekannte Einschränkungen / Hinweise
- **`.local`-E-Mails**: `UserCreate.email` (`EmailStr`) lehnt reservierte TLDs wie `.local` ab. Die Seed-Logins (`@test.local`) funktionieren nur, weil das Seed-Script die Validierung umgeht. Im Formular echte Domains verwenden.
- **Tests**: Die Pytest-Suite wurde für die neuen Endpoints/Migrationen (0010–0014) **nicht** aktualisiert; Verifikation erfolgte via `tsc -b`, API-Stichproben und Browser-Checks.
- **Dependabot**: GitHub meldet Sicherheits-Findings bei Abhängigkeiten (unabhängig von diesen Änderungen) – separat prüfen.
