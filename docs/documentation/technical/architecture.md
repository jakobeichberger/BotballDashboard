# Systemarchitektur

BotballDashboard ist ein **modularer Monolith**. Es gibt ein FastAPI-Backend, einen Celery-Worker mit Beat-Scheduler und ein React-Frontend. Die Module sind fest einkompiliert und werden über zwei statische Registries zusammengesetzt, je eine im Backend und im Frontend (siehe [Statische Modul-Registry](plugins.md)).

---

## Überblick

```
             Browser / PWA  (React, Service Worker, IndexedDB-Queue)
                         │ HTTPS, WebSocket
┌────────────────────────▼─────────────────────────────┐
│ Traefik  – TLS (Let's Encrypt), Routing               │
│   /api/*  → backend:8000   (ohne /api/system/metrics) │
│   /*      → frontend:80    (nginx, SPA + Security-Header)
└──────────┬───────────────────────────────┬────────────┘
           │                               │
┌──────────▼──────────┐          ┌─────────▼─────────┐
│ backend (FastAPI)   │          │ frontend (nginx)  │
│ REST, WebSocket,    │          └───────────────────┘
│ Rate-Limit, Audit   │
└───┬──────────┬──────┘
    │          │ Pub/Sub, Rate-Limit, Token-Sperrliste, Broker
┌───▼────┐  ┌──▼────┐   ┌──────────────────────────────────────┐
│Postgres│  │ Redis │◄──┤ worker (Celery): OCR, Outbox, Drucker,│
│  16    │  │   7   │   │   Erinnerungen                        │
└───▲────┘  └──▲────┘   │ beat (Celery Beat): Zeitplan          │
    └──────────┴────────┴──────────────────────────────────────┘
                         │ HTTP / MQTT
                   OctoPrint, Bambu Lab
```

Dienste in `docker-compose.yml`: `traefik`, `db`, `redis`, `backend`, `worker`, `beat`, `frontend`. Dazu kommen im Profil `production` der Dienst `backup` und im Profil `monitoring` die Dienste `prometheus`, `blackbox` und `alertmanager`. Details stehen in [Deployment](deployment.md) und [docs/operations.md](../../operations.md).

---

## Backend

| Bereich | Umsetzung |
|---|---|
| Framework | FastAPI (Pydantic v2), Python 3.11 |
| Datenbank | SQLAlchemy 2.0 async (asyncpg), Alembic-Migrationen `0001`–`0029` |
| Auth | PyJWT (HS256 fest), bcrypt, Refresh-Token als HttpOnly-Cookie, `token_version` und Redis-Sperrliste (`core/token_denylist.py`) |
| Rechte | `require_permission`, `require_any_permission`, `assert_team_access` (`core/auth.py`) |
| Hintergrundjobs | Celery mit Redis als Broker (`core/celery_app.py`) |
| Live-Daten | Redis Pub/Sub (`core/live.py`) → WebSocket |
| Benachrichtigungen | Transaktionale Outbox (`core/domain_events.py`, Tabelle `notification_events`) → Web Push (pywebpush, VAPID) und E-Mail (aiosmtplib, SendGrid als Rückfall) |
| PDF | reportlab (Exporte), pypdf (Paper-Diff), pdftotext (Score-Sheet-Vorlagen) |
| OCR | OpenCV und Tesseract, lokal im Worker |
| Verschlüsselung | Fernet für Drucker-Zugangsdaten (`PRINTER_CREDENTIAL_ENCRYPTION_KEY`) |
| Logging | structlog, JSON auf stdout (Konsole im Dev-Modus) |
| Metriken | Prometheus-Text unter `/api/system/metrics` (`core/metrics.py`) |

### Aufbau

```
backend/
  main.py              App, Middleware, Exception-Handler, System-Routen
  core/
    modules.py         statische Router-Registry
    auth.py            JWT, Rechte-Dependencies, Team-Scoping
    live.py            Redis-Pub/Sub, publish_after_commit, WebSocket-Weiterleitung
    domain_events.py   emit_event → Outbox
    rate_limit.py      Redis-Rate-Limits
    celery_app.py      Worker-Konfiguration und Beat-Zeitplan
    audit.py, files.py, notifications.py, metrics.py, logging.py, config.py
  modules/
    auth, seasons, events, teams, scoring (+ score_sheets), paper_review,
    printing, dashboard, exports, bots
```

Jedes Modul hat in der Regel `models.py`, `schemas.py`, `service.py` und `routes.py`. Scoring ist zusätzlich aufgeteilt:

- `formula*` – Formel-Engine;
- `competition_*` – DE, Aerial, Doku;
- `extras_*` – Regeln, Scouting, Qualifikation;
- `sheet*` – strukturierte Score-Sheets;
- `score_sheets/` – PDF-Vorlagen und OCR.

### Request-Pipeline (`main.py`)

1. **Request-Kontext:** Eine `X-Request-ID` wird übernommen oder erzeugt. Zu große Bodies werden mit 413 abgelehnt (`MAX_UPLOAD_SIZE_MB`, für Druckdateien `PRINT_UPLOAD_MAX_MB`): vorab anhand von `Content-Length`, und `BodySizeLimitMiddleware` (`core/request_limits.py`) zählt die empfangenen Bytes, sodass auch Anfragen ohne `Content-Length` (chunked) nicht unbegrenzt gepuffert werden.
2. **Security-Header** auf jeder Antwort: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`. In Produktion kommen CSP und HSTS dazu.
3. **Audit:** Jede erfolgreiche `POST`/`PUT`/`PATCH`/`DELETE` unter `/api/` wird als `audit_logs`-Zeile geschrieben, mit Aktion `"<METHOD> <path>"`, Nutzer und IP. Einige Stellen protokollieren zusätzlich fachlich, z. B. Quota-Override oder Druckerabbruch. Fehler beim Audit-Schreiben brechen die Anfrage nicht ab.
4. **CORS:** in der Entwicklung nur `localhost`/`127.0.0.1`, in Produktion `ALLOWED_ORIGINS`.
5. **Router** aus `core/modules.py` unter `/api`. Fachmodule mit Event-Schalter bekommen den Modul-Guard als Router-Dependency.
6. **Einheitliches Fehlerformat** `{code, message, fieldErrors, requestId}` für `HTTPException`, Validierungsfehler und `IntegrityError` (→ 409 `data_conflict`).

Einen Audit-Log- oder Error-Log-Bereich in der Oberfläche gibt es nicht. Auswerten lassen sich die Daten über die Tabelle `audit_logs` (SQL) und über die Container-Logs.

### Rate-Limiting

Das Rate-Limiting findet im Backend statt, nicht in Traefik (`core/rate_limit.py`). Es zählt pro Bucket und Client-IP in Redis. Hinter Traefik sieht das Backend dank `--proxy-headers` und `FORWARDED_ALLOW_IPS` die echte Client-IP. Die Buckets und Limits stehen in der [API-Referenz](api-reference.md#rate-limits). Ist Redis nicht erreichbar, lässt der Limiter die Anfrage durch, damit Login und Wiederherstellung möglich bleiben.

### Worker und Beat

`worker` und `beat` verwenden dasselbe Image wie das Backend (`celery -A core.celery_app:celery_app worker|beat`). Registrierte Tasks:

| Task | Auslöser | Zweck |
|---|---|---|
| `score_sheets.extract_template` | Upload einer Score-Sheet-Vorlage | Text mit `pdftotext` extrahieren, Feldkandidaten erkennen |
| `score_sheets.process_scan` | Upload/Retry eines Scans | Seite rastern, ausrichten (Anker der Vorlage, sonst Blattrand), Felder mit OpenCV/Tesseract lesen, Prüfregeln anwenden → Status `review` |
| `printing.poll_printers` | Beat, alle 15 s | OctoPrint/Bambu abfragen, Job-Status und Fortschritt; `generic` (manuell) wird nicht abgefragt |
| `notifications.deliver_outbox` | Beat, alle 10 s | Outbox ausliefern (Push, E-Mail, optional Live-Kanal) |
| `notifications.match_reminders` | Beat, jede Minute | „Match beginnt bald"-Hinweise einreihen |
| `notifications.deadline_reminders` | Beat, täglich 07:00 UTC | Erinnerungen an Saison-Deadlines 7/3/1 Tage vorher |
| `papers.deadline_reminders` | Beat, täglich 07:05 UTC | Erinnerungen an Paper-Deadlines (Teams, Reviewer) |
| `papers.process_review_deadlines` | Beat, stündlich | Überfällige Review-Zuweisungen markieren |

Die OCR läuft **nur im Worker**. Einen eigenen OCR-Container oder -Dienst gibt es nicht, und es verlassen keine Bilddaten die Installation. `/api/system/readiness` meldet 503, solange kein Worker auf `ping` antwortet.

### Outbox und Benachrichtigungen

Fachcode ruft `emit_event(db, event_type, payload=…)` in derselben Transaktion wie die fachliche Änderung auf. Die Zeile in `notification_events` wird also nur geschrieben, wenn die Änderung committet wird. `deliver_outbox` holt fällige Zeilen mit `SELECT … FOR UPDATE SKIP LOCKED`. Dadurch stellen parallele Worker nichts doppelt zu. Die Zustellung läuft so:

- Empfänger: `userId`/`userIds` oder ausdrücklich `broadcast`. Ohne Empfänger geht nichts raus.
- Nutzer, die die Kategorie in ihrem Profil stummgeschaltet haben, werden übersprungen. Kategorien: `match_soon`, `score_corrected`, `deadlines`, `paper_status`, `print_status`, `announcements`.
- Eine Zeile gilt als zugestellt, wenn mindestens ein Versand geklappt hat oder es keine Empfänger gab. Sonst folgt ein Retry mit Backoff, nach 5 Versuchen `failed`.
- Abgelaufene Push-Abos (404/410) werden gelöscht.
- E-Mail geht nur raus, wenn `SMTP_HOST` gesetzt ist.
- Die Benachrichtigungszentrale (`/api/dashboard/notifications`) liest dieselben Zeilen mit Lesestatus (`notification_reads`).

### Live-Stream

`publish_after_commit(db, event_id, "ranking_updated")` merkt das Ereignis in der Session vor. Veröffentlicht wird es erst nach dem Commit auf dem Redis-Kanal `botball:live:{event_id}`, bei Rollback gar nicht. Einziger WebSocket-Endpunkt ist `WS /api/v1/public/events/{slug}/ws`. Er leitet den Kanal eines Events an Clients weiter, sofern mindestens ein `public_*`-Flag gesetzt ist. Nur die öffentliche Event-Seite (`/public/:eventSlug`) nutzt den Stream. Sie lädt bei `ranking_updated`, `schedule_updated` und `announcement_*` neu. Die internen Seiten fragen per Polling ab (TanStack Query `refetchInterval`): Wertung, Scoreboard, Zeitplan, Druck, OCR-Scans und Benachrichtigungen.

---

## Fachliche Kernkonzepte

### Saison → Event

Die **Saison** hält das Regelwerk eines Jahres:

- Modul-Flags `use_*`;
- aktive Kategorien;
- Formeln und Bracket-Gewichte;
- Tie-Breaker, Kontakt-Bonus und Schiedsrichter-Checkliste;
- Score-Sheet-Vorlagen, Termine und Paper-Deadlines.

Ein **Event** ist ein konkretes Turnier der Saison, z. B. ein Regionalturnier, ECER oder GCER. Registrierungen, Phasen, Zeitplan, Wertungen, Ranglisten, DE-, Aerial- und Doku-Ergebnisse, Druck-Kontingente und Ankündigungen hängen am Event. Die Oberfläche ist entsprechend eventzentriert (`/events/:eventId/…`). Die Saison-Routen der API (`/scoring/seasons/{id}/…`) nutzen das Standard-Event der Saison oder `?event_id=`.

### Modul-Aktivierung pro Event

`modules/events/module_access.py` bestimmt die **wirksamen Module** eines Events. Ein Modul ist wirksam, wenn es in `Event.active_modules` steht **und** das zugehörige Saison-Flag es erlaubt:

| Modul | Saison-Flag |
|---|---|
| `seeding` | `use_seeding` |
| `double_elimination` | `use_double_elimination` |
| `documentation` | `use_documentation_scoring` |
| `aerial` | `use_aerial` |
| `paper`, `printing`, `bots` | – |

Neue Events starten mit `seeding`, `paper`, `printing`, `bots` sowie allen Modulen, die die Saison einschaltet. Durchgesetzt wird das so:

- **Backend:** Die Router für Paper, Druck und Bots haben einen Guard und antworten für ein Event mit abgeschaltetem Modul mit 404. DE-, Aerial- und Doku-Routen sowie die Druck-Checkliste haben eigene Guards. Eine Phase eines abgeschalteten Moduls ergibt 409.
- **Frontend:** `GET /api/v1/events/{id}/modules` liefert die wirksamen Module. `useEventModules` blendet damit Navigationseinträge aus, `ModuleRoute` sperrt Routen, und das Dashboard lässt Paper- und Druck-Kennzahlen weg.

### Lebenszyklus und Archiv-Schutz

- Saison: `draft` → `active` → `finished` → `archived`.
- Event: `draft`, `published`, `live`, `completed`, `archived`.

`modules/seasons/lifecycle.py::ensure_writable` ist der zentrale Guard. Er wird von den Schreibpfaden in Scoring, Events, Paper, Druck und Team-Registrierungen aufgerufen und lehnt Änderungen an archivierten Saisons oder Events mit 409 ab. Den Status eines archivierten Events selbst darf man noch ändern. Weitere Regeln:

- Eine Saison mit Registrierungen, Ergebnissen, Papers oder Druckjobs lässt sich nicht löschen, archivierte Events ebenfalls nicht.
- Entwürfe sind nur für Nutzer mit `seasons:write` bzw. `events:write` sichtbar.
- Öffentlich erreichbar sind nur Events in `published`, `live` oder `completed`.

### Wertung und Formel-Engine

1. **Score-Sheet → Lauf-Summe.** Ein Schema ist entweder flach (Σ Wert × Multiplikator) oder strukturiert (`modules/scoring/sheet.py`). Strukturierte Schemas kennen:
   - Bereiche mit Bereichs-Multiplikatoren;
   - Entweder-oder-Gruppen;
   - getrennte Seiten A/B;
   - Zähl-, Zahl- und Ja/Nein-Felder mit Maximalwerten.

   Das Frontend rechnet mit `frontend/src/modules/scoring/sheet/calculator.ts` dasselbe. Beide Implementierungen laufen gegen dieselben Fixtures. Zur Lauf-Summe kommen die Sonderregeln der Saison: Kontakt-Bonus am Spielende (Standard 25 %), „Runde verloren" (0 Punkte, keine DQ), gelbe und rote Karten. Das Backend berechnet die Summe immer selbst. Vom Client gesendete Summen werden ignoriert.
2. **Seeding.** Nur Läufe aus Seeding-Phasen zählen. DQ zählt als 0, negative Werte zählen als 0. Die Ränge gelten je Kategorie mit geteilten Plätzen (1, 2, 2, 4). Gleichstände werden nach der Tie-Breaker-Reihenfolge der Saison aufgelöst. Eine rote Karte beim Event disqualifiziert das Team.
3. **Gesamtwertung.** `modules/scoring/formula.py` ist ein sicherer Ausdrucks-Evaluator: AST-Whitelist, kein `eval`, Längen- und Tiefenlimit, Überlaufschutz. `formula_engine.py` wertet ein Formel-Set pro Kategorie über alle Teams des Events aus. Dafür gibt es Zeilenfunktionen (`avg`, `avg_best`, …) und Spaltenfunktionen (`rank`, `max_all`, `avg_all`, …). Standard ist das ECER-2025-Set, das die veröffentlichten Ergebnisse 2025 reproduziert. Presets: `ecer_2025_botball`, `ecer_2025_open`, `regional_2026_botball`, `gcer_2026_botball`, `aerial`, `jbc`. Die Eingaben der Engine sind:
   - Seeding-Läufe;
   - Double-Seeding-Läufe;
   - DE-Rang;
   - Bracket-Gewichte (pro Event, Rückfall auf die Saison);
   - Doku-Teile und Paper-Score;
   - Aerial-Läufe.
4. **Brackets.** `modules/events/brackets.py` erzeugt ein Double-Elimination-Bracket aus der Seeding-Setzliste:
   - Standard-Setzreihenfolge, Freilose für die besten Seeds;
   - Loser-Bracket mit Minor- und Major-Runden;
   - Grand Final und bedingtes Reset-Finale.

   Ergebnisse (`POST …/schedule/{match_id}/result`) lassen Sieger und Verlierer automatisch weiterrücken. Die DE-Platzierungen landen in `de_results`. Double Seeding ist als rotierende Paarungen umgesetzt, Alliance als Partnerpaare mit Summen-Score.
5. **Audit.** Jede Änderung einer Wertung erzeugt eine `score_revisions`-Zeile. Änderungen an DE-, Aerial- und Doku-Ergebnissen landen in `result_revisions`.

### Offline-Erfassung

Das Frontend speichert Score-POSTs ohne Verbindung in IndexedDB (`frontend/src/lib/offlineQueue.ts`), und zwar unter ihrem `idempotency_key`. Die Warteschlange wird beim Start, beim Wiederverbinden und jede Minute abgespielt, nur für den Nutzer, der die Wertungen erfasst hat. Das Backend behandelt einen wiederholten Schlüssel als dieselbe Wertung. Konflikte, etwa wenn das Match inzwischen gewertet wurde, werden pro Eintrag angezeigt. Alle anderen Schreibaktionen sind offline gesperrt. Der Service Worker (`frontend/src/sw.ts`, Workbox `injectManifest`) cacht App-Shell und ausgewählte GET-Anfragen (Event, Teams, Zeitplan, Schema) NetworkFirst.

---

## Frontend

| Bereich | Umsetzung |
|---|---|
| Framework | React 18, TypeScript, Vite |
| Routing | React Router 6: `/login`, `/forgot-password`, `/reset-password`, `/public/:eventSlug`, `/setup`, `/settings/*`, `/events/:eventId/<modul-route>` |
| Registry | `src/core/plugins.ts` (Routen, Navigation, Rechte, Modul-Schalter, i18n-Namensräume) |
| Daten | TanStack Query, axios (`src/lib/api.ts`, Token-Refresh, Offline-Sperre) |
| State | Zustand (`authStore`, `themeStore`) |
| Styles | Tailwind CSS mit Dark Mode; Theme wird im Profil gespeichert |
| Diagramme | Recharts (Performance, Statistik, Team-Historie) |
| i18n | i18next mit `de` und `en`; Rückfallsprache ist Deutsch. Viele Seiten enthalten noch fest deutschen Text (siehe [todo.md](../../todo.md)). |
| PWA | vite-plugin-pwa (`injectManifest`), Web Push, Offline-Queue |
| API-Typen | `src/api/generated.ts` aus `openapi.json` (`pnpm api:generate`) |

`/` leitet auf das laufende (`live`) oder erste Event weiter. Gibt es noch keins, geht es zu `/setup`, dem Einrichtungsassistenten.

---

## Logging, Metriken, Readiness

- **Logs:** structlog als JSON auf stdout. Docker rotiert die Dateien (`json-file`, `max-size`/`max-file`). Eine `error_log`-Tabelle gibt es nicht.
- **Audit:** Tabelle `audit_logs`, siehe oben.
- **Metriken:** Request-Zähler und Latenzen unter `/api/system/metrics`. Nicht zugeordnete Pfade teilen sich ein Label. Prometheus fragt `backend:8000` intern ab. Über Traefik ist der Pfad nicht erreichbar.
- **Health/Readiness:** `/api/system/health` (Prozess läuft) und `/api/system/readiness` (PostgreSQL, Redis, Worker).
- **Alarme und Backups:** Alertmanager-Regeln, Backup-Scheduler mit Status-Metriken, siehe [docs/operations.md](../../operations.md).

---

## Datenbankmigrationen

Alembic, nummerierte Revisionen `0001`–`0029` (Liste in [database.md](database.md#migrationen)). Beim Container-Start führt `scripts/migrate-then-start.sh` automatisch `alembic upgrade head` aus. Neue Modelle müssen in `backend/alembic/env.py` importiert werden.
