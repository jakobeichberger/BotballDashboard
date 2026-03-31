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

### Filament-Tracking

Materialverbrauch wird vollständig getrackt:

- **Pro Job:** Verbrauch in Gramm (aus Slicer-Metadaten oder Drucker-API)
- **Pro Drucker:** Gesamtverbrauch und Verbrauch pro Filament-Spule
- **Pro Team:** Gesamtverbrauch in der aktuellen Saison
- **Pro Saison:** Gesamtübersicht aller Teams und Drucker
- Dashboard-Widget: "Wer hat diesen Monat am meisten gedruckt?"

### Team-Limits (Soft & Hard)

Pro Team und Saison konfigurierbare Drucklimits:

| Limit-Typ | Verhalten |
|---|---|
| **Soft Limit** | Warnung an Team und Admin, Drucken weiterhin möglich |
| **Hard Limit** | Job-Einreichung wird blockiert, Admin-Override möglich |

Limit-Dimensionen (jeweils konfigurierbar):
- Max. Druckzeit in Stunden (pro Saison)
- Max. Filamentverbrauch in Gramm (pro Saison)
- Max. Anzahl Jobs (pro Saison)

### Credentials-Verwaltung

- Drucker-API-Keys und Verbindungsparameter werden **verschlüsselt in der Datenbank** gespeichert
- Verschlüsselung via App-Secret-Key (aus `.env`)
- **Installationsanleitung** dokumentiert: wie werden Credentials beim ersten Setup eingegeben, wie bei Updates sicher migriert
- Admin-UI zum Hinzufügen/Ändern von Drucker-Credentials (nie als Plaintext sichtbar nach dem Speichern)

### Drucker-Inventar (aktuell im Einsatz)

Ca. 5 Drucker, verschiedene Hersteller. Adapter sind bereits vorbereitet:

| Adapter | Abgedeckte Geräte |
|---|---|
| `BambuAdapter` | Bambu Lab Drucker (Cloud API + MQTT) |
| `OctoPrintAdapter` | Ender und andere generische Drucker via OctoPrint |
| `PrusaAdapter` | Prusa Drucker via Prusa Connect (für zukünftige Geräte) |

Neue Drucker können jederzeit hinzugefügt werden ohne Code-Änderung (nur Adapter-Config in Admin-UI).

### Statistiken
- Druckstunden pro Drucker
- Häufigste Fehlerursachen
- Filamentverbrauch pro Drucker / Team / Saison (siehe Filament-Tracking)

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
  filament_used_grams?,   // aus Drucker-API oder Slicer-Metadaten
  error_message?
}

TeamSeasonPrintQuota {
  id, team_id, season_id,
  soft_limit_hours, hard_limit_hours,
  soft_limit_grams, hard_limit_grams,
  soft_limit_jobs, hard_limit_jobs,
  used_hours, used_grams, used_jobs
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

## Entschiedene Fragen
- [x] **Drucker-Inventar:** ~5 Drucker (Bambu Lab, Ender/OctoPrint, weitere). Adapter vorbereitet für Bambu, OctoPrint, Prusa.
- [x] **Credentials:** Verschlüsselt in DB gespeichert, Installationsanleitung dokumentiert
- [x] **Limits:** Soft Limits (Warnung) + Hard Limits (Stop) pro Team & Saison, konfigurierbar in Stunden/Gramm/Jobs
- [x] **Filament-Tracking:** Ja – pro Job, Team und Saison
