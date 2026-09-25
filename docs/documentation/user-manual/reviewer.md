# Reviewer-Handbuch

Für die Begutachtung der Team-Papers. Die Rolle `reviewer` hat folgende Rechte:

- `papers:read`, `papers:review`;
- `teams:read`, `seasons:read`, `events:read`, `dashboard:read`.

Den Paper-Bereich gibt es nur, wenn das Modul **Paper** im Event aktiv ist.

---

## Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Ablauf eines Reviews](#ablauf-eines-reviews)
3. [Bewertungskriterien](#bewertungskriterien)
4. [Abgeben, sperren, wieder öffnen](#abgeben-sperren-wieder-öffnen)
5. [Revisionen und Versionen](#revisionen-und-versionen)
6. [Fristen und Erinnerungen](#fristen-und-erinnerungen)
7. [Was Teams sehen](#was-teams-sehen)

---

## Überblick

- **Dashboard:** Die **Review-Warteschlange** zeigt die dir zugewiesenen Papers, die auf dich warten. Dazu gehören überarbeitete (`resubmitted`) Papers. Papers, die gerade beim Team zur Überarbeitung liegen, stehen nicht darin.
- **Paper-Review** (`/events/…/papers`): alle Papers der Saison mit Status und Deadline-Hinweis.
- **Paper-Detailseite:** Abstract, aktuelle Version zum Herunterladen, Versionen samt Text-Vergleich, Deadline, dein Review-Formular.

Reviewen darfst du nur Papers, denen dich die Organisation zugewiesen hat. Die Organisation weist keine Reviewer aus dem eigenen Team oder von derselben Schule zu. Reviews sind nicht anonym gegenüber der Organisation. Teams sehen ihr Feedback aber ohne Namen der Reviewer.

---

## Ablauf eines Reviews

1. Paper in der Warteschlange oder Liste öffnen.
2. **Aktuelle Version** herunterladen (PDF). Frühere Versionen und ein **Text-Diff** zwischen zwei Versionen findest du unter „Versionen".
3. Im Formular die fünf Kriterien bewerten und kommentieren (siehe unten).
4. Einen **Gesamtkommentar** und, falls nötig, **Revisionshinweise** schreiben („Was konkret geändert werden soll…").
5. Eine **Empfehlung** wählen: annehmen, ablehnen, kleine Überarbeitung oder große Überarbeitung.
6. Optional **private Notizen**. Diese sieht nur die Organisation, nie das Team.
7. **Speichern** hält den Entwurf. **Einreichen** gibt das Review verbindlich ab.

Sobald die erste Person mit dem Review beginnt, wechselt das Paper auf `under_review`.

---

## Bewertungskriterien

Jedes Kriterium wird mit 0–10 bewertet und hat ein eigenes Kommentarfeld:

| Kriterium | Feld |
|---|---|
| Inhalt | `score_content` |
| Umsetzung | `score_implementation` |
| Ergebnisse | `score_results` |
| Sprache | `score_language` |
| Format | `score_format` |

Die Review-Summe ist der Mittelwert der vergebenen Kriterien. Beim **Finalisieren** verdichtet die Organisation alle abgegebenen Reviews der Runde zum Endergebnis (0–1). Ein **Formalabzug**, z. B. für eine Seite zu viel, wird dabei abgezogen. Das Endergebnis fließt in die Doku- bzw. Gesamtwertung ein, wenn die Saison das vorsieht.

Beim Verdacht auf KI-Missbrauch meldest du das in den privaten Notizen. Den Status `disqualified_ai` (Score 0, keine Revision) setzt nur die Organisation.

---

## Abgeben, sperren, wieder öffnen

- Nach **Einreichen** ist dein Review gesperrt („Bewertung verbindlich abgeben? Danach ist sie gesperrt.").
- Änderungen danach gehen nur, wenn die Organisation das Review **wieder öffnet**.
- Nach dem Finalisieren eines Papers lassen sich keine Reviews mehr ändern.
- Steht ein Paper nicht in einem begutachtbaren Status, zeigt das Formular „Das Paper ist derzeit nicht zur Begutachtung offen".

---

## Revisionen und Versionen

Fordert die Organisation eine Überarbeitung an (`revision_requested`), lädt das Team eine **neue PDF-Version** hoch. Frühere Versionen bleiben erhalten. Nach dem erneuten Einreichen (`resubmitted`):

- Deine Zuweisung steht wieder auf „ausstehend", jetzt für die neue Version.
- Das Paper erscheint wieder in deiner Warteschlange.
- Mit dem **Text-Diff** siehst du, was sich gegenüber der vorigen Version geändert hat. Enthält das PDF keinen extrahierbaren Text, vergleicht der Diff nur die Metadaten und sagt das dazu.

Jede Review-Runde hat ihre eigene `revision_number`. Zu jedem Review wird gespeichert, welche Version begutachtet wurde.

---

## Fristen und Erinnerungen

- Zuweisungen können ein Fälligkeitsdatum haben. Überfällige Zuweisungen werden als **Überfällig** markiert.
- Stündlich prüft der Server fällige Zuweisungen, täglich die internen Review-Deadlines. Die Organisation kann dich zusätzlich von Hand an ein offenes Review erinnern. Erinnerungen kommen per Push, wenn aktiviert (Profil → Benachrichtigungen → Deadlines & Erinnerungen).
- Alle Deadlines der Saison stehen unter **Deadlines** (Kalender, iCal-Abo).

---

## Was Teams sehen

Nach der Entscheidung einer Runde sieht das Team sein **Feedback**:

- Kriterien-Scores und Kommentare;
- Gesamtkommentar, Revisionshinweise, Empfehlung.

Das Team sieht dagegen **nicht**, wer das Review geschrieben hat, und auch nicht deine privaten Notizen. Schreibe Kommentare und Revisionshinweise deshalb so, dass das Team damit arbeiten kann.
