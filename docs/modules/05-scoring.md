# Modul 05 – Scoring-Modul

**Status:** [ ] Offen  
**Typ:** Plugin  
**Registriert beim Kern via:** `modules/scoring/manifest.json`  
**Kommuniziert mit:** Saisonverwaltung, Teamverwaltung, Dashboard

---

## Beschreibung

Eigenständiges Plugin für die gesamte Turnierbewertung über zwei Phasen: eine interne Vorbereitungsphase mit eigenen Testläufen und die offizielle ECER-Turnierphase. Scoring-Sheets sind jährlich konfigurierbar. Unterstützt OCR-Upload und die Dokumentation von Gegnern im Turnier.

---

## Wettbewerbs-Stufen & Phasen

Das Scoring-Modul unterstützt mehrere Wettbewerbs-Stufen. Teams können sich von einer Stufe für die nächste qualifizieren:

```
ECER (Europameisterschaft)          GCER (Weltmeisterschaft)
┌─────────────────────────┐         ┌─────────────────────────┐
│  Phase 1: Preparations  │         │  Phase 3: Preparations  │
│  (interne Testläufe)    │         │  (interne Testläufe)    │
├─────────────────────────┤  Quali  ├─────────────────────────┤
│  Phase 2: Tournament    │ ──────► │  Phase 4: Tournament    │
│  (offizielles Turnier)  │         │  (offizielles Turnier)  │
└─────────────────────────┘         └─────────────────────────┘
```

- Teams die die ECER gewinnen / sich qualifizieren, werden für die GCER freigeschaltet
- Jede Stufe hat ihre eigene Vorbereitungs- und Turnierphase
- Scores und Dokumentation werden pro Stufe getrennt geführt
- Phasen-Konfiguration ist pro Saison frei definierbar (weitere Stufen z.B. regionale Vorrunden möglich)

### Phase 1 – ECER Preparations (intern)

Interne Testläufe **vor** dem offiziellen ECER-Turnier. Ziel: Feedback an Teams, Leistungsentwicklung dokumentieren.

- Mehrere interne Testläufe pro Team möglich (keine feste Rundenanzahl)
- Alle eigenen Teams nehmen teil
- Scores werden intern dokumentiert, sind nicht öffentlich
- Jeder Testlauf kann mit Notizen kommentiert werden (was lief gut, was nicht)
- Performance-Dashboard zeigt Entwicklung jedes Teams über die Testläufe hinweg
- Zeitstempel pro Lauf → Fortschrittsverlauf über Wochen sichtbar

### Phase 2 – ECER Offizielles Turnier

Dokumentation der Ergebnisse beim offiziellen ECER-Turnier.

**Eigene Teams:**
- Seeding-Runden: Score pro Lauf, Durchschnitt der besten 2
- Double-Elimination: Match-Ergebnisse und Bracket-Position
- Alliance-Matches (falls vorhanden)
- Vollständige Dokumentation mit Audit Trail

**Gegnerteams (Scouting):**
- Andere Teams beim Turnier können dokumentiert werden (`external_team`)
- Beobachtete Seeding-Scores eintragen (soweit öffentlich/beobachtbar)
- Match-Ergebnisse gegen uns dokumentieren
- Ziel: Einschätzung der eigenen Turnierposition, Vorbereitung auf Double-Elimination-Gegner

**Qualifikation für GCER:**
- Admin markiert welche Teams sich für die GCER qualifiziert haben
- Qualifizierte Teams werden automatisch für Phase 3 freigeschaltet

### Phase 3 – GCER Preparations (intern)

Identisch zu Phase 1, aber für qualifizierte Teams auf Weltmeisterschafts-Niveau.

- Nur qualifizierte Teams nehmen teil
- Höhere Erwartungen / härtere Gegner → Notizen und Analyse wichtiger
- Vergleich mit ECER-Prep-Performance möglich

### Phase 4 – GCER Offizielles Turnier

Dokumentation der Ergebnisse bei der GCER (Global Conference on Educational Robotics).

- Seeding-Runden, Double-Elimination, Alliance-Matches (wie ECER)
- Gegner-Scouting noch wichtiger: internationales Feld
- Scouting-Daten aus Phase 2 (ECER) können als Referenz herangezogen werden
- Separate Rangliste für GCER

---

## Features

### Performance-Dashboard (Phase 1 & 2)

Das Scoring-Modul liefert ein eigenes internes Dashboard:

- **Teamvergleich:** Alle eigenen Teams im Überblick, sortiert nach aktuellem Durchschnittsscore
- **Verlaufsgraph:** Score-Entwicklung pro Team über alle Testläufe / Runden hinweg
- **Stärken/Schwächen-Analyse:** Aufschlüsselung welche Aufgabensegmente gut/schlecht laufen
- **Ranking-Vorschau:** Hochrechnung der Seeding-Platzierung auf Basis aktueller Scores
- **Gegner-Analyse (Phase 2):** Scouting-Übersicht aller dokumentierten Gegner mit ihren Scores → Einschätzung der eigenen Turnierposition
- **Phase-Vergleich:** Vergleich der Scores aus der Vorbereitungsphase mit den offiziellen Turnierergebnissen

### Wettbewerbs-Stufen & Qualifikation
- Stufen pro Saison konfigurierbar (Standard: ECER + GCER, erweiterbar)
- Qualifikationsschwelle definieren: Wer qualifiziert sich für die nächste Stufe?
- Admin kann Teams manuell qualifizieren oder disqualifizieren
- Qualifizierte Teams werden automatisch in der nächsten Stufe freigeschaltet
- Stufenübergreifende Statistiken: ECER-Prep vs. ECER-Turnier vs. GCER-Prep vs. GCER-Turnier

### Turnier- & Spielplanverwaltung
- Testläufe (Prep-Phasen): flexibel, kein fixer Zeitplan
- Seeding-Runden (Turnierphasen): Anzahl konfigurierbar, Standard: 3
- Double-Elimination-Bracket automatisch generieren
- Alliance-Matches
- Live-Zeitplan: welches Match läuft gerade, welches kommt als nächstes

### Konfigurierbares Scoring-Sheet
- Schema per YAML/JSON oder grafischem Editor definieren
- Felder: Name, Multiplikator, Maximalwert, Typ (Anzahl / Boolean)
- Pro Saison ein eigenes Schema (→ Saisonverwaltung)
- Dasselbe Schema gilt für Phase 1 und Phase 2
- Beispiel-Schemas 2024/2025/2026 werden mitgeliefert

### Score-Erfassung
- Manuelles Webformular
- OCR-Upload (Foto / PDF des handschriftlichen Sheets)
- Plausibilitätsprüfung: Maximalwerte, unrealistische Einträge werden markiert
- Kommentarfeld pro Lauf (z.B. "Roboter ist umgefallen bei Aufgabe 3")
- Audit Trail: wer hat wann welchen Score eingetragen / geändert

### Score-Berechnung (offizielle Formeln)
- **Seeding-Score** = Summe der Punkte auf Side A + Side B
- **Seeding-Durchschnitt** = Durchschnitt der besten 2 von N Seeding-Runs
- **Double-Elimination** = Nur Sieg / Niederlage
- **Gesamtscore** = Seeding + Double-Elimination + Dokumentationspunkte (saisonspezifisch konfigurierbar)

### OCR-Pipeline
- Upload: Foto (JPG/PNG) oder PDF
- Bildvorverarbeitung mit OpenCV (Kontrast, Entzerrung, Rauschen)
- Texterkennung mit Tesseract
- Erkannte Werte werden im Formular vorausgefüllt
- Unsichere Erkennungen farblich markiert → manuelle Korrektur

### Ranglisten & Scoreboard
- Interne Rangliste (Phase 1, nur für Admins/Mentoren sichtbar)
- Live-Rangliste Phase 2 (Seeding-Durchschnitt, sortierbar)
- Live-Bracket-Anzeige Double-Elimination
- Öffentliches Scoreboard via WebSocket (für Großbildschirme)
- Gegner-Rangliste: alle dokumentierten Teams (eigene + externe) im Vergleich

### Export
- Offizielle Ergebnisliste als PDF
- Rohdaten als CSV/Excel
- Team-Auswertung (Entwicklung über beide Phasen) als PDF
- Scouting-Bericht der Gegner als PDF

---

## Datenmodell

```
CompetitionLevel {
  id, season_id,
  name,                          // z.B. "ECER", "GCER"
  order: number,                 // 1 = ECER, 2 = GCER, etc.
  qualifies_from_level_id?: UUID // GCER qualifiziert sich aus ECER
}

Phase {
  id, competition_level_id,
  type: preparation | tournament,
  name, start_date, end_date
}

Tournament {
  id, phase_id,
  type: test_run | seeding | double_elim | alliance,
  name
}

Team {
  // Eigene Teams kommen aus Modul 04 (Teamverwaltung)
  // Externe/Gegner-Teams werden hier erfasst:
}

ExternalTeam {
  id, season_id,
  name, number, school?,
  source: observed | official   // selbst beobachtet oder aus offiziellen Daten
}

Match {
  id, tournament_id,
  round, status: scheduled | running | done,
  team_a_id, team_a_type: internal | external,
  team_b_id?, team_b_type?: internal | external,
  score_a, score_b, winner_id?
}

Score {
  id, match_id, team_id, team_type: internal | external,
  raw_values: JSON,
  calculated_total,
  notes,
  submitted_by, submitted_at,
  ocr_source_file?,
  audit_log: AuditEntry[]
}

ScoringSchema {
  id, season_id, fields: ScoringField[]
}

ScoringField {
  key, label, multiplier, max_value, type: count | boolean
}
```

---

## API-Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/scoring/seasons/:id/schema` | Scoring-Schema abrufen |
| PUT | `/scoring/seasons/:id/schema` | Schema bearbeiten (Admin) |
| GET | `/scoring/seasons/:id/levels` | Wettbewerbs-Stufen einer Saison |
| POST | `/scoring/seasons/:id/levels` | Stufe anlegen (Admin) |
| GET | `/scoring/levels/:id/phases` | Phasen einer Stufe abrufen |
| POST | `/scoring/phases` | Phase anlegen (Admin) |
| POST | `/scoring/levels/:id/qualify` | Teams für nächste Stufe qualifizieren |
| GET | `/scoring/tournaments` | Turniere/Testläufe auflisten |
| POST | `/scoring/tournaments` | Turnier/Testlauf anlegen |
| GET | `/scoring/tournaments/:id/bracket` | Bracket abrufen |
| POST | `/scoring/matches/:id/score` | Score einreichen |
| PUT | `/scoring/matches/:id/score` | Score korrigieren |
| POST | `/scoring/ocr/upload` | OCR-Upload starten |
| GET | `/scoring/seasons/:id/ranking` | Rangliste (eigene Teams) |
| GET | `/scoring/seasons/:id/ranking/full` | Rangliste inkl. Gegner |
| POST | `/scoring/external-teams` | Gegner-Team erfassen |
| GET | `/scoring/seasons/:id/dashboard` | Performance-Dashboard-Daten |
| GET | `/scoring/seasons/:id/export` | Ergebnisse exportieren |

---

## Schnittstellen zu anderen Modulen

| Richtung | Modul | Art |
|---|---|---|
| ← | Saisonverwaltung | `season_id`, Schema und Phasen sind saisonspezifisch |
| ← | Teamverwaltung | `team_id` für eigene Teams |
| → | Dashboard (Modul 08) | Scores, Ranglisten, Phasen-Vergleich, Gegner-Analyse |
| → | Frontend | WebSocket für Live-Rangliste & Scoreboard |
| → | Paper-Review-Modul | Dokumentationspunkte fließen in Gesamtscore ein |
