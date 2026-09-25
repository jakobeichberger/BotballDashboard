# FAQ – Häufig gestellte Fragen

---

## Allgemein

### Ich kann mich nicht einloggen. Was tun?

1. E-Mail-Adresse und Passwort prüfen. Nach zu vielen Versuchen (10 pro Minute) blockiert der Server kurz.
2. **„Passwort vergessen?"** auf der Login-Seite nutzen. Der Link ist eine Stunde gültig.
3. Kommt keine E-Mail: Spam-Ordner prüfen. Hat die Installation keinen Mailserver, setzt ein Admin das Passwort unter **Einstellungen → Benutzer**.
4. Dein Konto könnte deaktiviert sein. Dann hilft nur die Organisation.

### Ich sehe einen Bereich nicht in der Navigation. Warum?

Zwei Gründe sind möglich:

- **Rechte:** Die Navigation zeigt nur Bereiche, für die deine Rolle Rechte hat (siehe [Rollen](index.md#rollen)). Beispiele: Paper-Review braucht `papers:read`, Statistik `scoring:admin`, Punkteformeln `scoring:formulas`.
- **Modul im Event abgeschaltet:** Paper, 3D-Druck, Bot-Galerie, DE, Aerial und Dokumentation lassen sich pro Event abschalten. Dann fehlt der Bereich in diesem Event, auch für Admins.

### Warum hängt alles an einem Event?

Weil Wertungen, Ranglisten, Kontingente und Ankündigungen pro Turnier gelten. ECER und GCER derselben Saison haben getrennte Ergebnisse. Das Event wechselst du oben in der Seitenleiste.

### Wie ändere ich Passwort, E-Mail, Sprache oder Design?

Im **Profil** (Link in der Kopfzeile). Sprache und Design lassen sich auch direkt in der Kopfzeile umschalten. Beide Einstellungen werden im Konto gespeichert und gelten auf allen Geräten. Ändert man das Passwort, werden alle anderen Sitzungen beendet.

### Warum ist ein Teil der Oberfläche auf Englisch umgestellt und ein Teil nicht?

Die Übersetzung ist noch unvollständig. Viele Seiten enthalten fest deutschen Text. Siehe [todo.md](../../todo.md).

### Kann ich meine Daten exportieren oder mein Konto löschen?

Ja, im **Profil → Datenschutz**:

- **Datenexport** als JSON.
- **Konto löschen**, mit Passwort. Das Konto wird anonymisiert. Wertungen und andere historische Einträge bleiben ohne Personenbezug erhalten.

### Soll ich die App (PWA) installieren?

Für Jury und Mentoren am Turniertag: ja. Die App startet schneller, empfängt Push-Meldungen und speichert Wertungen offline zwischen.

---

## Wertung

### Wie wird ein Lauf berechnet?

Aus dem Score-Sheet-Schema des Events: Felder mal Punkte, Bereichs-Multiplikatoren, Entweder-oder-Gruppen, Seiten A/B. Dazu kommen die Sonderregeln der Saison:

- Kontakt-Bonus;
- „Runde verloren" (0 Punkte);
- DQ.

Der Server rechnet immer selbst nach.

### Wie wird der Seed-Score berechnet?

In der Seeding-Rangliste: **Ø der zwei besten Seeding-Läufe**. Eine DQ oder verlorene Runde zählt als 0-Lauf, negative Werte zählen als 0. Nur Läufe aus Seeding-Phasen zählen, keine Übungsläufe. Ränge gelten je Kategorie. Gleichstände entscheidet die Tie-Breaker-Reihenfolge der Saison. In die Gesamtwertung geht der Seeding-Wert über das Formel-Set ein (siehe [Juror-Handbuch](juror.md#rangliste-und-seeding-regeln)).

### Ich habe einen falschen Score eingegeben. Kann ich ihn korrigieren?

Mit `scoring:admin` (Jury, Organisation): **Punkte eintragen → Bearbeiten**. Jede Änderung wird als Revision gespeichert, mit altem und neuem Wert, Zeit und Person. Die Teams bekommen „Score korrigiert". Mentoren wenden sich an die Jury.

### Was passiert bei einer roten Karte?

Das Team ist für das Event disqualifiziert:

- kein Rang, Anzeige „DQ";
- es zählt nicht mehr zum Teilnehmerfeld der Formeln (n, Maxima).

Karten werden derzeit über die API gesetzt, ein Schalter in der Oberfläche fehlt noch.

### Zählen Übungsläufe?

Nein. Übungsläufe (Modus „Vorbereitung") erscheinen nur in der Performance-Ansicht des eigenen Teams. Sie zählen nie für Ranglisten, Gesamtwertung oder öffentliche Ergebnisse.

### Kann ich die Rangliste herunterladen?

Ja, auf **Rangliste & Ergebnisse**: Seeding und Gesamtwertung als CSV oder PDF, dazu alle Wertungen als CSV.

### Die Wertung klappt am Spieltisch nicht, das WLAN ist weg.

Einfach weiter erfassen. Die Wertungen werden auf dem Gerät gespeichert und automatisch übertragen, sobald wieder Verbindung besteht. Die Kopfzeile zeigt, wie viele warten. Siehe [Offline-Betrieb](juror.md#offline-betrieb).

### Die öffentliche Anzeige aktualisiert sich nicht.

Die öffentliche Seite nutzt eine WebSocket-Verbindung. Oben steht der Status („Verbunden"/„Getrennt"). Die Seite verbindet sich selbst neu. Hilft das nicht: Seite neu laden und prüfen, ob der Proxy WebSockets durchlässt. Ist die Seite ganz leer, sind im Event keine Bereiche freigegeben.

---

## Paper-Review

### Bis wann muss das Paper eingereicht werden?

Das Deadline-Banner im Paper-Bereich zeigt Frist und Countdown. Alle Termine stehen auch unter **Deadlines**. Die offizielle Frist gilt bis Tagesende in der Zeitzone des Events, danach ist das Einreichen gesperrt. Erinnerungen kommen 7, 3 und 1 Tag vorher.

### Welches Format muss das Paper haben?

PDF. Die inhaltlichen Vorgaben (Template, Seitenzahl, Abschnitte) stehen im Call for Papers der Saison (`docs/assets`). Ein Verstoß gegen das Format kann einen **Formalabzug** geben.

### Ich muss überarbeiten. Was tun?

1. Auf der Paper-Detailseite das **Feedback** lesen: Kriterien, Kommentare, Revisionshinweise.
2. Eine **neue Version** hochladen. Frühere Versionen bleiben erhalten.
3. **Einreichen.** Der Status wird „überarbeitet eingereicht", und die Reviewer bekommen das Paper erneut.

### Wie viele Überarbeitungsrunden gibt es?

Keine feste Grenze. Die Organisation entscheidet. Jede Runde und jede Version wird gespeichert.

### Darf ich KI-Tools verwenden?

Das regelt der Call for Papers. Bei Missbrauch kann die Organisation den Status `disqualified_ai` setzen: Score 0, keine Überarbeitung.

### Ich bin Reviewer und sehe nichts in meiner Warteschlange.

Dir ist noch kein Paper zugewiesen, oder deine Papers liegen gerade beim Team zur Überarbeitung. Die Zuweisung macht die Organisation.

---

## 3D-Druck

### Welche Dateiformate werden angenommen?

STL, 3MF, OBJ, G-Code und bgcode, bis zur eingestellten Maximalgröße (Standard 100 MB).

### Was bedeuten Soft- und Hard-Limit?

- **Soft-Limit:** Warnung, der Auftrag wird trotzdem angenommen.
- **Hard-Limit:** Teile, optional Gramm. Darüber wird ein neuer Auftrag abgelehnt. Offene Aufträge zählen mit.

Die Limits gelten pro Event und Team. Nur die Organisation kann sie überschreiten.

### Mein Auftrag wurde abgelehnt oder ist fehlgeschlagen.

Die Begründung bzw. Fehlermeldung steht auf der Detailseite des Auftrags. Datei überarbeiten und einen neuen Auftrag stellen.

### Kann ich Druckeinstellungen angeben?

Ja, im Notizfeld. Die Druck-Verantwortlichen entscheiden darüber.

### Warum warnt die Seite wegen einer Checkliste?

Die 3D-Druck-Checkliste deines Teams für die Saison ist unvollständig. Du findest sie auf der Team-Detailseite. Der Auftrag wird trotzdem angenommen.

---

## Benachrichtigungen

### Ich bekomme keine Push-Benachrichtigungen.

1. Push auf **diesem Gerät** aktivieren (Profil oder Kopfzeile) und die Browser-Berechtigung erlauben.
2. Im Profil prüfen, ob die Kategorie eingeschaltet ist.
3. Auf iOS funktioniert Web Push nur mit der installierten App.
4. Die Installation braucht VAPID-Schlüssel. Fehlen sie, ist Push serverseitig abgeschaltet.

Alle Meldungen stehen zusätzlich in der **Benachrichtigungszentrale** (Glocke).

### Kann ich einzelne Benachrichtigungen abschalten?

Ja, pro Kategorie im Profil: Match beginnt bald, Score korrigiert, Deadlines & Erinnerungen, Paper-Status, Druckaufträge, Ankündigungen.

### Kann ich die Deadlines in meinen Kalender übernehmen?

Ja: **Deadlines → Kalender-Abo (iCal)**. Der Link wird nur einmal angezeigt und lässt sich neu erzeugen oder widerrufen.

---

## Technisches

### Welche Browser werden unterstützt?

Aktuelle Versionen von Chrome, Edge, Firefox und Safari. Web Push auf iOS/iPadOS geht nur mit der installierten App.

### Funktioniert das Dashboard auf dem Handy?

Ja, die Seiten sind responsiv. Die Wertung am Spieltisch ist speziell fürs Handy gebaut, mit Wischen zwischen Matches und Kamera-Upload für Score-Sheets.

### Wie lange werden Daten gespeichert?

Bis die Organisation sie löscht. Abgeschlossene Saisons werden **archiviert** (schreibgeschützt), nicht gelöscht. Eine Saison mit Ergebnissen lässt sich gar nicht löschen. Personenbezogene Kontodaten kannst du selbst exportieren oder löschen.

---

## Admin-FAQ

### Wie setze ich das Passwort eines Benutzers zurück?

**Einstellungen → Benutzer → Passwort setzen.** Die Person wird auf allen Geräten abgemeldet. Alternativ nutzt sie selbst „Passwort vergessen?", sofern ein Mailserver eingerichtet ist.

### Wie archiviere ich eine Saison?

**Einstellungen → Saisons → Status `archived`.** Die Saison und ihre Events sind danach schreibgeschützt.

### Wie bereite ich die nächste Saison vor?

**Einstellungen → Saisons → Saison klonen.** Übernommen werden Konfiguration, Termine, leere Events, Schemas und Formeln. Danach die Termine prüfen und die Saison aktivieren.

### Wie sehe ich, wer einen Score geändert hat?

- Die Revisionen einer Wertung zeigt **Statistik → auffälligen Lauf öffnen**.
- Den Audit-Trail eines Events liefert die API `GET /api/scoring/events/{id}/revisions` bzw. `/result-revisions` für DE, Aerial und Doku.
- Alle API-Änderungen stehen zusätzlich in der Tabelle `audit_logs`.

Einen Audit-Log-Bereich in der Oberfläche gibt es nicht.

### Gibt es Demo-Daten?

Für die End-to-End-Tests legt `backend/scripts/seed_e2e.py` ein Beispiel-Event an. Für Probeläufe empfiehlt sich eine eigene Staging-Instanz.
