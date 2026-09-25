# Schulung: Von der Frage zum Auftrag

Eine Unterrichtsstunde (60 Minuten) für das Robotik-Team über das Arbeiten mit KI-Agenten. Beispiel ist dieses Repository: Das BotballDashboard ist fast vollständig durch Aufträge an KI-Agenten entstanden. Die Schülerinnen und Schüler lernen an echten Prompts, was funktioniert hat, wo es gehakt hat und wie man es besser macht. Am Schluss steht eine Live-Vorführung: Ein neues Gamedoc wird mit KI analysiert und direkt in der App hinterlegt.

## Materialien

| Datei | Wofür |
|---|---|
| Foliensatz (Artifact „Von der Frage zum Auftrag“) | 35 Folien mit Sprechernotizen. Die letzten zwei sind ein Anhang. |
| [`demo-gamedoc-2027.md`](demo-gamedoc-2027.md) | Drehbuch der Live-Vorführung mit Prompts zum Kopieren, Klickweg und Plan B |
| [`kurz-demos.md`](kurz-demos.md) | Zwei kurze Vorführungen: vage oder präzise, KI als Code-Reviewer |
| [`spickzettel.md`](spickzettel.md) | LEDVV-Spickzettel und Übung „Prompt-Werkstatt“ zum Ausdrucken |
| [`fallbeispiele.md`](fallbeispiele.md) | Die echten Beispiele aus dem Projekt zum Nachlesen |
| [`demo/botball-2026-sheet.json`](demo/botball-2026-sheet.json) | Fertiger Bewertungsbogen 2026 als JSON (Vorlage und Plan B) |
| [`demo/analyse-2026-erwartet.md`](demo/analyse-2026-erwartet.md) | Erwartete Antwort der Analyse, aus der geprüften Vorlage erzeugt |

## Ablauf (60 Minuten)

| Zeit | Block | Folien | Worum es geht |
|---|---|---|---|
| 0–7′ | Einstieg | Titel bis „Wo es gehakt hat“ | Das Projekt in Zahlen, echte Prompts, vier Stolpersteine |
| 7–20′ | Agentisch prompten | „Chat oder Agent“ bis „KI-Agenten wie ein Team“ | Auftrag statt Frage, LEDVV als Einsatzbefehl, erst lesen, dann ändern |
| 20–30′ | Bessere Ergebnisse | „Sechs Hebel“ bis „Vage gegen präzise“ | Quelle, Beispiel, Belege, Schritte, echte Ergebnisse als Prüfung. Die Kurz-Demo kann bei Zeitnot entfallen. |
| 30–40′ | Effizienter kommunizieren | „Weniger Nachrichten“ bis „Verantwortung“ | Weniger Runden, Entscheidungen in Dateien, Verantwortung bleibt beim Menschen |
| 40–57′ | Live-Vorführung | „Das Gamedoc 2027 ist da“ bis „Plan B“ | Gamedoc analysieren, Bogen erzeugen, in der App hinterlegen, prüfen |
| 57–60′ | Abschluss | Spickzettel, Schluss | Fragen und Diskussion |
| Anhang | – | Reserve-Demo, Übung | Für die nächste Stunde oder wenn Zeit übrig bleibt |

## Die rote Linie: LEDVV

Wer bei der Feuerwehr ist, kennt das Befehlsschema **LEDVV**: Lage – Entschluss – Durchführung – Versorgung – Verbindung. Ein guter Auftrag an einen KI-Agenten hat genau diese Struktur:

| Befehlsschema | Im Einsatz | Im Prompt |
|---|---|---|
| **L**age | Gefahren, eigene Kräfte, Umfeld | Ausgangsstand: Was gibt es schon, welcher Branch, was weiß die KI nicht? |
| **E**ntschluss | Gesamtziel | Ziel in einem Satz und woran man merkt, dass es erreicht ist |
| **D**urchführung | Wer macht was, wie, mit welcher Sicherheit | Aufgaben, Reihenfolge, Grenzen |
| **V**ersorgung | Löschmittel, Geräte, Sanität | Quellen, Dateien, Vorlagen, Zugänge |
| **V**erbindung | Funk, Meldungen, Dokumentation | Rückfragen, Berichtsformat, Entscheidungen festhalten |

Die vier Stolpersteine aus dem Projekt lassen sich jeweils einem fehlenden Buchstaben zuordnen. Die Lage fehlte bei „Testen auf Zeus“, die Versorgung beim falschen Repo-Namen, die Verbindung bei der verlorenen CI-Entscheidung und die gemeinsame Lage bei den parallelen Agenten auf altem Stand. Der Unterschied zum Einsatz: Die KI trägt keine Verantwortung. Die bleibt beim Menschen.

## Vorbereitung (am Vortag)

1. **Die Live-Demo einmal komplett durchspielen**, siehe [Checkliste im Drehbuch](demo-gamedoc-2027.md#vorbereitung-am-vortag).
2. Auf dem Vorführ-Rechner:
   - Die App läuft (lokal mit `make up` oder auf dem Testserver).
   - Ein Admin-Konto ist angemeldet.
   - Ein KI-Tool ist mit Datei-Upload offen, zum Beispiel claude.ai.
3. Diese Dateien bereitlegen:
   - `docs/assets/2026-Botball-Game-Review-v1.4.pdf`
   - `docs/assets/2026-Botball-Seeding-Score-Sheet.pdf`
   - `docs/assets/2026-Botball-Scoring-Examples.pdf`
   - `docs/schulung/demo/botball-2026-sheet.json`
4. Den Spickzettel für alle ausdrucken.
5. Auf der Titelfolie Datum und Namen eintragen.

## Hinweise für die Lehrkraft

- **Keine Zugangsdaten** in Prompts, auf Folien oder im Beamer-Bild. Das Admin-Passwort vor Stundenbeginn eingeben.
- **Prüfen gehört dazu.** Die KI klingt immer überzeugt. In der Demo schlägt die Klasse selbst Werte im PDF nach und rechnet die Scoring-Beispiele in der App nach.
- **Fehler sind gut.** Wenn die KI in der Demo einen Wert falsch hat, zeigt man den Hebel „Nachschärfen“: die Abweichung mit Seitenangabe zurückgeben, nicht von vorn anfangen.
- **Die Übung „Prompt-Werkstatt“** braucht 15 Minuten und passt nicht mehr in die Stunde. Sie eignet sich als Einstieg in die nächste Einheit.
