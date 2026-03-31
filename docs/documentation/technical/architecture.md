# Systemarchitektur

---

## Überblick

```
┌─────────────────────────────────────────────────────────┐
│                        Clients                          │
│  Browser (PC/Laptop/Tablet/Handy)  +  PWA               │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS
┌────────────────────▼────────────────────────────────────┐
│               Traefik (Reverse Proxy)                   │
│         SSL-Terminierung, Routing, Rate-Limiting        │
└───────┬──────────────────────┬──────────────────────────┘
        │                      │
┌───────▼──────┐    ┌──────────▼──────────┐
│   Frontend   │    │      Backend        │
│  React + Vite│    │  FastAPI (Python)   │
│  Nginx       │    │  Port 8000          │
└──────────────┘    └──────────┬──────────┘
                               │
               ┌───────────────┼───────────────┐
               │               │               │
    ┌──────────▼───┐  ┌────────▼──────┐  ┌────▼──────┐
    │  PostgreSQL  │  │  OCR-Service  │  │  3D-Drucker│
    │  (Datenbank) │  │  (Tesseract)  │  │  APIs      │
    └──────────────┘  └───────────────┘  └───────────┘
```

---

## Komponenten

### Frontend (React)
- **Framework:** React 18 + TypeScript
- **Build-Tool:** Vite
- **Styling:** Tailwind CSS (inkl. Dark Mode via `dark:`-Klassen)
- **State Management:** Zustand (lightweight, kein Redux-Overhead)
- **API-Client:** TanStack Query (Caching, Loading States, Refetch)
- **i18n:** i18next (DE + EN)
- **Charts:** Recharts
- **PWA:** Vite PWA Plugin + Service Worker
- **Routing:** React Router v6

### Backend (FastAPI)
- **Framework:** FastAPI (Python 3.11+)
- **ORM:** SQLAlchemy 2.0 (async)
- **Migrations:** Alembic
- **Validierung:** Pydantic v2
- **Auth:** JWT (python-jose), Passwort-Hashing mit bcrypt
- **WebSocket:** FastAPI WebSocket + Redis Pub/Sub für horizontales Scaling
- **Task Queue:** Celery + Redis (für E-Mail-Versand, OCR-Jobs)
- **Push Notifications:** pywebpush (Web Push API)
- **Verschlüsselung:** cryptography (Fernet für Drucker-Credentials)

### Datenbank
- **PostgreSQL 16**
- Persistentes Docker Volume auf `/data/db`
- Migrations automatisch beim Start (`migrate-then-start`)
- Backup täglich via `pg_dump` nach `/data/backups`

### OCR-Service
- Separater Docker-Container
- OpenCV für Bildvorverarbeitung (Kontrast, Entzerrung, Rauschen)
- Tesseract für Texterkennung
- REST-API: `POST /ocr/extract` → gibt erkannte Felder zurück

### Reverse Proxy (Traefik)
- Automatisches SSL via Let's Encrypt
- Routing: `/api/` → Backend, `/` → Frontend
- WebSocket-Support für Live-Daten
- Rate Limiting gegen Brute-Force

---

## Plugin-System

Jedes Modul außer Core (Auth, Saison, Teams) ist ein Plugin:

```
modules/
  scoring/
    manifest.json       ← Plugin-Registrierung
    routes.py           ← FastAPI-Router
    models.py           ← SQLAlchemy-Modelle
    schemas.py          ← Pydantic-Schemas
    service.py          ← Business Logic
  paper-review/
    manifest.json
    ...
  3d-print/
    manifest.json
    ...
```

**manifest.json Struktur:**
```json
{
  "id": "scoring",
  "name": "Scoring-Modul",
  "version": "1.0.0",
  "permissions": ["scoring:read", "scoring:write", "scoring:admin"],
  "db_tables": ["competition_level", "phase", "match", "score"],
  "dashboard_widgets": ["ranking", "bracket", "performance"],
  "api_prefix": "/scoring"
}
```

Der Plugin-Registry-Service lädt beim Start alle `manifest.json`-Dateien und registriert Router, Rechte und Widgets dynamisch. Neue Module erfordern keine Änderung am Core.

---

## Authentifizierung & Autorisierung

```
Login → Access Token (JWT, 15 min) + Refresh Token (JWT, 30 Tage)
      → Access Token in Authorization Header: Bearer <token>
      → Refresh Token in HttpOnly-Cookie (XSS-sicher)

Token Refresh: automatisch durch Frontend wenn 401 zurückkommt
```

**Rechte-Prüfung:**
```python
@router.post("/scoring/matches/{id}/score")
@require_permission("scoring:write")
async def submit_score(id: UUID, ...):
    ...
```

---

## Echtzeit-Daten (WebSocket)

```
Client ──WebSocket──► Backend ──Redis Pub/Sub──► alle verbundenen Clients
                              (bei Score-Update, Match-Statuswechsel, etc.)
```

WebSocket-Endpunkte:
- `/ws/scoring/live` – Live-Rangliste & Match-Status
- `/ws/print/status` – Drucker-Status & Job-Fortschritt
- `/ws/notifications` – Push-Benachrichtigungen fallback

---

## Logging & Error Tracking

### Application Logs (strukturiert)

Alle Logs werden als strukturiertes JSON ausgegeben:

```json
{
  "timestamp": "2026-01-15T14:32:01Z",
  "level": "INFO",
  "module": "scoring",
  "event": "score_submitted",
  "user_id": "abc-123",
  "match_id": "xyz-456",
  "message": "Score submitted for match xyz-456"
}
```

**Log-Level:**
| Level | Wann |
|---|---|
| `DEBUG` | Detaillierte Entwickler-Infos (nur in `DEBUG=true`) |
| `INFO` | Normale Ereignisse (Login, Score eingegeben, Job gestartet) |
| `WARNING` | Unerwartetes aber nicht kritisches Verhalten (Soft-Limit erreicht, Retry) |
| `ERROR` | Fehler die eine Aktion scheitern lassen (DB-Fehler, Drucker nicht erreichbar) |
| `CRITICAL` | Systemkritische Fehler (DB-Verbindung komplett weg, OOM) |

### Error Log

Alle `ERROR`- und `CRITICAL`-Einträge werden zusätzlich in einer separaten `error_log`-Tabelle in der Datenbank gespeichert:

```
ErrorLog {
  id, timestamp, level,
  module, event,
  user_id?,
  request_path?, request_method?,
  error_type, error_message, stack_trace,
  resolved: boolean, resolved_by?, resolved_at?
}
```

**Admin-UI → System → Error-Log:**
- Filterbar nach Level, Modul, Zeitraum, Status (offen/gelöst)
- Fehler als „gelöst" markieren mit Notiz
- Kritische Fehler lösen automatisch eine Admin-E-Mail aus

### Audit-Log

Alle sicherheitsrelevanten und datenkritischen Aktionen werden im Audit-Log protokolliert:

```
AuditLog {
  id, timestamp,
  user_id, user_email,
  action,              // z.B. "score.updated", "paper.status_changed"
  entity_type,         // z.B. "Score", "Paper", "User"
  entity_id,
  old_value: JSON?,
  new_value: JSON,
  ip_address
}
```

**Typische Audit-Einträge:**
- Score eingegeben / korrigiert (mit altem und neuem Wert)
- Paper-Status geändert
- Benutzer angelegt / deaktiviert / Rolle geändert
- Drucker-Credentials geändert
- Saison archiviert
- Yellow/Red Card vergeben

**Admin-UI → System → Audit-Log:**
- Nicht löschbar (unveränderliches Protokoll)
- Exportierbar als CSV

### Log-Ausgabe & Speicherung

- Logs werden auf `stdout` geschrieben → Docker sammelt sie
- `docker compose logs backend` zeigt alle Logs
- Optional: Log-Aggregation mit Loki + Grafana (für produktive Installationen)
- Rotation: Logs älter als 90 Tage werden automatisch bereinigt

---

## Datenbankmigrationen

```bash
# Neue Migration erstellen
alembic revision --autogenerate -m "add yellow_card to team_tournament"

# Alle ausstehenden Migrationen anwenden
alembic upgrade head

# Eine Version zurück
alembic downgrade -1

# Versions-Historie
alembic history
```

Beim Docker-Start wird automatisch `alembic upgrade head` ausgeführt bevor der Server startet (`migrate-then-start`-Skript im Entrypoint).
