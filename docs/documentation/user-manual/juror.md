# Juror-Handbuch

Für Schiedsrichter und Jury am Spieltisch. Die Rolle `juror` hat folgende Rechte:

- `scoring:read`, `scoring:write`, `scoring:admin`: Wertungen erfassen, bestätigen und korrigieren; DE, Aerial und Doku; Statistik;
- `events:read`, `events:write`: Event-Verwaltung und Zeitplan bearbeiten;
- `teams:read`, `seasons:read`, `dashboard:read`.

Zeitplan erzeugen, Setzliste und Formeln sind der Organisation vorbehalten.

---

## Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Wertung am Spieltisch](#wertung-am-spieltisch)
3. [Sonderregeln, Tie-Breaker, Duelle](#sonderregeln-tie-breaker-duelle)
4. [Bestätigen und korrigieren](#bestätigen-und-korrigieren)
5. [Karten und Disqualifikation](#karten-und-disqualifikation)
6. [Score-Sheet-Fotos (OCR)](#score-sheet-fotos-ocr)
7. [Brackets und Ergebnisse](#brackets-und-ergebnisse)
8. [DE, Aerial, Dokumentation](#de-aerial-dokumentation)
9. [Rangliste und Seeding-Regeln](#rangliste-und-seeding-regeln)
10. [Statistik und auffällige Läufe](#statistik-und-auffällige-läufe)
11. [Offline-Betrieb](#offline-betrieb)

---

## Überblick

| Seite | Wofür |
|---|---|
| **Dashboard** | Juror-Warteschlange: unbestätigte und von Mentoren erfasste Scores, nächste Matches, offene OCR-Scans |
| **Wertung** (`/events/…/scoring`) | Mobile Erfassung entlang des Zeitplans |
| **Zeitplan** | Matches, Tische, Zeiten, Bracket mit Sieger-Buttons |
| **OCR-Prüfung** | Fotos von Score-Sheets hochladen und prüfen |
| **Rangliste & Ergebnisse** | Seeding, DE, Aerial, Gesamtwertung, Exporte; Link „Wertung erfassen" |
| **Punkte eintragen** (`/events/…/scoring/entry`) | Liste der erfassten Wertungen mit **Bestätigen**, **Bearbeiten**, **Löschen** |
| **Statistik & Anomalien** | Verteilungen und auffällige Läufe |

---

## Wertung am Spieltisch

**Wertung** öffnen (`/events/…/scoring`). Die Seite ist fürs Handy gebaut:

1. **Match wählen:** Die Seite geht die geplanten Matches in Spielreihenfolge durch. Weiter geht es mit „Vorheriges/Nächstes Match" oder durch Wischen. Das Team ist vorausgewählt. Wertungen ohne geplantes Match („Ohne Zuordnung") sind ebenfalls möglich.
2. **Score-Sheet ausfüllen:** Das Sheet ist nach Bereichen gegliedert wie das Papier-Sheet, mit Zählern, Zahlen und Ja/Nein-Feldern. Entweder-oder-Felder schließen sich gegenseitig aus. Seite A und B werden getrennt erfasst. Maximalwerte werden geprüft. Die berechnete Gesamtwertung mit Aufschlüsselung je Bereich ist immer sichtbar.
3. **Sonderbedingungen** setzen, falls zutreffend (siehe unten).
4. **„Prüfen & absenden":** Eine Zusammenfassung zeigt jedes Feld, seine Punkte und die Summe. Danach **Offiziell speichern**.

Die Summe berechnet der Server aus dem aktiven Schema. Es zählt also nicht, was das Gerät anzeigt, sondern das Schema. Wer nur `scoring:read` hat, sieht die Seite schreibgeschützt.

---

## Sonderregeln, Tie-Breaker, Duelle

Welche Regeln gelten, legt die Organisation pro Saison fest. Voreinstellungen stammen aus den Game Reviews 2024–2026.

- **Runde verloren (0 Punkte, keine DQ).** Gründe: Startbox nie verlassen, Motoren/Servos am Ende nicht gestoppt, anderer Grund.
- **Absichtlicher Kontakt mit der gegnerischen Seite am Spielende:** Der Gegner erhält den eingestellten Bonus, Standard +25 % seines Scores.
- **Tie-Breaker-Angaben:** nur nötig, wenn ein Tie-Breaker-Wert nicht aus dem Score-Sheet kommt, z. B. ein gemessener Abstand.
- **Replay:** markiert ein wiederholtes Match.
- **Ergebnis des Duells** (Double Seeding, DE, Alliance): Sobald beide Seiten erfasst sind, zeigt die Seite den Sieger und was entschieden hat: höhere Punktzahl, Tie-Breaker, Disqualifikation oder verlorene Runde. Entscheidet kein Tie-Breaker, heißt es „Wiederholung nötig". Im Finale wird statt Tie-Breaker wiederholt, wenn die Saison das so einstellt.

---

## Bestätigen und korrigieren

**Punkte eintragen** (`/events/…/scoring/entry`) listet die erfassten Wertungen.

- **Bestätigen:** Hat die Saison eine **Schiedsrichter-Checkliste**, öffnet sich der Dialog „Schiedsrichter-Checkliste". Pflichtpunkte müssen abgehakt sein, bevor „Score bestätigen" geht. Die Haken werden mit der Wertung gespeichert.
- **Bearbeiten:** Werte ändern und speichern. Jede Änderung erzeugt eine **Revision** mit altem und neuem Wert, Zeit und Person. Teams mit Push bekommen „Score korrigiert".
- **Löschen:** Die Wertung verschwindet, ihre Revisionen bleiben erhalten (Audit-Trail je Event).

Von Mentoren selbst erfasste Wertungen erscheinen im Dashboard in der Juror-Warteschlange und sollten bestätigt werden.

---

## Karten und Disqualifikation

Gelbe und rote Karte sowie „disqualifiziert" sind Felder jeder Wertung. Ihre Wirkung:

- Eine disqualifizierte Runde zählt im Seeding als 0.
- Eine **rote Karte** irgendwo im Event disqualifiziert das Team: kein Rang, Anzeige „DQ", raus aus dem Formel-Feld.

> Diese drei Felder haben in der Oberfläche derzeit keinen Schalter. Die Organisation setzt sie über die API (`PATCH /api/scoring/matches/{id}` mit `yellow_card`, `red_card`, `is_disqualified`). Siehe [todo.md](../../todo.md).

---

## Score-Sheet-Fotos (OCR)

**OCR-Prüfung** (`/events/…/scans`):

1. **Vorlage** (Score-Sheet der Saison) und **Team** wählen. Das Team wird nach Seed, Name und Nummer angezeigt.
2. **Foto aufnehmen** (öffnet am Handy die Kamera) oder Datei wählen, dann **Hochladen**.
3. Der Server liest die Felder im Hintergrund lokal aus. Es werden keine Bilder an externe Dienste geschickt. Der Scan wechselt auf **Review erforderlich**.
4. Erkannte Werte mit den Bildausschnitten vergleichen, korrigieren und mit **Geprüft übernehmen** als Wertung speichern.

Unsichere Werte sind gelb markiert, mit Konfidenz und Grund. Schlägt die Erkennung ganz fehl, lässt sie sich derzeit nur über die API erneut anstoßen (`POST …/score-sheet-scans/{id}/retry`).

---

## Brackets und Ergebnisse

**Zeitplan** (`/events/…/schedule`):

- Mit `events:write` Zeiten, Tische und Status einzelner Matches ändern. Die betroffenen Teams bekommen einen Push.
- **Bracket:** Winner-Bracket, Loser-Bracket (Minor/Major), Grand Final, Reset-Finale, falls nötig, und Platzierungen. Mit `scoring:admin` trägst du per Button „*Team* gewinnt *Match*" den Sieger ein. Sieger und Verlierer rücken automatisch in ihre nächsten Matches. Korrekturen werden nachgezogen.

Zeitplan erzeugen und die Setzliste aus dem Seeding übernehmen braucht `events:admin`, liegt also bei der Organisation.

---

## DE, Aerial, Dokumentation

Diese Seiten gibt es nur, wenn das Modul im Event aktiv ist. Mit `scoring:admin` öffnest du sie direkt:

- `/events/…/scoring/de`: DE-Rang und Bracket-Score (0–1) je Team; Platzierung mit Tie-Breakern aus dem Bracket.
- `/events/…/scoring/aerial`: bis zu vier Aerial-Läufe; gewertet wird der Ø aller Läufe.
- `/events/…/scoring/doc`: Doku-Teile 1–3 und Onsite (0–1), dazu die Paper-Ergebnisse. Angezeigt werden der Doku-Score und der Wert aus dem Formel-Set.

Admins sehen dafür Buttons auf **Rangliste & Ergebnisse**. Jede Änderung wird als Ergebnis-Revision protokolliert.

---

## Rangliste und Seeding-Regeln

**Rangliste & Ergebnisse** zeigt Seeding, Double Elimination, Aerial und die Gesamtwertung, je nach aktiven Modulen. Für das Seeding gilt:

- Nur Läufe aus **Seeding-Phasen** zählen. DE-, Alliance- und Finalmatches zählen nicht, Übungsläufe nie.
- Eine disqualifizierte Runde zählt 0, negative Scores zählen 0.
- Ränge gelten **je Kategorie**, Gleichstände teilen sich den Platz (1, 2, 2, 4). Die Reihenfolge innerhalb eines Gleichstands entscheiden die Tie-Breaker der Saison. Die Tabelle zeigt, welcher Tie-Breaker entschieden hat.
- Die Seeding-Rangliste nutzt den **Ø der zwei besten Seeding-Läufe**. Eine verlorene Runde zählt wie eine disqualifizierte als 0 und als gespielter Lauf.
- Für die Gesamtwertung rechnet das Formel-Set der Saison den Seeding-Wert. Im Standard-Set ECER 2025 ist das `3/4 · (n − Rang + 1)/n + 1/4 · Seed-Schnitt / bester Lauf im Feld`.

Die Gesamtwertung rechnet die Formel-Engine aus Seeding, DE, Doku, Paper und Aerial, wie in den Punkteformeln hinterlegt.

---

## Statistik und auffällige Läufe

**Statistik & Anomalien** (`/events/…/statistics`):

- Boxplots je Runde und je Aufgabe;
- Heatmap Team × Aufgabe;
- Trends je Team.

Unter **Auffällige Läufe** stehen Läufe, die man prüfen sollte:

- unmögliche oder ungültige Werte;
- Summe passt nicht;
- Ausreißer gegenüber dem eigenen Team oder dem Feld;
- Sprünge;
- unbestätigt.

Ein Klick zeigt Rohwerte und Revisionen und erlaubt das Bestätigen. „Läufe CSV" exportiert alle Wertungen des Events.

---

## Offline-Betrieb

Fällt am Spieltisch das Netz aus:

- Wertungen weiter erfassen. Sie werden auf dem Gerät gespeichert („Offline gespeichert – wird synchronisiert, sobald eine Verbindung besteht").
- Die Kopfzeile zeigt, wie viele Wertungen warten. Übertragen wird automatisch beim Wiederverbinden, beim App-Start und jede Minute. Jede Wertung hat einen eindeutigen Schlüssel, Duplikate entstehen also nicht.
- **Konflikt** heißt: Das Team bzw. Match wurde inzwischen schon gewertet. Dann den Eintrag prüfen und **erneut senden**, **trotzdem speichern** oder **verwerfen**.
- Bestätigen, Korrigieren und alle anderen Änderungen gehen erst wieder mit Verbindung.

Wichtig: Gespeicherte Wertungen überträgt nur die Person, die sie erfasst hat, und nur auf diesem Gerät. Vor dem Abmelden also synchronisieren lassen.
