# API-Referenz

Das BotballDashboard stellt eine REST-API bereit. Die vollständige, interaktive API-Dokumentation ist automatisch generiert und unter folgender URL erreichbar:

```
https://dashboard.meineschule.at/api/docs      ← Swagger UI
https://dashboard.meineschule.at/api/redoc     ← ReDoc
```

---

## Authentifizierung

Alle Endpunkte (außer Login/Refresh) erfordern einen gültigen JWT Access Token:

```http
Authorization: Bearer <access_token>
```

### Login

```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "passwort"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900
}
```
> Refresh Token wird als HttpOnly-Cookie gesetzt.

### Token erneuern

```http
POST /api/auth/refresh
```
> Verwendet den Refresh Token aus dem Cookie.

### Logout

```http
POST /api/auth/logout
```

---

## Auth & Benutzer

| Methode | Pfad | Recht | Beschreibung |
|---|---|---|---|
| `GET` | `/api/users` | `admin:users` | Alle Benutzer auflisten |
| `POST` | `/api/users/invite` | `admin:users` | Benutzer einladen (sendet E-Mail) |
| `GET` | `/api/users/:id` | `admin:users` | Benutzer abrufen |
| `PUT` | `/api/users/:id` | `admin:users` | Benutzer bearbeiten |
| `PUT` | `/api/users/:id/roles` | `admin:users` | Rollen zuweisen |
| `DELETE` | `/api/users/:id` | `admin:users` | Benutzer deaktivieren |
| `GET` | `/api/roles` | `admin:roles` | Alle Rollen auflisten |
| `POST` | `/api/roles` | `admin:roles` | Neue Rolle anlegen |
| `PUT` | `/api/roles/:id` | `admin:roles` | Rolle bearbeiten |
| `GET` | `/api/me` | – | Eigenes Profil |
| `PUT` | `/api/me` | – | Eigenes Profil bearbeiten |
| `PUT` | `/api/me/password` | – | Passwort ändern |

---

## Saisonverwaltung

| Methode | Pfad | Recht | Beschreibung |
|---|---|---|---|
| `GET` | `/api/seasons` | `season:read` | Alle Saisons |
| `POST` | `/api/seasons` | `season:admin` | Neue Saison |
| `GET` | `/api/seasons/:id` | `season:read` | Saison abrufen |
| `PUT` | `/api/seasons/:id` | `season:admin` | Saison bearbeiten |
| `POST` | `/api/seasons/:id/clone` | `season:admin` | Saison klonen |
| `PUT` | `/api/seasons/:id/archive` | `season:admin` | Saison archivieren |
| `GET` | `/api/seasons/:id/deadlines` | `season:read` | Deadlines einer Saison |
| `POST` | `/api/seasons/:id/deadlines` | `season:admin` | Deadline anlegen |
| `PUT` | `/api/seasons/:id/deadlines/:did` | `season:admin` | Deadline bearbeiten |

---

## Teamverwaltung

| Methode | Pfad | Recht | Beschreibung |
|---|---|---|---|
| `GET` | `/api/teams` | `team:read` | Alle Teams |
| `POST` | `/api/teams` | `team:admin` | Team anlegen |
| `GET` | `/api/teams/:id` | `team:read` | Team abrufen |
| `PUT` | `/api/teams/:id` | `team:edit` | Team bearbeiten |
| `GET` | `/api/teams/:id/seasons` | `team:read` | Saison-Anmeldungen |
| `POST` | `/api/teams/:id/seasons` | `team:admin` | Team für Saison anmelden |
| `PUT` | `/api/teams/:id/seasons/:sid` | `team:admin` | Saison-Zugehörigkeit bearbeiten |

---

## Scoring

| Methode | Pfad | Recht | Beschreibung |
|---|---|---|---|
| `GET` | `/api/scoring/seasons/:id/schema` | `scoring:read` | Scoring-Schema abrufen |
| `PUT` | `/api/scoring/seasons/:id/schema` | `scoring:admin` | Schema bearbeiten |
| `GET` | `/api/scoring/seasons/:id/levels` | `scoring:read` | Wettbewerbs-Stufen |
| `POST` | `/api/scoring/seasons/:id/levels` | `scoring:admin` | Stufe anlegen |
| `POST` | `/api/scoring/levels/:id/qualify` | `scoring:admin` | Teams qualifizieren |
| `GET` | `/api/scoring/levels/:id/phases` | `scoring:read` | Phasen einer Stufe |
| `POST` | `/api/scoring/phases` | `scoring:admin` | Phase anlegen |
| `GET` | `/api/scoring/tournaments` | `scoring:read` | Turniere/Testläufe |
| `POST` | `/api/scoring/tournaments` | `scoring:admin` | Turnier anlegen |
| `GET` | `/api/scoring/tournaments/:id/bracket` | `scoring:read` | Bracket abrufen |
| `POST` | `/api/scoring/matches/:id/score` | `scoring:write` | Score einreichen |
| `PUT` | `/api/scoring/matches/:id/score` | `scoring:write` | Score korrigieren |
| `POST` | `/api/scoring/ocr/upload` | `scoring:write` | OCR-Upload |
| `GET` | `/api/scoring/seasons/:id/ranking` | `scoring:read` | Rangliste |
| `GET` | `/api/scoring/seasons/:id/ranking/full` | `scoring:read` | Rangliste inkl. Gegner |
| `POST` | `/api/scoring/external-teams` | `scoring:write` | Gegner-Team erfassen |
| `GET` | `/api/scoring/seasons/:id/dashboard` | `scoring:read` | Performance-Dashboard |
| `POST` | `/api/scoring/teams/:id/cards` | `scoring:admin` | Yellow/Red Card vergeben |

---

## Paper-Review

| Methode | Pfad | Recht | Beschreibung |
|---|---|---|---|
| `GET` | `/api/papers` | `paper:read` | Papers auflisten |
| `POST` | `/api/papers` | `paper:submit` | Paper einreichen |
| `GET` | `/api/papers/:id` | `paper:read` | Paper abrufen |
| `GET` | `/api/papers/:id/file` | `paper:read` | PDF herunterladen |
| `POST` | `/api/papers/:id/revisions` | `paper:submit` | Revision hochladen |
| `GET` | `/api/papers/:id/reviews` | `paper:read` | Reviews eines Papers |
| `POST` | `/api/papers/:id/reviews` | `paper:review` | Review schreiben |
| `PUT` | `/api/papers/:id/reviews/:rid` | `paper:review` | Review bearbeiten |
| `POST` | `/api/papers/:id/assign` | `paper:assign` | Reviewer zuweisen |
| `PUT` | `/api/papers/:id/status` | `paper:admin` | Status manuell setzen |

---

## 3D-Druck

| Methode | Pfad | Recht | Beschreibung |
|---|---|---|---|
| `GET` | `/api/print/printers` | `print:manage` | Drucker auflisten |
| `POST` | `/api/print/printers` | `print:admin` | Drucker hinzufügen |
| `PUT` | `/api/print/printers/:id` | `print:admin` | Drucker bearbeiten |
| `DELETE` | `/api/print/printers/:id` | `print:admin` | Drucker entfernen |
| `GET` | `/api/print/printers/:id/status` | `print:manage` | Echtzeit-Status |
| `GET` | `/api/print/jobs` | `print:request` | Jobs (gefiltert nach Rolle) |
| `POST` | `/api/print/jobs` | `print:request` | Job beantragen |
| `PUT` | `/api/print/jobs/:id/approve` | `print:manage` | Job genehmigen |
| `PUT` | `/api/print/jobs/:id/reject` | `print:manage` | Job ablehnen |
| `PUT` | `/api/print/jobs/:id/cancel` | `print:request` | Job abbrechen |
| `GET` | `/api/print/jobs/:id/progress` | `print:request` | Fortschritt abrufen |
| `GET` | `/api/print/seasons/:id/quotas` | `print:admin` | Team-Limits einsehen |
| `PUT` | `/api/print/seasons/:id/quotas/:tid` | `print:admin` | Limits setzen |
| `GET` | `/api/print/stats` | `print:manage` | Statistiken & Filament-Tracking |

---

## Score Sheet Import

| Methode | Pfad | Recht | Beschreibung |
|---|---|---|---|
| `POST` | `/api/scoring/seasons/:id/score-sheets` | `scoring:admin` | PDF hochladen, OCR startet im Hintergrund |
| `GET` | `/api/scoring/seasons/:id/score-sheets` | `scoring:read` | Alle Sheets einer Saison auflisten |
| `GET` | `/api/scoring/score-sheets/:id` | `scoring:read` | Sheet + OCR-Kandidaten abrufen |
| `GET` | `/api/scoring/score-sheets/:id/file` | `scoring:read` | Original-PDF herunterladen |
| `POST` | `/api/scoring/score-sheets/:id/confirm` | `scoring:admin` | Felder bestätigen (optional: sofort in Scoring-Schema übernehmen) |
| `PUT` | `/api/scoring/score-sheets/:id/active` | `scoring:admin` | Sheet als aktiv markieren |
| `DELETE` | `/api/scoring/score-sheets/:id` | `scoring:admin` | Sheet + PDF-Datei löschen |

**Upload-Workflow:**
1. `POST` mit `multipart/form-data` (Felder: `file`, `label`, `year`, `game_theme?`, `competition_level_id?`)
2. Response sofort mit `ocr_status: "pending"`
3. Background-Task läuft: `pdftotext` → Feldextraktion → `ocr_status: "done"`
4. Frontend pollt `GET /score-sheets/:id` bis `ocr_status === "done"` (alle 3s)
5. Admin überprüft `extracted_fields`, editiert und sendet `POST /confirm`

---

## Dashboard

| Methode | Pfad | Recht | Beschreibung |
|---|---|---|---|
| `GET` | `/api/dashboard/summary` | – | Übersichts-Daten (rollenspezifisch) |
| `GET` | `/api/dashboard/seasons/:id/overview` | `season:read` | Saison-Timeline & Status |
| `GET` | `/api/dashboard/seasons/:id/deadlines` | `season:read` | Alle Deadlines |
| `GET` | `/api/dashboard/seasons/:id/deadlines.ical` | `season:read` | iCal-Export |
| `GET` | `/api/dashboard/seasons/:id/stats` | `season:read` | Statistiken |
| `GET` | `/api/dashboard/teams/:id/history` | `team:read` | Team-Verlauf |
| `GET` | `/api/dashboard/scoreboard` | – | Öffentliches Scoreboard (WebSocket) |

---

## System (Admin)

| Methode | Pfad | Recht | Beschreibung |
|---|---|---|---|
| `GET` | `/api/system/logs` | `admin:system` | Application Logs |
| `GET` | `/api/system/errors` | `admin:system` | Error-Log |
| `PUT` | `/api/system/errors/:id/resolve` | `admin:system` | Fehler als gelöst markieren |
| `GET` | `/api/system/audit` | `admin:system` | Audit-Log |
| `GET` | `/api/system/audit/export` | `admin:system` | Audit-Log als CSV |
| `POST` | `/api/system/backup` | `admin:system` | Manuelles Backup auslösen |
| `GET` | `/api/system/health` | – | Health-Check (kein Auth nötig) |

---

## Fehler-Formate

Alle Fehler folgen diesem Format:

```json
{
  "error": "validation_error",
  "message": "Ungültige Score-Felder",
  "details": [
    { "field": "warehouse_floor_cubes", "message": "Wert darf nicht negativ sein" }
  ]
}
```

| HTTP-Status | Bedeutung |
|---|---|
| `200` | Erfolgreich |
| `201` | Erfolgreich erstellt |
| `400` | Ungültige Anfrage / Validierungsfehler |
| `401` | Nicht eingeloggt |
| `403` | Keine Berechtigung |
| `404` | Nicht gefunden |
| `409` | Konflikt (z.B. E-Mail bereits vergeben) |
| `422` | Unverarbeitbare Daten (Pydantic-Validierung) |
| `500` | Interner Serverfehler |
