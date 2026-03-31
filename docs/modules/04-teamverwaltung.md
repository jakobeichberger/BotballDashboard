# Modul 04 – Teamverwaltung

**Status:** [ ] Offen  
**Typ:** Kern  
**Kommuniziert mit:** Saisonverwaltung, Scoring-Modul, Paper-Review-Modul, 3D-Druck-Modul, Dashboard

---

## Beschreibung

Verwaltung aller Teams über mehrere Saisons hinweg. Ein Team gehört entweder zum **Botball**- oder zum **Open**-Wettbewerb – diese Unterscheidung beeinflusst Scoring-Formeln, Paper-Pflichten und sichtbare Dashboard-Inhalte. Bei uns müssen **beide Team-Typen ein Paper einreichen**.

---

## Team-Typen

### Botball-Teams
- Vollständige Botball-Teilnahme: Roboter + Dokumentation (Period 1–3) + Paper
- Gesamt-Score: `DE + Seeding + AdaptedDocScore` (mit AdaptedDocScore = ½·DocScore + ½·PaperScore)
- Kit wird von KIPR bereitgestellt (Versandstatus relevant)
- Paper-Einreichung: **Pflicht** (bei uns intern)

### Open-Teams (PRIA Open)
- Roboter-Teilnahme ohne offizielle Botball-Dokumentation (Period-Scores)
- Gesamt-Score: `DE + Seeding + ½·PaperScore` (kein DocScore)
- Kein Kit-Versand (bringen eigene Hardware oder verwenden Schul-Equipment)
- Paper-Einreichung: **Pflicht** (bei uns intern)

> **Hinweis:** Beide Team-Typen nehmen am selben Turnier teil und spielen gegeneinander. Die Unterscheidung betrifft nur die Score-Berechnung und Paper-Anforderungen, nicht den Spielbetrieb.

---

## Features

### Team-Stammdaten
- Teamname, Teamnummer (offizielle KIPR-Nummer)
- **Team-Typ:** `botball` | `open` (pro Saison zuweisbar, kann sich von Jahr zu Jahr ändern)
- Schule / Organisation (Name, Adresse, Land)
- Kontaktperson der Schule (Name, E-Mail, Telefon)

### Mitgliederverwaltung
- Mitglieder eines Teams hinzufügen/entfernen (Name, Rolle im Team)
- Betreuer/Mentor zuweisen (verknüpft mit Auth-Benutzer aus Modul 02)
- Mitgliederliste ist saisonspezifisch (Team kann in jeder Saison andere Mitglieder haben)

### Saison-Teilnahme
- Team für eine Saison anmelden
- **Team-Typ pro Saison:** Ein Team kann in einer Saison als Botball-Team und in einer anderen als Open-Team teilnehmen
- Pro Saison: Teilnahmegebühr-Status (offen / bezahlt)
- Kit-Versandstatus: nur für Botball-Teams relevant
- Team kann in mehreren Saisons gleichzeitig aktiv sein

### Teamhistorie
- Übersicht über alle Saisons an denen das Team teilgenommen hat
- Vergleich der Leistung über mehrere Jahre (→ Dashboard-Modul)
- Dokumente pro Team und Saison (Projektplan, Präsentation, Code-Doku)

### Dokumente & Uploads
- Upload von Projektplänen, Präsentationen, Code-Dokumentation
- Dokumente sind versionsiert (neueste Version + Archiv)
- Zugriff: Team-Mitglieder und Mentoren sehen eigene Dokumente; Admins sehen alle

### 3D-Druck-Regeln für Roboterteile (Wettbewerbs-Regeln)

Diese Regeln betreffen das **Drucken von Roboterteilen** für den Wettbewerb – nicht das 3D-Druck-Verwaltungsmodul (Modul 07). Die Regeln variieren pro Saison und sind für die Dokumentation und Compliance-Prüfung relevant.

| Saison | Material | Max. Teile | Max. Größe pro Teil | Besonderheiten |
|---|---|---|---|---|
| 2025 | PLA (grauskalig) | 4 Teile zwischen beiden Robotern | Ender 3 V3 SE: 220×220×250mm | STL-Datei in Periode 3 einzureichen |
| 2026 | PLA oder PETG (grauskalig) | 6 Teile zwischen beiden Robotern | Ender 3 V3 SE: 220×220×250mm | STL-Datei in Periode 3 einzureichen |

**Allgemeine Regeln (2025 & 2026):**
- Jedes bewegliche Teil zählt einzeln (z.B. Kette mit 10 Gliedern = 10 Teile)
- Jig/Positionierhilfe für Start-Box zählt **nicht** zum Limit, wenn nicht am Roboter
- Von jedem Teil muss eine zweite identische Kopie für Judge-Inspektion mitgebracht werden
- Judge kann Teile aus Sicherheits- oder Unangemessenheitsgründen ablehnen
- Kein Drucken direkt beim Turnier erlaubt
- STL-Dateien werden nach dem letzten regionalen Turnier und nach GCER für die Botball-Community freigegeben

> Diese Informationen sollen im Team-Dokumentations-Bereich sichtbar sein (z.B. als Compliance-Checkliste für die aktuelle Saison).

### Suche & Filter
- Teams suchen nach Name, Nummer, Schule, Saison
- Filtern nach Status (aktiv, archiviert), Land, Saison

---

## Datenmodell

```
Team {
  id: UUID
  number: string          // Offizielle KIPR-Nummer
  name: string
  school: string
  country: string
  contact_name: string
  contact_email: string
  created_at: datetime
}

TeamSeason {
  id: UUID
  team_id: UUID
  season_id: UUID
  team_type: botball | open        // Typ pro Saison (kann sich ändern)
  fee_status: pending | paid
  kit_status: not_sent | sent | received  // nur für botball relevant
  paper_required: boolean          // Standard: true für beide Typen (bei uns)
  members: TeamMember[]
  documents: Document[]
}

TeamMember {
  id: UUID
  team_season_id: UUID
  name: string
  role: string            // z.B. "Programmierer", "Konstrukteur"
  user_id: UUID?          // Optional: verknüpft mit Auth-User
}
```

---

## API-Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/teams` | Alle Teams auflisten |
| POST | `/teams` | Neues Team anlegen (Admin) |
| GET | `/teams/:id` | Team-Details abrufen |
| PUT | `/teams/:id` | Team bearbeiten (Admin, Mentor) |
| GET | `/teams/:id/seasons` | Saisons-Teilnahmen eines Teams |
| POST | `/teams/:id/seasons/:seasonId` | Team für Saison anmelden |
| PUT | `/teams/:id/seasons/:seasonId` | Saison-Teilnahme bearbeiten |
| POST | `/teams/:id/documents` | Dokument hochladen |
| GET | `/teams/:id/documents` | Dokumente eines Teams abrufen |

---

## Schnittstellen zu anderen Modulen

| Richtung | Modul | Art |
|---|---|---|
| ← | Saisonverwaltung | `season_id` als Fremdschlüssel |
| → | Scoring-Modul | Team-ID wird Scores und Matches zugeordnet |
| → | Paper-Review-Modul | Team-ID wird eingereichten Papers zugeordnet |
| → | 3D-Druck-Modul | Team-ID wird Druckjobs zugeordnet |
| → | Dashboard | Teamdaten & Historien für Visualisierungen |
