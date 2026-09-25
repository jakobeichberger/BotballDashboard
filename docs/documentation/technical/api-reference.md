# API-Referenz

Stand: Migration `0029`, Commit `aa61752`. Die Tabellen unten sind aus den registrierten FastAPI-Routen erzeugt (`backend/core/modules.py` → `main.py`) und von Hand um den Zweck ergänzt. Maßgeblich bleibt das OpenAPI-Schema:

- im Entwicklungsmodus live unter `http://localhost:8000/api/docs` (Swagger UI), `/api/redoc` und `/api/openapi.json`; in Produktion sind alle drei abgeschaltet;
- als Datei `frontend/openapi.json`, erzeugt mit `python3 backend/scripts/export_openapi.py --output frontend/openapi.json` bzw. `pnpm api:generate` (erzeugt zusätzlich `frontend/src/api/generated.ts`).

---

## Grundlagen

### Präfixe

Jeder Modul-Router wird in `main.py` unter `/api` eingebunden. Es gibt zwei Generationen von Pfaden:

| Präfix | Inhalt |
|---|---|
| `/api/v1/events/…` | Event-API: Events, Registrierungen, Phasen, Zeitplan, Bracket, Event-Wertungen, OCR-Scans |
| `/api/v1/public/events/{slug}/…` | Öffentliche, schreibgeschützte Event-Ansicht inkl. WebSocket und QR-Code |
| `/api/auth`, `/api/seasons`, `/api/teams`, `/api/scoring`, `/api/papers`, `/api/printing`, `/api/dashboard`, `/api/exports`, `/api/bots` | Fach-Module |
| `/api/system/…` | Health, Readiness, Metriken |

### Authentifizierung

```http
POST /api/auth/login
Content-Type: application/json

{"email": "user@example.org", "password": "…"}
```

Antwort:

```json
{"access_token": "eyJ…", "token_type": "bearer", "expires_in": 900}
```

- Access-Token (JWT, HS256, Standard 15 min) im Header `Authorization: Bearer <token>`.
- Der Refresh-Token wird als Cookie `refresh_token` gesetzt: `HttpOnly`, `SameSite=strict`, `Secure` außerhalb der Entwicklung, Pfad `/api/auth`. `POST /api/auth/refresh` rotiert ihn und liefert ein neues Access-Token.
- `POST /api/auth/logout` widerruft den Refresh-Token und setzt die `jti` des vorgelegten Access-Tokens bis zu dessen Ablauf auf eine Redis-Sperrliste (`core/token_denylist.py`).
- Passwortänderung, Passwort-Reset, Deaktivierung und Löschung erhöhen `users.token_version`. Damit werden alle bestehenden Access-Tokens des Nutzers ungültig.
- Superuser (`users.is_superuser`) bestehen jede Rechteprüfung.

### Fehlerformat

Alle Fehler haben dieselbe Form (`main.py`, Exception-Handler):

```json
{
  "code": "validation_error",
  "message": "Request validation failed.",
  "fieldErrors": {"email": ["value is not a valid email address"]},
  "requestId": "3f0c…"
}
```

| Status | `code` | Wann |
|---|---|---|
| 401 / 403 / 404 / 409 / 400 | `http_<status>` | Fachliche Fehler (`core/exceptions.py`). `message` enthält den Text, z. B. `"Missing permissions: scoring:admin"` oder `"Season is archived and read-only"`. |
| 409 | `data_conflict` | Verletzte Datenbank-Constraints (fehlende Referenz, Duplikat). SQL-Details werden nicht ausgeliefert. |
| 413 | `request_too_large` | Body größer als `MAX_UPLOAD_SIZE_MB` (Druckdateien: `PRINT_UPLOAD_MAX_MB`) |
| 422 | `validation_error` | Pydantic-Validierung; `fieldErrors` ist nach Feldpfad gruppiert |
| 429 | `rate_limit_exceeded` | Rate-Limit überschritten; Header `Retry-After` in Sekunden |

Jede Antwort trägt den Header `X-Request-ID`. Ein vom Client gesendeter `X-Request-ID` (1–64 Zeichen `[A-Za-z0-9._-]`) wird übernommen, sonst erzeugt der Server eine UUID.

### Rate-Limits

Redis-gestützt pro Client-IP (`core/rate_limit.py`). Bei Redis-Ausfall wird nicht blockiert.

| Bucket | Endpunkt | Limit |
|---|---|---|
| `login` | `POST /api/auth/login` | 10 / 60 s |
| `refresh` | `POST /api/auth/refresh` | 30 / 60 s |
| `password-change` | `POST /api/auth/me/password` | 10 / 60 s |
| `email-change` | `POST /api/auth/me/email` | 10 / 60 s |
| `account-delete` | `DELETE /api/auth/me` | 5 / 60 s |
| `password-reset` | `POST /api/auth/password-reset/request` | 5 / 15 min |
| `password-reset-confirm` | `POST /api/auth/password-reset/confirm` | 10 / 15 min |
| `paper-upload` | `POST /api/papers/{id}/upload` | 20 / 60 s |
| `print-upload` | `POST /api/printing/jobs/{id}/file` | 20 / 60 s |
| `team-document-upload` | Team-Dokumente (Upload, neue Version) | 20 / 60 s |
| `score-scan-upload` | `POST /api/v1/events/{id}/score-sheet-scans` | 30 / 60 s |
| `score-template-upload` | `POST /api/scoring/seasons/{id}/score-sheets` | 10 / 60 s |

### Modul-Aktivierung pro Event

Fachmodule lassen sich pro Event abschalten (`Event.active_modules` zusammen mit den Saison-Flags, siehe [Architektur](architecture.md#modul-aktivierung-pro-event)).

- Die Router **papers**, **printing** und **bots** hängen komplett hinter einem Guard (`event_module` in `core/modules.py`). Adressiert eine Anfrage ein Event mit abgeschaltetem Modul (über Pfad, Query, JSON-Body oder den adressierten Datensatz), lautet die Antwort 404. Anfragen auf Saisonebene gehen durch, wenn mindestens ein Event der Saison das Modul nutzt.
- In den Tabellen steht `Modul <key>`, wenn eine einzelne Route einen eigenen Guard hat (DE, Aerial, Doku, 3D-Druck-Checkliste).
- Eine Phase eines abgeschalteten Moduls anzulegen oder zu planen ergibt 409.

### Objektbezogene Rechte

Die Spalte „Recht" nennt die Rechte-Prüfung der Route. Viele Routen schränken zusätzlich auf das eigene Team ein (`assert_team_access` in `core/auth.py`). Wer das erhöhte Recht nicht hat (z. B. `scoring:admin`, `papers:admin`, `printing:admin`, `teams:admin`), darf nur auf Teams zugreifen, bei denen er als `TeamMember.user_id` eingetragen ist. Betroffen sind:

- Wertungen erfassen, auch OCR-Scans;
- Paper lesen, hochladen und einreichen;
- Druckjobs und Kontingente;
- Team-Dokumente, Team-Details und Saison-Kader;
- Bots;
- Scouting;
- Performance-Analysen.

Kontaktdaten und Mitglieder-E-Mails anderer Teams werden ohne `teams:admin` ausgeblendet.

### Archiv-Schutz

Schreibzugriffe auf eine archivierte Saison oder ein archiviertes Event werden mit 409 abgelehnt (`modules/seasons/lifecycle.py::ensure_writable`). Ausnahme: der Status des Events selbst, damit es wieder aus dem Archiv geholt werden kann. Entwurfs-Saisons und -Events sehen nur Nutzer mit `seasons:write` bzw. `events:write`.

---

## Rechte

Die Rechte werden in den Migrationen angelegt (`0002`, `0010`, `0012`, `0013`, `0014`, `0016`, `0017`):

| Recht | Bedeutung |
|---|---|
| `users:read` / `users:write` | Benutzer ansehen / anlegen, bearbeiten, löschen, Passwort setzen |
| `roles:read` / `roles:write` | Rollen und Rechte ansehen / Rollen anlegen und ändern |
| `seasons:read` / `seasons:write` | Saisons, Stufen, Termine ansehen / verwalten, Qualifikationen setzen |
| `events:read` / `events:write` / `events:admin` | Events ansehen / verwalten (Registrierungen, Phasen, Zeitplan) / löschen, Zeitplan erzeugen, Setzliste, Bracket-Gewichte |
| `teams:read` / `teams:write` / `teams:admin` | Teams ansehen / eigenes Team pflegen / Teams anlegen und löschen, Registrierungen bestätigen, Konten verknüpfen |
| `scoring:read` / `scoring:write` / `scoring:admin` | Wertungen ansehen / erfassen (eigenes Team ohne `scoring:admin`) / bestätigen, korrigieren, Schemas, DE/Aerial/Doku, Statistik |
| `scoring:formulas` | Punkteformeln und Bracket-Gewichte der Saison bearbeiten, Vorschau |
| `papers:read` / `papers:write` / `papers:review` / `papers:admin` | Paper lesen / einreichen / begutachten / Prozess steuern |
| `printing:read` / `printing:write` / `printing:admin` | Druckjobs ansehen / einreichen / Drucker, Kontingente, Freigaben |
| `dashboard:read` / `dashboard:write` | Dashboard ansehen / Ankündigungen verwalten |

Die Zuordnung zu den Rollen steht in [SECURITY.md](../../SECURITY.md#roles-and-permissions).

---

## Endpunkte

Legende Recht: `öffentlich` = ohne Token · `Login` = jeder angemeldete Nutzer · `a` + `b` = beide nötig · `a` oder `b` = eines genügt.

### System

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/system/health` | öffentlich | Liveness: `{"status": "ok", "version": …}` |
| GET | `/api/system/readiness` | intern | Prüft PostgreSQL, Redis und einen Celery-Worker (Ping höchstens alle 15 s); 200 `ready` oder 503 `not_ready` mit `checks`. Traefik leitet den Pfad nicht nach außen; Docker-Healthchecks und Prometheus fragen `backend:8000` direkt |
| GET | `/api/system/metrics` | intern | Prometheus-Metriken; Anfragen mit `X-Forwarded-For` (also über Traefik) erhalten 404 |

### Auth & Konto (`/api/auth`)

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| POST | `/api/auth/login` | öffentlich | Anmelden, setzt Refresh-Cookie |
| POST | `/api/auth/refresh` | öffentlich (Cookie) | Tokens rotieren |
| POST | `/api/auth/logout` | öffentlich | Refresh-Token widerrufen, Access-Token sperren |
| GET | `/api/auth/me` | Login | Eigenes Profil inkl. Rollen und Rechten |
| PATCH | `/api/auth/me` | Login | Anzeigename, Sprache (`de`/`en`), Theme (`light`/`dark`/`system`) |
| POST | `/api/auth/me/password` | Login | Passwort ändern; beendet alle anderen Sitzungen |
| POST | `/api/auth/me/email` | Login | E-Mail-Adresse ändern (mit Passwort) |
| GET | `/api/auth/me/export` | Login | Datenexport aller eigenen Daten (DSGVO Art. 15/20) |
| DELETE | `/api/auth/me` | Login | Eigenes Konto anonymisieren (mit Passwort) |
| POST | `/api/auth/password-reset/request` | öffentlich | Reset-Link anfordern; antwortet immer 204 |
| POST | `/api/auth/password-reset/confirm` | öffentlich | Neues Passwort mit Token (einmalig, 1 h gültig) setzen |
| GET | `/api/auth/me/notification-preferences` | Login | Push-Kategorien lesen |
| PUT | `/api/auth/me/notification-preferences` | Login | Push-Kategorien ein-/ausschalten |
| POST | `/api/auth/me/push-subscriptions` | Login | Web-Push-Abo dieses Geräts speichern |
| DELETE | `/api/auth/me/push-subscriptions` | Login | Web-Push-Abo entfernen |
| GET | `/api/auth/users` | `users:read` | Benutzerliste |
| POST | `/api/auth/users` | `users:write` | Benutzer anlegen (mit SMTP: Hinweis-Mail) |
| GET | `/api/auth/users/{user_id}` | `users:read` | Benutzer lesen |
| PATCH | `/api/auth/users/{user_id}` | `users:write` | Name, Status, Rollen ändern |
| POST | `/api/auth/users/{user_id}/password` | `users:write` | Passwort setzen und Sitzungen beenden |
| DELETE | `/api/auth/users/{user_id}` | `users:write` | Benutzer anonymisieren; Historie bleibt zugeordnet |
| GET | `/api/auth/roles` | `roles:read` | Rollen mit Rechten |
| GET | `/api/auth/permissions` | `roles:read` | Alle Rechte |
| POST | `/api/auth/roles` | `roles:write` | Eigene Rolle anlegen |
| PUT | `/api/auth/roles/{role_id}` | `roles:write` | Rechte einer Rolle ersetzen; die Admin-Rolle behält ihre kritischen Rechte |

### Saisons (`/api/seasons`)

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/seasons` | `seasons:read` | Saisons (Entwürfe nur mit `seasons:write`) |
| GET | `/api/seasons/active` | Login | Aktive Saison |
| POST | `/api/seasons` | `seasons:write` | Saison anlegen; `is_active` deaktiviert die bisherige, `create_default_event` optional |
| GET | `/api/seasons/{season_id}` | `seasons:read` | Saison lesen |
| POST | `/api/seasons/{season_id}/clone` | `seasons:write` | Konfiguration (ohne Ergebnisse) in eine neue Entwurfs-Saison kopieren, Termine verschoben |
| GET | `/api/seasons/{season_id}/export.json` | `seasons:write` | Vollständiger JSON-Snapshot der Saison |
| PATCH | `/api/seasons/{season_id}` | `seasons:write` | Saison bearbeiten, Status `draft`/`active`/`finished`/`archived` |
| PUT | `/api/seasons/{season_id}/activate` | `seasons:write` | Als aktive Saison setzen |
| DELETE | `/api/seasons/{season_id}` | `seasons:write` | Löschen; 409 bei vorhandenen Registrierungen, Ergebnissen, Papers oder Druckjobs |
| PUT | `/api/seasons/{season_id}/phases/{phase_id}/activate` | `seasons:write` | Saison-Phase aktivieren |
| GET | `/api/seasons/competition-levels/all` | Login | Wettbewerbsstufen |
| POST | `/api/seasons/competition-levels` | `seasons:write` | Stufe anlegen (Reihenfolge, „qualifiziert aus") |
| PATCH | `/api/seasons/competition-levels/{level_id}` | `seasons:write` | Stufe bearbeiten |
| DELETE | `/api/seasons/competition-levels/{level_id}` | `seasons:write` | Stufe löschen |
| GET | `/api/seasons/{season_id}/events` | `seasons:read` | Termine und Deadlines der Saison (`season_events`) |
| POST | `/api/seasons/{season_id}/events` | `seasons:write` | Termin/Deadline anlegen |
| DELETE | `/api/seasons/{season_id}/events/{event_id}` | `seasons:write` | Termin/Deadline löschen |

### Events (`/api/v1/events`)

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/v1/events` | `events:read` | Events (Entwürfe nur mit `events:write`) |
| POST | `/api/v1/events` | `events:write` | Event anlegen; Module werden aus der Saison abgeleitet |
| GET | `/api/v1/events/{event_id}` | `events:read` | Event lesen |
| PATCH | `/api/v1/events/{event_id}` | `events:write` | Stammdaten, Status, Module, `public_*`-Freigaben |
| DELETE | `/api/v1/events/{event_id}` | `events:admin` | Event löschen (nicht archivierte) |
| GET | `/api/v1/events/{event_id}/modules` | `events:read` | Aktive und wirksame Module plus Saison-Flags |
| GET | `/api/v1/events/{event_id}/registrations` | `events:read` | Teilnehmende Teams |
| POST | `/api/v1/events/{event_id}/registrations` | `events:write` | Team registrieren (Kategorie, Stufe; qualifizierte Stufen verlangen eine Qualifikation) |
| PATCH | `/api/v1/events/{event_id}/registrations/{registration_id}` | `events:write` | Registrierung ändern (Seed, Check-in, Kategorie) |
| DELETE | `/api/v1/events/{event_id}/registrations/{registration_id}` | `events:write` | Registrierung entfernen |
| GET | `/api/v1/events/{event_id}/phases` | `events:read` | Phasen |
| POST | `/api/v1/events/{event_id}/phases` | `events:write` | Phase anlegen (`seeding`, `double_seeding`, `double_elimination`, `alliance`, `final`) |
| PATCH | `/api/v1/events/{event_id}/phases/{phase_id}` | `events:write` | Phase bearbeiten |
| DELETE | `/api/v1/events/{event_id}/phases/{phase_id}` | `events:write` | Phase löschen |
| GET | `/api/v1/events/{event_id}/schedule` | `events:read` | Zeitplan mit Teilnehmern |
| POST | `/api/v1/events/{event_id}/schedule/generate` | `events:admin` | Zeitplan einer Phase erzeugen (Seeding-Runden, Double Seeding, DE-Bracket, Alliance) |
| PATCH | `/api/v1/events/{event_id}/schedule/{match_id}` | `events:write` | Zeit, Tisch, Status eines geplanten Matches |
| POST | `/api/v1/events/{event_id}/schedule/{match_id}/result` | `scoring:admin` | Ergebnis eines Duells; Sieger und Verlierer rücken automatisch weiter |
| POST | `/api/v1/events/{event_id}/registrations/seeds-from-seeding` | `events:admin` | Setzliste je Kategorie aus der Seeding-Rangliste übernehmen |
| GET | `/api/v1/events/{event_id}/bracket` | `events:read` | Bracket-Struktur (Winner/Loser/Finale, Platzierungen) |
| GET | `/api/v1/events/{event_id}/phases/{phase_id}/alliances` | `events:read` | Alliance-Paare einer Phase |
| GET | `/api/v1/events/{event_id}/bracket-weights` | `events:read` | Bracket-Gewichte des Events |
| PUT | `/api/v1/events/{event_id}/bracket-weights` | `events:admin` | Bracket-Gewichte des Events setzen (überschreiben die der Saison) |
| GET | `/api/v1/events/{event_id}/matches` | `scoring:read` | Erfasste Wertungen des Events |
| POST | `/api/v1/events/{event_id}/matches` | `scoring:write` | Wertung erfassen; ohne `scoring:admin` nur fürs eigene Team; `idempotency_key` verhindert Duplikate (Offline-Queue) |
| GET | `/api/v1/events/{event_id}/ranking` | `events:read` | Seeding-Rangliste |
| GET | `/api/v1/events/{event_id}/scoring-schema` | `scoring:read` | Aktives Score-Sheet-Schema |
| POST | `/api/v1/events/{event_id}/scoring-schema/versions` | `scoring:admin` | Neue Schema-Version (flach oder strukturiert) |

### OCR-Scans (`/api/v1/events/{event_id}/score-sheet-scans`)

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| POST | `/api/v1/events/{event_id}/score-sheet-scans` | `scoring:write` | Foto/PDF eines Score-Sheets hochladen; die OCR läuft im Worker |
| GET | `/api/v1/events/{event_id}/score-sheet-scans` | `scoring:read` | Scans des Events |
| GET | `/api/v1/events/{event_id}/score-sheet-scans/{scan_id}` | `scoring:read` | Scan mit erkannten Werten |
| POST | `/api/v1/events/{event_id}/score-sheet-scans/{scan_id}/retry` | `scoring:write` | OCR erneut anstoßen |
| POST | `/api/v1/events/{event_id}/score-sheet-scans/{scan_id}/accept` | `scoring:write` | Geprüfte Werte als Wertung übernehmen |
| GET | `/api/v1/events/{event_id}/score-sheet-scans/{scan_id}/crops/{file_name}` | `scoring:read` | Bildausschnitt eines Feldes |

### Öffentliche Event-Ansicht (`/api/v1/public/events/{slug}`)

Nur Events mit Status `published`, `live` oder `completed`. Jede Teilansicht verlangt ihr Freigabe-Flag, sonst 404.

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/v1/public/events/{slug}` | öffentlich | Stammdaten und Freigaben |
| GET | `/api/v1/public/events/{slug}/schedule` | `public_schedule` | Zeitplan |
| GET | `/api/v1/public/events/{slug}/bracket` | `public_schedule` | Bracket |
| GET | `/api/v1/public/events/{slug}/ranking` | `public_scoreboard` | Rangliste |
| GET | `/api/v1/public/events/{slug}/results` | `public_results` | Einzelergebnisse (ohne Übungsläufe) |
| GET | `/api/v1/public/events/{slug}/announcements` | `public_announcements` | Veröffentlichte Ankündigungen mit Zielgruppe `all` |
| GET | `/api/v1/public/events/{slug}/qr.svg` | öffentlich | QR-Code auf `APP_BASE_URL/public/{slug}` |
| WS | `/api/v1/public/events/{slug}/ws` | mind. ein `public_*`-Flag | Live-Stream des Events (Redis Pub/Sub) |

Den angemeldeten Live-Stream `WS /api/v1/events/{event_id}/ws` (`events:read`) beschreibt der Abschnitt „Live-Stream“.

### Teams (`/api/teams`)

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/teams` | `teams:read` | Suche (Name, Nummer, Schule, Ort) und Filter (Land, Status, Saison, Kategorie) |
| GET | `/api/teams/countries` | `teams:read` | Länder für den Filter |
| GET | `/api/teams/mine` | Login | Eigene Teams (Mentor-Auswahl) |
| POST | `/api/teams` | `teams:admin` | Team anlegen |
| GET | `/api/teams/registrations` | `teams:read` | Saison-Registrierungen |
| POST | `/api/teams/registrations` | `teams:write` | Team für eine Saison anmelden (Anmeldefenster gilt für Nicht-Admins) |
| PUT | `/api/teams/registrations/{registration_id}/confirm` | `teams:admin` | Registrierung bestätigen |
| DELETE | `/api/teams/registrations/{registration_id}` | `teams:admin` | Registrierung löschen |
| GET | `/api/teams/{team_id}` | `teams:read` | Team mit Mitgliedern |
| PATCH | `/api/teams/{team_id}` | `teams:write` | Team bearbeiten (eigenes Team) |
| DELETE | `/api/teams/{team_id}` | `teams:admin` | Team löschen |
| GET | `/api/teams/{team_id}/history` | `teams:read` | Saison-Historie |
| POST | `/api/teams/{team_id}/members` | `teams:write` | Mitglied anlegen (Konto verknüpfen nur mit `teams:admin`) |
| PATCH | `/api/teams/{team_id}/members/{member_id}` | `teams:write` | Mitglied bearbeiten; `user_id` nur mit `teams:admin` |
| DELETE | `/api/teams/{team_id}/members/{member_id}` | `teams:write` | Mitglied entfernen |
| GET | `/api/teams/{team_id}/seasons` | `teams:read` | Saison-Teilnahmen mit Details |
| GET | `/api/teams/{team_id}/seasons/{season_id}` | `teams:read` | Eine Saison-Teilnahme |
| PUT | `/api/teams/{team_id}/seasons/{season_id}` | `teams:write` | Teilnahme bearbeiten (Admins alles, Mentoren nur Kontaktfelder) |
| GET | `/api/teams/{team_id}/seasons/{season_id}/members` | `teams:read` | Saison-Kader |
| PUT | `/api/teams/{team_id}/seasons/{season_id}/members` | `teams:write` | Saison-Kader setzen |
| GET | `/api/teams/{team_id}/documents` | `teams:read` | Team-Dokumente mit Versionen (eigenes Team und Organisation) |
| POST | `/api/teams/{team_id}/documents` | `teams:write` | Dokument (PDF/Bild) hochladen |
| POST | `/api/teams/{team_id}/documents/{document_id}/versions` | `teams:write` | Neue Version hochladen |
| PATCH | `/api/teams/{team_id}/documents/{document_id}` | `teams:write` | Titel, Kategorie, Beschreibung |
| DELETE | `/api/teams/{team_id}/documents/{document_id}` | `teams:write` | Dokument mit allen Versionen löschen |
| GET | `/api/teams/{team_id}/documents/{document_id}/download` | `teams:read` | Version herunterladen (Standard: neueste) |
| GET | `/api/teams/print-compliance/items` | `teams:read` · Modul `printing` | Checklisten-Punkte der Saison (Regeln für Druckteile) |
| POST | `/api/teams/print-compliance/items` | `teams:admin` oder `printing:admin` · Modul `printing` | Punkt anlegen |
| POST | `/api/teams/print-compliance/items/defaults` | `teams:admin` oder `printing:admin` · Modul `printing` | Standardregeln übernehmen |
| PATCH | `/api/teams/print-compliance/items/{item_id}` | `teams:admin` oder `printing:admin` · Modul `printing` | Punkt bearbeiten |
| DELETE | `/api/teams/print-compliance/items/{item_id}` | `teams:admin` oder `printing:admin` · Modul `printing` | Punkt löschen |
| GET | `/api/teams/{team_id}/seasons/{season_id}/print-compliance` | `teams:read` oder `printing:read` · Modul `printing` | Checkliste des Teams |
| PUT | `/api/teams/{team_id}/seasons/{season_id}/print-compliance/{item_id}` | `teams:write`, `teams:admin` oder `printing:admin` · Modul `printing` | Punkt abhaken; hebt eine Bestätigung auf |
| PUT | `/api/teams/{team_id}/seasons/{season_id}/print-compliance/verify` | `teams:admin` oder `printing:admin` · Modul `printing` | Checkliste bestätigen oder zurückziehen |

### Scoring (`/api/scoring`)

#### Wertungen, Revisionen, Ranglisten

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/scoring/seasons/{season_id}/schema` | `scoring:read` | Aktives Schema der Saison |
| GET | `/api/scoring/seasons/{season_id}/matches` | `scoring:read` | Wertungen der Saison (Standard-Event), `is_practice` filterbar |
| POST | `/api/scoring/seasons/{season_id}/matches` | `scoring:write` | Wertung oder Übungslauf erfassen (eigenes Team ohne `scoring:admin`) |
| POST | `/api/scoring/seasons/{season_id}/matches/bulk` | `scoring:write` | Bis zu 200 Wertungen auf einmal |
| GET | `/api/scoring/matches/{match_id}` | `scoring:read` | Eine Wertung |
| PATCH | `/api/scoring/matches/{match_id}` | `scoring:write` | Korrektur; Gesamtpunkte werden immer neu berechnet, jede Änderung erzeugt eine Revision |
| GET | `/api/scoring/matches/{match_id}/revisions` | `scoring:read` | Revisionen, auch nach dem Löschen |
| PUT | `/api/scoring/matches/{match_id}/confirm` | `scoring:admin` | Bestätigen; Pflichtpunkte der Schiedsrichter-Checkliste müssen abgehakt sein |
| DELETE | `/api/scoring/matches/{match_id}` | `scoring:admin` | Löschen (Revision „deleted" bleibt) |
| GET | `/api/scoring/events/{event_id}/revisions` | `scoring:read` | Score-Audit-Trail des Events |
| GET | `/api/scoring/events/{event_id}/result-revisions` | `scoring:read` | Audit-Trail von DE-, Aerial- und Doku-Ergebnissen |
| GET | `/api/scoring/seasons/{season_id}/ranking` | öffentlich | Seeding-Rangliste (siehe Restrisiken in SECURITY.md) |
| GET | `/api/scoring/seasons/{season_id}/ranking/extended` | öffentlich | Seeding-Rangliste mit Teamnamen und Kategorie |
| GET | `/api/scoring/events/{event_id}/ranking/extended` | öffentlich | dasselbe für ein Event, Ränge je Kategorie |
| GET | `/api/scoring/events/{event_id}/ranking/overall` | öffentlich | Gesamtwertung eines Events |
| GET | `/api/scoring/scheduled-matches/{scheduled_match_id}/outcome` | `scoring:read` | Sieger eines Duells und was entschied (Punkte, Tie-Breaker, DQ, Replay) |

#### DE, Aerial, Dokumentation

Die Ergebnisse gehören zu einem Event (`/events/{event_id}/…`); die früheren Saison-Varianten sind entfernt. Jede Route antwortet mit 404, wenn das Modul für das Event aus ist.

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/scoring/events/{event_id}/de-results` | `scoring:read` · Modul `double_elimination` | DE-Ergebnisse |
| PUT | `…/de-results` | `scoring:admin` · Modul `double_elimination` | DE-Ergebnisse (Liste) speichern |
| PUT | `…/de-results/{team_id}` | `scoring:admin` · Modul `double_elimination` | DE-Ergebnis eines Teams |
| GET | `…/aerial-results` | `scoring:read` · Modul `aerial` | Aerial-Läufe |
| GET | `…/aerial-ranking` | öffentlich · Modul `aerial` | Aerial-Rangliste (Ø aller Läufe) |
| PUT | `…/aerial-results` | `scoring:admin` · Modul `aerial` | Aerial-Läufe speichern |
| PUT | `…/aerial-results/{team_id}` | `scoring:admin` · Modul `aerial` | Aerial-Läufe eines Teams |
| GET | `…/doc-scores` | `scoring:read` · Modul `documentation` | Doku-Bewertungen |
| PUT | `…/doc-scores` | `scoring:admin` · Modul `documentation` | Doku-Bewertungen speichern |
| PUT | `…/doc-scores/{team_id}` | `scoring:admin` · Modul `documentation` | Doku-Bewertung eines Teams |
| GET | `/api/scoring/events/{event_id}/de-placement` | `scoring:read` | DE-Platzierung aus dem Bracket, inkl. Tie-Breaker |

#### Score-Sheet-Vorlagen (PDF)

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| POST | `/api/scoring/seasons/{season_id}/score-sheets` | `scoring:admin` | Score-Sheet-PDF hochladen; Textextraktion im Worker |
| GET | `/api/scoring/seasons/{season_id}/score-sheets` | `scoring:read` | Vorlagen der Saison |
| GET | `/api/scoring/score-sheets/{sheet_id}` | `scoring:read` | Vorlage mit erkannten Feldkandidaten |
| GET | `/api/scoring/score-sheets/{sheet_id}/file` | `scoring:read` | Original-PDF |
| POST | `/api/scoring/score-sheets/{sheet_id}/confirm` | `scoring:admin` | Felder bestätigen, optional ins Schema übernehmen |
| PUT | `/api/scoring/score-sheets/{sheet_id}/active` | `scoring:admin` | Als aktive Vorlage setzen |
| PATCH | `/api/scoring/score-sheets/{sheet_id}/layout` | `scoring:admin` | OCR-Layout (Anker, Feldbereiche, Prüfregeln) |
| DELETE | `/api/scoring/score-sheets/{sheet_id}` | `scoring:admin` | Vorlage löschen |

#### Formeln

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/scoring/formulas/reference` | `scoring:read` | Variablen, Funktionen, Standard-Sets und Presets |
| GET | `/api/scoring/formulas/seasons/{season_id}` | `scoring:read` | Gespeicherte Formeln der Saison |
| GET | `/api/scoring/formulas/seasons/{season_id}/{category}/effective` | `scoring:read` | Wirksame Formeln (gespeichert oder Standard) |
| PUT | `/api/scoring/formulas/seasons/{season_id}/{category}` | `scoring:formulas` | Formel-Set speichern (max. 60 Formeln) |
| POST | `/api/scoring/formulas/seasons/{season_id}/{category}/reset` | `scoring:formulas` | Auf Standard zurücksetzen |
| POST | `/api/scoring/formulas/seasons/{season_id}/presets/{preset_id}` | `scoring:formulas` | Preset laden (`ecer_2025_botball`, `ecer_2025_open`, `regional_2026_botball`, `gcer_2026_botball`, `aerial`, `jbc`) |
| POST | `/api/scoring/formulas/events/{event_id}/{category}/preview` | `scoring:formulas` | Entwurf gegen echte Event-Daten rechnen, ohne zu speichern |
| GET | `/api/scoring/formulas/seasons/{season_id}/{category}/bracket-weights` | `scoring:read` | Bracket-Gewichte der Saison |
| PUT | `/api/scoring/formulas/seasons/{season_id}/{category}/bracket-weights` | `scoring:formulas` | Bracket-Gewichte der Saison setzen |

#### Regeln, Vorlagen, Schemas

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/scoring/seasons/{season_id}/rules` | `scoring:read` | Tie-Breaker-Reihenfolge, Finals-Replay, Kontakt-Bonus, Schiedsrichter-Checkliste |
| PUT | `/api/scoring/seasons/{season_id}/rules` | `scoring:admin` | Regeln speichern |
| GET | `/api/scoring/tiebreaker-presets` | `scoring:read` | Tie-Breaker aus den Game Reviews 2024/2025/2026 |
| GET | `/api/scoring/schema-templates` | `scoring:read` | Score-Sheet-Vorlagen 2024/2025 (vollständig) und 2026 (Struktur) |
| GET | `/api/scoring/schemas` | `scoring:read` | Aktive Schemas aller Events/Stufen als Quelle für „Klonen" |
| POST | `/api/scoring/events/{event_id}/scoring-schema/clone` | `scoring:admin` | Schema eines anderen Events übernehmen (z. B. ECER → GCER) |

#### Parts Challenges, Scouting, Qualifikation

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/scoring/events/{event_id}/parts-challenges` | `scoring:read` | Parts Challenges des Events |
| POST | `/api/scoring/events/{event_id}/parts-challenges` | `scoring:admin` | Challenge erfassen |
| PUT | `/api/scoring/parts-challenges/{challenge_id}/ruling` | `scoring:admin` | Entscheidung; die unterlegene Seite verliert die Runde |
| GET | `/api/scoring/seasons/{season_id}/external-teams` | `scoring:read` | Externe Teams (Scouting) |
| POST | `/api/scoring/external-teams` | `scoring:write` | Externes Team anlegen |
| PATCH | `/api/scoring/external-teams/{external_team_id}` | `scoring:write` | Externes Team bearbeiten |
| DELETE | `/api/scoring/external-teams/{external_team_id}` | `scoring:admin` | Externes Team löschen |
| GET | `/api/scoring/events/{event_id}/scouting/notes` | `scoring:read` | Notizen (Organisation alle, sonst die der eigenen Teams) |
| POST | `/api/scoring/events/{event_id}/scouting/notes` | `scoring:write` | Notiz anlegen |
| PATCH | `/api/scoring/scouting/notes/{note_id}` | `scoring:write` | Notiz bearbeiten |
| DELETE | `/api/scoring/scouting/notes/{note_id}` | `scoring:write` | Notiz löschen |
| GET | `/api/scoring/events/{event_id}/scouting/observations` | `scoring:read` | Beobachtete Scores |
| POST | `/api/scoring/events/{event_id}/scouting/observations` | `scoring:write` | Beobachtung erfassen |
| DELETE | `/api/scoring/scouting/observations/{observation_id}` | `scoring:write` | Beobachtung löschen |
| GET | `/api/scoring/events/{event_id}/opponent-ranking` | `scoring:read` | Eigene Teams (offizielles Seeding) und externe Teams (beobachtet) gemeinsam gereiht |
| GET | `/api/scoring/events/{event_id}/scouting/report.pdf` | `scoring:read` | Scouting-Bericht als PDF |
| GET | `/api/scoring/seasons/{season_id}/qualifications` | `scoring:read` | Qualifikationen der Saison |
| GET | `/api/scoring/seasons/{season_id}/qualification-status` | `scoring:read` | Kandidaten einer Stufe und ihr Status |
| POST | `/api/scoring/levels/{level_id}/qualify` | `seasons:write` | Teams manuell (mit Notiz) qualifizieren |
| DELETE | `/api/scoring/qualifications/{qualification_id}` | `seasons:write` | Qualifikation zurücknehmen |
| POST | `/api/scoring/events/{event_id}/register-qualified` | `events:write` | Alle Qualifizierten der Stufe beim Event registrieren |

### Paper-Review (`/api/papers`, Modul `paper`)

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/papers` | `papers:read` | Papers (Mentoren: nur eigenes Team; Reviewer: alle) |
| GET | `/api/papers/deadline` | `papers:read` | Paper-Deadline der Saison in der Event-Zeitzone |
| GET | `/api/papers/deadlines` | `papers:read` | Offizielle und interne Deadlines |
| POST | `/api/papers/deadlines` | `papers:admin` | Deadline anlegen (`official_submission`, `official_final`, `internal_*`) |
| PATCH | `/api/papers/deadlines/{deadline_id}` | `papers:admin` | Deadline ändern |
| DELETE | `/api/papers/deadlines/{deadline_id}` | `papers:admin` | Deadline löschen |
| POST | `/api/papers/auto-assign` | `papers:admin` | Reviewer automatisch zuweisen (bis N pro Paper, `dry_run` als Vorschau) |
| GET | `/api/papers/stats` | `papers:admin` | Durchschnitte, Annahmequote, Review-Fortschritt |
| GET | `/api/papers/reviewers/workload` | `papers:admin` | Offene Reviews je Reviewer |
| POST | `/api/papers` | `papers:write` | Paper anlegen (eines pro Team und Saison) |
| GET | `/api/papers/{paper_id}` | `papers:read` | Paper mit Status, Deadline-Info, Zuweisungen |
| PATCH | `/api/papers/{paper_id}` | `papers:write` | Titel, Abstract |
| POST | `/api/papers/{paper_id}/upload` | `papers:write` | PDF als neue Version hochladen (nur Entwurf und angeforderte Revision) |
| GET | `/api/papers/{paper_id}/versions` | `papers:read` | Versionen |
| GET | `/api/papers/{paper_id}/versions/diff` | `papers:read` | Text-Diff zweier Versionen |
| GET | `/api/papers/{paper_id}/download` | `papers:read` | PDF herunterladen (`?version=`) |
| PUT | `/api/papers/{paper_id}/submit` | `papers:write` | Einreichen; Deadline wird durchgesetzt (`papers:admin` darf übersteuern) |
| PUT | `/api/papers/{paper_id}/status` | `papers:admin` | Status setzen, inkl. `disqualified_ai` (Score 0) |
| POST | `/api/papers/{paper_id}/assignments` | `papers:admin` | Reviewer zuweisen (nicht aus dem Team oder derselben Schule) |
| POST | `/api/papers/{paper_id}/assignments/{assignment_id}/remind` | `papers:admin` | Reviewer erinnern |
| PUT | `/api/papers/{paper_id}/reviews` | `papers:review` | Eigenes Review speichern, mit `?submit=true` verbindlich abgeben |
| POST | `/api/papers/{paper_id}/reviews/{review_id}/reopen` | `papers:admin` | Abgegebenes Review wieder öffnen |
| GET | `/api/papers/{paper_id}/reviews` | `papers:admin` | Alle Reviews |
| GET | `/api/papers/{paper_id}/feedback` | `papers:read` | Freigegebenes Feedback entschiedener Runden, ohne Reviewer-Identität |
| PUT | `/api/papers/{paper_id}/score` | `papers:admin` | Ergebnis oder Formalabzug setzen |
| POST | `/api/papers/{paper_id}/finalize` | `papers:admin` | Reviews abzüglich Formalabzug zu `final_score` (0–1) verdichten, Rang setzen |
| GET | `/api/papers/{paper_id}/history` | `papers:read` | Statushistorie |

### 3D-Druck (`/api/printing`, Modul `printing`)

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/printing/printers` | `printing:read` | Drucker (ohne URL/Seriennummer/Notizen für Nicht-Admins) |
| POST | `/api/printing/printers` | `printing:admin` | Drucker anlegen (`bambu`, `octoprint`, `generic` = manuell) |
| PATCH | `/api/printing/printers/{printer_id}` | `printing:admin` | Drucker bearbeiten, Zugangsdaten verschlüsselt speichern |
| GET | `/api/printing/jobs` | `printing:read` | Druckjobs (Mentoren: eigenes Team) |
| POST | `/api/printing/jobs` | `printing:write` | Job anlegen; Kontingent wird geprüft, liefert `quota_warning` und `compliance_warning` |
| GET | `/api/printing/jobs/{job_id}` | `printing:read` | Job lesen |
| PATCH | `/api/printing/jobs/{job_id}` | `printing:admin` | Drucker, Priorität, Verbrauch, Spule |
| PUT | `/api/printing/jobs/{job_id}/approve` | `printing:admin` | Freigeben/einreihen |
| PUT | `/api/printing/jobs/{job_id}/reject` | `printing:admin` | Mit Begründung ablehnen |
| PUT | `/api/printing/jobs/{job_id}/cancel` | `printing:write` oder `printing:admin` | Abbrechen (Team: eigener offener Job); ein laufender Druck wird auch am Drucker gestoppt |
| POST | `/api/printing/jobs/{job_id}/file` | `printing:write` oder `printing:admin` | Druckdatei hochladen (STL, 3MF, OBJ, G-Code, bgcode; bis `PRINT_UPLOAD_MAX_MB`) |
| GET | `/api/printing/jobs/{job_id}/file` | `printing:read` | Druckdatei herunterladen |
| GET | `/api/printing/quotas` | `printing:read` | Kontingente (Mentoren: eigenes Team) |
| GET | `/api/printing/events/{event_id}/quotas` | `printing:admin` | Alle Kontingente eines Events |
| PUT | `/api/printing/quotas` | `printing:admin` | Kontingent je (Event, Team) setzen |
| GET | `/api/printing/spools` | `printing:admin` | Filament-Spulen |
| POST | `/api/printing/spools` | `printing:admin` | Spule anlegen |
| POST | `/api/printing/spools/{spool_id}/consume` | `printing:admin` | Verbrauch buchen |

### Dashboard (`/api/dashboard`)

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/dashboard/announcements` | Login | Ankündigungen (Entwürfe nur mit `dashboard:write`) |
| POST | `/api/dashboard/announcements` | `dashboard:write` | Ankündigung anlegen |
| PUT | `/api/dashboard/announcements/{ann_id}/publish` | `dashboard:write` | Veröffentlichen (Push/Live-Stream nur bei Zielgruppe `all`) |
| PUT | `/api/dashboard/announcements/{ann_id}/unpublish` | `dashboard:write` | Zurückziehen |
| DELETE | `/api/dashboard/announcements/{ann_id}` | `dashboard:write` | Löschen |
| GET | `/api/dashboard/stats` | `dashboard:read` | Kennzahlen für die Übersicht |
| GET | `/api/dashboard/summary` | `dashboard:read` | Rollenbezogene Übersicht: Juror-Warteschlange, eigene Teams, Orga-Fortschritt, wirksame Module |
| GET | `/api/dashboard/notifications` | Login | Benachrichtigungszentrale (eigene und Broadcasts) |
| POST | `/api/dashboard/notifications/read` | Login | Einzelne als gelesen markieren |
| POST | `/api/dashboard/notifications/read-all` | Login | Alle als gelesen markieren |
| GET | `/api/dashboard/teams/{team_id}/history` | `teams:read` | Mehrjahres-Ergebnisse eines Teams |
| GET | `/api/dashboard/events/{event_id}/performance` | `scoring:read` | Teamvergleich (Organisation alle, Mentoren eigene Teams) |
| GET | `/api/dashboard/events/{event_id}/teams/{team_id}/performance` | `scoring:read` | Verlauf, Stärken/Schwächen, Phasenvergleich, Ranking-Vorschau |
| GET | `/api/dashboard/events/{event_id}/statistics` | `scoring:admin` | Verteilungen, Heatmap, Trends, auffällige Läufe |
| GET | `/api/dashboard/deadlines` | `seasons:read` | Deadlines einer oder aller relevanten Saisons |
| GET | `/api/dashboard/seasons/{season_id}/timeline` | `seasons:read` | Saison-Zeitleiste |
| GET | `/api/dashboard/calendar-feed` | Login | Status des eigenen iCal-Abos |
| POST | `/api/dashboard/calendar-feed` | `seasons:read` | iCal-Token erzeugen oder rotieren (nur einmal sichtbar) |
| DELETE | `/api/dashboard/calendar-feed` | Login | iCal-Abo widerrufen |
| GET | `/api/dashboard/deadlines.ics` | `?token=` (Feed-Token) oder Login | iCal-Feed der eigenen Deadlines |

### Exporte (`/api/exports`)

CSV-Dateien sind UTF-8 mit BOM. Zellen, die mit `=`, `+`, `-` oder `@` beginnen, werden entschärft (Formel-Injection).

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/exports/events/{event_id}/ranking.csv` · `.pdf` | `scoring:read` oder `dashboard:read` | Seeding-Rangliste des Events |
| GET | `/api/exports/events/{event_id}/overall-ranking.csv` · `.pdf` | `scoring:read` oder `dashboard:read` | Gesamtwertung mit allen Formelwerten |
| GET | `/api/exports/events/{event_id}/matches.csv` | `scoring:read` | Alle Wertungen des Events |
| GET | `/api/exports/seasons/{season_id}/ranking.csv` · `.pdf` | `scoring:read` oder `dashboard:read` | Rangliste (Standard-Event der Saison) |
| GET | `/api/exports/seasons/{season_id}/matches.csv` | `scoring:read` | Wertungen der Saison |
| GET | `/api/exports/seasons/{season_id}/papers.csv` · `.pdf` | `papers:admin` | Paper-Übersicht |
| GET | `/api/exports/seasons/{season_id}/reviews.csv` | `papers:admin` | Alle Reviews mit Kriterien und Kommentaren |
| GET | `/api/exports/seasons/{season_id}/printing.pdf` | `printing:admin` | Druckbericht |
| GET | `/api/exports/seasons/{season_id}/teams.csv` · `.pdf` | `teams:read` | Teamliste |
| GET | `/api/exports/teams/{team_id}/report.pdf` | `teams:read` | Ergebnisse eines Teams über alle Events |
| GET | `/api/exports/teams/{team_id}/history.csv` | `teams:read` | Mehrjahres-Ergebnisse eines Teams |
| GET | `/api/exports/history.csv` | `scoring:admin` oder `teams:admin` | Offizielle Ergebnisse aller Teams über alle Saisons |

### Bot-Galerie (`/api/bots`, Modul `bots`)

| Methode | Pfad | Recht | Zweck |
|---|---|---|---|
| GET | `/api/bots` | `teams:read` | Bots (unveröffentlichte nur für Admins und das eigene Team) |
| GET | `/api/bots/{bot_id}` | `teams:read` | Bot lesen |
| POST | `/api/bots` | `teams:write` | Bot anlegen (eigenes Team; externe Teams nur `teams:admin`) |
| PATCH | `/api/bots/{bot_id}` | `teams:write` | Bot bearbeiten |
| DELETE | `/api/bots/{bot_id}` | `teams:write` | Bot löschen |
| POST | `/api/bots/{bot_id}/image` | `teams:write` | Bild hochladen (Magic-Byte-geprüft) |
| GET | `/api/bots/{bot_id}/image` | `teams:read` | Bild |

---

## Live-Stream

Es gibt zwei WebSocket-Endpunkte mit demselben Nachrichtenformat:

- `WS /api/v1/public/events/{slug}/ws`: öffentlich, nur für Events mit mindestens einem `public_*`-Flag (Großbildschirme, öffentliche Seite).
- `WS /api/v1/events/{event_id}/ws`: angemeldet, für jedes Event, das der Benutzer lesen darf (`events:read`; Entwürfe nur mit `events:write`). Die angemeldeten Seiten nutzen ihn; solange er getrennt ist, fragen sie alle 15 s ab.

Nach dem Verbindungsaufbau sendet der Server `{"event": "connection", "payload": {"status": "connected"}}`. Danach reicht er die Nachrichten des Redis-Kanals `botball:live:{event_id}` weiter:

```json
{"event": "ranking_updated", "eventId": "…", "payload": {…}, "sentAt": "2026-06-01T09:30:00+00:00"}
```

Die Ereignisse `ranking_updated`, `schedule_updated`, `announcement_published` und `announcement_removed` werden erst nach dem Datenbank-Commit veröffentlicht (`core/live.py::publish_after_commit`). Clients laden daraufhin die betroffenen Daten neu. Außerdem veröffentlicht der Outbox-Worker Benachrichtigungen, die mit `publicLive` markiert sind, auf demselben Kanal. Jede andere Nachricht des Clients ist ein Ping; der Server antwortet `{"event": "pong"}`.

### Anmeldung am Event-Stream

Das Token steht nie in der URL (sonst landete es in Proxy- und Zugriffslogs). Der Client sendet es als erste Nachricht, spätestens nach 10 s:

```json
{"type": "auth", "token": "<Access-Token>"}
```

Der Server prüft es wie jede API-Anfrage (Signatur, Ablauf, Logout-Sperrliste, `token_version`, aktiver Benutzer), dazu `events:read` und die Entwurfsregel. Erst dann folgt `connection`. Bekommt der Client ein neues Access-Token, sendet er dieselbe Nachricht erneut; der Server antwortet `{"event": "auth", "payload": {"status": "ok"}}`. Alle 60 s und beim Ablauf des Tokens prüft der Server erneut, jeweils in einer eigenen kurzen Datenbanksitzung. Während des Streamens hält er keine Sitzung.

| Close-Code | Bedeutung | Client |
|---|---|---|
| 4400 | Erste Nachricht keine Anmeldung oder zu spät | verbindet neu (mit Backoff) |
| 4401 | Token ungültig, abgelaufen oder widerrufen, Benutzer deaktiviert | erneuert die Sitzung, verbindet neu |
| 4403 | Kein `events:read` (mehr) | hört auf, fragt ab |
| 4404 | Event unbekannt oder Entwurf ohne `events:write` | hört auf, fragt ab |
| 1013 | Redis-Abonnement verloren | verbindet neu (mit Backoff) |

Traefik leitet beide Pfade über den Router `api-ws` ohne Puffer-Middleware.
