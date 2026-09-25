# Statische Modul-Registry

BotballDashboard ist ein modularer Monolith. Die Module gehören fest zum gebauten Artefakt. Sie werden weder zur Laufzeit installiert noch aus fremdem Code geladen. Es gibt keine `manifest.json` (die letzte, ungenutzte Datei wurde entfernt), keine dynamischen Imports aus Uploads und keine installierbaren Drittanbieter-Plugins.

## Backend: `backend/core/modules.py`

`MODULES` ist die einzige Router-Registry. Jeder Eintrag (`ModuleDefinition`) hat:

| Feld | Bedeutung |
|---|---|
| `key` | stabiler Schlüssel (`auth`, `seasons`, `events`, `public-events`, `teams`, `scoring`, `score-sheet-scans`, `papers`, `printing`, `dashboard`, `exports`, `bots`) |
| `router` | FastAPI-Router des Moduls |
| `permissions` | Rechte, die das Modul verwendet (Dokumentation; die Prüfung passiert in den Routen) |
| `event_module` | optionaler Schlüssel des Event-Modul-Schalters; `None` für Kernmodule |

`main.py` bindet alle Router unter `/api` ein. Hat ein Eintrag ein `event_module` (`paper`, `printing`, `bots`), bekommt der ganze Router `require_module(event_module)` als Dependency. Der Guard ermittelt das adressierte Event aus Pfad, Query, JSON-Body oder dem adressierten Datensatz. Ist das Modul dort nicht wirksam, antwortet er mit 404. Einzelne Routen anderer Router nutzen dieselben Guards direkt, etwa DE, Aerial, Doku und die Druck-Checkliste in `teams`.

Die Datenmodelle aller Module teilen sich eine PostgreSQL-Datenbank und eine lineare Alembic-Kette (`0001`–`0029`).

## Frontend: `frontend/src/core/plugins.ts`

Die Datei heißt aus historischen Gründen `plugins.ts`, ist aber eine statische Registry. Pro Modul (`dashboard`, `teams`, `events`, `admin`, `scoring`, `papers`, `printing`) enthält sie:

- die Routen unterhalb von `/events/:eventId/` mit lazy geladener Seite;
- das nötige Recht (`permission`, leer = jeder Angemeldete);
- ob ein Navigationseintrag entsteht, mit Label (de/en) und Icon;
- `module`: welcher Event-Modul-Schalter die Route braucht (`paper`, `printing`, `bots`, `double_elimination`, `aerial`, `documentation` oder das Saison-Flag `paper_scoring`);
- Dashboard-Widget-Deklarationen und i18n-Namensräume.

`App.tsx` erzeugt aus `eventRoutes` die Routen, jeweils eingepackt in `ProtectedRoute` (Recht) und `ModuleRoute` (Modul-Schalter). `Layout.tsx` baut aus `navigationRoutes` die Navigation und blendet Einträge für abgeschaltete Module aus. So bleiben Route, Navigation und Rechte-Prüfung konsistent. Die Felder `dashboardWidgets` und `translations` werden derzeit von keiner Komponente ausgewertet. Die Dashboards (`pages/dashboard/*`) wählen ihre Abschnitte selbst anhand der Rolle und von `/api/dashboard/summary`.

Außerhalb der Registry liegen nur die Routen ohne Event-Kontext:

- `/login`, `/forgot-password`, `/reset-password`;
- `/public/:eventSlug`;
- `/setup` (Event-Assistent);
- `/settings/*` (Administration).

## Modul-Aktivierung pro Event

Welche Fachmodule ein Event nutzt, entscheiden zwei Schalter gemeinsam (`backend/modules/events/module_access.py`):

- `Event.active_modules`: gesetzt in der Event-Verwaltung. Schlüssel sind `seeding`, `double_elimination`, `paper`, `documentation`, `aerial`, `printing`, `bots`.
- die Saison-Flags `use_seeding`, `use_double_elimination`, `use_documentation_scoring`, `use_aerial`: Ein in der Saison abgeschaltetes Modul bleibt auch im Event inaktiv. `use_paper_scoring` entscheidet, ob der Paper-Score in die Doku- bzw. Gesamtwertung eingeht.

`GET /api/v1/events/{id}/modules` liefert `active_modules`, die wirksamen Module und die Saison-Flags. Frontend und Backend verhalten sich dabei so:

- Frontend: Navigationseinträge werden ausgeblendet, `ModuleRoute` zeigt „Dieses Modul ist für dieses Event nicht aktiv".
- Backend: 404 für Routen abgeschalteter Module, 409 beim Anlegen oder Planen einer Phase eines abgeschalteten Moduls.

## Neues Modul ergänzen

1. Backend-Paket unter `backend/modules/<name>` anlegen: `models.py`, `schemas.py`, `service.py`, `routes.py`.
2. Migration mit der nächsten freien Nummer anlegen, mit allen Foreign Keys, Unique- und Check-Constraints. Die Migration muss auf PostgreSQL und SQLite laufen und ein funktionierendes `downgrade` haben. Das neue Modell-Modul in `backend/alembic/env.py` importieren.
3. Neue Rechte per Migration anlegen und den Rollen zuweisen. Router und Rechte in `backend/core/modules.py` registrieren. Soll das Modul pro Event abschaltbar sein, den Schlüssel in `MODULE_KEYS` (`module_access.py`) ergänzen und `event_module` setzen.
4. Schreibpfade mit `ensure_writable` gegen archivierte Saisons und Events schützen. Team-bezogene Aktionen mit `assert_team_access` absichern.
5. Frontend-Seite und Übersetzungen anlegen und genau einen Eintrag in `frontend/src/core/plugins.ts` ergänzen, gegebenenfalls mit `module`.
6. Unit- und Integrationstests schreiben, dazu Rechte-Tests, die ohne die Prüfung fehlschlagen. Für zentrale Abläufe einen Playwright-Flow ergänzen.
7. Die OpenAPI-Typen mit `pnpm api:generate` neu erzeugen (`frontend/openapi.json`, `src/api/generated.ts`) und mit committen.
