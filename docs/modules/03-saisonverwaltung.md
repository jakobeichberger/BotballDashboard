# Modul 03 – Saisonverwaltung

**Status:** [ ] Offen  
**Typ:** Kern  
**Kommuniziert mit:** Teamverwaltung, Scoring-Modul, Paper-Review-Modul, 3D-Druck-Modul

---

## Beschreibung

Zentrale Verwaltung von Botball-Saisons (z.B. 2024, 2025, 2026). Alle Fachmodule referenzieren eine Saison. Saisons können angelegt, konfiguriert, archiviert und als Vorlage geklont werden.

---

## Features

### Saison-Lebenszyklus

| Status | Bedeutung |
|---|---|
| `draft` | In Vorbereitung, noch nicht für Teams sichtbar |
| `active` | Läuft, Teams können sich anmelden und Daten einreichen |
| `finished` | Turnier abgeschlossen, nur noch Lesezugriff |
| `archived` | Vollständig archiviert, schreibgeschützt |

### Saison anlegen & konfigurieren
- Name, Jahr, Beschreibung, Start- und Enddatum
- Konfigurieren welche Module für diese Saison aktiv sind (z.B. Scoring ✓, Paper-Review ✓, 3D-Druck ✗)
- Spielfeld-Konfiguration: Anzahl Seeding-Runden, Anzahl Teams im Double-Elimination

### Saison klonen (Vorlage)
- Bestehende Saison als Vorlage für eine neue Saison verwenden
- Übernommen werden: Modul-Konfiguration, Rollen-Einstellungen, Scoring-Sheet-Vorlagen
- Nicht übernommen werden: Teams, Scores, eingereichte Papers

### Archivierung
- Abgeschlossene Saisons werden archiviert und schreibgeschützt
- Archivierte Saisons bleiben abrufbar (Teamhistorie, Statistiken)
- Kein Löschen von archivierten Saisons möglich (Datensicherheit)

### Saisonübergreifende Features
- Teams können über mehrere Saisons hinweg verknüpft werden
- Mehrjahresstatistiken im Dashboard (→ Modul 08)
- Export aller Saison-Daten als JSON/CSV

### Termine & Deadlines
- Wichtige Termine pro Saison: Anmeldeschluss, Workshop-Termin, Paper-Deadline, Turniertag
- Erinnerungen per E-Mail bei bevorstehenden Deadlines

---

## Datenmodell

```
Season {
  id: UUID
  name: string
  year: number
  description: text
  status: draft | active | finished | archived
  start_date: date
  end_date: date
  active_modules: string[]   // z.B. ["scoring", "paper-review"]
  config: JSON               // Modul-spezifische Konfiguration
  created_at: datetime
  updated_at: datetime
}
```

---

## API-Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/seasons` | Alle Saisons auflisten |
| POST | `/seasons` | Neue Saison anlegen (Admin) |
| GET | `/seasons/:id` | Saison-Details abrufen |
| PUT | `/seasons/:id` | Saison bearbeiten (Admin) |
| POST | `/seasons/:id/clone` | Saison als Vorlage klonen (Admin) |
| PUT | `/seasons/:id/status` | Status ändern (Admin) |
| GET | `/seasons/:id/export` | Saison-Daten exportieren |

---

## Schnittstellen zu anderen Modulen

| Richtung | Modul | Art |
|---|---|---|
| → | Teamverwaltung | Teams werden einer Season zugeordnet (`season_id`) |
| → | Scoring-Modul | Scoring-Vorlagen und Turniere sind saisonspezifisch |
| → | Paper-Review-Modul | Papers gehören zu einer Saison |
| → | 3D-Druck-Modul | Druckjobs können einer Saison zugeordnet werden |
| → | Dashboard | Liefert Saison-Übersicht und Mehrjahresvergleiche |
