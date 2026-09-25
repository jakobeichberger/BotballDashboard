# Done – umgesetzter Stand

Stand: 2026-09-25, Commit `aa61752`, Migrationen `0001`–`0029`. Die Liste ist nach Modulen gegliedert. Jeder Punkt ist gegen den Code geprüft. Offenes steht in [todo.md](todo.md), die Änderungen chronologisch in [CHANGELOG.md](../CHANGELOG.md).

---

## Infrastruktur und Betrieb

- Docker-Compose-Dienste `traefik`, `db` (PostgreSQL 16), `redis`, `backend`, `worker`, `beat`, `frontend`. Im Profil `production` kommt `backup` dazu, im Profil `monitoring` `prometheus`, `blackbox` und `alertmanager`. Alle Dienste mit Log-Rotation.
- `scripts/proxmox-setup.sh` erzeugt alle Secrets, darunter den Fernet-Schlüssel und das age-Schlüsselpaar für Backups. Es startet **alle** Dienste inklusive Worker und Beat und prüft danach mit `scripts/verify-deployment.sh`.
- `scripts/update.sh` baut die Images neu, merkt sich Commit und Alembic-Stand für ein Rollback und prüft danach. `deploy.yml` läuft per `workflow_dispatch` über SSH auf dem Host.
- `.env.example` enthält alle Variablen. In Produktion werden Standard-Secrets und ein ungültiger Fernet-Schlüssel abgelehnt. `SMTP_HOST` leer bedeutet: kein Mailversand.
- Backups: `backup.sh` bricht bei Fehlern laut ab. `backup_scheduler.py` wiederholt fehlgeschlagene Läufe, führt eine Statusdatei und liefert Metriken. `restore.sh` und `restore-test.sh` prüfen die Uploads per Manifest.
- Alertmanager-Regeln: API down, Readiness, 5xx-Rate, Backup fehlgeschlagen, veraltet oder nie gelaufen.
- `/api/system/health`, `/api/system/readiness` (PostgreSQL, Redis, Worker) und `/api/system/metrics` (nur intern).
- Uvicorn mit `--proxy-headers` und `FORWARDED_ALLOW_IPS`. nginx setzt die Security-Header auch auf `index.html` und Assets.
- CI: ruff, mypy und pytest mit Coverage-Bericht; Alembic up/down/up auf PostgreSQL; pip-audit; ESLint, tsc, Vitest und Build; Playwright-Smoke (`platform.spec.ts`); Build und Prüfung des Produktions-Stacks.
- Pre-commit: ruff (check und format), ESLint, shellcheck, YAML.

## Architektur

- Modularer Monolith mit statischer Registry: `backend/core/modules.py` und `frontend/src/core/plugins.ts`. Die ungenutzte `manifest.json` ist entfernt.
- Einheitliches Fehlerformat `{code, message, fieldErrors, requestId}`, `X-Request-ID`, Größenlimit für Requests, Security-Header, Audit jeder erfolgreichen Änderung in `audit_logs`.
- Redis-Rate-Limits im Backend für Login, Refresh, Passwort, E-Mail, Kontolöschung, Reset und Uploads.
- Celery-Worker und -Beat: OCR, Drucker-Polling, Outbox, Match- und Deadline-Erinnerungen, Paper-Fristen.
- Live-Stream über Redis Pub/Sub. Veröffentlicht wird erst nach dem Commit (`publish_after_commit`). Einziger WebSocket ist der öffentliche Event-Stream.
- Transaktionale Outbox (`notification_events`) mit `FOR UPDATE SKIP LOCKED`, Backoff und maximal 5 Versuchen. Zugestellt gilt nur, was tatsächlich versendet wurde. Abgelaufene Push-Abos werden entfernt. Migrationen `0012`, `0024`.

## Auth und Konto (`0002`, `0021`, `0027`)

- Benutzer, Rollen, Rechte. Fünf Standardrollen mit den Rechten aus `0002`, `0010`, `0012`–`0014`, `0016`, `0017`. Eigene Rollen und editierbare Rechte (`PUT /auth/roles/{id}`, die Admin-Rolle behält ihre kritischen Rechte).
- JWT mit PyJWT (HS256 fest, `exp`/`sub` Pflicht). Refresh-Token als HttpOnly-Cookie mit Rotation. `token_version` beendet alle Sitzungen bei Passwortänderung, Reset, Deaktivierung und Löschung. Logout setzt das Access-Token auf eine Redis-Sperrliste. python-jose und ecdsa sind entfernt.
- Passwort-Reset per E-Mail: gehashter Einmal-Token, 1 h gültig. Admins können Passwörter setzen. Passwort-Policy: mindestens 10 Zeichen, kein Wiederholungszeichen, nicht die E-Mail.
- Profil: Anzeigename, Sprache, Theme (im Konto gespeichert), E-Mail-Änderung, Datenexport (`GET /auth/me/export`), Kontolöschung als Anonymisierung, auch durch Admins.
- Benachrichtigungs-Einstellungen pro Kategorie (`users.notification_preferences`) und Benachrichtigungszentrale mit Lesestatus (`0027`).
- `create_admin.py --reset` macht niemanden mehr zum Superuser. Dafür gibt es nur noch `--superuser`.

## Saisons (`0003`, `0009`, `0018`, `0021`)

- Saisons mit Modul-Flags, aktiven Kategorien, Terminen, Phasen und Wettbewerbsstufen (Reihenfolge, „qualifiziert aus", `0028`).
- Lebenszyklus `draft`/`active`/`finished`/`archived`. Zentraler Archiv-Schutz `ensure_writable` in Scoring, Events, Paper, Druck und Registrierungen. Entwürfe sehen nur Organisatoren. Löschen ist nur ohne Daten möglich.
- `SeasonCreate` beachtet `is_active` und kann das Standard-Event auslassen (Einrichtungsassistent).
- Klonen (Konfiguration, Termine um die Jahresdifferenz verschoben, Events als leere Entwürfe, Schemas, Formeln, Bracket-Gewichte) und JSON-Export.
- Zusätzliche Termine und Deadlines pro Saison (`season_events`, `0018`). Das Anmeldefenster wird für Nicht-Admins durchgesetzt.

## Events und Turnier (`0010`, `0024`, `0027`)

- Events mit Slug, Zeitzone, Tischen, Status (`draft`, `published`, `live`, `completed`, `archived`), öffentlichen Freigaben und Modulen.
- **Modul-Aktivierung pro Event:** `active_modules` zusammen mit den Saison-Flags. 404 für abgeschaltete Module in Paper, Druck, Bots, DE, Aerial, Doku und Druck-Checkliste; 409 für deren Phasen. `GET /v1/events/{id}/modules`. Frontend mit `ModuleRoute` und ausgeblendeter Navigation (`0027`).
- Registrierungen, Phasen (`seeding`, `double_seeding`, `double_elimination`, `alliance`, `final`), Zeitplan-Generator.
- Double-Elimination-Bracket (`events/brackets.py`):
  - Standard-Setzreihenfolge, Freilose;
  - Loser-Bracket mit Minor- und Major-Runden;
  - Grand Final und Reset-Finale;
  - automatisches Weiterrücken, auch nach Korrekturen;
  - DE-Platzierungen landen in `de_results`.
- Setzliste aus der Seeding-Rangliste. Double Seeding als rotierende Paarungen. Alliance als Partnerpaare mit Summen-Score. Bracket-Labels über A/B hinaus. Bracket-Gewichte pro Event (`0024`).
- Öffentliche Event-API mit Rangliste, Zeitplan, Bracket, Ergebnissen (ohne Übungsläufe), Ankündigungen, QR-Code und WebSocket. Jede Teilansicht verlangt ihr Freigabe-Flag.
- Einrichtungsassistent (`/setup`) und Event-Verwaltung mit Modul-Schaltern, Phasen, Teams, Schema-Editor, Regeln, Qualifikation und Ankündigungen.

## Teams (`0004`, `0016`, `0029`)

- Teams und Mitglieder. `TeamMember.user_id` verknüpft Konten (nur `teams:admin`) und ist die Grundlage aller Prüfungen auf das eigene Team (`assert_team_access`).
- Mentoren pflegen ihr Team selbst (`teams:write`). Teams anlegen und löschen sowie Registrierungen bestätigen braucht `teams:admin` (`0016`).
- Suche und Filter, Länderliste, Team-Saison-Matrix.
- Saison-Details: Kategorie, Gebühr, Kit, Paper-Pflicht, Kontakt, Adresse. Saison-Kader. Kontaktdaten sind für andere Teams und Gäste ausgeblendet (`0029`).
- Versionierte Team-Dokumente (PDF/Bild, inhaltlich geprüft), nur für das eigene Team und die Organisation (`0029`).
- 3D-Druck-Checkliste pro Saison: Standardregeln, Abhaken durch das Team, Bestätigung durch die Organisation (`0029`).
- Mehrjahres-Historie mit Diagrammen, Team-Bericht PDF, Historie CSV.

## Scoring (`0005`, `0011`, `0013`, `0015`, `0025`, `0028`)

- Versionierte Score-Sheet-Schemas pro Event und Stufe. Jede Wertung speichert eine Kopie des Schemas. Die Summe wird immer serverseitig berechnet. Unbekannte Felder ergeben 422.
- **Strukturierte Score-Sheets** (`scoring/sheet.py`):
  - Bereiche mit Multiplikator;
  - Entweder-oder-Gruppen;
  - Seiten A/B;
  - Zähl-, Zahl- und Ja/Nein-Felder mit Maximalwerten.

  Vorlagen 2024/2025 vollständig, 2026 als Struktur. Liste der Schemas und „Klonen von". Der Frontend-Rechner nutzt dieselben Fixtures (`0028`).
- **Regeln pro Saison:** Tie-Breaker-Reihenfolge mit Presets 2024/2025/2026, Finals-Replay, Kontakt-Bonus (25 %), Schiedsrichter-Checkliste vor dem Bestätigen. „Runde verloren" (0 Punkte, keine DQ). Duell-Ergebnis und DE-Platzierung mit dem entscheidenden Tie-Breaker. Parts Challenges (nur API) (`0028`).
- **Seeding nach Game Review:**
  - nur Läufe aus Seeding-Phasen;
  - DQ und verlorene Runde zählen 0, negative Werte zählen 0;
  - Ø der besten zwei Läufe;
  - Ränge je Kategorie mit geteilten Plätzen;
  - rote Karte ⇒ Team ohne Rang und raus aus dem Feld;
  - n und Feld kommen aus dem Event (`0025`).
- **Formel-Engine:**
  - sicherer AST-Evaluator mit Längen- und Tiefenlimit, maximal 60 Formeln;
  - Formeln pro Saison und Kategorie;
  - Presets ECER 2025 (Botball/Open), Regional 2026, GCER 2026 (Doku = nur Onsite), Aerial, JBC;
  - Vorschau mit echten Daten;
  - Standard reproduziert die ECER-Ergebnisse 2025 (`0013`).
- DE-, Aerial- und Doku-Ergebnisse pro Event. Aerial = Ø aller Läufe, Doku 0,2/0,2/0,2/0,4. Audit in `result_revisions` (`0025`).
- Score-Revisionen bleiben nach dem Löschen einer Wertung erhalten (`match_id` SET NULL, `match_ref`) (`0025`).
- Übungsläufe (`is_practice`) zählen nirgends für Ranglisten (`0015`). Mentoren erfassen Wertungen fürs eigene Team (`0014`).
- **Offline-Erfassung:** IndexedDB-Warteschlange mit `idempotency_key`, Abspielen beim Start, beim Wiederverbinden und minütlich; Konfliktanzeige. Service Worker mit NetworkFirst für ausgewählte GETs.
- Mobile Wertung: Navigation durch die Matches, Wischen, Bestätigungsdialog.
- Score-Sheet-PDF-Vorlagen (pdftotext im Worker) und lokale OCR von Fotos (OpenCV/Tesseract im Worker) mit Pflicht-Prüfung vor der Übernahme (`0001`, `0011`).
- Scouting: externe Teams, Notizen und Beobachtungen pro eigenem Team, Gegner-Rangliste, PDF-Bericht (`0028`).
- Qualifikation: Stufen-Reihenfolge, manuelle Qualifikation, Registrierung der Qualifizierten. Für qualifizierte Stufen ist eine Qualifikation Pflicht (`0028`).

## Paper-Review (`0006`, `0012`, `0014`, `0023`, `0029`)

- Ein Paper pro Team und Saison. Jeder Upload wird eine eigene Version, Download pro Version, Text-Diff zwischen Versionen (pypdf).
- Status `draft` → `submitted` → `under_review` → `revision_requested` → `resubmitted` → `accepted`/`rejected`, dazu `disqualified_ai`. Statushistorie mit Begründung.
- Deadlines: Paper-Deadline der Saison bis Tagesende in der Event-Zeitzone. Offizielle und interne Deadlines (`paper_deadlines`, `0029`), `papers:admin` darf übersteuern. Erinnerungen 7/3/1 Tage vorher.
- Reviews:
  - fünf Kriterien (0–10) mit Kommentaren, Revisionshinweise, private Notizen, Empfehlung;
  - nach der Abgabe gesperrt, wieder öffnen durch Admins;
  - Reviewer aus dem eigenen Team oder derselben Schule werden abgelehnt.
- Automatische Zuweisung mit Vorschau, Reviewer-Auslastung, stündliche Prüfung überfälliger Zuweisungen.
- Formalabzug und Finalisieren zu `final_score` (0–1). Score-Felder nur über `PUT /papers/{id}/score` (`papers:admin`).
- Feedback für Teams ohne Identität der Reviewer. Statistik, Paper-Export CSV/PDF, Reviews CSV.
- Mentoren sehen nur Papers des eigenen Teams.

## 3D-Druck (`0007`, `0022`)

- Drucker `bambu` (MQTT), `octoprint` (REST), `generic` (manuell, ohne Adapter). Zugangsdaten Fernet-verschlüsselt. Polling alle 15 s mit Fortschritt, Restzeit und Fehlern.
- Datei-Upload (STL, 3MF, OBJ, G-Code, bgcode), inhaltlich geprüft, bis `PRINT_UPLOAD_MAX_MB`. Download immer als Anhang.
- Kontingente pro (Event, Team), eindeutig. Das Hard-Limit zählt offene Jobs mit. Gramm-Limit. Soft-Limit liefert `quota_warning`. Admin-Override wird markiert und protokolliert.
- Status inklusive `rejected` (mit Begründung). Abbrechen durch das Team (eigener offener Job) oder Admins. Ein laufender Druck wird auch am Drucker gestoppt.
- Verbrauch und Spule werden beim Abschluss aufs Kontingent und die Spule gebucht. Filament-Spulen.
- `compliance_warning`, wenn die Druck-Checkliste des Teams unvollständig ist.

## Dashboard und Analyse (`0008`, `0017`, `0026`)

- Ankündigungen mit Zielgruppe. Öffentlich und als Push an alle nur mit Zielgruppe `all`.
- Rollenbezogene Übersicht (`/dashboard/summary`):
  - Juror-Warteschlange;
  - Mentor-Karten je Team;
  - Orga-Fortschritt X von N;
  - Deadlines.

  Paper- und Druck-Angaben entfallen, wenn das Modul aus ist.
- Performance: Teamvergleich, Verlauf mit Übungsläufen, Stärken und Schwächen je Aufgabe, Ranking-Vorschau, Phasen- und Event-Vergleich.
- Statistik (`scoring:admin`): Boxplots, Heatmap, Trends, Anomalie-Erkennung mit Prüf-Dialog.
- Deadline-Kalender, Saison-Zeitleiste, persönlicher iCal-Feed mit widerrufbarem, gehashtem Token (`0026`).
- Exporte:
  - Seeding und Gesamtwertung pro Event als CSV/PDF;
  - Wertungen CSV;
  - Paper, Reviews, Druck, Teams;
  - Team-Bericht, Team-Historie, Mehrjahresvergleich.

  CSV mit BOM und Schutz gegen Formel-Injection.

## Bot-Galerie (`0019`, `0020`)

- Bots eigener und externer Teams mit Bild (Magic-Byte-geprüft, Medientyp gespeichert). Unveröffentlichte Bots sehen nur Admins und das eigene Team. Externe Bots pflegt nur `teams:admin`.

## PWA

- Manifest mit PNG-Icons (192, 512, maskable), apple-touch-icon, Favicon.
- Web Push mit VAPID. Push-Einstellungen pro Kategorie. Benachrichtigungszentrale im Header.
- Theme (hell/dunkel/System) wird im Konto gespeichert.

## Tests

- Backend:
  - pytest, Unit- und Integrationstests für alle Module, dazu Rechte- und Team-Scoping-Regressionstests (z. B. `test_security_scoping.py`, `test_mentor_event_scoping`);
  - Akzeptanztests ECER 2025;
  - PostgreSQL-Abhängigkeitstests.
- Frontend: Vitest mit Testing Library und jest-axe. Der Score-Sheet-Rechner läuft gegen die gemeinsamen Fixtures.
- Playwright: `platform`, `auth`, `gallery`, `scoring`. In der CI läuft nur `platform`.
