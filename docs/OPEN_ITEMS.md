# Offene Punkte – aktueller Stand

Stand: 2026-09-25 · Commit `aa61752` (integrierter Stand nach PR #20, #22, #23 und den Paketen der Audit-Nacharbeit) · Migrationen `0001`–`0029`, eine lineare Kette.

Die Befunde aus [audit-2026-09.md](audit-2026-09.md) sind bis auf die dort als offen markierten Punkte umgesetzt. Die vollständige Liste offener Aufgaben steht in [todo.md](todo.md). Diese Seite fasst den Stand zusammen.

---

## Zusammenfassung

- **Turnierbetrieb:**
  - eventzentrierte Wertung mit strukturierten Score-Sheets, Tie-Breakern, Sonderregeln, Brackets mit automatischem Weiterrücken, Formel-Engine und Offline-Erfassung;
  - Worker und Beat laufen in jeder Installation mit.
- **Sicherheit:**
  - Prüfungen auf das eigene Team für Papers, Druck, Wertungen, Scans, Dokumente, Bots und Scouting;
  - Archiv-Schutz, Token-Widerruf, Passwort-Reset, DSGVO-Export und Kontolöschung.

  Restrisiken siehe [SECURITY.md](SECURITY.md#residual-risks).
- **Dokumentation:** API-Referenz, Datenbankschema, Architektur und Handbücher entsprechen dem Code (dieser Stand).

## Früher gemeldete Bugs

| Befund | Stand |
|---|---|
| Doppelte Ränge bei gemischten Wettbewerbsstufen (`_refresh_ranks`) | **Behoben.** Ränge werden pro Event, pro Stufe (`competition_level_id`, `NULL` als eigene Gruppe) und pro Kategorie berechnet, mit geteilten Plätzen. Die Produktfrage „global oder pro Stufe" ist damit zugunsten „pro Stufe und Kategorie" entschieden. |
| Race beim Quota-Upsert | **Behoben.** `team_season_print_quotas` ist eindeutig pro `(event_id, team_id)`. Constraint seit Migration `0010`. Außerdem löst `printing/service.py::set_quota` Kontingente immer pro Event auf, auch bei Saisons mit mehreren Events. |

## Nur per API, ohne Oberfläche

Siehe [todo.md → Funktionen](todo.md#funktionen). Betroffen sind:

- Karten und DQ;
- Parts Challenges;
- Event-Check-in;
- Bracket-Gewichte pro Event;
- Event-Audit-Trail;
- Phasen bearbeiten oder löschen;
- Alliance-Paare;
- externe Teams bearbeiten;
- Paper-Statushistorie;
- manuelle Reviewer-Erinnerung;
- OCR-Retry und OCR-Layout.

Einige Endpunkte sind bewusst Alternativen zu bereits verdrahteten und werden deshalb vom Frontend nicht aufgerufen:

- `POST /scoring/seasons/{id}/matches/bulk`;
- die Einzel-`PUT`s `…/{de-results|aerial-results|doc-scores}/{team_id}`;
- `GET /scoring/matches/{id}`;
- `GET /papers/{id}/reviews`;
- `GET /auth/users/{id}`.

## Bekannte Einschränkungen

- **`.local`-Adressen:** `EmailStr` lehnt reservierte TLDs wie `.local` ab. Die Dev- und Seed-Konten (`admin@dev.local`) legen Skripte an, die die Validierung umgehen. Im Formular echte Domains verwenden.
- **E2E-Tests** brauchen den laufenden Stack mit Seed-Daten:

  ```bash
  cd frontend && pnpm install && pnpm exec playwright install chromium
  E2E_BASE_URL=http://localhost:5173 pnpm e2e
  ```

  Die CI (manuell gestartet) führt die ganze Playwright-Suite gegen `backend/scripts/seed_e2e.py` aus: alle Specs auf Desktop-Chromium, die `@mobile`-Flows zusätzlich auf einem Pixel-7-Profil.
- **i18n:** Alle Seiten nutzen Übersetzungsschlüssel in `de` und `en` (geprüft von `frontend/src/__tests__/i18n/translationKeys.test.ts`).
