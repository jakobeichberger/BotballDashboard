# Mentor-Handbuch

Für Team-Betreuerinnen und -Betreuer. Die Rolle `mentor` hat folgende Rechte:

- `teams:read`/`teams:write`, `scoring:read`/`scoring:write`, `papers:read`/`papers:write`, `printing:read`/`printing:write`;
- `seasons:read`, `events:read`, `dashboard:read`.

Alles Schreibende gilt **nur für das eigene Team**.

---

## Inhaltsverzeichnis

1. [Voraussetzung: Konto mit dem Team verknüpfen](#voraussetzung-konto-mit-dem-team-verknüpfen)
2. [Dashboard](#dashboard)
3. [Eigenes Team pflegen](#eigenes-team-pflegen)
4. [Wertungen und Übungsläufe](#wertungen-und-übungsläufe)
5. [Performance](#performance)
6. [Scouting](#scouting)
7. [Paper einreichen](#paper-einreichen)
8. [3D-Druck](#3d-druck)
9. [Bot-Galerie](#bot-galerie)
10. [Deadlines und Kalender](#deadlines-und-kalender)

---

## Voraussetzung: Konto mit dem Team verknüpfen

Ein Team gilt als dein „eigenes Team", wenn dein Benutzerkonto dort als **Mitglied verknüpft** ist. Die Verknüpfung setzt die Organisation auf der Team-Detailseite („Konto verknüpfen", Recht `teams:admin`). Ohne Verknüpfung kannst du lesen, aber nichts für ein Team einreichen. Die Oberfläche bietet dir in Auswahllisten nur deine eigenen Teams an.

---

## Dashboard

Pro eigenem Team zeigt das Dashboard eine Karte mit:

- Seeding-Rang und Seed-Score;
- den nächsten Matches;
- den letzten Wertungen (bestätigt oder nicht);
- dem Paper-Status;
- offenen und fertigen Druckaufträgen.

Dazu kommen anstehende Deadlines und Ankündigungen. Paper- und Druck-Angaben fehlen, wenn das Event diese Module nicht nutzt.

---

## Eigenes Team pflegen

Auf der **Team-Detailseite** (Teams → dein Team):

- **Stammdaten und Mitglieder** bearbeiten. Mitglieder hinzufügen oder entfernen. Konten verknüpfen kann nur die Organisation.
- **Saison-Teilnahme:** Kontaktperson, E-Mail, Telefon und Adresse pflegst du selbst. Kategorie, Gebühr und Kit-Status pflegt die Organisation. Den **Saison-Kader** legst du mit Rollen pro Saison fest.
- **Dokumente:** Projektplan, Präsentation, Code-Dokumentation und Sonstiges als PDF oder Bild hochladen. Jeder weitere Upload wird eine **neue Version**, ältere Versionen bleiben im Archiv. Dokumente sehen nur dein Team und die Organisation.
- **3D-Druck-Checkliste** der Saison: die Regeln für gedruckte Teile abhaken. Die Organisation bestätigt die vollständige Liste. Änderst du danach einen Haken, fällt die Bestätigung weg.
- **Historie:** Ergebnisse über alle Saisons mit Diagrammen, dazu **Teambericht PDF** und **Historie CSV**. Übungswerte sieht nur das eigene Team.

Kontaktdaten und Mitglieder-E-Mails anderer Teams sind für dich ausgeblendet.

---

## Wertungen und Übungsläufe

**Punkte eintragen** (`/events/…/scoring/entry`) hat zwei Modi:

- **Vorbereitung (Übungsläufe):** Eure Trainingsläufe erfassen. Sie zählen **nie** für Ranglisten oder die Gesamtwertung. Andere Teams sehen sie nicht.
- **Wettbewerb:** Wertungen des eigenen Teams selbst erfassen, z. B. beim Regionalturnier ohne eigene Jury am Tisch. Vor dem Absenden kommt eine Zusammenfassung zum Bestätigen. Solche Wertungen landen in der Warteschlange der Jury und werden dort bestätigt.

Zusätzlich gibt es die mobile **Wertung** (`/events/…/scoring`) entlang des Zeitplans und die **OCR-Prüfung**. Dort lädst du ein Foto des Papier-Score-Sheets hoch, prüfst die erkannten Werte und übernimmst sie. Beides geht nur für das eigene Team.

**Offline:** Ohne Netz werden Wertungen und Übungsläufe auf dem Gerät gespeichert und später automatisch übertragen (siehe [Benutzerhandbuch](index.md#offline-und-handy-pwa)).

Die offizielle Rangliste (Seeding je Kategorie, DE, Gesamtwertung) steht unter **Rangliste & Ergebnisse**.

---

## Performance

**Performance** (`/events/…/performance`) zeigt nur eure eigenen Teams:

- Kennzahlen: bester Lauf, Durchschnitt, Abstand zum nächsten Seeding-Rang;
- **Score-Verlauf** mit Übungsläufen als eigener, gestrichelter Linie;
- **Stärken & Schwächen je Aufgabe**: Punkte pro Aufgabe gegenüber dem Durchschnitt des Teilnehmerfelds;
- **Ranking-Vorschau**: wo das Team stünde, wenn das Event jetzt endete;
- Vergleich der Phasen und der Events der Saison.

---

## Scouting

**Scouting** (`/events/…/scouting`) hilft bei der Vorbereitung auf Gegner, z. B. bei ECER oder GCER:

- **Externe Teams** erfassen: Name, Nummer, Land, Schule.
- **Beobachtete Scores** je Team und Phase notieren.
- **Notizen** mit Einschätzung, etwa Stärken, Schwächen und Strategie, jeweils für eines deiner Teams.
- **Gegner-Rangliste:** deine Teams (offizielles Seeding) und die beobachteten externen Teams gemeinsam gereiht.
- **Scouting-Bericht (PDF).**

Externe Teams, die du selbst angelegt hast, kannst du über den Stift bearbeiten (Name, Nummer, Land, Schule, Notizen). Löschen kann nur die Organisation.

Deine Notizen und Beobachtungen sehen nur dein Team und die Organisation.

---

## Paper einreichen

Den Bereich gibt es nur, wenn das Modul **Paper** im Event aktiv ist. Pro Team und Saison gibt es **ein** Paper.

1. **Paper-Review → Paper einreichen:** Team, Titel und Abstract angeben. Das Paper wird als Entwurf angelegt.
2. Auf der Paper-Detailseite **Neue Version (PDF)** hochladen. Du kannst beliebig oft hochladen, jeder Upload wird eine neue Version.
3. **Einreichen.** Danach ist das Paper gesperrt: „Abgegeben und gesperrt. Änderungen nur nach Freigabe durch die Organisation."

**Deadlines:** Das Deadline-Banner zeigt einen Countdown bis zur Einreichungsfrist.

- Die Frist gilt bis Tagesende in der Zeitzone des Events. Danach sind Anlegen, Hochladen und Einreichen gesperrt („Einreichungsfrist abgelaufen").
- Überarbeitete Versionen richten sich nach der offiziellen Final-Deadline.
- Interne Deadlines der Organisation erscheinen nur als Warnung.

**Revision:** Fordert die Organisation eine Überarbeitung an (Status „Zu überarbeiten"):

1. Das **Feedback** lesen: Kriterien, Kommentare, Revisionshinweise, ohne Namen der Reviewer.
2. Eine neue Version hochladen.
3. Erneut einreichen. Status wird `resubmitted`.

**Ergebnis:** `accepted` oder `rejected`, danach das Endergebnis (0–1). Es fließt in die Doku- bzw. Gesamtwertung ein, wenn die Saison das vorsieht.

---

## 3D-Druck

Den Bereich gibt es nur, wenn das Modul **3D-Druck** im Event aktiv ist.

1. **Druckauftrag erstellen:** Team, Datei, Material, Farbe, geschätzte Gramm und Minuten, Notizen.
   - Erlaubte Dateien: STL, 3MF, OBJ, G-Code, bgcode.
   - Die Größe ist begrenzt durch `PRINT_UPLOAD_MAX_MB`, Standard 100 MB.
2. **Kontingent** pro Event und Team:
   - **Soft-Limit:** Warnung, der Auftrag wird trotzdem angenommen.
   - **Hard-Limit:** Teile, optional Gramm. Offene Aufträge zählen mit. Darüber wird abgelehnt.
3. **Checkliste:** Ist die 3D-Druck-Checkliste deines Teams unvollständig, warnt die Seite vor dem Absenden. Der Auftrag wird trotzdem angenommen.
4. **Status verfolgen:** `pending` → `approved`/`queued` → `printing` → `completed`. Andere Ausgänge sind `rejected` (mit Begründung), `failed` und `cancelled`. Bei laufendem Druck siehst du Fortschritt und Restzeit. Die Liste aktualisiert sich selbst. Push-Meldungen gibt es in der Kategorie „Druckaufträge".
5. **Zurückziehen:** Einen eigenen, noch nicht freigegebenen Auftrag kannst du selbst abbrechen.

Die Druckerliste siehst du ohne technische Details wie Adresse oder Seriennummer.

---

## Bot-Galerie

Nur wenn das Modul **Bot-Galerie** aktiv ist. Die Galerie zeigt Roboter eigener und externer Teams:

- Funktionsweise, Antrieb, Sensorik, Saison und Bild;
- filterbar nach Saison und Team.

Die Bots deines Teams legst du selbst an und bearbeitest sie. Ein Bild lädst du nach dem Anlegen auf der Detailseite hoch. Unveröffentlichte Bots sehen nur dein Team und die Organisation. Bots externer Teams pflegt die Organisation.

---

## Deadlines und Kalender

**Deadlines** (`/events/…/calendar`):

- Liste und Monatsansicht aller für dich relevanten Termine: Anmeldung, Turniere, offizielle und interne Paper-Deadlines, Zusatztermine der Saison;
- **Saison-Timeline**.

**Kalender-Abo (iCal):** Hier erzeugst du einen persönlichen Link, z. B. für Google Calendar, Outlook oder Apple Kalender.

- Der Link wird **nur einmal** angezeigt.
- Du kannst ihn jederzeit neu erzeugen. Der alte Link wird dann ungültig.
- Du kannst das Abo widerrufen.
- Alternativ lädst du die `.ics`-Datei herunter.

Erinnerungen 7, 3 und 1 Tag vor Deadlines kommen per Push. Ist ein Mailserver eingerichtet, gehen sie auch per E-Mail an die Teammitglieder.
