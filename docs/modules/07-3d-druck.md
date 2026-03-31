# Modul 07 – 3D-Druck-Modul

**Status:** [ ] Offen  
**Typ:** Plugin  
**Registriert beim Kern via:** `modules/print/manifest.json`  
**Kommuniziert mit:** Teamverwaltung, Saisonverwaltung, Auth

---

## Beschreibung

Eigenständiges Plugin zur Verwaltung von 3D-Druckjobs über mehrere Drucker verschiedener Hersteller. Teams stellen Druckanfragen, Admins verwalten die Queue und weisen Jobs Druckern zu. Der Drucker-Adapter-Layer abstrahiert herstellerspezifische APIs hinter einem einheitlichen Interface.

---

## Features

### Drucker-Verwaltung
- Drucker anlegen: Name, Hersteller, Modell, Standort, Adapter-Typ
- Drucker aktivieren / deaktivieren
- Status-Übersicht aller Drucker in Echtzeit
- Druckergruppen (z.B. "Schuldrucker", "Wettbewerbsdrucker")

### Drucker-Adapter-Layer
Einheitliches Interface für alle Drucker:

```
interface PrinterAdapter {
  getStatus(): PrinterStatus
  sendJob(file, settings): JobID
  cancelJob(jobId): void
  getProgress(jobId): JobProgress
  getJobHistory(): Job[]
}
```

Implementierte Adapter:

| Adapter | Hersteller | Protokoll |
|---|---|---|
| `BambuAdapter` | Bambu Lab (X1C, P1S, A1) | Bambu Cloud API + MQTT |
| `PrusaAdapter` | Prusa (MK4, XL, Mini) | Prusa Connect REST-API |
| `OctoPrintAdapter` | Generisch (Fallback) | OctoPrint REST-API |

Neuer Adapter kann durch Implementierung des Interfaces hinzugefügt werden ohne bestehenden Code zu ändern.

### Druckjob-Anfrage (Team-Seite)
- STL oder 3MF Datei hochladen
- Material angeben (PLA, PETG, ABS, ...)
- Priorität / Dringlichkeit (normal / hoch)
- Freitext-Kommentar (z.B. "bitte 0.2mm Layer Height")
- Status des eigenen Jobs jederzeit einsehbar

### Druckjob-Verwaltung (Admin-Seite)
- Eingehende Anfragen prüfen und freigeben oder ablehnen (mit Begründung)
- Freigegebenen Job einem Drucker zuweisen
- Queue-Ansicht: welche Jobs warten, welche laufen, welche sind fertig
- Priorität eines Jobs manuell anpassen
- Job abbrechen (auf Drucker und in Datenbank)

### Job-Status-Workflow

```
requested → approved → queued → printing → done
         ↘ rejected
                              ↘ failed | cancelled
```

### Echtzeit-Statusanzeige
- Fortschritt in Prozent pro laufendem Job
- Geschätzte verbleibende Zeit
- Druckertemperaturen (Hotend, Bett) wo verfügbar
- Fehlermeldungen vom Drucker werden angezeigt
- WebSocket für Live-Updates im Frontend

### Benachrichtigungen
- E-Mail/Push bei: Job genehmigt, Job abgelehnt, Druck gestartet, Druck fertig, Fehler

### Statistiken
- Druckstunden pro Drucker
- Häufigste Fehlerursachen
- Materialverbrauch

---

## Datenmodell

```
Printer {
  id, name, manufacturer, model, location,
  adapter_type: bambu|prusa|octoprint,
  adapter_config: JSON,   // API-Keys, IP, etc. (verschlüsselt)
  status: online|offline|printing|error,
  active: boolean
}

PrintJob {
  id, team_id, season_id?,
  file_url, file_name, material, priority,
  comment, status,
  printer_id?,
  requested_at, approved_at, started_at, finished_at,
  progress_percent, estimated_remaining_seconds,
  error_message?
}
```

---

## API-Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/print/printers` | Alle Drucker auflisten |
| POST | `/print/printers` | Drucker hinzufügen (Admin) |
| GET | `/print/printers/:id/status` | Echtzeit-Status eines Druckers |
| GET | `/print/jobs` | Jobs auflisten (gefiltert nach Rolle) |
| POST | `/print/jobs` | Druckjob beantragen (Team) |
| PUT | `/print/jobs/:id/approve` | Job genehmigen & Drucker zuweisen (Admin) |
| PUT | `/print/jobs/:id/reject` | Job ablehnen (Admin) |
| PUT | `/print/jobs/:id/cancel` | Job abbrechen |
| GET | `/print/jobs/:id/progress` | Fortschritt abrufen |

---

## Schnittstellen zu anderen Modulen

| Richtung | Modul | Art |
|---|---|---|
| ← | Teamverwaltung | `team_id` für Job-Zuweisung |
| ← | Saisonverwaltung | `season_id` optional |
| ← | Auth | Rolle `print_manager` für Admin-Aktionen |
| → | Frontend | WebSocket für Echtzeit-Druckerstatus |

---

## Offene Fragen
- [ ] Welche Drucker sind konkret im Einsatz? (Modelle, Hersteller)
- [ ] Sollen Drucker-Credentials (API-Keys) in der Datenbank verschlüsselt gespeichert werden oder über Umgebungsvariablen?
- [ ] Soll es eine maximale Dateigröße / Druckzeit pro Team-Anfrage geben?
