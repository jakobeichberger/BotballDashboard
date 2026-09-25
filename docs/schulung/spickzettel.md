# Spickzettel: Ein Einsatzbefehl für die KI

Zum Ausdrucken und an den Arbeitsplatz hängen.

## LEDVV – der Auftrag in fünf Teilen

| | Frage | Beispiel |
|---|---|---|
| **L – Lage** | Was ist schon da? Was weiß die KI nicht? | „Unser Roboter fährt mit `drive(80)` 30 cm zu weit. Code im Ordner `src/`.“ |
| **E – Entschluss** | Was soll am Ende da sein, und woran merke ich das? | „Der Roboter hält an der schwarzen Linie. Fertig, wenn er 5 von 5 Mal hält.“ |
| **D – Durchführung** | Was genau, in welcher Reihenfolge, was nicht? | „Nur `drive_to_line()` ändern, die Motor-Ports bleiben.“ |
| **V – Versorgung** | Welche Quellen, Dateien, Beispiele bekommt die KI? | „Sensorwerte im Anhang, Game Review Seite 12.“ |
| **V – Verbindung** | Wann soll sie fragen, wie berichten? | „Wenn unklar: erst fragen. Antwort: geänderter Code plus drei Sätze Erklärung.“ |

## Checkliste vor dem Absenden

- [ ] Ziel in einem Satz
- [ ] Namen, Links und Ausgangsstand: kopieren statt abtippen
- [ ] Was nicht angefasst wird
- [ ] „Fertig, wenn …“, prüfbar
- [ ] Antwortformat festgelegt
- [ ] Plan B, falls etwas nicht geht
- [ ] Belege verlangen: Datei, Zeile, Seite
- [ ] Keine Passwörter, keine privaten Daten
- [ ] Alles in **einer** Nachricht

## Nach der Antwort

- [ ] Stimmt das? Mindestens eine Stelle selbst nachprüfen.
- [ ] Kann ich den Code erklären? Wenn nicht: erklären lassen.
- [ ] Prüft der Test die Wirklichkeit, mit realistischen Werten?
- [ ] Entscheidungen, die weiter gelten, in eine Datei im Projekt schreiben.
- [ ] Wenn etwas falsch ist: die Abweichung genau benennen, statt neu anzufangen.

## Übung „Prompt-Werkstatt“ (15 Minuten, in Gruppen)

Drei Prompts aus dem Alltag eines Botball-Teams:

1. „Mach den Roboter schneller.“
2. „Fix den Fehler im Code.“
3. „Schreib unsere Doku für Period 2.“

**Aufgabe:**

1. Wählt einen Prompt und schreibt ihn als Einsatzbefehl nach LEDVV um.
2. Tauscht mit einer anderen Gruppe: Was fehlt noch? Was müsste die KI erraten?
3. Testet beide Fassungen mit einem KI-Tool und vergleicht die Antworten.

**Tipps:**

- „Schneller“: Was heißt schneller? Fahrzeit, Reaktionszeit, weniger verlorene Punkte? Welche Hardware, welcher Code?
- „Fix den Fehler“: Welcher Fehler? Woran merkt man ihn? Welche Datei? Was wurde schon versucht?
- „Doku für Period 2“: Die Bewertungsbögen für Period 2 liegen offiziell vor, zum Beispiel `docs/assets/2026-Botball-Period-2-Documentation.pdf`. Die gehören als Versorgung dazu.
