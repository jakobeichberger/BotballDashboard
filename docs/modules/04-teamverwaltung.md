# Modul 04 – Teamverwaltung

**Status:** [ ] Offen  
**Typ:** Kern  
**Kommuniziert mit:** Saisonverwaltung, Scoring-Modul, Paper-Review-Modul, 3D-Druck-Modul, Dashboard

---

## Beschreibung

Verwaltung aller Botball-Teams über mehrere Saisons hinweg. Teams können angelegt, bearbeitet und einer oder mehreren Saisons zugeordnet werden. Mitglieder, Betreuer und Schuldaten werden pro Team gepflegt.

---

## Features

### Team-Stammdaten
- Teamname, Teamnummer (offizielle KIPR-Nummer)
- Schule / Organisation (Name, Adresse, Land)
- Kontaktperson der Schule (Name, E-Mail, Telefon)

### Mitgliederverwaltung
- Mitglieder eines Teams hinzufügen/entfernen (Name, Rolle im Team)
- Betreuer/Mentor zuweisen (verknüpft mit Auth-Benutzer aus Modul 02)
- Mitgliederliste ist saisonspezifisch (Team kann in jeder Saison andere Mitglieder haben)

### Saison-Teilnahme
- Team für eine Saison anmelden
- Pro Saison: Teilnahmegebühr-Status (offen / bezahlt), Kit-Versandstatus
- Team kann in mehreren Saisons gleichzeitig aktiv sein

### Teamhistorie
- Übersicht über alle Saisons an denen das Team teilgenommen hat
- Vergleich der Leistung über mehrere Jahre (→ Dashboard-Modul)
- Dokumente pro Team und Saison (Projektplan, Präsentation, Code-Doku)

### Dokumente & Uploads
- Upload von Projektplänen, Präsentationen, Code-Dokumentation
- Dokumente sind versionsiert (neueste Version + Archiv)
- Zugriff: Team-Mitglieder und Mentoren sehen eigene Dokumente; Admins sehen alle

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
  fee_status: pending | paid
  kit_status: not_sent | sent | received
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
