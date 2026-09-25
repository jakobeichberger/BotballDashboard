# Live-Vorführung: Gamedoc 2027 analysieren und in der App hinterlegen

Das Drehbuch für den letzten Block der Schulung (40.–57. Minute). Es ist gleichzeitig die Arbeitsanleitung für den Ernstfall: Wenn im Jänner 2027 die Spielregeln für die ECER 2027 erscheinen, läuft es genau so ab.

- **ECER 2027:** 5.–9. April 2027, Linzer Technikum, Linz
- **Anmeldeschluss Botball:** 15. Dezember 2026
- **Game-Dokumente und Call for Papers:** Jänner 2027 ([ecer.eraa.at](https://ecer.eraa.at))

Bis dahin wird mit dem **Game Review 2026 v1.4** geprobt. Wir tun so, als würde die App die Regeln 2026 noch nicht kennen. Der Ablauf ist derselbe.

## Überblick

| Schritt | Wo | Zeit | Ergebnis |
|---|---|---|---|
| 1. Saison anlegen | App | 2′ | Entwurfssaison „ECER 2027“ mit Terminen und Kategorien |
| 2. Gamedoc analysieren | KI | 4′ | Punkte-Tabelle mit Seitenangaben und offenen Fragen |
| 3. Bewertungsbogen erzeugen | KI | 3′ | JSON im Format der Vorlage und eine Liste der erwarteten Punkte |
| 4. Hinterlegen | App | 3′ | Aktive Schema-Version im Event |
| 5. Prüfen | App + Mensch | 5′ | Offizielle Scoring-Beispiele ergeben die richtigen Punkte |

## Vorbereitung am Vortag

- [ ] Die App läuft auf dem Vorführ-Rechner: lokal `make up` oder der Testserver. Den Login mit einem Admin-Konto testen.
- [ ] Ein Test-Event existiert, in dem das Scoring-Schema geändert werden darf. **Nicht das echte Turnier-Event verwenden!**
- [ ] Das KI-Tool ist offen, zum Beispiel claude.ai mit Datei-Upload. Einen neuen, leeren Chat vorbereiten.
- [ ] Diese Dateien liegen griffbereit:
  - `docs/assets/2026-Botball-Game-Review-v1.4.pdf` (Probe-Gamedoc)
  - `docs/assets/2026-Botball-Seeding-Score-Sheet.pdf`
  - `docs/assets/2026-Botball-Scoring-Examples.pdf`
  - `docs/schulung/demo/botball-2026-sheet.json` (Format-Beispiel und Plan B)
  - `docs/schulung/demo/analyse-2026-erwartet.md` (Plan B für Schritt 2)
- [ ] Die Prompts unten sind in einem Editor zum Kopieren offen.
- [ ] Einmal komplett durchgespielt und die Zeit gestoppt.
- [ ] Beamer-Test: Schriftgröße im Browser auf 125–150 %, keine Passwörter oder privaten Tabs sichtbar.

## Schritt 1 – Saison anlegen (App)

**Klickweg:** Admin-Einstellungen → Saisons → bei der Saison 2026 auf **Klonen** → Name „ECER 2027“, Jahr 2027 → Klonen.

Der Klon übernimmt Kategorien, Formel-Presets und Regeln. Für die ECER 2027 gibt es alternativ ein Skript, das die Saison als Entwurf mit den bekannten Terminen anlegt:

```bash
cd backend
python scripts/example_season_2027.py           # nur anzeigen
python scripts/example_season_2027.py --apply   # Entwurf anlegen
```

Die Saison bleibt ein Entwurf, bis alles geprüft ist. Erzählen, während man klickt: „Das ist die **Lage**: Was haben wir schon, worauf bauen wir auf?“

## Schritt 2 – Gamedoc analysieren (KI)

Game Review und Score Sheet als PDF an den Chat anhängen, dann diesen Prompt einfügen. Er ist bewusst nach **LEDVV** gegliedert.

```text
LAGE
Wir sind ein Botball-Turnierteam. Die Spielregeln für die neue Saison sind erschienen
(angehängt: Game Review und Seeding Score Sheet). Unser Wertungs-System kennt sie noch nicht.

ENTSCHLUSS
Ich brauche eine vollständige, belegte Punkte-Tabelle, aus der wir den Bewertungsbogen bauen.

DURCHFÜHRUNG
1. Erstelle je Spielfeld-Bereich eine Tabelle mit den Spalten:
   Objekt | Punkte je Stück | Maximalanzahl auf dem Tisch | Multiplikator (Art, Faktor, Auslöser) | Seite/Regel
2. Liste die Tie-Breaker für Seeding-Runden in der richtigen Reihenfolge.
3. Beschreibe die Seeding-Regel: Wie viele Runden, welche zählen, was passiert mit negativen Werten?
4. Liste die Änderungen gegenüber der Vorsaison, soweit das Dokument sie nennt.
Erfinde nichts. Verwende kein Wissen aus früheren Jahren, nur die angehängten Dokumente.

VERSORGUNG
Quellen sind ausschließlich die angehängten PDFs.

VERBINDUNG
- Alles, was unklar oder widersprüchlich ist, kommt in eine Liste „Offene Fragen“, mit wörtlichem Zitat und Seite.
- Fertig, wenn jede Tabellenzeile eine Seitenangabe hat.
- Antworte auf Deutsch, Tabellen in Markdown, keine Einleitung.
```

**Während die KI arbeitet:** Die Bausteine an der Folie erklären.

**Danach:** Die Klasse sucht sich drei Zeilen aus, und zwei Freiwillige schlagen sie im PDF nach. Gute Stichproben für 2026:

- Botguy im Packaging Bin: 150 Punkte
- Sortierte Pipes in der Drum Storage: 200 Punkte je Stück, × Anzahl der Posts
- Upper Start Box: × (Anzahl Roboter + 2)

Wenn die Scoring-Beispiele angehängt sind, noch nachschieben:

```text
Rechne die Beispiele aus „Scoring Examples“ mit deiner Tabelle nach und zeige, wo es nicht passt.
```

## Schritt 3 – Bewertungsbogen als JSON (KI)

Im selben Chat bleiben, damit die geprüfte Tabelle als Kontext da ist. Die Datei `docs/schulung/demo/botball-2026-sheet.json` als **Format-Beispiel** anhängen.

```text
Baue aus deiner geprüften Tabelle den Bewertungsbogen für unser System.

Format: exakt wie die angehängte Beispiel-Datei (Bogen der Vorsaison):
- oberste Ebene: "sides" und "sections"
- jede Section: "key", "label", "fields", "multipliers"
- Felder: "key", "label", "type" ("count" oder "boolean"), "multiplier" (Punkte je Stück),
  "min_value": 0, "max_value" (Maximalanzahl), "required": false
- Multiplikatoren wie im Beispiel: Checkbox mit "factor"; Anzahl mit "factor" und "offset"
  (Ergebnis = Zwischensumme × (n × factor + offset)); Multiplikatoren, die automatisch gelten,
  sobald ein Feld ≥ 1 ist, mit "source": "<feld-key>"
- keys nur klein, Ziffern und Unterstrich, innerhalb des Bogens eindeutig

Fertig, wenn:
1. du gültiges JSON ohne Kommentare in einem einzigen Codeblock lieferst und
2. darunter eine Tabelle steht: Scoring-Beispiel | Eingaben (Feld-key = Wert) | erwartete Punkte.

Wenn das JSON zu lang wird, liefere es in zwei Teilen und sag mir, wo ich sie zusammensetze.
```

## Schritt 4 – Hinterlegen (App)

**Klickweg:** Event-Verwaltung → Test-Event wählen → Abschnitt **Versioniertes Scoring-Schema**:

1. Oben auf den Reiter **JSON** wechseln.
2. Den Inhalt komplett ersetzen: das JSON aus Schritt 3 einfügen.
3. Zurück auf **Editor** wechseln. Die App liest das JSON ein und zeigt Probleme sofort an, zum Beispiel doppelte Schlüssel oder unbekannte Auslöser-Felder.
4. Kurz durch die Bereiche scrollen und einen Wert mit der Tabelle vergleichen.
5. **Neue Version aktivieren.**

Darunter, im Regel-Editor der Saison:

- **Tie-Breaker:** Preset wählen oder anpassen, damit es zur Liste aus Schritt 2 passt.
- **Schiri-Checkliste:** Preset wählen und um die neuen Punkte ergänzen.

Dabei erzählen:

- Jede Aktivierung erzeugt eine **neue Version**. Die alte bleibt erhalten, und bereits gewertete Läufe behalten ihren Stand. Man kann also gefahrlos ausprobieren.
- Das ist die **Durchführung**, und die macht die App, nicht die KI. Die KI hat keinen Zugriff auf unser System.

## Schritt 5 – Prüfen (Mensch)

**Klickweg:** Wertung → Punkte eintragen → Modus **Übung**. Übungsläufe zählen nicht zur Rangliste. Die offiziellen Scoring-Beispiele eintragen, jeweils auf Seite A:

| Scoring-Beispiel 2026 | Eingabe | Erwartet |
|---|---|---:|
| 2 sortierte Kisten auf einer Palette im Interior Dock | Internal Dock: Sorted Cubes 2, # of Pallets with Cubes 1 | **60** |
| Botguy in die Upper Start Box, 1 Roboter | Upper Start Box: Botguy 1, # of Robots 1 | **600** |
| Poms in zwei Bereiche des Warehouse Floors | Sorted Poms 12, Unsorted Poms 3, # of Sorted Pom Sections 2 | **126** |
| 8 Drums sortiert auf beide Uprights | Drum Storage: Pipes Sorted 8, # of Posts 2 | **3 200** |

Alle 13 offiziellen Beispiele stehen in [`demo/analyse-2026-erwartet.md`](demo/analyse-2026-erwartet.md). Sie sind im Projekt auch als automatische Tests hinterlegt.

- **Wenn alles stimmt:** Die Übungsläufe können bleiben, sie zählen nicht zur Rangliste. Im Ernstfall danach die Saison aktivieren.
- **Wenn ein Wert abweicht:** Nicht neu anfangen, sondern nachschärfen:

```text
Beispiel „Botguy in die Upper Start Box“ ergibt bei uns 300 statt 600.
Laut Seite <X> ist der Multiplikator × (Roboter + 2). Korrigiere nur diese Section und gib sie neu aus.
```

Abschluss der Demo: „Das ist die **Verbindung**: Wir melden zurück, was nicht passt, und halten fest, was entschieden wurde.“

## Plan B

| Problem | Ausweg |
|---|---|
| Kein Internet oder KI zu langsam | Die vorbereitete Antwort `demo/analyse-2026-erwartet.md` zeigen. Das JSON aus `demo/botball-2026-sheet.json` verwenden. |
| JSON wird von der App abgelehnt | Die Fehlermeldung wörtlich an die KI geben („Die App meldet: …“). Notfalls im Schema-Editor die Vorlage „Botball 2026 – Stack Attack“ wählen und **Laden**. |
| App nicht erreichbar | Lokal mit `make up` starten. Vorher testen! |
| Zeit wird knapp | Schritt 1 überspringen (bestehendes Test-Event) und nur zwei Beispiele prüfen. |
| KI erfindet Werte ohne Seitenangabe | Gutes Lehrbeispiel! Nachfragen: „Auf welcher Seite steht das?“ |

## Im Ernstfall (Jänner 2027): zusätzliche Punkte

Die Demo deckt den Bewertungsbogen ab. Für die echte Saison 2027 sind außerdem zu prüfen und einzutragen:

- [ ] **ECER-Amendments 2027:** Diese Änderungen gehen dem Game Review vor. Dazu gehören Gewichtung von Seeding, Double Elimination und Dokumentation, die Paper-Wertung und die ECER-Open-Regeln. → Punkteformeln, Presets `ecer_2026_*` als Ausgangspunkt
- [ ] **Dokumentation:** Perioden, Maximalpunkte und Normierung → Dokumentations-Wertung
- [ ] **Tie-Breaker** und Regel zur Wiederholung im Finale → Regel-Editor der Saison
- [ ] **Kategorien:**
  - Botball, Open, Aerial, JBC
  - bei Aerial: Anzahl der Läufe und wie viele davon zählen
  - → Admin-Einstellungen, Kategorien der Saison
- [ ] **Termine:** Anmeldeschluss, Dokumentations-Deadlines → Deadlines
- [ ] **Awards:** Vorlage ECER prüfen → Awards
- [ ] **Dauerhaft in den Code übernehmen (für Entwickler):**
  - neue Vorlage `botball_2027` in `backend/modules/scoring/sheet_templates.py`
  - Tie-Breaker-Preset in `backend/modules/scoring/tiebreak.py`
  - die offiziellen Scoring-Beispiele als Testfälle in `frontend/src/modules/scoring/sheet/__fixtures__/score-sheet-cases.json`
  - Auftrag dafür am besten wieder nach LEDVV, mit „Fertig, wenn alle Scoring-Beispiele 2027 als Tests grün sind“
- [ ] **Offene Fragen** aus Schritt 2 mit der Turnierleitung klären und die Antworten im Repo festhalten, damit sie auch der nächste Agent kennt.
