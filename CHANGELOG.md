# Changelog

Alle nennenswerten Änderungen am BotballDashboard. Das Format folgt [Keep a Changelog](https://keepachangelog.com/de/1.1.0/). Das Projekt hat noch keine Versionsnummern. Die Abschnitte unter „Unreleased" sind deshalb nach den gemergten Pull Requests benannt.

## [Unreleased]

### AIRCER 2026: Score-Sheet

- **Vorlage `aircer_2026` („AIRCER 2026 – Laboratory Lockdown“)** aus Scoring Sheet 1.0 und Game Manual 1.0 von robo4you: neun Bereiche, eine Seite pro Team, Tie-Breaker-Felder `centrifuge_sorted_drums`, `centrifuge_unsorted_drums`, `waste_rocks`, `safety_lever`.
- **Neue Multiplikator-Arten im Score-Sheet:** Summen-Multiplikator (`type: "sum"`, `inputs`, `mode: "sum" | "product"`) für „Max Stack Height + # of Stacks“, Abzug (`allow_below_one`) für die Restricted Area Rule (× 0,5) und die Null-Regel (`zero_means: "neutral" | "zero"`). Backend und Live-Vorschau rechnen identisch (gemeinsame Fixture, 27 neue Fälle); bestehende Vorlagen und gespeicherte Schemas bleiben unverändert.
- Offene Fragen der AIRCER-Dokumente (Summe oder Produkt, leeres Feld, fehlendes „=“ bei Unsorted Drums) stehen in den Vorlagen-Notizen; die Standards sind im Schema-Editor umschaltbar. Details: `docs/modules/05-scoring.md`.

### Review 2: Backend-Sicherheit und -Performance

- **Passwort-Reset:** Der Reset-Link steht nur noch in Development im Log. Ohne Mail-Konfiguration schreibt Produktion eine Warnung `password_reset_mail_unavailable` ohne Token. Eine reine SendGrid-Konfiguration gilt als Mail-Konfiguration und versendet direkt über SendGrid.
- **Account-Mails nach dem Commit:** Reset- und Konto-Mails laufen nach dem Commit im Hintergrund (`core.task_queue.run_after_commit`). Die Antwort wartet nicht mehr auf den Mailserver, und ihre Laufzeit verrät nicht mehr, ob ein Konto existiert. SMTP und SendGrid haben ein Timeout von 15 s.
- **Refresh-Token:** Die Zeile wird mit `FOR UPDATE` gelesen. Wird ein bereits rotierter Token erneut vorgelegt, enden alle Sitzungen des Kontos, Access-Tokens eingeschlossen.
- **Paper-Upload:** Die Seitenzählung läuft in einem Worker-Thread mit Zeit- und Arbeitsgrenze (höchstens 1000 Seiten, 5000 Knoten, 15 s, zwei gleichzeitig). Ein PDF, dessen Seiten sich so nicht zählen lassen, wird abgelehnt und umgeht die 5-Seiten-Regel nicht mehr.
- **Review-Mahnungen** gehen nur noch an Reviewer von Papers im Review-Status und nicht mehr für archivierte Saisons.
- **Ranking-Cache:** `category` muss eine Kategorie der Saison sein (sonst 422, bevor etwas gecacht wird); `offset` der öffentlichen Ergebnisse ist begrenzt. Gleichzeitige Cache-Misses rechnen nur einmal (Single-Flight im Prozess, Redis-Lock über Instanzen). Das Frontend lädt Ranglisten nach `ranking_updated` gebündelt und um 300–1000 ms zufällig verzögert nach.
- **STL-Upload:** Die Bounding-Box wird blockweise gelesen (100-MB-STL: +6 MB statt +206 MB), höchstens zwei Messungen gleichzeitig.
- **Druck-Quota:** Ein Retry `failed → queued` prüft das harte Limit und braucht darüber `quota_override` (mit Audit-Eintrag). Einreichung und Retry sperren die Quota-Zeile, gleichzeitige Einreichungen überschreiten das Limit nicht mehr.

### Wertung: Korrektheit und Eingabe am Tisch (Review 2, Paket A)

- **DE-Scores nie negativ, solange ein Bracket läuft:** Jedes Team des Brackets hat ab dem ersten Ergebnis eine `de_results`-Zeile (ohne Platzierung, solange es noch dabei ist). `n_bracket` ist damit die Feldgröße, nicht die Zahl der schon ausgeschiedenen Teams. Ein Platz zählt während des Brackets so viel wie danach (vorher z. B. Platz 7 von 8: −2,0). Teams ohne Platzierung haben DE-Score 0. Die Dashboard-Kennzahl „DE-Ergebnisse“ zählt nur Zeilen mit Platz oder Score.
- **Aerial- und JBC-Teams bekommen keine Match-Scores:** Die Score-Eingabe (Entry-Seite und mobile Wertung) bietet nur die Teams des Events an, deren Kategorie Matches spielt (Art botball, open oder custom). Die API lehnt einen Match-Score für ein Aerial- oder JBC-Team mit 422 `category_has_no_matches` ab. Die Seeding-Rangliste (auch öffentlich und in Exporten) lässt solche Zeilen weg.
- **Doppelte Seeding-Runde wird abgelehnt:** Ein zweiter offizieller Lauf derselben Seeding-Runde (gleiche Rundennummer bzw. gleiches geplantes Seeding-Match) ergibt 409 `duplicate_round`, statt als zusätzlicher Lauf in den Seed-Score einzugehen. Korrekturen laufen über „Bearbeiten“ (mit Revision). Unverändert: Übungsläufe und Wiederholungen (Replay) eines Head-to-Head-Matches, bei denen wie bisher der neueste Lauf je Team zählt. Entry-Seite und Bestätigungsdialog nennen den vorhandenen Eintrag und bieten „Vorhandenen Eintrag korrigieren“ an; die mobile Wertung warnt bei einem schon gewerteten Match (Replay-Hinweis bei Head-to-Head).
- **Rundennummer:** `round_number` ist optional. Ein Lauf zu einem geplanten Match übernimmt dessen Runde und Tisch (vorher wurde wegen des Standardwerts 1 jede Runde als 1 gespeichert), ein freier Lauf die nächste freie Runde des Teams. Die Entry-Seite wählt beim Team die nächste freie Runde vor.
- **Tie-Breaker:** Der Vergleich ist jetzt total. Ein Team ohne Seeding-Rang kommt nach Teams mit Rang, statt allen gleich zu sein; nicht trennbare Teams stehen nach ID. Beim Seeding-Tiebreak zählen von gleich hohen Läufen die mit den für das Team besseren Tie-Breaker-Werten, dann der frühere, dann nach ID.
- **Sammel-Speichern von DE, Aerial, Doku und JBC** ohne Abfrage pro Eintrag: vorhandene Zeilen mit einer Abfrage, Regeln einmal, ein Flush, ein Reload (16 Teams kosten so viele Abfragen wie 4).
- **Eingabe am Handy:** sichtbare Bestätigung nach dem Speichern (Entry-Seite und in der Sticky-Leiste der mobilen Wertung, dazu ein Toast). Das Rundenfeld lässt sich normal überschreiben („1“, Löschen, „2“ ergibt 2) und hat +/−-Tasten, Zählfelder lassen sich leeren und haben 44-px-Stepper. Eingabefehler erscheinen übersetzt mit Feldname statt internem Schlüssel; negative Zählwerte werden schon beim Tippen erkannt, und Speichern ist bei Fehlern gesperrt. „Runde verloren“, „End-Kontakt“, „Wiederholt“ und Ja/Nein-Felder haben 44-px-Tap-Flächen.
- „Offline gespeichert“ verschwindet, sobald der Eintrag synchronisiert (oder verworfen) ist.
- Timeout-Karten: Lade- und Fehlerzustand mit „Erneut versuchen“ statt einer leeren Liste.

### Review 2: Awards und Frontend-UX

- **Awards:** „Entscheidung speichern“ übernimmt die bestehende Platzierung in die Auswahl und löscht sie nicht mehr mit einer leeren Liste. Das Backend lehnt eine leere Platzierung (422) und eine abweichende Platzierung eines entschiedenen Awards (409) ab, solange nicht `replace: true` mitgeschickt wird; die Seite fragt vorher „Bestehende Platzierung ersetzen?“. Nominierungen zurückziehen fragt ebenfalls nach.
- **Awards-Sichtbarkeit:** Gäste, Mentoren und andere ohne `awards:admin`/`scoring:admin` sehen nur die veröffentlichten Platzierungen, keine Nominierungen, Jury-Notizen oder `nominated_by`. CSV- und PDF-Export nur noch für die Jury. Nominieren und Platzieren nur für beim Event angemeldete Teams.
- **Performance:** Das Awards-PDF entsteht im Threadpool; „Berechnen“ rechnet jede Kategorie nur einmal. Der Login-Chunk schrumpft von 116 kB (36 kB gzip) auf 35 kB (13 kB gzip): Das Formular prüft ohne zod, `zod` und `@hookform/resolvers` entfallen.
- **3D-Druck:** Lehnt das Backend das erneute Einreihen eines fehlgeschlagenen Auftrags wegen des Kontingents ab (409), erklärt die Detailseite das; Druck-Admins können ihn nach Rückfrage „Trotz Kontingent freigeben“ (`quota_override`).
- **Handy:** Die App lässt sich nicht mehr über das Seitenende hinaus in eine graue Fläche scrollen (`relative` am Layout, `overscroll-contain` am Inhalt).
- **Fehlerzustände:** Awards, Aerial, JBC, Formeln und die Dashboard-Kennzahlen zeigen „Daten konnten nicht geladen werden“ mit „Erneut versuchen“ statt leerer Tabellen und Nullen. Aerial meldet fehlgeschlagene Speichervorgänge; Aerial und JBC warnen beim Schließen mit ungespeicherten Änderungen; „Formeln auf Standard zurücksetzen“ fragt nach.
- **Dashboard:** Die Jury bekommt ein eigenes Dashboard („Jury“ statt „Administrator“) mit nur den Kacheln und Kennzahlen, die sie öffnen darf und deren Module aktiv sind.
- **Texte und Barrierefreiheit:** Phasentypen und Score-Sheet-Abschnitte mit Namen statt interner Schlüssel, „Wertung“ statt „Scoring“, „Lauf“ in der Aerial-Tabelle, echte Pluralformen, axe-Befunde behoben (Paper-Kennzahlen, fokussierbare Scroll-Bereiche, `<main>` auf `/settings`, `h1` bei inaktivem Modul, Überschriften auf `/teams`, Spaltenkopf auf Performance). Neue Lint-Regel `local/no-literal-ui-attribute`: unübersetzte Texte in `aria-label`, `title`, `placeholder`, `alt` und `label` sind ein Fehler.

### Betrieb, Monitoring und Tests (Review 2026-09, Paket D)

- **Readiness pro Queue:** `/api/system/readiness` fragt alle Celery-Worker nach ihren Queues (statt die erste Ping-Antwort zu nehmen) und meldet `default`, `periodic` und `ocr` einzeln; ein toter `worker` fällt nicht mehr hinter einem laufenden `worker-ocr` weg. `/api/system/metrics` liefert `botball_celery_queue_consumers{queue}` und den Beat-Heartbeat (Beat schreibt ihn jetzt auch nach Redis).
- **Neue Alarme** (mit promtool-Tests): `WorkerQueueDown`, `BeatNotRunning`, `SiteUnreachable` und `TLSCertificateExpiresSoon`/`…Critical` (Blackbox-Probe von `https://$DOMAIN/` über Traefik), `Watchdog` als Totmannschalter an `ALERT_HEARTBEAT_URL` (externer Heartbeat-Dienst), `AlertmanagerNotificationsFailing`, `RestoreTestFailed`/`RestoreTestStale`. `BackupStale` richtet sich nach `BACKUP_INTERVAL_SECONDS`.
- **Restore-Test automatisch:** Der Backup-Dienst testet wöchentlich das neueste Archiv mit einem eigenen Test-Schlüssel (eigenes Volume, nie außer Haus); Ergebnis als Metrik und Alarm, manuelle Tests werden ebenso erfasst. `restore.sh` spielt in eine Staging-Datenbank in einer Transaktion ein und ersetzt die Produktion erst danach; `restore-test.sh` ebenfalls in einer Transaktion.
- **`update.sh`:** verifiziertes Backup vor den Migrationen (auch beim Deploy aus GitHub), Images pro Commit getaggt, `update.sh --rollback` startet die vorherige Version ohne Neubau (Downgrade mit gestopptem Backend, kein erneutes Upgrade), funktioniert auf detached HEAD. Der Deploy-Workflow deployt nur Commits mit grünem CI-Lauf.
- **Härtung:** `worker-ocr` ohne `.env` (keine JWT-/App-/Drucker-/SMTP-Secrets), postgres-exporter als `pg_monitor`-Rolle (automatisch angelegt), Redis mit `maxmemory` und `noeviction`. Der Dump von `postgres-upgrade.sh` wird mit age verschlüsselt, `--remove-old-data` löscht die Dumps.
- **CI:** Migrationen mit Seed-Daten (Round-Trip mit Vergleich), neuer Job „Deployment – update“ (vorherige Version mit Daten → `update.sh` → Rollback). Neue Tests für Umplanen, Check-in und Phasen (Backend) sowie `EventSchedulePage`, `EventSetupPage`, `ScoreboardPage` und `SettingsPage` (Frontend). Ein gefundener Fehler außerhalb des Pakets ist als xfail-Test dokumentiert: Zeiten ohne UTC-Offset beim Umplanen führen auf PostgreSQL zu HTTP 500.

### PostgreSQL 18, Redis 8 und Python 3.14

- **PostgreSQL 16 → 18** (`postgres:18-alpine`, 18.6) in Compose, CI und Doku. Das Volume `pgdata` (Proxmox: `/data/db`) hängt jetzt unter `/var/lib/postgresql`, der Cluster liegt wie im offiziellen Image ab 18 in `18/docker`.
- **Neu: `scripts/postgres-upgrade.sh`**, von `scripts/update.sh` und `scripts/proxmox-setup.sh` aufgerufen. Es stoppt die Anwendung, erstellt mit PostgreSQL 16 in einem Container ohne Netzwerk einen Dump und prüft ihn. Danach spielt es den Dump in einen neuen 18er-Cluster im Zwischenverzeichnis ein, in einer Transaktion. Es vergleicht die Zeilenzahlen jeder Tabelle und die Alembic-Revision und schaltet erst dann um. Die Dateien von PostgreSQL 16 bleiben als Rollback-Kopie liegen (`--remove-old-data` löscht sie später). Schlägt ein Schritt fehl, bleibt alles beim Alten. Läuft nach einem Rollback wieder PostgreSQL 16 auf den alten Dateien, startet der `db`-Dienst nicht mehr auf der veralteten 18er-Kopie. Das Skript fragt dann nach `--redo` oder `--keep-new` ([Update-Anleitung](docs/documentation/installation/update.md#versionshinweis-postgresql-18-redis-8-und-python-314-2026-09), [Betrieb](docs/operations.md#postgresql-major-upgrade)).
- **`update.sh`** macht nach dem `git pull` mit der neuen Fassung weiter, wenn sich das Skript selbst geändert hat. Läuft das Backend nicht (abgebrochenes Update), überschreibt es den Rollback-Punkt in `.deploy-state` nicht.
- **Backend-Image:** `postgresql-client-18` aus apt.postgresql.org statt Debians `postgresql-client` (17). So passen `pg_dump`/`pg_restore` für Backup, Restore und Restore-Test zur Server-Version (`PG_MAJOR` im Dockerfile). Der Build bricht ab, wenn die Version nicht stimmt.
- **Redis 7 → 8** (`redis:8-alpine`, 8.10) in Compose und CI. Redis 8 übernimmt die Daten von Redis 7 unverändert. Pub/Sub, Cache, Rate-Limit-Skript, Token-Sperrliste und Celery-Broker sind gegen Redis 8 getestet. Hinweise zur Lizenz (AGPLv3/RSALv2/SSPLv1) und zum Rollback (Redis 7 liest die Datei von Redis 8 nicht) stehen in der Update-Anleitung.
- **Python 3.11 → 3.14** (`python:3.14-slim`, CI, `requires-python >=3.14`, Ruff `py314`, mypy `python_version = "3.14"`). Alle festgelegten Pakete haben Wheels für 3.14 auf x86-64 und ARM64. Lockfiles mit `make lock-backend` für 3.14 neu erzeugt (die Marker für ältere Pythons entfallen: numpy nur noch 2.5.3, kein `async-timeout`/`tomli`). Ruff-Umstellungen: PEP-695-Typparameter, `except A, B` ohne Klammern (PEP 758), keine Anführungszeichen mehr um Annotationen. `scripts/create_admin.py` übergibt uvloop per `loop_factory` statt der in 3.14 veralteten Event-Loop-Policy.
- Alle Backend-Pakete sind auf dem neuesten stabilen Stand. pydantic bleibt auf 2.13.5, weil 2.14 (und damit pydantic-core 2.49) nur als Beta vorliegt.
- Traefik (v3.7), Prometheus, Alertmanager, Blackbox-, Node- und Postgres-Exporter sind bereits auf dem neuesten Stand. Der postgres-exporter v0.20.1 liest alle Collector-Daten von PostgreSQL 18.
- Test `test_create_admin_refuses_a_long_password_even_in_development` setzt `PYTHONPATH` und läuft damit auch außerhalb des Images.

### ECER 2026: beide Lesarten wählbar

- Neue Formel-Vorlagen `ecer_2026_open_results` (Open ohne Paper, wie die veröffentlichten Ergebnisse) und `ecer_2026_botball_rubric` (Doku als Anteil am Bewertungsmaximum, wie die Amendments). Damit entscheidet der Veranstalter pro Saison, welche Lesart gilt; die bisherigen Vorlagen bleiben unverändert.

### Node.js 24 und Monitoring-Images

- **Node.js 24 LTS** statt 22 für den Frontend-Build: `frontend/Dockerfile`, `Dockerfile.dev` und `docker-compose.dev.yml` (`node:24-alpine`), alle `setup-node`-Schritte der CI und `scripts/proxmox-setup.sh` (NodeSource `setup_24.x`). `scripts/update.sh` warnt, wenn auf dem Host noch ein älteres Node das Frontend baut ([Update-Anleitung](docs/documentation/installation/update.md#versionshinweis-nodejs-24-und-neue-monitoring-images-2026-09)).
- **Monitoring** (übernimmt Dependabot #29, Prometheus darüber hinaus): Prometheus v3.5.5 → v3.15.0, Alertmanager v0.27.0 → v0.34.1, Blackbox-Exporter v0.25.0 → v0.28.0. Die Konfiguration bleibt unverändert und ist mit den neuen Images geprüft (`promtool check config`, `promtool test rules`, `amtool check-config` für alle Varianten von `render-config.sh`).
- Doku: Versionstabelle in `docs/documentation/technical/deployment.md` aktualisiert (Traefik v3.7, node-exporter und postgres-exporter ergänzt), promtool-Aufrufe auf v3.15.0.

### Abhängigkeiten: bcrypt 5, OpenCV 5, reportlab 5

Ersetzt die Dependabot-PRs #31 und #32. #30 (pydantic-core 2.49.0) ist nicht installierbar: pydantic 2.13.5 verlangt genau pydantic-core 2.46.5, und 2.49.0 gehört zu pydantic 2.14 (bisher nur Beta). Beide bleiben deshalb auf dem stabilen Stand.

- **bcrypt 5.0.0:** Neue Passwörter dürfen höchstens 72 Byte (UTF-8) lang sein. Die Passwort-Richtlinie lehnt längere beim Anlegen, Ändern, Zurücksetzen, Admin-Setzen und in `scripts/create_admin.py` ab, dort auch mit `APP_ENV=development`. Beim Prüfen wird das Passwort wie früher unter bcrypt 4 auf 72 Byte gekürzt. Bestehende Konten mit längerem Passwort melden sich also weiter an, und ein überlanges Passwort beim Login ergibt 401 statt eines Fehlers 500 (bcrypt 5 wirft auch in `checkpw`).
- **opencv-python-headless 5.0.0.93:** keine Codeänderung nötig. Alle verwendeten Funktionen sind vorhanden, `OPENCV_IO_MAX_IMAGE_PIXELS` greift weiter, die OCR-Ausrichtungstests laufen mit dem echten OpenCV.
- **reportlab 5.0.1:** keine Codeänderung nötig. 5.0 vertraut entfernten Bildquellen nur noch per Whitelist und entfernt renderPM-C-Erweiterung und pyRXP; nichts davon wird genutzt. Alle sieben PDF-Exporte wurden gerendert und mit pypdf geöffnet, Markup bleibt Text.
- Build-Anforderung `setuptools>=84.0.0`; Lockfiles mit `make lock-backend` neu erzeugt.

### Frontend-Majors nach dem Design-Refresh

- React 19, React Router 8 (`react-router` statt `react-router-dom`), Vite 8 (Rolldown) mit `@vitejs/plugin-react` 6 und `vite-plugin-pwa` 1, Vitest 5, Tailwind CSS 4, Zod 4 mit `@hookform/resolvers` 5, i18next 26 / react-i18next 17, Recharts 3, Zustand 5, lucide-react 1, jsdom 30, jest-axe 11, ESLint 10, `@types/node` 24; `engines.node` ≥ 24. `date-fns` entfällt (ungenutzt).
- TypeScript 7 prüft die Typen (`tsc`); typescript-eslint und openapi-typescript brauchen die JavaScript-API und laufen mit TypeScript 6 (`typescript` 6 plus Alias `typescript-7`).
- Tailwind 4 CSS-first: Tokens als `@theme` in `src/index.css`, `tailwind.config.ts` und PostCSS-Konfiguration entfallen. Wo Tailwind 4 anders rendert (Kaskaden-Layer, `space-*`/`divide-*`, Zeilenhöhen, Preflight, Farbpalette), hält `index.css` das bisherige Verhalten; Screenshots und berechnete Styles sind gegenüber vorher unverändert, abgesehen von neu gezeichneten Lucide-Icons und Halbpixel-Verschiebungen in den Diagrammen.
- Passwörter über 72 Byte (UTF-8) meldet das Formular schon vor dem Absenden (bcrypt-Grenze des Backends).

### Schulung „Von der Frage zum Auftrag“

- `docs/schulung/schueler-handbuch.md` und `schueler-handbuch.html`: Handbuch für Schülerinnen und Schüler mit LEDVV, Hebeln für bessere Ergebnisse, Prüfregeln, Übungen mit Lösungen und Glossar. Die HTML-Fassung enthält einen Prompt-Baukasten, der Aufträge nach LEDVV zusammensetzt, fehlende Teile anzeigt und vor Passwörtern im Text warnt.
- `docs/schulung/`: Unterlagen für eine 60-minütige Schulung zum Arbeiten mit KI-Agenten am Beispiel dieses Projekts. Enthalten sind ein Lehrerleitfaden mit Ablauf, LEDVV als Aufbau für Aufträge, ein Spickzettel mit Übung, Kurz-Demos und Fallbeispiele.
- Drehbuch für die Live-Vorführung „Gamedoc 2027 analysieren und in der App hinterlegen“ (`demo-gamedoc-2027.md`) mit Prompts, Klickweg und Plan B. Dazu kommen der Bogen 2026 als JSON (`demo/botball-2026-sheet.json`) und die erwartete Analyse (`demo/analyse-2026-erwartet.md`). Beide sind aus der Vorlage `botball_2026` erzeugt, alle 13 offiziellen Scoring-Beispiele wurden dabei nachgerechnet.

### Botball 2026 und ECER 2026 (Migration `0034`)

Abgleich mit den offiziellen Dokumenten (Game Review v1.4, Score-Sheet und Scoring Examples 2026, ECER Amendments 2026, Bewertungsbögen, Aerial Junior Rulebook, Call for Papers, Ergebnisse ECER 2026; Quellen in `docs/assets/README.md`).

- **Score-Sheet 2026** vollständig (`botball_2026`), abgeleitete Multiplikatoren („Drum ×2" folgt dem Feld), Scoring Examples als gemeinsame Fixture; Tie-Breaker nach v1.4 mit den echten Feldern.
- **Kategorien pro Saison** (Botball, ECER Open, Aerial Junior, Aerial Senior, Junior Botball Challenge, eigene) statt fester Liste; Gesamtwertung optional je Kurs (GCER).
- **Formelvorlagen** `ecer_2026_botball` (Dokumentation je Periode relativ zum Besten – so rechnen die offiziellen Ergebnisse), `ecer_2026_open`, `aerial_2025`/`aerial_2026`, `jbc_2026`; `seed_rank` = angezeigter Seeding-Rang. Die ECER-2026-Ergebnisse sind Test-Fixture (alle 18 Botball-Teams).
- **Aerial-Läufe als Liste**, gewertete Läufe pro Kategorie; **JBC-Punkte** für gelöste Challenges.
- **Seeding-Tie-Breaker** als Saisonregel, standardmäßig aus (Gleichstand teilt den Rang). Maximalpunkte der Dokumentation je Periode (2026: 100/95/100/100); der gespeicherte Doku-Score folgt dem Formel-Set.
- **Awards** (ECER/GCER-Vorlagen, berechnet oder per Jury, Veröffentlichung, Export) und **Ergebnis-Export im ECER-Format** (XLSX/CSV).
- Timeout-Karte (einmal pro Turnier), Schiedsrichter-Checkliste 2026, 3D-Druck-Regeln (Material, Graustufen, Bauraum aus der STL, sechs Roboterteile, STL mit Periode 3), Paper: Benachrichtigungstermin, „auf der Bühne", Seitenlimit 5.
- Beispieldaten ECER 2027 (Linz, 5.–9.4.2027, Botball-Anmeldeschluss 15.12.2026): `scripts/example_season_2027.py`, legt nichts automatisch an.

Nacharbeit zum Audit vom September 2026 ([docs/audit-2026-09.md](docs/audit-2026-09.md)). Integriert auf `main` nach PR #23, Migrationen `0021`–`0033`.

### Added

- **Saison-Lebenszyklus:**
  - Status `draft`/`active`/`finished`/`archived` mit zentralem Schreibschutz für archivierte Saisons und Events;
  - Saison klonen (Konfiguration, Termine um die Jahresdifferenz verschoben, Events als leere Entwürfe) und JSON-Export;
  - Anmeldefenster wird durchgesetzt (`0021`).
- **Konto:**
  - Passwort-Reset per E-Mail (Einmal-Token, 1 h) und durch Admins;
  - E-Mail ändern;
  - Datenexport (`GET /auth/me/export`) und Kontolöschung als Anonymisierung;
  - editierbare Rollen-Rechte;
  - Theme im Profil gespeichert.
- **Events und Turnier:**
  - Double-Elimination-Bracket mit Standard-Setzreihenfolge, Freilosen, Loser-Bracket, Grand Final und Reset-Finale;
  - Ergebnis-Endpunkt mit automatischem Weiterrücken;
  - Setzliste aus dem Seeding;
  - Double Seeding als Paarungen, Alliance als Partnerpaare mit Summen-Score;
  - Bracket-Gewichte pro Event (`0024`);
  - Bracket-Ansicht im Zeitplan und auf der öffentlichen Seite.
- **Modul-Aktivierung pro Event:** `active_modules` zusammen mit den Saison-Flags; Modul-Schalter in der Event-Verwaltung; ausgeblendete Navigation; 404 bzw. 409 im Backend (`0027`).
- **Wertung:**
  - strukturierte Score-Sheets (Bereiche, Multiplikatoren, Entweder-oder, Seiten A/B) mit Vorlagen 2024/2025/2026 und „Klonen von";
  - Tie-Breaker-Presets aus den Game Reviews, Finals-Replay, Kontakt-Bonus, „Runde verloren", Schiedsrichter-Checkliste;
  - Duell-Ergebnis und DE-Platzierung mit entscheidendem Tie-Breaker;
  - Parts Challenges (API);
  - Scouting mit externen Teams, Gegner-Rangliste und PDF;
  - GCER-Qualifikation (`0028`);
  - Formel-Presets Regional 2026 und GCER 2026.
- **Offline und Mobil:**
  - Offline-Erfassung von Wertungen (IndexedDB, Idempotenz, Konfliktauflösung);
  - Bestätigungsdialog;
  - Match-Navigation mit Wischen;
  - Kamera-Upload für OCR;
  - PWA-Icons.
- **Benachrichtigungen:**
  - „Match beginnt bald", „Score korrigiert", Deadline-Erinnerungen 7/3/1 Tage per Push und E-Mail;
  - Push-Einstellungen pro Kategorie und Benachrichtigungszentrale (`0027`).
- **Paper-Review:**
  - PDF-Versionen mit Text-Diff;
  - ein Paper pro Team und Saison;
  - offizielle und interne Deadlines mit Durchsetzung und Erinnerungen;
  - fünf Review-Kriterien mit Kommentaren;
  - Feedback für Teams ohne Identität der Reviewer;
  - Status `disqualified_ai`;
  - Formalabzug;
  - automatische Zuweisung;
  - Statistik, Reviews-CSV (`0023`, `0029`).
- **3D-Druck:**
  - Datei-Upload (STL, 3MF, OBJ, G-Code, bgcode);
  - Ablehnen mit Begründung, Abbrechen auch am Drucker;
  - Live-Status mit Restzeit;
  - Verbrauchsbuchung auf Kontingent und Spule;
  - Kontingent-Editor pro Event (`0022`);
  - Checklisten-Warnung.
- **Teams:**
  - Suche und Filter;
  - Saison-Details (Gebühr, Kit, Kontakt) und Saison-Kader;
  - versionierte Team-Dokumente;
  - 3D-Druck-Checkliste pro Saison (`0029`).
- **Analyse:**
  - Performance-Seite, Statistik mit Anomalie-Erkennung, rollenbezogene Dashboards;
  - Deadline-Kalender mit persönlichem iCal-Feed (`0026`);
  - Team-Historie mit Diagrammen, Team-Bericht PDF, Mehrjahres-CSV, Gesamtwertung als CSV/PDF.
- **Betrieb:**
  - `scripts/update.sh`, `scripts/verify-deployment.sh`, `deploy.yml` (manuell auslösbar);
  - Alertmanager-Regeln, Backup-Scheduler mit Status-Metriken, `restore.sh`;
  - Log-Rotation, Compose-Profile `production` und `monitoring`;
  - Pre-commit-Hooks;
  - CI baut und prüft den Produktions-Stack;
  - Off-site-Kopie jedes Backups nach `BACKUP_OFFSITE_TARGET` (rsync, rclone oder Verzeichnis) mit eigenem Status, Metriken `botball_backup_offsite_*`, Alert `BackupOffsiteCopyFailed` und Wiederholung ohne neues Backup; `proxmox-setup.sh` fragt das Ziel ab und richtet SSH-Schlüssel und `known_hosts` ein.
- **OCR:** Editor für Anker (Passmarken) und Prüfregeln im OCR-Layout der Score-Sheet-Vorlage. Der Worker richtet Scans an den Ankern aus (Rückfall: Blattrand) und markiert Werte nach Mindest-Konfidenz, Minimum/Maximum/Ganzzahl je Feld und Summenregeln; die OCR-Prüfung zeigt die Gründe übersetzt an.
- **Sprachen:** Oberfläche vollständig auf Deutsch und Englisch, Zahlen und Daten über `Intl`, Rückfallsprache Englisch.
- **Tests:** Die CI führt die ganze Playwright-Suite gegen Seed-Daten aus (`seed_e2e.py`). Coverage-Schwellen für Backend und Frontend.
- `CHANGELOG.md`.

### Changed

- CI startet nur noch manuell (Actions → CI → „Run workflow“), nicht mehr bei Push oder Pull Request.
- Seeding nach Game Review:
  - nur Läufe aus Seeding-Phasen;
  - Ränge je Kategorie mit geteilten Plätzen;
  - Feld und n kommen aus dem Event statt aus der Saison-Registrierung.
- DE-, Aerial- und Doku-Ergebnisse sind pro Event gespeichert. Die Scoring-Seiten nutzen das Event der Route. Aerial = Ø aller Läufe, Doku 0,2/0,2/0,2/0,4.
- Druck-Kontingente werden immer pro (Event, Team) aufgelöst. Das Hard-Limit zählt offene Jobs mit. Der Drucker-Typ `generic` heißt jetzt „Manuell (ohne Adapter)".
- Passwort-Policy: mindestens 10 Zeichen, kein Wiederholungszeichen, nicht die E-Mail, nicht auf der Liste häufiger/geleakter Passwörter.
- Modul-Registry (`frontend/src/core/plugins.ts`): Die ungenutzten Dashboard-Widget-Deklarationen, der Typ `PluginDefinition` und `modules/scoring/index.tsx` sind entfernt; die Dashboards wählen ihre Abschnitte nach Rolle.
- `proxmox-setup.sh` startet alle Dienste inklusive Worker, Beat und Backup und erzeugt alle Secrets. `.env.example` enthält alle Variablen.
- Dokumentation: API-Referenz, Datenbankschema, Architektur, Modul-Registry, Handbücher und Tracking-Dokumente entsprechen dem Code.

### Fixed

- **Lesen nach dem Schreiben:** FastAPI führt den Commit in `get_db` erst aus, nachdem die Antwort gesendet ist. Ein Client konnte deshalb 201 bekommen und mit der nächsten Anfrage noch den alten Stand lesen, etwa eine neue Saison, die in der Liste fehlt, oder ein neues Team, das bei der Anmeldung „nicht gefunden“ wurde. `CommitBeforeResponseMiddleware` hält Antworten auf schreibende Anfragen zurück, bis committet ist. Scheitert der Commit, bekommt der Client 409 oder 500 statt eines falschen Erfolgs.
- **Wiederherstellung von Backups:** Das Backup-Image bringt inzwischen `pg_restore` 17 mit, die Datenbank läuft auf PostgreSQL 16. `pg_restore` 17 setzt `transaction_timeout`, das PostgreSQL 16 nicht kennt, deshalb brachen `restore.sh` und `restore-test.sh` sofort ab. Beide Skripte erzeugen jetzt zuerst SQL, entfernen diese Einstellung und spielen den Rest mit `psql` ein, mit Abbruch beim ersten Fehler. Nachgestellt und geprüft mit `pg_dump`/`pg_restore` 17.11 gegen PostgreSQL 16. Die CI übergibt dem Restore-Test die Schlüsseldatei jetzt so, dass der Backup-Benutzer (uid 10001) sie lesen kann.
- **Backups ohne Uploads:** Eine leere Prüfsummenliste (`uploads.sha256`) ließ `restore.sh` und `restore-test.sh` scheitern, weil `sha256sum -c` sie ablehnt. Eine frische Installation war damit nicht wiederherstellbar. Leere Listen werden jetzt übersprungen, manipulierte Dateien fallen weiterhin auf.
- Worker und Beat starteten bei der Proxmox-Installation nicht (Readiness 503, keine OCR, keine Pushes).
- Einrichtungsassistent: Die neue Saison blieb inaktiv, ein doppeltes Haupt-Event wurde angelegt.
- DQ-Läufe wurden im Seeding weggelassen statt mit 0 gewertet. Negative Scores wurden nicht auf 0 gesetzt.
- DE-Bracket: Seeds 1 und 2 trafen in Runde 2 aufeinander, das Loser-Bracket war falsch verdrahtet, das Reset-Finale fehlte.
- `PUT /printing/quotas` erzeugte bei mehreren Events eine Zeile ohne Event (HTTP 500).
- Bambu „FINISH" schloss frisch eingereihte Jobs ab.
- Saison löschen löschte per CASCADE die ganze Historie. Jetzt 409, Archivieren stattdessen.
- Score-Revisionen gingen beim Löschen einer Wertung verloren (`0025`).
- Modelle und Migrationen wichen voneinander ab (`alembic check` meldete 27 Unterschiede): JSONB-Spalten, partielle und NULL-sichere Unique-Indizes, `CHECK`-Constraints und Index-Namen stehen jetzt auch in den Modellen, damit die SQLite-Tests dasselbe Schema prüfen wie PostgreSQL. `0033` ergänzt den Index `print_jobs(printer_id)` und macht `event_registrations.team_id` und `score_sheet_templates.uploaded_at` `NOT NULL`. `tests/postgres/test_schema_drift.py` hält beide Seiten in der CI deckungsgleich.
- Der OCR-Auftrag eines Scans wurde vor dem Commit eingereiht. Der Worker fand die Zeile manchmal noch nicht, und der Scan blieb auf „queued". Jetzt nach dem Commit, ohne die Event-Loop zu blockieren.

### Security

Sicherheitsreview 2026-09 (15 Befunde, jeweils mit Regressionstest; Restrisiken in [docs/SECURITY.md](docs/SECURITY.md)):

- **Größenlimit für gestreamte Bodies:** Das Limit prüfte nur `Content-Length`. Anfragen ohne diesen Header (chunked) wurden vor der Anmeldung vollständig gepuffert (200 MB → 516 MB RSS). Eine ASGI-Middleware zählt jetzt die empfangenen Bytes und bricht mit 413 ab; Druckdateien behalten `PRINT_UPLOAD_MAX_MB`. Traefik lehnt API-Bodies über `API_MAX_BODY_BYTES` (102 MiB) ab.
- **Duell-Wertungen nur für Teilnehmer:** Eine Wertung ließ sich an ein fremdes Head-to-Head-Match hängen und entschied dessen Ausgang. Saison-, Event- und Scan-Routen verlangen jetzt, dass das Team im Match spielt.
- **OCR-Dekompressionsbomben:** Bilder werden vor dem Dekodieren anhand des Headers auf 40 MP begrenzt (Upload und Worker), `OPENCV_IO_MAX_IMAGE_PIXELS` ist gesetzt, PDFs werden mit 150 dpi und höchstens 3000 px Kantenlänge gerastert, der Worker hat ein Speicherlimit.
- **SSRF über Push-Abos:** Endpunkte müssen `https`-URLs bekannter Push-Dienste sein (FCM, Mozilla, WNS, Apple), ohne IP-Literale, Zugangsdaten oder fremde Ports. Früher gespeicherte Abos werden nicht mehr kontaktiert, sondern gelöscht.
- **Ankündigungen nach Zielgruppe:** Die Liste zeigte interne, Juroren-, Reviewer- und Team-Ankündigungen allen. Jetzt nach Rechten (Teams → `teams:write`, Reviewer → `papers:review`, Juroren → `scoring:admin`, intern → Organisatoren), abgelaufene werden ausgeblendet, unbekannte Zielgruppen abgelehnt.
- **Übungsläufe und Notizen fremder Teams:** Match-Listen, Einzel-Match, Score-Historie, Audit-Trail und beide `matches.csv` zeigen sie nur noch dem eigenen Team und `scoring:admin`. Revisionen tragen dazu eine Kopie von `is_practice` (`0031`).
- **PDF-Exporte:** Nutzertexte (Paper-Titel, Dateinamen, Saison-/Event-/Level-Namen, Kategorien) werden für reportlab escaped. Ein offener Tag machte den Export zum 500, `<img src>` ließ den Server URLs abrufen oder lokale Dateien einbetten.
- **Team-Stammdaten:** Mentoren ändern nur noch Name, Schule, Ort und Land. Team-Nummer, Level, Aktiv-Status und Organisator-Notizen brauchen `teams:admin`; das Formular zeigt diese Felder nur Organisatoren.
- **Container ohne Root:** `backend`, `worker`, `beat` und `backup` laufen als UID 10001, ohne Capabilities, mit `no-new-privileges`, Speicherlimits und (außer `backup`) schreibgeschütztem Root-Dateisystem. Die Init-Dienste `volume-permissions`/`backup-permissions` stellen bestehende Volumes automatisch um, siehe [Update-Anleitung](docs/documentation/installation/update.md#versionshinweis-container-ohne-root-rechte-security-update-2026-09). Wiederherstellung und Restore-Test brauchen geänderte Befehle ([docs/operations.md](docs/operations.md#restore-in-production)).
- **Entwurfs-Events:** Unterrouten (`/v1/events/{id}/…`, `/scoring/events/{id}/…`, `?event_id=` …) und `/scoring/schemas` lieferten Entwürfe an Gäste und Mentoren. Jetzt 404 ohne `events:write`.
- **Scan-Uploads:** Vorlage, Team, Match, Saison-Status und Dateityp (Magic Bytes, kein GIF) werden vor dem Schreiben geprüft; abgelehnte oder zurückgerollte Uploads hinterlassen keine Datei mehr. Upload und Wiederholung sind in archivierten Saisons gesperrt.
- **Team-Dokumente** lassen sich nicht mehr aus einer archivierten Saison heraus- oder in sie hineinverschieben.
- **Login:** bcrypt läuft in einem Worker-Thread statt auf der Event-Loop; unbekannte E-Mail-Adressen werden gegen einen Dummy-Hash geprüft, die Antwortzeit verrät keine Konten mehr.
- **`APP_ENV`** akzeptiert nur `development`, `test` und `production`; alles außer `development` verlangt sichere Secrets. Werte wie `prod` oder `Production` übersprangen die Prüfung.
- **Download-Namen:** Scouting-Bericht und Saison-Export setzen `Content-Disposition` aus bereinigten Namen statt aus dem Pfadparameter.

- python-jose und `ecdsa` durch PyJWT ersetzt. Access-Tokens tragen eine `jti` und landen beim Logout auf einer Redis-Sperrliste. `token_version` beendet alle Sitzungen bei Passwortänderung, Reset, Deaktivierung und Löschung.
- `ranking_updated`, `schedule_updated` und Ankündigungen werden erst nach dem Commit veröffentlicht.
- Outbox: Zeilen werden gesperrt (`FOR UPDATE SKIP LOCKED`), nur tatsächlich Versendetes gilt als zugestellt, abgelaufene Push-Abos werden gelöscht.
- Entwurfs-Saisons und -Events sehen nur Organisatoren. Kontaktdaten anderer Teams sind ausgeblendet. Team-Dokumente sind nur für das eigene Team sichtbar.
- Rate-Limits für Passwort-Reset, E-Mail-Änderung, Kontolöschung und alle Uploads.
- Passwörter aus einer mitgelieferten Liste von rund 2.300 häufigen oder geleakten Passwörtern (SecLists, ab 10 Zeichen, plus deutsche Muster) werden beim Anlegen, Ändern, Zurücksetzen und Setzen durch Admins abgelehnt, ohne Groß-/Kleinschreibung.

### Performance

- Öffentlicher WebSocket hält keine Datenbankverbindung mehr; ein Redis-Abo pro API-Prozess verteilt Live-Ereignisse an alle WebSockets. Geteilte Redis-Clients mit kurzen Timeouts für Veröffentlichen, Rate-Limit (jetzt atomar per Lua) und Cache.
- Ranglisten, Gesamtwertung und öffentliche Ergebnisse werden pro Event versioniert in Redis gecacht und mit `ETag`/`304` ausgeliefert. Die Gesamtwertung lädt ihre Eingaben einmal für alle Kategorien.
- Celery: eigene Queues (`ocr`, `periodic`, `default`) mit neuem Dienst `worker-ocr`, Beat-Aufträge verfallen, Tasks ohne Connection-Pool pro Event-Loop, Drucker werden gleichzeitig mit Timeout abgefragt.
- Outbox: Zeilen werden beansprucht (`sending` mit Lease) und ohne offene Sperren versendet; nur die Push-Abos der Empfänger werden geladen. Neue Tabelle `notification_recipients` für die Benachrichtigungszentrale, Aufräumen nach 30 Tagen (`0032`).
- Weniger Abfragen: Mentor-Dashboard und Team-Historie ohne N+1, Sammel-Wertungen sortieren die Rangliste einmal pro Anfrage, Audit-Zeile in der Transaktion der Anfrage, fehlende Indizes (`0032`), Seitenweise Abfrage (`limit`/`offset`) für Wertungslisten, öffentliche Ergebnisse und Zeitplan; Listen ohne `schema_snapshot`.
- PDF-Exporte laufen im Threadpool. SQL-Logging nur noch mit `DB_ECHO=true`; `pool_pre_ping` und `pool_recycle` für die API.
- Zusammenspiel mit dem Sicherheitsreview: Seitenweise Match-Listen filtern fremde Übungsläufe schon in der Abfrage (volle Seiten, keine Lücken) und blenden fremde Notizen aus. Gecachte Ranglisten und Ergebnisse enthalten nie Übungsläufe; Saison-Ranglisten ohne `event_id` prüfen den Entwurfsstatus des Standard-Events vor dem Cache, und öffentliche Seiten liefern Events einer Entwurfs-Saison nicht mehr aus. `worker-ocr` ist wie `worker` gehärtet (UID 10001, `cap_drop: ALL`, schreibgeschützt, `OCR_WORKER_MEM_LIMIT`, `OPENCV_IO_MAX_IMAGE_PIXELS`); `worker` braucht ohne OCR nur noch 1 GB (`WORKER_MEM_LIMIT`). Die Vorlagen-Extraktion wird wie Scans erst nach dem Commit in die Queue `ocr` gestellt.

## PR #23 – Frontend-Ausbau (#21) im eventzentrierten `main` (2026-09-24)

### Added

- Detailseiten für Team, Paper, Druckauftrag und Bot.
- Paper-Review-Workflow in der Oberfläche.
- Team-Selbstverwaltung: Mentoren reichen Wertungen, Papers und Druckaufträge fürs eigene Team ein.
- Bot-Galerie.
- Übungsläufe (`is_practice`).
- Saison-Deadlines.
- Admin-Einstellungen: Benutzer, Rollen, Saisons, Stufen, Drucker, Spulen, Ankündigungen.
- Playwright-Suite.
- Migrationen `0014`–`0020`.
- Die Seiten für DE, Aerial, Doku und Rangliste sind wieder als Event-Routen erreichbar.
- `EventLink` bzw. `useEventNavigate` für Links im aktuellen Event.

### Changed

- Die Migrationen aus #21 wurden hinter `0013` neu nummeriert, um doppelte Revisions-IDs zu vermeiden. `0016_quota_unique` wurde verworfen, weil `main` Kontingente pro (Event, Team) eindeutig macht.
- `validate_raw_scores` lehnt unbekannte Score-Felder mit 422 ab.

### Fixed

- Übungsläufe fließen nirgends mehr in Ranglisten ein: `_recompute_ranking`, Formel-Engine, öffentliche Ergebnisse.
- Paper-Upload schrieb nach dem Merge eine leere Datei.
- `list_matches` wurde positional mit vertauschten Argumenten aufgerufen.

### Security

- Nach dem Merge konnten Mentoren (`scoring:write`) Wertungen für fremde Teams eintragen und OCR-Scans fremder Teams übernehmen. Alle vier Routen sind jetzt auf das eigene Team beschränkt.
- Der Schutz gegen CSV-Formel-Injection gilt auch für die Event-Exporte.

## PR #22 – Formel-Evaluator gehärtet, Score-Manipulation geschlossen (2026-09-24)

### Changed

- Formel-Engine linear statt superlinear: gemeinsamer `ScopeContext`, `bisect` für Ränge.
- `require_permission` liest die Rechte vom bereits geladenen Nutzer. Das halbiert die DB-Abfragen jeder geschützten Anfrage.
- `_recompute_ranking` lädt nur noch `total_score`. `list_events` hat ein `limit`.

### Fixed

- `RecursionError` und `OverflowError` im Formel-Evaluator führten zu HTTP 500. Jetzt gibt es Längen- und Tiefenlimits, Überlaufschutz und maximal 60 Formeln pro Set.

### Security

- `PaperUpdate` enthielt `final_score` und `paper_rank` für `papers:write`, also auch für Mentoren. Diese Felder liegen jetzt hinter `PUT /papers/{id}/score` (`papers:admin`).
- `MatchUpdate` enthielt `total_score`, damit ließ sich die Schema-Validierung umgehen. Die Summe wird jetzt nur noch berechnet.
- Die Formel-Vorschau verlangt `scoring:formulas`.
- `ScoreBulkEntry` ist auf 200 Einträge begrenzt.
- Metriken: Nicht zugeordnete Pfade teilen sich ein Label. Das verhindert unbegrenzte Kardinalität.

## PR #20 – Formelbasierte Wertung aus den Game-Dokumenten (2026-07-25)

### Added

- Konfigurierbare Punkteformeln pro Saison und Kategorie mit Editor und Live-Vorschau.
- Standardformeln aus den Game-Dokumenten. Sie reproduzieren die ECER-Ergebnisse 2025 auf 1e-12 genau.
- Bracket-Gewichte, Recht `scoring:formulas` (`0013`).

### Fixed

- Fehlende Flushes vor `db.refresh()` in `create_user`, `update_user` und `create_season`.
- `scalar_one_or_none()` bei `get_active_season`.
- UUID-Routenparameter gegen `String(36)`-Spalten in den Score-Sheet-Routen.
