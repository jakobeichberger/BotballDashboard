# Admin-Handbuch

Für die Organisation eines Wettbewerbs. Die Rolle `admin` hat alle Rechte. Einzelne Aufgaben lassen sich über eigene Rollen an andere Personen übertragen (siehe [Rollen](#rollen-und-rechte)).

---

## Inhaltsverzeichnis

1. [Erste Einrichtung](#erste-einrichtung)
2. [Benutzer](#benutzer)
3. [Rollen und Rechte](#rollen-und-rechte)
4. [Saisons](#saisons)
5. [Events einrichten](#events-einrichten)
6. [Wertungsregeln](#wertungsregeln)
7. [Turnierablauf: Zeitplan, Brackets, Ergebnisse](#turnierablauf-zeitplan-brackets-ergebnisse)
8. [Teams](#teams)
9. [Qualifikation (z. B. GCER)](#qualifikation)
10. [Paper-Review](#paper-review)
11. [3D-Druck](#3d-druck)
12. [Ankündigungen und öffentliche Anzeige](#ankündigungen-und-öffentliche-anzeige)
13. [Auswertung und Exporte](#auswertung-und-exporte)
14. [Betrieb](#betrieb)

---

## Erste Einrichtung

Der erste Admin wird bei der Installation angelegt:

- per `proxmox-setup.sh`;
- oder per `backend/scripts/create_admin.py`;
- im Entwicklungsmodus automatisch: `admin@dev.local` / `admin1234`.

Nach dem ersten Login führt `/` zum **Einrichtungsassistenten** (`/setup`), solange es kein Event gibt:

1. **Erste Saison anlegen:** Name und Jahr. Die Saison wird als aktiv angelegt, ohne zusätzliches Standard-Event.
2. **Event anlegen:** Saison, Name, Slug (für die öffentliche Adresse), Zeitzone, Ort, Status, Anzahl Tische. Die Module sind aus der Saison vorbelegt. Dazu kommen die öffentlichen Freigaben.
3. Nach dem Speichern öffnet sich die **Event-Verwaltung** des neuen Events. Dort legst du Phasen, Teams, Score-Sheet-Schema, Regeln, Qualifikation und Ankündigungen an (siehe [Events einrichten](#events-einrichten)).

---

## Benutzer

**Einstellungen → Benutzer** (`/settings/users`, Recht `users:read`/`users:write`):

- **Anlegen:** E-Mail, Anzeigename, Startpasswort, Rollen. Mit eingerichtetem Mailserver bekommt die Person eine Hinweis-Mail ohne Passwort. Einladungslinks gibt es nicht. Das Startpasswort gibst du selbst weiter.
- **Bearbeiten:** Name, aktiv/inaktiv, Rollen. Deaktivieren beendet alle Sitzungen der Person sofort.
- **Passwort setzen:** für vergessene Passwörter ohne Mailserver; beendet die Sitzungen der Person.
- **Löschen:** anonymisiert das Konto. Wertungen, Reviews und Historie bleiben ohne Personenbezug erhalten.

Damit Mentoren ihr Team bearbeiten können, muss ihr Konto mit einem Teammitglied verknüpft sein (siehe [Teams](#teams)).

---

## Rollen und Rechte

**Einstellungen → Rollen** (`/settings/roles`):

- Die fünf Standardrollen `admin`, `juror`, `reviewer`, `mentor` und `guest` samt Rechten stehen in der [Rollen-Tabelle](index.md#rollen).
- **Rechte einer Rolle ändern:** Häkchen setzen und speichern. Der Admin-Rolle lassen sich die kritischen Rechte nicht entziehen.
- **Eigene Rolle anlegen:** Name, Beschreibung, Rechte-Auswahl. Beispiele: „Druck-Team" mit `printing:*`, „Formel-Verantwortliche" mit `scoring:formulas`.

Superuser (bei der Installation mit `create_admin.py --superuser`) bestehen jede Rechteprüfung, unabhängig von ihren Rollen.

---

## Saisons

**Einstellungen → Saisons** (`/settings/seasons`):

| Aktion | Wirkung |
|---|---|
| Anlegen | Name, Jahr, Thema; optional sofort aktiv (die bisher aktive wird deaktiviert) |
| Aktivieren | macht die Saison zur aktiven Saison |
| Status | `draft` (nur für Organisatoren sichtbar), `active`, `finished`, `archived` |
| **Archivieren** | Status `archived`: Saison und alle Events sind schreibgeschützt. Wertungen, Papers, Druckjobs und Registrierungen können nicht mehr geändert werden. |
| **Klonen** | legt eine neue Entwurfs-Saison an, Termine um die Jahresdifferenz verschoben. Übernommen werden: Saison-Einstellungen (Module, Kategorien, Termine), Saison-Phasen und Zusatztermine, Events als leere Entwürfe (Phasen, Module, Freigaben), aktive Score-Sheet-Schemas, Formeln und Bracket-Gewichte. Nicht übernommen werden Registrierungen, Ergebnisse, Tie-Breaker-Regeln, Paper-Deadlines und die Druck-Checkliste. |
| **Export (JSON)** | vollständiger Snapshot der Saison: Events, Registrierungen, Ergebnisse usw. |
| Löschen | nur möglich, solange keine Registrierungen, Ergebnisse, Papers oder Druckjobs existieren; sonst archivieren |

**Einstellungen → Saison-Details** (`/settings/season-details`): Termine (Anmeldung von/bis, Event-Zeitraum, Paper- und Druck-Deadline, Notizen). Unter „Zusätzliche Deadlines & Events" legst du beliebige weitere Termine an. Sie erscheinen im Kalender und lösen Erinnerungen aus. Das Anmeldefenster wird für Nicht-Admins durchgesetzt.

**Einstellungen → Saison-Module** (`/settings/modules`):

- Saison-Flags: Seeding, Double Elimination, Dokumentation, Aerial, Paper-Score in der Wertung;
- aktive Kategorien: `botball`, `open`, `aerial`, `jbc`.

Ein hier abgeschaltetes Modul bleibt in allen Events der Saison inaktiv.

**Einstellungen → Wettbewerbsstufen** (`/settings/levels`): Stufen wie ECER, GCER oder Junior mit Reihenfolge und „qualifiziert aus" (z. B. GCER aus ECER).

---

## Events einrichten

**Event-Verwaltung** in der Navigation (`/events/…/settings`, Recht `events:write`):

- **Stammdaten:** Name, Slug, Zeitzone (für Deadlines und Anzeige), Ort, Tische und Status:
  - `draft`: nur intern sichtbar;
  - `published`, `live`: öffentlich erreichbar;
  - `completed`: abgeschlossen;
  - `archived`: schreibgeschützt.
- **Aktive Module:** Seeding, Double Elimination, Paper, Dokumentation, Aerial, 3D-Druck, Bot-Galerie. Ist ein Modul in der Saison abgeschaltet, steht „In der Saison deaktiviert – bleibt inaktiv" daneben.
- **Öffentliche Freigaben:** Scoreboard, Zeitplan (inkl. Bracket), Ergebnisse, Ankündigungen.
- **Phasen:** `seeding`, `double_seeding`, `double_elimination`, `alliance`, `final`, jeweils mit Rundenzahl. Eine Phase eines abgeschalteten Moduls wird abgelehnt.
- **Teams:** Team mit Kategorie registrieren. Für qualifizierte Stufen ist eine Qualifikation nötig.
- **Score-Sheet-Schema:** siehe [Wertungsregeln](#wertungsregeln).
- **Tie-Breaker & Sonderregeln (Saison)**, **Qualifikation**, **Öffentliche Ankündigungen**.

Ein Event löschen darf nur, wer `events:admin` hat, und nur solange es nicht archiviert ist.

---

## Wertungsregeln

### Score-Sheet-Schema

In der Event-Verwaltung unter **Score-Sheet**. Jede Speicherung ist eine neue, versionierte Schema-Version. Jede Wertung speichert eine Kopie des Schemas, mit dem sie gerechnet wurde.

- **Vorlagen:** Score-Sheets 2024 und 2025 vollständig, 2026 als Struktur aus dem Game Review.
- **Klonen:** Schema eines anderen Events oder einer anderen Stufe übernehmen, z. B. ECER → GCER.
- **Aufbau:**
  - Bereiche mit Bereichs-Multiplikator;
  - Felder (Anzahl, Zahl, Ja/Nein) mit Punkten und Maximalwert;
  - Entweder-oder-Gruppen;
  - getrennte Seiten A/B.

  Ein JSON-Editor steht als Rückfall bereit. Der Editor zeigt Definitionsfehler vor dem Speichern.

### Score-Sheet-PDFs und OCR-Layout

Unter **Rangliste → Score-Sheets** (`/events/…/scoring/score-sheets`, `scoring:admin`) lädst du das offizielle PDF hoch. Der Worker extrahiert daraus Feldkandidaten. Diese kannst du bestätigen und ins Schema übernehmen. Die OCR von Fotos braucht zusätzlich das Layout der Vorlage: Anker, Feldbereiche und Prüfregeln. Das Layout wird derzeit über die API gesetzt (`PATCH /api/scoring/score-sheets/{id}/layout`), eine Oberfläche dafür fehlt.

### Tie-Breaker und Sonderregeln (pro Saison)

Abschnitt **Tie-Breaker & Sonderregeln (Saison)** in der Event-Verwaltung:

- **Tie-Breaker-Reihenfolge:** aus den Game Reviews 2024/2025/2026 übernehmen („Game Review wählen") oder selbst anlegen. Jeder Tie-Breaker hat:
  - Richtung (max/min);
  - Quelle: Summe aus Score-Sheet-Feldern oder Eingabe durch die Jury;
  - optional „nur nach einem Replay".
- **Finale wiederholen statt Tie-Breaker.**
- **Bonus bei Kontakt am Spielende** in % des Gegner-Scores, Standard 25 %.
- **Schiedsrichter-Checkliste:** Prüfpunkte, die vor dem Bestätigen eines Scores abgehakt werden, optional als Pflicht.

### Punkteformeln

**Punkteformeln** (`/events/…/formulas`, Recht `scoring:formulas`): Die Gesamtwertung wird pro Kategorie aus einem Formel-Set berechnet, so wie in den Game-Dokumenten formuliert.

- Standard ist das ECER-2025-Set.
- **Vorlage laden:** Presets ECER 2025 (Botball/Open), Regional 2026, GCER 2026, Aerial, JBC.
- Die Seite zeigt Variablen und Funktionen als Hilfe, dazu die Auswertungsreihenfolge.
- **Vorschau mit echten Daten:** rechnet den Entwurf gegen die Ergebnisse des Events, ohne zu speichern.
- **Bracket-Gewichtung** je Kategorie für die Saison. Pro Event lassen sich eigene Gewichte setzen (API `PUT /api/v1/events/{id}/bracket-weights`).
- „Zurücksetzen" stellt die Standardformeln wieder her.

---

## Turnierablauf: Zeitplan, Brackets, Ergebnisse

**Zeitplan** (`/events/…/schedule`):

1. **Zeitplan erzeugen** (`events:admin`): Phase wählen, Startzeit. Je nach Phasentyp entstehen Seeding-Runden über die Tische, Double-Seeding-Paarungen, das DE-Bracket oder Alliance-Paare.
2. **Setzliste aus Seeding übernehmen** (`events:admin`): schreibt die Seeds je Kategorie aus der Seeding-Rangliste. Das ist die Grundlage für das DE-Bracket.
3. **Bearbeiten** (`events:write`): Zeit, Tisch und Status einzelner Matches. Teams mit Push werden über Änderungen benachrichtigt.
4. **Bracket:** Winner- und Loser-Bracket, Grand Final und Reset-Finale, falls nötig. Mit `scoring:admin` trägt man per Klick den Sieger ein. Sieger und Verlierer rücken automatisch weiter. Korrekturen sind möglich. Die Platzierungen werden als DE-Ergebnis gespeichert.

**Wertungen bestätigen und korrigieren:** siehe [Juror-Handbuch](juror.md). Jede Korrektur wird versioniert. Die Revisionen bleiben auch nach dem Löschen einer Wertung erhalten.

**DE, Aerial, Dokumentation:** Auf **Rangliste & Ergebnisse** führen Buttons zur Eingabe. Die Buttons sehen nur Nutzer mit der Rolle `admin`. Jurorinnen öffnen die Seiten direkt: `/events/…/scoring/de`, `…/scoring/aerial`, `…/scoring/doc`.

- DE-Rang und Bracket-Score (0–1);
- Aerial-Läufe (gewertet wird der Ø aller Läufe);
- Doku-Teile 1–3 und Onsite, dazu der Paper-Score. Angezeigt wird zusätzlich der Wert aus dem Formel-Set.

**Parts Challenges:** werden über die API erfasst und entschieden. Die unterlegene Seite verliert die Runde. Eine eigene Oberfläche gibt es dafür derzeit nicht.

---

## Teams

**Teams** (`/events/…/teams`):

- Suche nach Name, Nummer, Schule, Ort; Filter nach Land, Status, Saison, Kategorie.
- **Team anlegen/löschen** (`teams:admin`).
- **Team-Saison-Matrix** (`/events/…/teams/matrix`): Teams schnell Saisons zuordnen und Registrierungen bestätigen.

**Team-Detailseite:**

- **Mitglieder:** Name, E-Mail, Rolle. Mit **Konto verknüpfen** (`teams:admin`) wird ein Benutzerkonto dem Mitglied zugeordnet. Erst damit gilt das Team als „eigenes Team" dieser Person, z. B. für eine Mentorin.
- **Saison-Teilnahmen:** Kategorie, Bestätigung, Gebühr (`pending`/`paid`/`waived`), Kit (`not_sent`/`sent`/`received`), Paper-Pflicht, Kontaktperson und Adresse. Organisatoren bearbeiten alles, Mentoren nur die Kontaktfelder. Dazu kommt der **Saison-Kader** mit Rollen pro Saison.
- **Dokumente:** Projektplan, Präsentation, Code-Doku und Sonstiges als PDF oder Bild. Jeder Upload wird eine neue Version. Sichtbar für das eigene Team und die Organisation.
- **3D-Druck-Checkliste** der Saison: Punkte anlegen oder die Standardregeln übernehmen (`teams:admin` oder `printing:admin`). Das Team hakt ab, die Organisation bestätigt. Ändert das Team einen Haken, wird die Bestätigung aufgehoben.
- **Historie** über alle Saisons mit Diagrammen, dazu Team-Bericht PDF und Historie CSV.

---

## Qualifikation

In der Event-Verwaltung, Abschnitt **Qualifikation** (`seasons:write`):

1. Zielstufe wählen (z. B. GCER). Angezeigt werden die Kandidaten der Ausgangsstufe.
2. Teams **qualifizieren**, mit Notiz wie „ECER-Sieger".
3. **Qualifizierte Teams für dieses Event registrieren** (`events:write`).

Eine Qualifikation lässt sich wieder entfernen.

---

## Paper-Review

**Paper-Review** (`/events/…/papers`, Modul `paper`):

- **Deadlines** der Saison:
  - offiziell `official_submission` / `official_final`, blockierend;
  - intern `internal_draft`, `internal_review`, `internal_revision`, `internal_final`, diese warnen nur.

  Ohne offizielle Einreichungs-Deadline gilt die Paper-Deadline der Saison. Eine Deadline gilt bis Tagesende in der Zeitzone des Events. Mit `papers:admin` darf man übersteuern.
- **Reviewer zuweisen:** Einzeln auf der Paper-Detailseite, oder **automatisch** bis N Reviewer pro Paper, zuerst mit Vorschau. Reviewer aus dem Team selbst oder von derselben Schule werden abgelehnt. Die **Reviewer-Auslastung** zeigt offene Reviews je Person. Fällige Zuweisungen erinnert der Server automatisch. Eine zusätzliche manuelle Erinnerung geht derzeit nur über die API (`POST /api/papers/{id}/assignments/{assignment_id}/remind`).
- **Status:**
  - `draft` → `submitted` → `under_review` → `revision_requested` → `resubmitted` → `accepted`/`rejected`;
  - `disqualified_ai` für KI-Missbrauch (Score 0, keine Revision).

  Jede Änderung wird mit Begründung in der Historie festgehalten.
- **Reviews:** Abgegebene Reviews sind gesperrt, ein Admin kann sie wieder öffnen. Private Notizen der Reviewer sieht nur die Organisation.
- **Formalabzug** (z. B. für eine Seite zu viel) und **Finalisieren**: verdichtet die Reviews abzüglich Formalabzug zum `final_score` (0–1). Das Ergebnis geht in die Doku- bzw. Gesamtwertung ein, wenn „Paper-Score in der Wertung" in der Saison aktiv ist.
- **Statistik:** Paper gesamt, offene Reviews, Ø Review-Score, Ø Endergebnis, Annahmequote. Exporte: Paper CSV/PDF, Reviews CSV.

Teams sehen das Feedback entschiedener Runden ohne Namen der Reviewer.

---

## 3D-Druck

**Einstellungen → Drucker** (`/settings/printers`, `printing:admin`):

- **Drucker:**
  - Typ Bambu Lab (Seriennummer, Access Code);
  - Typ OctoPrint (URL, API-Key);
  - Typ „Manuell (ohne Adapter)".

  Zugangsdaten werden verschlüsselt gespeichert und nie wieder angezeigt. Bambu und OctoPrint fragt der Worker alle 15 s ab.
- **Druck-Kontingente** pro Event und Team: Hard-Limit Teile, Soft-Limit (Warnung), optional Gramm-Limit. Offene Jobs zählen mit.
- **Filament-Spulen:** Material, Farbe, Hersteller, Anfangs- und Restgewicht.

**3D-Druck** (`/events/…/printing`):

- **Freigeben/Einreihen**, **Ablehnen mit Begründung**, **Abbrechen**. Ein laufender Druck wird bei OctoPrint und Bambu auch am Drucker gestoppt. Ob das geklappt hat, meldet die Oberfläche.
- Auf der Job-Detailseite: Drucker, Priorität, Datei herunterladen oder ersetzen, **als fertig markieren** mit tatsächlichem Verbrauch (Gramm, Minuten, Spule). Der Verbrauch wird aufs Kontingent und die Spule gebucht.
- Admins dürfen über das Kontingent hinaus einreichen. Das wird markiert und protokolliert.
- Unvollständige **3D-Druck-Checkliste** des Teams: Der Job wird angenommen, aber mit Warnung.

---

## Ankündigungen und öffentliche Anzeige

- **Einstellungen → Ankündigungen** oder Event-Verwaltung: Titel, Text, Zielgruppe (`all`, `teams`, `reviewers`, `jurors`, `internal`), veröffentlichen oder zurückziehen. Nur Ankündigungen mit Zielgruppe `all` erscheinen öffentlich und als Push an alle.
- **Öffentliche Seite** `/public/<slug>`: siehe [Gast-Handbuch](guest.md). Freigaben setzt du in der Event-Verwaltung.

---

## Auswertung und Exporte

- **Rangliste & Ergebnisse:** Seeding je Kategorie mit entscheidendem Tie-Breaker, DE, Aerial, Gesamtwertung aus dem Formel-Set. Rot-karierte Teams stehen mit „DQ" statt Rang. Exporte als CSV und PDF.
- **Statistik & Anomalien** (`scoring:admin`):
  - Boxplots je Runde und Aufgabe;
  - Heatmap Team × Aufgabe;
  - Trends;
  - **auffällige Läufe**: unmögliche Werte, Summenfehler, Ausreißer gegenüber Team und Feld, Sprünge, unbestätigt.

  Ein Klick zeigt Rohwerte und Revisionen und erlaubt das Bestätigen.
- **Performance:** Teamvergleich, Verlauf inkl. Übungsläufen, Stärken und Schwächen je Aufgabe, Ranking-Vorschau.
- **Dashboard:** Fortschritt der Organisation (X von N), nächste Deadlines, Juror-Warteschlange.
- **Deadlines:** Kalender, Saison-Zeitleiste, iCal-Abo.
- **Mehrjahresvergleich** aller Teams als CSV auf der Teams-Seite.

---

## Betrieb

Einen Log- oder Audit-Bereich gibt es in der Oberfläche nicht:

- Jede erfolgreiche Änderung über die API steht in der Datenbanktabelle `audit_logs` (Aktion, Nutzer, IP, Zeit).
- Score-Änderungen stehen zusätzlich als Revisionen je Wertung bzw. Event.
- Anwendungslogs: `docker compose logs backend worker beat`.

Backups, Updates, Monitoring und Wiederherstellung beschreiben [Deployment](../technical/deployment.md), [Update](../installation/update.md) und [docs/operations.md](../../operations.md).
