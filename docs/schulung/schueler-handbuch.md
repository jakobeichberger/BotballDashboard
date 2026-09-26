# Von der Frage zum Auftrag – Handbuch für Schülerinnen und Schüler

So arbeitest du mit KI, damit das Ergebnis stimmt: klare Aufträge nach LEDVV, gezielt bessere Antworten, weniger Hin und Her. Und immer selbst prüfen.

Die interaktive Fassung mit Prompt-Baukasten und Spickzettel zum Abhaken liegt daneben: [`schueler-handbuch.html`](schueler-handbuch.html). Die Datei im Browser öffnen, sie funktioniert auch ohne Internet (dann mit Standardschrift).

## 1. Frage oder Auftrag

Ein **Prompt** ist alles, was du einer KI schreibst. Die KI kennt nur das, was in diesem Text steht, plus ihr allgemeines Wissen. Diese Dinge kennt sie **nicht**:

- euren Roboter und euren Code
- eure Tischvermessung
- die Regeln, die erst diese Saison erschienen sind

Was fehlt, muss sie raten. Dabei klingt sie genauso sicher wie bei Dingen, die sie wirklich weiß.

| Chat | Agent |
|---|---|
| beantwortet **eine Frage** | arbeitet einen **Auftrag** in vielen Schritten ab |
| sieht nur, was du einfügst | liest Dateien, führt Befehle und Tests aus |
| du kopierst, testest, meldest zurück | prüft selbst und berichtet am Ende |

**Merksatz:** Eine Frage bekommt eine Antwort. Ein Auftrag bekommt ein Ergebnis, das du prüfen kannst.

## 2. LEDVV: ein Einsatzbefehl für die KI

Bei der Feuerwehr gibt der Gruppenkommandant keinen Befehl „macht mal“. Er folgt dem Befehlsschema **LEDVV**. Genau so baust du einen guten Auftrag an eine KI.

| | Im Einsatz | Im Prompt |
|---|---|---|
| **L – Lage** | Gefahren, eigene Kräfte, Umfeld | Was ist schon da? Welche Hardware, welcher Code, welche Regeln? Was weiß die KI nicht? |
| **E – Entschluss** | das Gesamtziel | Ziel in einem Satz und **„Fertig, wenn …“**: woran man merkt, dass es erreicht ist |
| **D – Durchführung** | wer macht was, wie, sicher | Aufgaben, Reihenfolge, Grenzen: was nicht verändert werden darf |
| **V – Versorgung** | Löschmittel, Geräte | Quellen, Dateien, Beispiele, Messwerte |
| **V – Verbindung** | Funk, Meldungen, Doku | Wann nachfragen? In welcher Form antworten? Was halten wir fest? |

**Vorher:** „Mach den Roboter schneller.“

**Nachher:**

> **L:** Unser Wombat-Roboter fährt die Strecke Start → Pom-Ecke in 9,5 s. Code in `src/drive.c`.
>
> **E:** Unter 7 s. Fertig, wenn er 5 von 5 Läufen unter 7 s schafft und die Linie nicht verlässt.
>
> **D:** Nur `drive_to_corner()` anpassen, die Motor-Ports bleiben.
>
> **V:** Messprotokoll der letzten 5 Läufe im Anhang.
>
> **V:** Erklär jede Änderung in einem Satz. Bei Unklarheit erst fragen.

## 3. Sechs Hebel für bessere Ergebnisse

1. **Quelle mitgeben.** Gib der KI das echte Game Review als PDF, nicht einfach „die Botball-Regeln“. Ohne Quelle erfindet sie plausible, aber falsche Punktwerte.
2. **Beispiel zeigen.** „Im selben Format wie diese Datei“ trifft besser als jede Beschreibung.
3. **Belege verlangen.** Frag nach Seite, Regelnummer, Datei und Zeile. So merkst du Erfundenes in Sekunden.
4. **In Schritten arbeiten.** Lass dir erst eine Tabelle geben, die du prüfst, und dann den Code.
5. **Gegen Echtes prüfen.** Offizielle Scoring-Beispiele, echte Messwerte und echte Ergebnisse sind die besten Tests.
6. **Nachschärfen.** „Botguy im Bin zählt 150, nicht 100, siehe Seite 12“ ist besser, als alles neu zu verlangen.

**Erst lesen, dann ändern:** Lass die KI zuerst nur analysieren und einen Plan vorschlagen. Einen Plan zu korrigieren kostet einen Satz, falschen Code zu korrigieren eine Stunde.

## 4. Weniger Hin und Her

1. **Alles in eine Nachricht.** Link, Name, Ziel und Grenzen gemeinsam schicken.
2. **Kopieren statt abtippen.** Dateinamen, Links und Fehlermeldungen wörtlich einfügen.
3. **Rückfragen vollständig beantworten.** Die KI fragt, weil sie sonst raten müsste.
4. **Entscheidungen festhalten.** Sag „Ab jetzt gilt …“ und lass es in eine Datei im Projekt schreiben.
5. **Wenn du die Lösung schon kennst, sag sie.** Schreib „Titel: Von der Frage zum Auftrag“ statt „besserer Titel“.

**Drei Nachrichten:**

> „Fix den Fehler.“ → „Welchen?“ → „Der Roboter bleibt stehen.“ → „Wo?“ → „Nach dem Greifer.“

**Eine Nachricht:**

> „Nach `grab_pom()` bleibt der Roboter stehen, ohne Fehlermeldung. Code im Anhang, Zeile 40–75. Vermutung: der Servo erreicht Position 1800 nie. Finde die Ursache, ändere nur diese Funktion.“

## 5. Prüfen statt glauben

KI irrt selbstbewusst. Eine echte Geschichte aus dem Dashboard:

- **Symptom:** Die Paper-Punkte gingen fast gar nicht in die Gesamtwertung ein.
- **Ursache:** Die Formel teilte durch 100, obwohl der Wert schon zwischen 0 und 1 lag.
- **Warum es niemand merkte:** Der zugehörige Test war grün, weil er mit dem Wert 80 rechnete. Diesen Wert speichert die App nie.

Frag bei jedem Ergebnis:

- Kann ich eine Stelle selbst nachprüfen?
- Rechnet der Test mit realistischen Werten?
- Kann ich den Code in eigenen Worten erklären?
- Stimmt die Seitenangabe im PDF wirklich?

**Selbst nachrechnen:** Beim Seeding zählen die besten 2 von 3 Runden, Werte unter 0 zählen als 0. Beispiel mit den Runden 120, −10 und 85:

1. −10 wird zu 0.
2. Die besten zwei Runden sind 120 und 85.
3. Der Schnitt ist **102,5**.

## 6. Spielregeln

- **Keine Geheimnisse im Prompt.** Passwörter, Zugangsdaten und private Daten von Mitschülern gehören in keinen Chat.
- **Verstehen vor Übernehmen.** Was du nicht erklären kannst, gibst du nicht ab. Bei Botball wird die Dokumentation bewertet, und die Jury fragt nach.
- **Die KI trägt keine Verantwortung.** Wie beim Einsatzleiter bleibt sie bei dir und deinem Team.
- **Offen sagen, wo KI geholfen hat.** Das gilt im Team und in der Doku, wenn die Regeln es verlangen. Schaut in die aktuellen Wettbewerbsregeln.

## 7. Übungen

**Übung 1 – Was fehlt?** „Schreib unsere Doku für Period 2.“

**Übung 2 – Rechne nach.**
- a) Zwei sortierte Kisten auf einer Palette im Interior Dock.
- b) Botguy in der Upper Start Box, 1 Roboter.

**Übung 3 – Finde den Fehler.** `return final_score / 100`, obwohl `final_score` zwischen 0 und 1 liegt.

**Übung 4 – Welcher Buchstabe fehlt?** „Testen auf Zeus.“

**Übung 5 – Baue selbst.** Schreib einen Auftrag für euren Greifer nach LEDVV. Teste ihn danach mit einem KI-Tool und prüft die Antwort in der Gruppe.

<details>
<summary>Lösungen</summary>

**Übung 1**
- **Lage:** Welches Team, welcher Roboter, was habt ihr gebaut?
- **Entschluss:** Welcher Teil der Doku? Fertig, wenn alle Punkte des Bewertungsbogens abgedeckt sind.
- **Versorgung:** der offizielle Bewertungsbogen Period 2 und eure Notizen, Fotos und Messwerte.
- **Verbindung:** nur ein Entwurf, mit Markierung, wo Fakten fehlen.

**Übung 2**
- a) 2 × 30 = 60, × 1 Palette = **60**
- b) 200 × (1 + 2) = **600**

Beide Werte stehen in den offiziellen Scoring Examples 2026.

**Übung 3**
- Der Wert wird doppelt umgerechnet: 0,8 wird zu 0,008.
- Ein guter Test rechnet mit 0,8 und erwartet 0,8.

**Übung 4**
- Es fehlt **L – Lage**: Niemand außer uns weiß, was „Zeus“ ist.
- Besser: „Teste auf unserem Testserver Zeus (Zugang über …). Fertig, wenn alle Dienste laufen. Falls du Zeus nicht erreichst, sag es sofort und teste lokal.“

</details>

## 8. Spickzettel

Vor dem Absenden abhaken:

- [ ] Ziel in einem Satz
- [ ] „Fertig, wenn …“ ist messbar
- [ ] Namen, Links, Ausgangsstand kopiert
- [ ] Was nicht angefasst wird
- [ ] Quellen und Beispiele mitgegeben
- [ ] Antwortformat festgelegt
- [ ] Belege verlangt: Datei, Zeile, Seite
- [ ] Plan B, falls etwas nicht geht
- [ ] Keine Passwörter, keine privaten Daten
- [ ] Alles in einer Nachricht

## 9. Glossar

| Begriff | Bedeutung |
|---|---|
| Prompt | Der Text, den du der KI schickst. |
| Agent | Eine KI, die selbstständig mehrere Schritte ausführt: Dateien lesen, Befehle ausführen, prüfen. |
| Kontext | Alles, was die KI in diesem Gespräch sieht. Was nicht drinsteht, kennt sie nicht. |
| Halluzination | Eine erfundene Antwort, die überzeugend klingt. |
| Fertig-Kriterium | Eine prüfbare Bedingung, woran man merkt, dass der Auftrag erledigt ist. |
| Test | Code, der automatisch prüft, ob anderer Code richtig rechnet. |
| LEDVV | Befehlsschema der Feuerwehr: Lage, Entschluss, Durchführung, Versorgung, Verbindung. |
| Seeding | Die Vorrunden bei Botball. Es zählt der Schnitt der besten 2 von 3 Runden. |
| Game Review | Das offizielle Regeldokument einer Botball-Saison. |
