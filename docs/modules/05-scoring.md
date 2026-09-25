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

### GCER-Qualifikation

- **1–2 Teams** qualifizieren sich typischerweise von der ECER für die GCER
- Qualifikation erfolgt **manuell durch den Admin** (kein automatischer Schwellenwert)
- Admin wählt qualifizierte Teams aus und gibt sie für GCER-Phasen frei
- System zeigt welche Teams noch nicht für GCER freigeschaltet sind

### Alliance-Matches

- Alliance-Matches finden **nicht immer** statt — abhängig vom jeweiligen Turnier
- Admin kann Alliance-Matches pro Tournament-Phase aktivieren oder deaktivieren
- Einstellung in der Turnier-Konfiguration (Settings-Seite)

### Prep-Phase Sichtbarkeit

- Scores aus der Vorbereitungsphase sind **auch für Teams selbst sichtbar**
- Teams sehen ihre eigenen Scores und die Entwicklung über Testläufe
- Andere Teams' Prep-Scores bleiben unsichtbar (kein gegenseitiger Vergleich in der Prep-Phase)
- Admins und Mentoren sehen alle Teams

### Scoring-Einstellungen (Settings-Seite pro Saison & Phase)

Jede Kombination aus **Saison × Wettbewerbs-Stufe** (ECER / GCER) hat eine eigene Settings-Seite:

**Scoring-Schema:**
- Felder: Name, Multiplikator, Maximalwert, Typ (Anzahl / Boolean)
- Schema per YAML/JSON oder grafischem Editor definieren
- GCER-Schema ist typischerweise eine leicht abgeänderte Version des ECER-Schemas → **"Von ECER klonen"**-Button erzeugt Kopie die unabhängig bearbeitet werden kann
- Beispiel-Schemas 2024/2025/2026 werden als Vorlage mitgeliefert

**Formel-Einstellungen:**
- Welche Formel gilt? (Botball Standard / ECER-Amendments / ECER Open)
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
| 2024 | `DocScore = 3/10·P1 + 3/10·P2 + 1/10·P3 + 3/10·Onsite` |
| 2025/2026 | `DocScore = 2/10·P1 + 2/10·P2 + 2/10·P3 + 4/10·Onsite` (Formel-Vorlage `regional_2026_botball`) |
| GCER 2026 | `DocScore = Onsite` – „Documentation scores at GCER will only include the Onsite Documentation score“ (Vorlage `gcer_2026_botball`) |

**Documentation Score – ECER-spezifisch (kein Onsite):**

| Saison | Formel |
|---|---|
| 2024 ECER | `DocScore = 3/10·P1 + 3/10·P2 + 1/10·P3` (Summe = 0.7) |
| 2025 ECER | `DocScore = 1/3·P1 + 1/3·P2 + 1/3·P3` (Summe = 1.0) |
| 2026 ECER | `DocScore = 1/3·(P1/max P1 + P2/max P2 + P3/max P3)` – jede Periode relativ zum besten Team dieser Periode (Vorlage `ecer_2026_botball`) |

Die Amendments 2026 nennen nur `1/3·P1 + 1/3·P2 + 1/3·P3`. Die offiziellen Ergebnisse von ECER 2026 (`docs/assets/Results 2026.xlsx`) rechnen jede Periode aber relativ zum Besten (P1 54/54 = 1, P2 85/85 = 1, P3 94/94 = 1; ProbablyLast: (4/54 + 85/85 + 60/94)/3 = 0,5708). Die Vorlage bildet das nach; `backend/tests/unit/test_formula_ecer_2026.py` rechnet alle 18 Botball-Teams nach, `test_results_export_ecer_2026.py` dasselbe über die API bis zum Export.

**Maximalpunkte der Bewertungsbögen** (Saisonregel `doc_max_points`, Formel-Eingaben `doc_p1_max` … `onsite_max`): 2026 Periode 1 /100, Periode 2 /95, Periode 3 /100, Onsite /100 (48 + 32 + 20). Eingaben über dem Maximum werden abgelehnt; die Game-Review-Formel rechnet mit Prozent des Maximums. Der gespeicherte `doc_score` einer Dokumentationswertung ist der `doc_score` der Formel der Team-Kategorie (ohne solche Formel: 0,2/0,2/0,2/0,4 der Maxima).

**Gesamtscore ECER – nach Team-Typ:**

| Team-Typ | Formel | Bemerkung |
|---|---|---|
| Botball | `DE + Seeding + AdaptedDocScore` | AdaptedDocScore = ½·DocScore + ½·PaperScore |
| ECER Open (in den Amendments bis 2026 „PRIA Open“) | `DE + Seeding + ½·PaperScore` | Kein Botball-DocScore, nur Paper |

> Bei uns: **beide Team-Typen müssen ein Paper einreichen.** Paper-Einreichung ist in unserem System für alle Teams Pflicht, unabhängig vom Team-Typ. Die Score-Berechnung bleibt dennoch typ-spezifisch.

```
AdaptedDocScore  = ½ × DocScore + ½ × PaperScore   (nur Botball-Teams)
Botball Overall  = DE + Seeding + AdaptedDocScore
ECER Open        = DE + Seeding + ½ × PaperScore
```

> Zwei Stellen, an denen Amendments und veröffentlichte Ergebnisse 2026 auseinandergehen, gibt es als eigene Vorlagen; der Veranstalter wählt pro Saison:
>
> - **ECER Open:** `ecer_2026_open` folgt den Amendments (`+ ½ × PaperScore`), `ecer_2026_open_results` rechnet wie die veröffentlichten Ergebnisse `Seeding + DE` ohne Paper (z. B. Tracer: 0,2998 + 0,5 = 0,7998, obwohl Paper = 100) und reproduziert die Open-Rangliste 2026.
> - **Botball-Doku:** `ecer_2026_botball` rechnet jede Periode relativ zum besten Team, wie die veröffentlichten Ergebnisse (alle 18 Teams reproduziert); `ecer_2026_botball_rubric` nimmt die Amendments wörtlich und rechnet mit dem Anteil am Bewertungsmaximum (P1 /100, P2 /95, P3 /100).

**Aerial:** ECER 2025 wertete den Schnitt aller Läufe (Vorlage `aerial_2025`). Das Aerial Junior Rulebook 2026: mindestens fünf Wertungsläufe, „ranked according to the arithmetic mean of their three highest scores“ – Vorlage `aerial_2026` = `avg_best(aerial_runs, 3)`; ECER 2026 flog sechs Läufe. Läufe sind eine Liste (`aerial_results.runs`, Migration `0034`); wie viele gezählt werden, legt die Kategorie fest (`counted_runs`, Formel-Eingabe `aerial_counted_runs`; ohne gespeicherte Formeln zählt die Standardformel so viele beste Läufe, sonst alle).

**Junior Botball Challenge:** ECER 2026 veröffentlicht „Points for Solved Challenges“ und den Rang (Gleichstand teilt). Erfassung pro Team als Punkte oder als Liste gelöster Challenges (`jbc_results`, Seite „JBC-Punkte“); Formel-Eingabe `jbc_points`, Vorlage `jbc_2026`. Die Vorlage `jbc` (nur Seeding) bleibt für Saisons, die JBC über Läufe werten.

**Gesamtscore GCER (0–4):**
```
Overall = SeedScore + DEScore + DoubleSeedScore + OnsiteDocScore
```

*(n = Anzahl Teams im Turnier/Bracket)*

**Umsetzung in der Formel-Engine (verbindliche Regeln aus dem Game Review):**

- `seed_runs` enthält nur Läufe aus Seeding-Phasen (Phase des Matches bzw. seines geplanten Matches;
  frei erfasste Matches ohne Phase zählen als Seeding). DE-, Double-Seeding-, Alliance- und Finalmatches
  zählen nie zum Seed Score.
- Ein disqualifizierter Seeding-Lauf zählt als **0** (er wird nicht weggelassen), Scores unter 0 zählen als 0.
  Der Seed Score ist der Schnitt der zwei besten gespielten Läufe inklusive dieser Nullen.
- `double_seed_runs` kommen aus Double-Seeding-Phasen; `double_seed_total` ist der Schnitt **aller**
  Läufe („No scores will be dropped in Double Seeding“).
- `n` und das Teilnehmerfeld kommen aus dem Event (Event-Anmeldungen plus Teams mit Ergebnissen dort),
  nicht aus der Saison-Anmeldung. Die Kategorie kommt aus der Event-Anmeldung, sonst aus der Saison-Anmeldung.
- Seeding-Ränge werden pro Kategorie vergeben (Botball und Open getrennt); Gleichstand teilt sich einen
  Rang (1, 2, 2, 4). Die Formel-Eingabe `seed_rank` ist genau dieser angezeigte Rang; die Vorlagen 2026
  rechnen damit, so dass Seeding-Tabelle und Gesamtwertung nie auseinanderlaufen.
- Eine **rote Karte** in irgendeinem offiziellen Match des Events disqualifiziert das Team für die
  gesamte Wertung des Events: es erhält keinen Rang (`rank = null`, `disqualified = true`), zählt nicht
  zu `n` und wird in Exporten/öffentlicher Rangliste nicht gelistet.
- Formel-Vorlagen: `ecer_2026_botball`, `ecer_2026_botball_rubric`, `ecer_2026_open`,
  `ecer_2026_open_results`, `ecer_2025_botball` (Standard),
  `ecer_2025_open` (Standard), `regional_2026_botball`, `gcer_2026_botball`, `aerial_2025`,
  `aerial_2026`, `jbc`, `jbc_2026` – im Formel-Editor über „Vorlage laden“ (angeboten werden die
  Vorlagen der Art der Kategorie). Eine Kategorie kann eine Vorlage als Standard setzen, solange die
  Saison keine eigenen Formeln speichert.

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
| Serving Station | Red/Orange/Yellow Pom in Tray | ×5 | # Full Pom Sets in Trays **oder** # Full Trays ×2 |
| Serving Station | One Side in Tray | ×15 | |
| Serving Station | One Entree in Tray | ×15 | |
| Cups | Ice | ×10 | Full Cup ×2 |
| Cups | Wrong Drink Color | ×10 | 2+ Cups in Beverage Station ×2 |
| Cups | Matching Drink Color | ×30 | |
| Beverage Station | Cups | ×5 | 5 Water Bottles ×3 **oder** 6 Water Bottles ×6 |
| Beverage Station | Water Bottles | ×10 | |
| Fry Station | Potato | ×50 | No Fries on Game Surface ×2 |

#### 2026 – Stack Attack (Logistics/Warehouse)

Aus dem offiziellen „2026 Botball Seeding Score Sheet“ (`docs/assets/2026-Botball-Seeding-Score-Sheet.pdf`), Regeln aus Game Review v1.4. Vorlage `botball_2026`, vollständig; Total = Seite A + Seite B.

| Bereich | Felder (Punkte) | Bereichs-Multiplikator |
|---|---|---|
| Lower Start Box | Poms ×2, Cubes ×5, Cubes on Pallets ×10, Drums ×25, Traffic Cone ×50, Botguy ×100 | Drum ×2, Botguy ×2 (automatisch, sobald Drum bzw. Botguy dort zählt; beide zusammen ×4) |
| Upper Start Box | Poms ×2, Cubes ×5, Cubes on Pallets ×10, Drums ×25, Traffic Cone ×100, Botguy ×200 | × (# Robots + 2) |
| Warehouse Floor | Unsorted Poms ×1, Sorted Poms ×5, Cubes ×1, Cubes on Pallets ×10, Drums ×25, Botguy ×50 | × # Sorted Pom Sections |
| Internal Loading Dock | Unsorted Cubes ×10, Sorted Cubes ×30 | × # Pallets with Cubes |
| Drum Storage | 2" PVC Pipes unsorted ×100, sorted ×200 | × # of Posts |
| Packaging Bin | Non-matched Poms ×10, Matched Poms ×20, Botguy ×150 | × (Sorted Baskets + 1) × Returned Baskets |
| Upper Warehouse | Poms ×2, Botguy ×200, Clean Deck ×100 | × # of Robots |
| External Loading Dock | Unsorted Cubes ×15, Sorted Cubes ×45 | × (# Pallets with Cubes + 1) |

Ein leeres Multiplikator-Feld (0) lässt die Zwischensumme unverändert, wie auf allen Botball-Sheets. Die „2026 Botball Scoring Examples“ enthalten nur Aufgaben ohne Punktzahlen; sie sind als durchgerechnete Fälle in der gemeinsamen Fixture (`frontend/src/modules/scoring/sheet/__fixtures__/score-sheet-cases.json`) hinterlegt.

**Wichtige Sonderregeln 2026:**
- Cubes auf Warehouse Floor zählen **nicht** als "sortierte Section" (nur Poms)
- Ein Cube/Pom kann nur in **einem** Bereich gewertet werden (höchster Bereich gewinnt)
- Roboterinterpretation bei Kubenüberlappung: erster Volume den das Stück bricht
- Drum muss physisch durch ADDS automatisch ausgeliefert werden (autonomer Delivery-Mechanismus)
- Stacks: unterster Piece muss Pallet oder Cube sein; nur Cubes können gestapelt werden

> Alle Felder werden als konfigurierbares YAML/JSON-Schema pro Saison im System hinterlegt.

#### Umsetzung: strukturiertes Score-Sheet

Ein Schema ist entweder eine flache Feldliste (Σ Wert × Multiplikator) oder eine strukturierte `definition` (`backend/modules/scoring/sheet.py`, gespiegelt in `frontend/src/modules/scoring/sheet/calculator.ts`, beide gegen dieselben Fixtures getestet):

- **Bereiche** mit Feldern (Anzahl/Boolean, Punkte, Maximalwert) → Zwischensumme.
- **Bereichs-Multiplikatoren** auf die Zwischensumme: Häkchen (× Faktor), Anzahl (× (n · Faktor + Offset), z. B. „Robots back ×n+1“), **Entweder-oder** (die bessere Alternative zählt), **abgeleitet** (`source`: das Häkchen folgt einem Feld desselben Bereichs, 2026 „Drum ×2“ – kein eigenes Eingabefeld). Werte unter 1 lassen die Zwischensumme unverändert. Mehrere Multiplikatoren eines Bereichs werden multipliziert.
- **Seiten A/B**: jeder Bereich pro Seite, Total = A + B. Rohwerte heißen dann `A.<feld>` / `B.<feld>`.
- Vorlagen 2024, 2025 und 2026 (vollständig, aus den Score-Sheets) sind im Editor wählbar; „Klonen von“ kopiert das aktive Schema eines anderen Events/einer anderen Stufe als neue Version.

### Tie-Breaker & Sonderregeln (Game Review)

Pro Saison konfigurierbar (`/scoring/seasons/:id/rules`, Vorlagen 2024/2025/2026 aus den Game Reviews):

- **Tie-Breaker-Liste** in Reihenfolge. Jeder Tie-Breaker liest seinen Wert aus dem Score-Sheet (Summe beider Seiten) oder wird vom Juror pro Match eingetragen. Verwendet für Seeding-Gleichstände (Werte der gewerteten besten zwei Läufe), DE-Duelle und gleiche DE-Ränge; die UI zeigt, welcher Tie-Breaker entschieden hat.
  - Seeding: Ränge je Kategorie (Botball/Open getrennt). Standard (wie Game Review und ECER 2026): gleiche Seed-Scores teilen sich den Rang (1, 2, 2, 4). Mit der Saisonregel „Tie-Breaker auch auf Seeding anwenden“ (`seeding_tiebreakers`) trennen die Tie-Breaker gleiche Seed-Scores; trennt keiner, bleibt der geteilte Rang. Eine DQ oder verlorene Runde zählt 0, ihre Tie-Breaker-Werte zählen nicht. Eine geänderte Regel rankt alle Events der Saison neu. `seed_rank` in den Formeln ist immer der angezeigte Rang.
  - 2026 (Game Review v1.4): Die Vorlage liest die Werte aus den Feldern des Score-Sheets 2026 (sortierte Cubes auf dem External Dock, Cubes auf Pallets = „Cubes on Pallets“ der Bereiche plus sortierte Dock-Cubes, Pipes auf Posts, Traffic Cones in beiden Start Boxes, Botguy in Upper/Lower Start Box). Was das Sheet nicht hergibt (sortierte Poms in Baskets, höchster Stapel, Floor-Bereiche mit beiden Pom-Farben, Objekttypen, Teile auf schwarzem Band, Abstand zu Botguy), trägt der Juror ein.
  - Duelle (DE, Finale): Sobald beide Scores eines geplanten Matches erfasst sind, wird das Ergebnis über `record_match_result` eingetragen – Bracket-Fortschritt, Korrektur und DE-Ränge (`de_results`) laufen damit über dieselbe Stelle wie das manuelle Ergebnis. Ein unentschiedenes Duell bleibt offen („replay“).
  - DE-Platzierung: Teams, die in derselben Runde ausscheiden, teilen sich den Bracket-Rang (`rank`). `placement`/`decided_by` ordnen sie nach Tie-Breakern (Werte aus den Läufen der Eliminationsphase), zuletzt nach Seeding-Rang. Bracket-Ansicht und `/scoring/events/:id/de-placement` nutzen dieselbe Implementierung (`events.service.tiebroken_placements`).
- **Finale wiederholen** (`finals_replay`, 2026): Im Finale entscheidet kein Tie-Breaker, das Match wird wiederholt. Der Tie-Breaker „closest to Botguy“ (2026) gilt erst nach einem Replay (`replay_only`, Match-Kennzeichen „Replay“).
- **Kontakt am Spielende**: Berührt ein Roboter absichtlich die gegnerische Seite, erhält der Gegner 25 % des Scores des verursachenden Teams (Prozentsatz konfigurierbar).
- **Runde verloren** (Startbox nie verlassen / Motoren laufen am Ende): Die Runde zählt 0 Punkte, ist aber keine DQ. Im Duell verliert das Team; haben beide Teams die Runde verloren, verliert das Team, das die Startbox nie verlassen hat.
- **Schiedsrichter-Checkliste**: Prüfpunkte, die der Juror vor dem Bestätigen eines Scores abhakt; das Ergebnis wird mit dem Match gespeichert. Vorlage 2026 (`/scoring/referee-checklist-presets`) mit dem Wortlaut der Packaging-Bin-Regel 9 aus Game Review v1.4.
- **Timeout-Karte**: ein 3-Minuten-Timeout pro Team und Turnier (vor Hands-Off oder bei der On-Deck-Inspektion), erfasst auf der Wertungsseite (`/scoring/events/:id/timeouts`); ein zweiter wird abgelehnt.
- **Parts Challenge**: Die Einsprache wird mit dem Match erfasst. Entscheidet der Head Judge für den Challenger, wird das angefochtene Team für die Runde disqualifiziert, sonst der Challenger. Eine eigene Rangliste gibt es dafür nicht, weil die Challenge keine Wertung ist.

### Kategorien, Awards und Ergebnis-Export (2026)

- **Kategorien pro Saison** (`/seasons/:id/categories`, Admin → Saison-Module): Schlüssel, Bezeichnung DE/EN, Art (`botball`, `open`, `aerial`, `jbc`, `custom`), Standard-Formelvorlage, Aerial-Läufe (angezeigt / gewertet) und „Rang je Kurs“. Ohne eigene Liste gelten Botball, ECER Open, Aerial Junior (6 Läufe, beste 3), Aerial Senior (historischer Schlüssel `aerial`) und Junior Botball Challenge. Kategorien mit „Rang je Kurs“ erhalten in der Gesamtwertung zusätzlich `course`/`course_rank` pro DE-Bracket (GCER-Tiers).
- **Awards** (Seite „Awards“ des Events, Modul `modules/awards`): Vorlagen ECER und GCER. Berechnete Awards kommen aus denselben Formelzeilen wie die Gesamtwertung (Gleichstand teilt den Platz, rot gesperrte Teams erhalten keinen); Jury-Awards über Nominierungen und Entscheidung (`awards:admin` oder `scoring:admin`, nominieren auch `scoring:write`). „Best Paper Presentation“ wird aus den Papers mit „auf der Bühne präsentiert“ vorgeschlagen. Veröffentlichte Awards erscheinen auf der öffentlichen Event-Seite; Export als CSV und PDF.
- **Ergebnis-Export im ECER-Format**: `/exports/events/:id/results.xlsx` (Blätter Teams, Botball & Open, Aerial, Alliance, Junior Botball Challenge; Spalten wie in den offiziellen Ergebnissen) und `results.csv?sheet=…`. Der Paper-Rang ist eine gemeinsame Liste über Botball und Open.

### Yellow/Red Card System – Team Misconduct

Eingeführt bei ECER 2024, weitergeführt 2025. Wird vom Head Judge ausgestellt.

| Karte | Auswirkung |
|---|---|
| Gelbe Karte | Verwarnung; Team ist offiziell verwarnt |
| Rote Karte | 2. Verwarnung → sofortige DQ aus dem gesamten Turnier und allen Awards |

**Gründe für Verwarnungen (nicht abschließend):**
- Beleidigung oder Respektlosigkeit gegenüber Teilnehmern, Betreuern, Judges oder anderen Beteiligten
- Weigerung, eine finale Head-Judge-Entscheidung zu akzeptieren
- Manipulation oder böswillige Einmischung in Roboter/Runden anderer Teams oder Turnier-Administrationsgeräte
- Physische Gewalt, willentliche Zerstörung → direktes Rot möglich

> Für das Scoring-Modul relevant: DQ-Status muss im Match-Datensatz speicherbar sein. Admin kann Yellow/Red-Card-Status pro Team setzen und Turnier-DQ auslösen.

### Turnier-Ablauf & Setup-Regeln (ECER-spezifisch)

**Seeding-Runde:**
1. Team bringt Roboter zum Tisch
2. Setup-Phase: max. 2 Minuten → 1. Fehler: Verwarnung, 2. Fehler: DQ
3. Judge prüft Setup → OK / Korrektur nötig
4. Hands-Off → Judge-definierte Zeit (normal 30s–2min)
5. Spiel startet

**Double-Elimination-Runde:**
- Gleicher Ablauf wie Seeding + Parts Challenge möglich
- Gegner kann Parts Challenge stellen → Head Judge entscheidet
  - Challenge korrekt: gegnerisches Team DQ
  - Challenge falsch/irrelevant: Challenger-Team DQ
- Gegner darf Concerns zum Judge äußern während Setup

> Diese Informationen sind für die Schiedsrichter-Ansicht im Scoring-Modul relevant (Ablauf-Checkliste, DQ-Knopf, Card-System).

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
