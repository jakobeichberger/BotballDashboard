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

### Scoring-Einstellungen (Settings-Seite pro Saison & Phase)

Jede Kombination aus **Saison × Wettbewerbs-Stufe** (ECER / GCER) hat eine eigene Settings-Seite:

**Scoring-Schema:**
- Felder: Name, Multiplikator, Maximalwert, Typ (Anzahl / Boolean)
- Schema per YAML/JSON oder grafischem Editor definieren
- GCER-Schema ist typischerweise eine leicht abgeänderte Version des ECER-Schemas → **"Von ECER klonen"**-Button erzeugt Kopie die unabhängig bearbeitet werden kann
- Beispiel-Schemas 2024/2025/2026 werden als Vorlage mitgeliefert

**Formel-Einstellungen:**
- Welche Formel gilt? (Botball Standard / ECER-Amendments / PRIA Open)
- Onsite-Score aktiviert? (Ja bei GCER, Nein bei ECER)
- Gewichtung der Periods (P1/P2/P3/Onsite) konfigurierbar
- Double Seeding aktiviert? (Ja bei GCER, Nein bei ECER)
- Paper-Score integriert? (Ja/Nein, Gewichtung)

**Turnier-Einstellungen:**
- Anzahl Seeding-Runden (Standard: 3)
- Anzahl Teams im Double-Elimination-Bracket
- Alliance-Matches aktiviert?

**Beispiel: GCER 2025 erbt ECER 2025, ändert aber:**
- Onsite-Score: aktiviert (×4 statt ×0)
- Double Seeding: aktiviert
- Schema: leicht abweichende Felder (z.B. andere Multiplikatoren)

### Score-Erfassung
- Manuelles Webformular
- OCR-Upload (Foto / PDF des handschriftlichen Sheets)
- Plausibilitätsprüfung: Maximalwerte, unrealistische Einträge werden markiert
- Kommentarfeld pro Lauf (z.B. "Roboter ist umgefallen bei Aufgabe 3")
- Audit Trail: wer hat wann welchen Score eingetragen / geändert

### Score-Berechnung (offizielle Formeln)

**Roh-Score eines Laufs:**
- `RunScore = Side_A_Points + Side_B_Points`
- Team-Seed-Score = Durchschnitt der besten 2 Runs

**Seeding Score:**
```
SeedScore = (3/4) × (n − SeedRank + 1) / n
          + (1/4) × (TeamAvgSeedScore / MaxTournamentSeedScore)
```

**Double Elimination Score:**
```
DEScore = (n − DERank + 1) / n
```

**Double Seeding Score (nur GCER):**
```
DoubleSeedScore = (2/3) × (n − DoubleSeedRank + 1) / n
               + (1/3) × (TeamAvgDoubleSeedScore / MaxTournamentDoubleSeedScore)
```

**Documentation Score – regulär (Botball global):**

| Saison | Formel |
|---|---|
| 2024 | `DocScore = 3/10·P1 + 3/10·P2 + 3/10·P3 + 1/10·Onsite` |
| 2025/2026 | `DocScore = 2/10·P1 + 2/10·P2 + 2/10·P3 + 4/10·Onsite` |

**Documentation Score – ECER-spezifisch (kein Onsite):**

| Saison | Formel |
|---|---|
| 2024 ECER | `DocScore = 3/10·P1 + 3/10·P2 + 1/10·P3` (Summe = 0.7) |
| 2025 ECER | `DocScore = 1/3·P1 + 1/3·P2 + 1/3·P3` (Summe = 1.0) |

**Gesamtscore ECER – nach Team-Typ:**

| Team-Typ | Formel | Bemerkung |
|---|---|---|
| Botball | `DE + Seeding + AdaptedDocScore` | AdaptedDocScore = ½·DocScore + ½·PaperScore |
| Open (PRIA Open) | `DE + Seeding + ½·PaperScore` | Kein Botball-DocScore, nur Paper |

> Bei uns: **beide Team-Typen müssen ein Paper einreichen.** Paper-Einreichung ist in unserem System für alle Teams Pflicht, unabhängig vom Team-Typ. Die Score-Berechnung bleibt dennoch typ-spezifisch.

```
AdaptedDocScore  = ½ × DocScore + ½ × PaperScore   (nur Botball-Teams)
Botball Overall  = DE + Seeding + AdaptedDocScore
PRIA Open        = DE + Seeding + ½ × PaperScore
```

**Gesamtscore GCER (0–4):**
```
Overall = SeedScore + DEScore + DoubleSeedScore + OnsiteDocScore
```

*(n = Anzahl Teams im Turnier/Bracket)*

---

### Scoring-Sheet-Felder pro Saison

#### 2024 – Moon Base Mission

| Bereich | Feld | Multiplikator | Bereichs-Multiplikator |
|---|---|---|---|
| Area 1–6 | Sorted Poms | ×5 | Botguy/Cube in Zone ×5 |
| Area 1–6 | All Other Game Pieces | ×1 | |
| Small/Large Rover Bay | Sorted Poms | ×5 | Botguy/Cube in Zone ×5 |
| Small/Large Rover Bay | All Other Game Pieces | ×1 | |
| Rock Heap | Only Rocks | ×6 | Botguy/Cube ×5 |
| Rock Heap | All Other Game Pieces | ×1 | |
| Solar Panel | Solar Panel Flipped | ×50 | Robots Back in Start Box ×(+1) |
| Lava Tube | Purple Noodles in Area | ×50 | Deepest Lava Tube depth (1/2/3) |
| Lava Tube | Purple Noodles in Tubes | ×100 | |
| Lava Tube | Lava Tube Cap | ×25 | |
| Moon Base Air Lock | Air Lock Open | ×25 | Air Lock Closed ×3 |
| Moon Base Air Lock | Light Blue Poms | ×15 | |
| Moon Base Air Lock | Dark Blue Poms | ×50 | |
| Habitat Construction | Red/Green Noodles | ×8 | # of Posts with Habitats |
| Astronauts | Astronauts In Stations | ×25 | # Areas with Astronaut |
| Astronauts | Flag Raised | ×25 | |
| Astronauts | Flipped Switch | ×20 | |

#### 2025 – Restaurant/Kitchen Theme

| Bereich | Feld | Multiplikator | Bereichs-Multiplikator |
|---|---|---|---|
| Starting Box/Prep Station | Vegetables | ×5 | Botguy ×2 |
| Starting Box/Prep Station | Botguy | ×15 | |
| Kitchen Floor | Any Game Piece | ×1 | |
| Kitchen Floor | Botguy | ×15 | |
| Condiment Stations | Unsorted Poms | ×1 | # of Sorted Stations |
| Condiment Stations | Sorted Poms | ×5 | |
| Serving Station | Red/Orange/Yellow Pom in Tray | ×5 | # Full Pom Sets in Trays |
| Serving Station | One Side in Tray | ×15 | # Full Trays ×2 |
| Serving Station | One Entree in Tray | ×15 | |
| Beverage Station | Cups | ×5 | Full Cup ×2 |
| Beverage Station | Water Bottles | ×10 | 2+ Cups ×2 |
| Beverage Station | Ice | ×10 | 5 Water Bottles ×3 |
| Beverage Station | Matching Drink Color | ×30 | 6 Water Bottles ×6 |
| Beverage Station | Wrong Drink Color | ×10 | |
| Fry Station | Potato | ×50 | No Fries on Game Surface ×2 |

#### 2026 – Logistics/Warehouse Theme

Scoring-Sheet-Felder aus dem PDF grafisch eingebettet, konnten nicht automatisch extrahiert werden. Manuelle Erfassung aus dem Dokument nötig. Bekannte Elemente aus Regeltext: sortierte Cubes, Poms, Pallets, Loading Docks, Packaging Bins, Drum Storage, Warehouse Floor Areas.

> Alle Felder werden als konfigurierbares YAML/JSON-Schema pro Saison im System hinterlegt.

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
