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
- 4 latente Berechtigungs-Bugs behoben (Migrationen 0010–0014)
- **Tests**: 14 neue Tests (Season-Events, Level-CRUD, Quota, Rollen, Finalisierung, Übungsläufe, Team-Zugriff); Gesamtsuite **574 grün**

## 🟢 Keine substanziell offenen Features mehr
Alle ursprünglich offenen Punkte sind abgearbeitet.

## ⚪ Bewusst nicht umgesetzt (redundant zu bereits Genutztem)
- `GET /scoring/seasons/{id}/ranking` – Basis-Rangliste; Frontend nutzt `ranking/extended`.
- `POST /scoring/seasons/{id}/matches/bulk` – Bulk-Eingabe; Einzeleingabe ist verdrahtet.
- `PUT /scoring/seasons/{id}/{de|aerial|doc}-results/{team_id}` – Einzel-Varianten; Bulk-`PUT` ist verdrahtet.
- `GET /scoring/matches/{id}` – Einzelabruf; die Bearbeitung nutzt die Listendaten.
- `GET /papers/{id}/reviews` – Reviews sind bereits in `GET /papers/{id}` enthalten.
- `GET /auth/users/{id}` – Einzelabruf; die Benutzerliste wird verwendet.

## ⚠️ Bekannte Einschränkungen / Hinweise
- **`.local`-E-Mails**: `UserCreate.email` (`EmailStr`) lehnt reservierte TLDs wie `.local` ab. Die Seed-Logins (`@test.local`) funktionieren nur, weil das Seed-Script die Validierung umgeht. Im Formular echte Domains verwenden.
- **Tests**: Pytest-Suite auf **574 grün** (14 neue Tests für die neuen Endpoints); Frontend via `tsc -b`, API-Stichproben und Browser-Checks verifiziert. Keine automatisierten Frontend-E2E-Tests.
- **Dependabot**: GitHub meldet Sicherheits-Findings bei Abhängigkeiten (unabhängig von diesen Änderungen) – separat prüfen.
