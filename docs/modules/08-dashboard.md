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
