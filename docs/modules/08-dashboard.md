# Modul 08 – Dashboard & Visualisierung

**Status:** [ ] Offen  
**Typ:** Kern (aggregiert alle Module)  
**Kommuniziert mit:** Saisonverwaltung, Teamverwaltung, Scoring-Modul, Paper-Review-Modul, 3D-Druck-Modul

---

## Beschreibung

Übergreifendes Dashboard das Daten aus allen aktiven Modulen aggregiert und rollenspezifisch darstellt. Jedes Plugin kann eigene Dashboard-Widgets registrieren. Unterstützt Echtzeit-Updates via WebSocket sowie statische Exporte.

---

## Features

### Modulares Widget-System
- Jedes Plugin kann Widgets beim Dashboard registrieren
- Widgets werden je nach aktiven Modulen der Saison angezeigt
- Benutzer können ihr Dashboard personalisieren (welche Widgets wo)

### Rollen-spezifische Ansichten

| Rolle | Sieht |
|---|---|
| Admin | Alles: alle Teams, alle Scores, alle Papers, alle Druckjobs, Systemstatus |
| Juror | Scoring-Widgets: aktuelle Rangliste, offene Scores, nächste Matches |
| Reviewer | Paper-Review-Widgets: zugewiesene Papers, ausstehende Reviews |
| Mentor | Eigenes Team: Scores, Paper-Status, Druckjobs |
| Guest | Öffentliche Rangliste, Bracket-Anzeige |

### Saison-Übersicht & Prozess-Timeline

Eine dedizierte **Übersichtsseite pro Saison** zeigt den gesamten Ablauf und alle Timelines auf einen Blick:

**Prozess-Ablauf-Visualisierung:**
- Horizontale Timeline aller Wettbewerbsphasen (ECER Prep → ECER Turnier → GCER Prep → GCER Turnier)
- Aktuell aktive Phase wird hervorgehoben
- Status-Indikatoren pro Phase: `geplant | aktiv | abgeschlossen`
- Klick auf Phase öffnet Detailansicht

**Deadline-Kalender (alle Timelines pro Saison):**

| Deadline-Typ | Modul | Farbe |
|---|---|---|
| Paper-Einreichung (intern) | Paper-Review | orange |
| Paper-Einreichung (offiziell) | Paper-Review | rot |
| Internes Paper-Review | Paper-Review | orange |
| Paper-Revision | Paper-Review | orange |
| Finales Paper (offiziell) | Paper-Review | rot |
| ECER Prep-Phase Start/Ende | Scoring | blau |
| ECER Turnier | Scoring | blau |
| GCER Prep-Phase Start/Ende | Scoring | lila |
| GCER Turnier | Scoring | lila |
| Druckjob-Deadlines | 3D-Druck | grün |

- Alle Deadlines in einer gemeinsamen Kalenderansicht (Monat / Liste)
- Automatische Erinnerungs-Badges: "X Tage bis [Deadline]"
- Verstrichene Deadlines werden anders dargestellt (grau/rot)
- Export als iCal-Datei möglich

**Status-Übersicht pro Saison:**
- Wie viele Teams haben Paper eingereicht? (X von N)
- Wie viele Reviews sind noch ausstehend?
- Wie viele Testläufe wurden bereits dokumentiert?
- Welche Teams haben sich für GCER qualifiziert?
- Druckjob-Queue: aktuelle Auslastung

### Scoring-Widgets
- Live-Rangliste (Seeding-Durchschnitt, sortierbar)
- Double-Elimination-Bracket (interaktiv)
- Nächste geplante Matches
- Punkteverteilung pro Aufgabensegment (Balkendiagramm)
- Team-Vergleich: zwei Teams nebeneinander

### Paper-Review-Widgets
- Übersicht: eingereichte / reviewed / ausstehende Papers
- Durchschnittsnoten pro Bewertungskategorie
- Timeline der Einreichungen

### 3D-Druck-Widgets
- Drucker-Status-Übersicht (alle Drucker auf einen Blick)
- Aktuelle Queue (wer druckt gerade, wer wartet)
- Fehler-Übersicht

### Statistik & Analyse
- Graphen und Tabellen zur Punkteverteilung (Chart.js / D3.js)
- Boxplots: Punktestreuung aller Teams
- Heatmaps: häufigste Fehler / schwache Aufgabenbereiche
- Mehrjahresvergleiche über Saisons
- Trend-Analyse: wie entwickelt sich ein Team über Jahre

### Historische Daten
- Ergebnisse vergangener Saisons abrufbar
- Archivierte Saisons im Dashboard durchsuchen

### Export
- PDF-Berichte (Saison-Zusammenfassung, Team-Bericht)
- CSV/Excel für Weiterverarbeitung
- Öffentliches Live-Scoreboard (separater View für Großbildschirme, via WebSocket)

---

## API-Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/dashboard/summary` | Übersichts-Daten für aktuellen User |
| GET | `/dashboard/seasons/:id/overview` | Saison-Übersicht mit Phasen-Timeline & Status |
| GET | `/dashboard/seasons/:id/deadlines` | Alle Deadlines einer Saison (saisonübergreifend) |
| GET | `/dashboard/seasons/:id/deadlines.ical` | Deadlines als iCal-Export |
| GET | `/dashboard/seasons/:id/stats` | Statistiken einer Saison |
| GET | `/dashboard/teams/:id/history` | Team-Verlauf über Saisons |
| GET | `/dashboard/scoreboard` | Öffentliches Scoreboard (WebSocket) |
| GET | `/dashboard/export/pdf` | Bericht als PDF exportieren |
| GET | `/dashboard/export/csv` | Rohdaten als CSV exportieren |

---

## Schnittstellen zu anderen Modulen

| Richtung | Modul | Art |
|---|---|---|
| ← | Saisonverwaltung | Saison-Metadaten, aktive Module |
| ← | Teamverwaltung | Team-Stammdaten, Historien |
| ← | Scoring-Modul | Scores, Ranglisten, Match-Daten |
| ← | Paper-Review-Modul | Paper-Status, Bewertungen |
| ← | 3D-Druck-Modul | Drucker-Status, Job-Queue |
| → | Frontend | WebSocket für Live-Daten |
