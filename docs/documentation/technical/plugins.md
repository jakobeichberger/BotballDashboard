# Statische Modul-Registry

BotballDashboard ist ein modularer Monolith. Module sind Teil des deployten Artefakts und werden nicht zur Laufzeit installiert oder aus fremdem Code geladen.

## Backend

`backend/core/modules.py` ist die einzige Router-Registry. Ein Modul definiert einen stabilen Schlüssel, seinen FastAPI-Router und die zugehörigen Permissions. `main.py` bindet diese Liste unter `/api` ein. Datenmodelle teilen sich eine PostgreSQL-Datenbank und reproduzierbare Alembic-Migrationen.

## Frontend

`frontend/src/core/plugins.ts` ist trotz des historischen Dateinamens eine statische Registry. Sie enthält pro Modul:

- eventbezogene Routen;
- Navigationseinträge und erforderliche Permission;
- rollenbezogene Dashboard-Widgets;
- deutsche und englische Bezeichnungen;
- benötigte i18next-Namensräume.

`App.tsx`, `Layout.tsx` und `DashboardPage.tsx` lesen dieselben Definitionen. Dadurch können Route, Navigation und Permission-Gate nicht unabhängig voneinander auseinanderlaufen.

## Modul-Aktivierung pro Event

Welche Fachmodule ein Event nutzt, entscheiden zwei Schalter gemeinsam (`backend/modules/events/module_access.py`):

- `Event.active_modules` – vom Orga-Team in der Event-Verwaltung gesetzt (`seeding`, `double_elimination`, `paper`, `documentation`, `aerial`, `printing`, `bots`);
- die Saison-Flags `use_seeding`, `use_double_elimination`, `use_documentation_scoring` und `use_aerial` – ein in der Saison abgeschaltetes Modul bleibt auch im Event inaktiv. `use_paper_scoring` steuert nur, ob der Paper-Score in die Gesamtwertung eingeht (und damit die Doku-/Paper-Erfassung).

`GET /api/v1/events/{id}/modules` liefert die wirksamen Module. Das Frontend blendet damit Navigationseinträge aus und sperrt Routen (`module` in der Registry, `ModuleRoute`). Im Backend antworten die Router für Paper, Druck und Roboter (`event_module` in `core/modules.py`) sowie die DE-, Aerial- und Doku-Routen für ein Event mit abgeschaltetem Modul mit 404; eine DE-Phase lässt sich dann nicht anlegen (409).

## Neues Modul ergänzen

1. Backend-Paket unter `backend/modules/<name>` anlegen, Modelle und Router implementieren.
2. Migration mit allen Foreign Keys, Unique- und Check-Constraints hinzufügen.
3. Router und Permissions in `backend/core/modules.py` registrieren.
4. Frontend-Seite und Übersetzungen anlegen und genau einen Eintrag in der statischen Registry ergänzen.
5. Unit-/Integrationstests, Permission-Tests sowie bei zentralen Abläufen einen Playwright-Flow hinzufügen.
6. OpenAPI-Typen mit `pnpm api:generate` neu erzeugen und gemeinsam committen.

Es gibt absichtlich keine `manifest.json`, dynamische Imports aus Uploads oder installierbare Drittanbieter-Plugins.
