# Todo – offene Aufgaben

Stand: 2026-09-25, Commit `aa61752`, Migration `0029`. Hier steht nur, was im Code **nachweislich noch fehlt**. Erledigtes steht in [done.md](done.md), die Einordnung der Audit-Befunde in [audit-2026-09.md](audit-2026-09.md).

---

## Funktionen

- [ ] **Karten und DQ in der Wertungsoberfläche.** `yellow_card`, `red_card` und `is_disqualified` lassen sich nur per `PATCH /api/scoring/matches/{id}` setzen. `EventScoringPage.tsx` und `ScoreEntryPage.tsx` haben keinen Schalter dafür. Die Wirkung im Backend (DQ = 0, rote Karte ⇒ Team ohne Rang) ist umgesetzt.
- [ ] **Parts Challenges ohne Oberfläche.** Die API gibt es (`/api/scoring/events/{id}/parts-challenges`, `…/ruling`), eine Seite fehlt.
- [ ] **Weitere Funktionen nur per API:**
  - manuelle Reviewer-Erinnerung (`…/assignments/{id}/remind`);
  - Event-Check-in (`PATCH …/registrations/{id}`, `checked_in_at`);
  - Bracket-Gewichte pro Event (`/api/v1/events/{id}/bracket-weights`);
  - Audit-Trail eines Events (`/api/scoring/events/{id}/revisions`, `/result-revisions`). In der Oberfläche sind nur die Revisionen einzelner Läufe zu sehen, im Statistik-Dialog;
  - Event-Phasen bearbeiten oder löschen (`PATCH`/`DELETE /api/v1/events/{id}/phases/{phase_id}`). Die Event-Verwaltung kann nur anlegen;
  - Alliance-Paare anzeigen (`…/phases/{id}/alliances`);
  - externe Scouting-Teams bearbeiten oder löschen;
  - Paper-Statushistorie (`/api/papers/{id}/history`);
  - OCR-Scan erneut verarbeiten (`…/score-sheet-scans/{id}/retry`);
  - OCR-Layout einer Score-Sheet-Vorlage (`PATCH /api/scoring/score-sheets/{id}/layout`).
- [ ] **Saison klonen ist unvollständig.** `modules/seasons/portability.py::clone_season` kopiert weder die Tie-Breaker- und Sonderregeln (`scoring_rule_sets`) noch die Paper-Deadlines (`paper_deadlines`) noch die Druck-Checkliste (`print_compliance_items`).
- [ ] **Rollennamen statt Rechten im Frontend.**
  - `ScoreboardPage.tsx` zeigt die Buttons „Score-Sheets", „DE/Aerial/Doku eingeben" nur für die Rolle `admin` und „Wertung erfassen" nur für `admin`/`juror`/`mentor`.
  - `ScoreEntryPage.tsx` (`canManageAll`) prüft ebenfalls Rollennamen.

  Eigene Rollen mit `scoring:admin` sehen die Buttons deshalb nicht. Die Routen selbst sind korrekt über Rechte geschützt.
- [ ] **i18n unvollständig.** Nur `DashboardPage`, `PublicEventPage` und `EventScoringPage` (plus Layout und Komponenten) nutzen `useTranslation`. 27 Seiten enthalten fest deutschen Text. Die Rückfallsprache ist `de` (`frontend/src/i18n/config.ts`), laut Spezifikation Englisch.
- [ ] **Registry-Felder ungenutzt.** `dashboardWidgets` und `translations` in `frontend/src/core/plugins.ts` liest keine Komponente. Entweder anbinden oder entfernen.
- [ ] **Score-Sheet 2026.** Die Vorlage enthält nur die Struktur aus dem Game Review. Die Punktwerte trägt die Organisation im Schema-Editor ein.

## Produktentscheidungen

- [ ] **Öffentliche Ranglisten-Endpunkte.** `/api/scoring/seasons|events/{id}/ranking*` und `…/aerial-ranking` sind ohne Login lesbar und ignorieren die `public_*`-Flags und den Event-Status. Das ist gewollt (Test `test_ranking_public_no_auth`), gibt aber Ranglisten von Entwurfs-Events preis, wenn jemand die ID kennt. Entscheidung: an die Freigaben koppeln oder so lassen.
- [ ] **Gäste und OCR-Scans.** `guest` hat `scoring:read` und kann damit Scans aller Teams einschließlich der Bildausschnitte abrufen. Soll das so bleiben?

## Qualität und Betrieb

- [ ] **E2E in CI:** Nur `frontend/e2e/platform.spec.ts` läuft. `auth`, `gallery` und `scoring` brauchen Seed-Daten, die `backend/scripts/seed_e2e.py` nicht anlegt.
- [ ] **Keine Coverage-Schwellen.** Das Backend läuft mit `--cov`, aber ohne `fail_under`. Vitest hat keine thresholds. Prettier gibt es nicht (Pre-commit: ruff, eslint, shellcheck, YAML).
- [ ] **Passwort-Policy:** mindestens 10 Zeichen, kein Wiederholungszeichen, nicht die E-Mail. Es gibt keine Prüfung gegen bekannte geleakte Passwörter.
- [ ] **Off-site-Backup** ist dokumentiert (`BACKUP_HOST_DIR` plus rsync/rclone per Cron, siehe [operations.md](operations.md)), wird aber nicht von der Installation eingerichtet.
- [ ] **Redis-Ausfall:** Rate-Limits und die Access-Token-Sperrliste lassen dann alles durch (fail open). Das ist beabsichtigt, damit Login und Wiederherstellung möglich bleiben, sollte aber im Monitoring sichtbar sein.

## Bewusst nicht geplant

- Laufzeit-Plugins, `manifest.json`: Es bleibt bei der statischen Registry.
- Eigener OCR-Dienst: Die OCR läuft im Worker.
- Audit- oder Error-Log-Oberfläche: Die Daten liegen in `audit_logs` und in den Container-Logs.
- Einladungs-Links und Selbstregistrierung: Konten legen Admins an.
