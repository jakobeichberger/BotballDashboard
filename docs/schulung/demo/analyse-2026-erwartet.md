# Vorbereitete Analyse: Botball 2026 (Plan B für die Live-Demo)

Diese Datei ist die erwartete Antwort auf Prompt 1 aus [`../demo-gamedoc-2027.md`](../demo-gamedoc-2027.md), wenn man das Game Review 2026 v1.4 als Probe-Gamedoc verwendet. Sie wird aus der geprüften Vorlage `botball_2026` im Code erzeugt (`backend/modules/scoring/sheet_templates.py`), die Zahlen sind also dieselben, die die App rechnet. Die Seitenangaben fehlen hier absichtlich: Die liefert die KI in der Demo, und die Klasse schlägt sie im PDF nach.

Der Bogen hat zwei Seiten (A und B); Gesamtpunkte = Seite A + Seite B.

## Lower Start Box

| Objekt | Punkte je Stück | Maximum |
|---|---:|---:|
| Poms | 2 | 48 |
| Cubes | 5 | 30 |
| Cubes on Pallets | 10 | 30 |
| Drums | 25 | 16 |
| Traffic Cone | 50 | 4 |
| Botguy | 100 | 1 |

- Multiplikator **Drum ×2**: ×2, sobald „lower_start_box_drums“ ≥ 1
- Multiplikator **Botguy ×2**: ×2, sobald „lower_start_box_botguy“ ≥ 1

## Upper Start Box

| Objekt | Punkte je Stück | Maximum |
|---|---:|---:|
| Poms | 2 | 48 |
| Cubes | 5 | 30 |
| Cubes on Pallets | 10 | 30 |
| Drums | 25 | 16 |
| Traffic Cone | 100 | 4 |
| Botguy | 200 | 1 |

- Multiplikator **# of Robots (× n + 2)**: × (n + 2), n ≤ 4

## Warehouse Floor

| Objekt | Punkte je Stück | Maximum |
|---|---:|---:|
| Unsorted Poms | 1 | 48 |
| Sorted Poms | 5 | 48 |
| Cubes | 1 | 30 |
| Cubes on Pallets | 10 | 30 |
| Drums | 25 | 16 |
| Botguy | 50 | 1 |

- Multiplikator **# of Sorted Pom Sections**: × (n), n ≤ 6

## Internal Loading Dock

| Objekt | Punkte je Stück | Maximum |
|---|---:|---:|
| Unsorted Cubes | 10 | 30 |
| Sorted Cubes | 30 | 30 |

- Multiplikator **# of Pallets with Cubes**: × (n), n ≤ 8

## Drum Storage

| Objekt | Punkte je Stück | Maximum |
|---|---:|---:|
| 2" PVC Pipes Unsorted | 100 | 16 |
| 2" PVC Pipes Sorted | 200 | 16 |

- Multiplikator **# of Posts**: × (n), n ≤ 2

## Packaging Bin

| Objekt | Punkte je Stück | Maximum |
|---|---:|---:|
| Non-matched Poms | 10 | 48 |
| Matched Poms | 20 | 48 |
| Botguy | 150 | 1 |

- Multiplikator **Sorted Baskets (× n + 1)**: × (n + 1), n ≤ 4
- Multiplikator **Returned Baskets**: × (n), n ≤ 4

## Upper Warehouse

| Objekt | Punkte je Stück | Maximum |
|---|---:|---:|
| Poms | 2 | 48 |
| Botguy | 200 | 1 |
| Clean Deck | 100 | 1 |

- Multiplikator **# of Robots**: × (n), n ≤ 4

## External Loading Dock

| Objekt | Punkte je Stück | Maximum |
|---|---:|---:|
| Unsorted Cubes | 15 | 30 |
| Sorted Cubes | 45 | 30 |

- Multiplikator **# of Pallets with Cubes (× n + 1)**: × (n + 1), n ≤ 8

## Tie-Breaker (Seeding-Runden, in dieser Reihenfolge)

1. Largest number of sorted cubes on the External Loading Docks
2. Largest number of cubes on pallets
3. Largest number of sorted poms in baskets
4. Largest number of pipes on Drum Storage posts
5. Largest number of traffic cones scoring in start boxes
6. Tallest stack of scored cubes
7. Most Warehouse Floor Areas with both pom colors
8. Botguy in Upper Start Box
9. Botguy in Lower Start Box
10. Most different object types in Warehouse Floor Areas
11. Fewest game pieces on black tape
12. Robot closest to Botguy (cm) – only after one replay (nur nach Wiederholung)

Im Finale gibt es keine Tie-Breaker: Die Runde wird wiederholt, bis ein Team mehr Punkte hat.

## Offizielle Scoring-Beispiele zum Prüfen

Aus `docs/assets/2026-Botball-Scoring-Examples.pdf`, im Projekt als automatische Tests hinterlegt (`frontend/src/modules/scoring/sheet/__fixtures__/score-sheet-cases.json`).

| Beispiel | Eingabe (Seite A) | Erwartet |
|---|---|---:|
| Basic: 2 small yellow crates onto a pallet on the Interior Dock | `internal_dock_sorted_cubes` = 2, `internal_dock_pallets` = 1 | 60 |
| Basic: packaging material pushed into a Warehouse Floor area (sorted) | `floor_sorted_poms` = 6, `floor_sorted_pom_sections` = 1 | 30 |
| Intermediate: packaging material into multiple Warehouse Floor areas | `floor_sorted_poms` = 12, `floor_unsorted_poms` = 3, `floor_sorted_pom_sections` = 2 | 126 |
| Intermediate: packing material into packing material bins, unsorted | `bin_non_matched_poms` = 4 | 40 |
| Intermediate: packing material bins moved into the Packaging Center | `bin_matched_poms` = 4, `bin_non_matched_poms` = 3, `bin_sorted_baskets` = 1, `bin_returned_baskets` = 2 | 440 |
| Intermediate: stacking unsorted crates on the warehouse floor | `floor_cubes` = 3 | 3 |
| Intermediate: Botguy moved to the lower starting box | `lower_start_box_botguy` = 1 | 200 |
| Intermediate: Botguy moved to the upper starting box | `upper_start_box_botguy` = 1, `upper_start_box_robots` = 1 | 600 |
| Intermediate/Advanced: delivered Drums retrieved onto your side | `lower_start_box_drums` = 2, `floor_drums` = 1 | 125 |
| Advanced: Drums onto the Drum Storage uprights | `drum_pipes_unsorted` = 3, `drum_posts` = 1 | 300 |
| Advanced/Expert: 8 Drums sorted onto the Drum Storage uprights | `drum_pipes_sorted` = 8, `drum_posts` = 2 | 3200 |
| Intermediate: cube and pallet from the upper warehouse onto a loading dock | `external_dock_unsorted_cubes` = 1, `external_dock_pallets` = 1 | 30 |
| Advanced/Expert: sorted stacks on pallets in the interior and exterior docks | `internal_dock_sorted_cubes` = 3, `internal_dock_pallets` = 1, `external_dock_sorted_cubes` = 4, `external_dock_pallets` = 2 | 630 |

Alle Werte in dieser Tabelle wurden beim Erzeugen der Datei mit dem Rechenkern der App nachgerechnet.
