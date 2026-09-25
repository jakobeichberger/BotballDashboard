# Changelog

Alle nennenswerten Änderungen am BotballDashboard. Das Format folgt [Keep a Changelog](https://keepachangelog.com/de/1.1.0/). Das Projekt hat noch keine Versionsnummern. Die Abschnitte unter „Unreleased" sind deshalb nach den gemergten Pull Requests benannt.

## [Unreleased]

Nacharbeit zum Audit vom September 2026 ([docs/audit-2026-09.md](docs/audit-2026-09.md)). Integriert auf `main` nach PR #23, Migrationen `0021`–`0031`.

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

- Worker und Beat starteten bei der Proxmox-Installation nicht (Readiness 503, keine OCR, keine Pushes).
- Einrichtungsassistent: Die neue Saison blieb inaktiv, ein doppeltes Haupt-Event wurde angelegt.
- DQ-Läufe wurden im Seeding weggelassen statt mit 0 gewertet. Negative Scores wurden nicht auf 0 gesetzt.
- DE-Bracket: Seeds 1 und 2 trafen in Runde 2 aufeinander, das Loser-Bracket war falsch verdrahtet, das Reset-Finale fehlte.
- `PUT /printing/quotas` erzeugte bei mehreren Events eine Zeile ohne Event (HTTP 500).
- Bambu „FINISH" schloss frisch eingereihte Jobs ab.
- Saison löschen löschte per CASCADE die ganze Historie. Jetzt 409, Archivieren stattdessen.
- Score-Revisionen gingen beim Löschen einer Wertung verloren (`0025`).
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
