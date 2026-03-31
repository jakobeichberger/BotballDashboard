# Modul 05 – Scoring-Modul

**Status:** [ ] Offen  
**Typ:** Plugin  
**Registriert beim Kern via:** `modules/scoring/manifest.json`  
**Kommuniziert mit:** Saisonverwaltung, Teamverwaltung, Dashboard

---

## Beschreibung

Eigenständiges Plugin für die gesamte Turnierbewertung. Verwaltet Seeding-Runden, Double-Elimination-Brackets und Alliance-Matches. Scoring-Sheets sind jährlich konfigurierbar ohne Programmieraufwand. Unterstützt OCR-Upload von handschriftlichen Sheets.

---

## Features

### Turnier- & Spielplanverwaltung
- Seeding-Runden anlegen (Anzahl konfigurierbar, Standard: 3)
- Double-Elimination-Bracket automatisch generieren
- Alliance-Matches (Kooperationsläufe zweier Teams)
- Übungszeiten im Zeitplan berücksichtigen
- Live-Zeitplan: welches Match läuft gerade, welches kommt als nächstes

### Konfigurierbares Scoring-Sheet
- Scoring-Sheet-Schema per YAML/JSON oder grafischem Editor definieren
- Felder: Name, Multiplikator, Maximalwert, Typ (Anzahl / Boolean)
- Pro Saison ein eigenes Schema (→ Saisonverwaltung)
- Beispiel-Schema 2024/2025/2026 wird mitgeliefert
- Änderungen am Schema wirken sich nicht auf bereits eingetragene Scores aus

### Score-Erfassung
- Juror gibt Score manuell über Webformular ein
- Oder: Score via OCR-Upload (Foto / PDF des handschriftlichen Sheets)
- Plausibilitätsprüfung: Maximalwerte, unrealistische Einträge werden markiert
- Manuelle Korrektur mit Kommentarfeld (Begründung pflicht bei Korrektur)
- Audit Trail: wer hat wann welchen Score eingetragen / geändert

### Score-Berechnung (offizielle Formeln)
- **Seeding-Score** = Summe der Punkte auf Side A + Side B
- **Seeding-Durchschnitt** = Durchschnitt der besten 2 von N Seeding-Runs
- **Double-Elimination** = Nur Sieg / Niederlage (Punktehöhe irrelevant für Platzierung)
- **Gesamtscore** = Kombination aus Seeding-Punkten, Double-Elimination-Ergebnis und Dokumentationspunkten (Formel aus Regelwerk, saisonspezifisch konfigurierbar)

### OCR-Pipeline
- Upload: Foto (JPG/PNG) oder PDF des ausgefüllten Scoring-Sheets
- Bildvorverarbeitung: Kontrast, Entzerrung, Rauschunterdrückung (OpenCV)
- Texterkennung: Tesseract OCR
- Erkannte Werte werden dem Scoring-Formular vorausgefüllt
- Unsichere Erkennungen (niedrige Konfidenz) werden farblich markiert
- Juror korrigiert markierte Felder manuell bevor er speichert

### Ranglisten & Scoreboard
- Live-Rangliste während der Seeding-Runden (nach Durchschnitt sortiert)
- Live-Bracket-Anzeige während Double-Elimination
- Öffentliches Scoreboard via WebSocket (für Großbildschirme / Publikum)
- Historische Ranglisten vergangener Saisons abrufbar

### Export
- Offizielle Ergebnisliste als PDF
- Rohdaten als CSV/Excel
- Einzelne Team-Auswertung als PDF

---

## Datenmodell

```
Tournament {
  id, season_id, name, type: seeding|double_elim|alliance
}

Match {
  id, tournament_id, round, team_a_id, team_b_id?,
  score_a, score_b, winner_id?, status: scheduled|running|done
}

ScoringSchema {
  id, season_id, fields: ScoringField[]
}

ScoringField {
  key, label, multiplier, max_value, type: count|boolean
}

Score {
  id, match_id, team_id, raw_values: JSON,
  calculated_total, submitted_by, submitted_at,
  ocr_source_file?, audit_log: AuditEntry[]
}
```

---

## API-Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/scoring/seasons/:id/schema` | Scoring-Schema einer Saison |
| PUT | `/scoring/seasons/:id/schema` | Schema bearbeiten (Admin) |
| GET | `/scoring/tournaments` | Turniere auflisten |
| POST | `/scoring/tournaments` | Turnier anlegen |
| GET | `/scoring/tournaments/:id/bracket` | Bracket abrufen |
| POST | `/scoring/matches/:id/score` | Score einreichen |
| PUT | `/scoring/matches/:id/score` | Score korrigieren |
| POST | `/scoring/ocr/upload` | Foto/PDF hochladen, OCR starten |
| GET | `/scoring/seasons/:id/ranking` | Aktuelle Rangliste |
| GET | `/scoring/seasons/:id/export` | Ergebnisse exportieren |

---

## Schnittstellen zu anderen Modulen

| Richtung | Modul | Art |
|---|---|---|
| ← | Saisonverwaltung | `season_id`, Schema ist saisonspezifisch |
| ← | Teamverwaltung | `team_id` für Match-Zuweisung |
| → | Dashboard | Scores, Ranglisten, Statistiken |
| → | Frontend | WebSocket für Live-Rangliste & Scoreboard |
