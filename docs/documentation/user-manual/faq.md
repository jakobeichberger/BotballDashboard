# FAQ – Häufig gestellte Fragen

---

## Allgemein

### Ich kann mich nicht einloggen. Was tun?

1. Prüfe ob Groß-/Kleinschreibung bei der E-Mail stimmt
2. Nutze „Passwort vergessen" auf der Login-Seite → Reset-E-Mail kommt binnen weniger Minuten
3. Falls keine E-Mail kommt: Spam-Ordner prüfen
4. Falls weiterhin kein Zugang: Admin kontaktieren (dein Konto könnte deaktiviert sein)

### Ich sehe ein Modul nicht in der Navigation. Warum?

Bestimmte Module sind nur für bestimmte Rollen sichtbar:
- **Scoring** → nur für Juror und Admin
- **Paper-Review (Admin-Ansicht)** → nur für Reviewer-Admin oder Admin
- **3D-Druck (Verwaltung)** → nur für Admin
- **Benutzerverwaltung** → nur für Admin

Falls du ein Modul sehen solltest aber es fehlt: Admin bitten, deine Rollen zu prüfen.

### Wie ändere ich mein Passwort?

**Profil → Mein Konto → Passwort ändern** → Altes Passwort, neues Passwort (2×) eingeben.

### Wie schalte ich zwischen Deutsch und Englisch um?

Topbar oben rechts → Flagge/Sprachkürzel anklicken → `DE` oder `EN` wählen. Die Einstellung wird gespeichert.

### Wie aktiviere ich den Dark Mode?

Topbar → Mond-/Sonne-Icon anklicken. Einstellung wird gespeichert.

### Was ist eine PWA und soll ich sie installieren?

Eine **Progressive Web App (PWA)** verhält sich wie eine native App auf deinem Gerät:
- Funktioniert auch offline (zumindest eingeschränkt)
- Eigenes Icon auf dem Startbildschirm
- Schnellerer Start
- Push-Benachrichtigungen auch wenn der Browser geschlossen ist

Installation: Chrome/Edge → URL-Leiste → Install-Icon (oder Menü → „App installieren")

---

## Scoring

### Wie wird der Seed-Score berechnet?

```
Seed-Score = (bester Lauf + zweitbester Lauf) / 2
```

Teams mit nur einem Lauf erhalten diesen direkt als Seed-Score. Teams ohne Lauf erscheinen am Ende der Rangliste.

### Wie wird der Gesamtscore pro Lauf berechnet?

```
Gesamtscore = Σ (Feldwert × Multiplikator)
```

Jedes Feld im Score-Schema hat einen Wert und einen Multiplikator. Die Summe aller Produkte ergibt den Gesamtscore.

### Ich habe einen falschen Score eingegeben. Kann ich ihn korrigieren?

Ja. **Scoring → Match → Score → Bearbeiten** → Korrekten Wert eingeben + Korrekturgrund (Pflichtfeld). Der ursprüngliche Score bleibt im Audit-Log erhalten.

### Was passiert bei einer roten Karte?

Das Team wird aus allen weiteren Runden **und** Awards ausgeschlossen. Der Score bleibt in der Rangliste erhalten (historisch), aber das Team ist für das Turnier disqualifiziert.

### Kann ich die Rangliste herunterladen?

Ja. **Scoring → Rangliste → PDF** (druckfertig, A4) oder **CSV** (für Excel/Sheets). Der Export zeigt den Stand zum Zeitpunkt des Downloads.

### Das Live-Scoreboard aktualisiert sich nicht. Was tun?

Das Scoreboard nutzt WebSockets. Mögliche Ursachen:
1. Seite neu laden (F5 / Wisch-Refresh auf Mobil)
2. Netzwerkunterbrechung → kurz warten, automatische Reconnect-Logik greift
3. Proxy/Firewall blockiert WebSockets → Admin informieren

---

## Paper-Review

### Bis wann muss ich das Paper einreichen?

Die aktuellen Deadlines findest du unter **Dashboard → Saison-Übersicht** oder **Paper-Review → Deadlines**. Erinnerungen kommen automatisch per E-Mail / Push-Benachrichtigung 7 Tage, 3 Tage und 1 Tag vor der Deadline.

### Welches Format muss das Paper haben?

- **Format:** PDF, IEEE A4-Template
- **Seitenzahl:** Maximal 5 Seiten (inkl. Abbildungen und Referenzen)
- **Pflichtabschnitte:** Abstract, Introduction, Concept/Design, Implementation, Results/Conclusion

### Ich habe eine Revision angefordert bekommen. Was genau muss ich tun?

1. **Paper-Review → Meine Papers → Paper → Feedback lesen** (öffentlicher Kommentar des Reviewers)
2. Paper gemäß Feedback überarbeiten (außerhalb des Systems, z.B. in Word/LaTeX)
3. Überarbeitetes Paper als PDF hochladen
4. Status wechselt automatisch auf „Überarbeitung eingereicht"

### Wie viele Revisions-Runden sind erlaubt?

Es gibt keine feste Grenze. Der Prozess geht so lange weiter bis das Paper angenommen oder abgelehnt wird. Jede Revision erhöht die Versionsnummer.

### Darf ich KI-Tools für das Paper verwenden?

Eingeschränkt ja:
- **Erlaubt:** Rechtschreibkorrektur, Grammatikverbesserung, Recherchehilfe (wenn manuell geprüft)
- **Nicht erlaubt:** Unkontrolliert generierte Inhalte, ungeprüfter Text, verschleierte Bedeutung

Bei Verdacht auf unerlaubte KI-Nutzung kann der Reviewer das Paper ablehnen. Das Team kann dann einen Nachweis der Eigenleistung einreichen (z.B. Google-Docs-Verlauf).

### Ich bin Reviewer und sehe kein Paper unter „Meine Papers". Warum?

Dir wurde noch kein Paper zugewiesen. Die Zuweisung erfolgt durch einen Admin oder Lead-Reviewer. Bitte beim Admin nachfragen.

---

## 3D-Druck

### Welche Dateiformate werden für Druckjobs akzeptiert?

STL und 3MF.

### Was bedeutet „Soft Limit" und „Hard Limit"?

- **Soft Limit:** Eine Warnung erscheint wenn du das Limit erreichst. Du kannst noch weitere Jobs beantragen.
- **Hard Limit:** Neue Druckjobs können nicht mehr beantragt werden bis das Limit zurückgesetzt wird (durch Admin).

### Mein Druckjob ist „Fehlgeschlagen". Was nun?

1. Druckjob öffnen → Fehlermeldung lesen (zeigt Ursache falls verfügbar)
2. Falls nötig: Datei überarbeiten (z.B. nicht-manifolde Geometrie reparieren)
3. Neuen Druckjob beantragen

### Kann ich Druckeinstellungen (Infill, Layer Height) angeben?

Ja, im Kommentarfeld beim Erstellen des Druckjobs. Der Admin/Print-Manager entscheidet ob und wie die Einstellungen übernommen werden.

### Wie lange dauert ein Druckjob?

Das hängt von der Größe und Komplexität des Teils ab. Während des Drucks siehst du den Fortschritt in % und die geschätzte Restzeit unter **3D-Druck → Meine Jobs**.

### Mein Druckjob wurde abgelehnt. Warum?

Die Ablehnungsbegründung steht im Job-Detail. Häufige Gründe:
- Datei ist nicht druckbar (nicht-manifolde Geometrie)
- Teil überschreitet die maximale Baugröße (220×220×250 mm)
- Druckjob verstößt gegen die Wettbewerbs-Regeln (z.B. falsches Material)
- Hard Limit bereits erreicht

---

## Benachrichtigungen

### Ich erhalte keine Push-Benachrichtigungen. Woran liegt das?

1. Browser-Berechtigung: **Browser-Einstellungen → Benachrichtigungen → BotballDashboard** → Erlauben
2. Profil-Einstellungen: **Profil → Benachrichtigungen** → gewünschte Ereignisse aktivieren
3. Gerät: Push-Benachrichtigungen funktionieren nur wenn die App/Tab nicht komplett geschlossen ist (außer bei PWA-Installation)

### Kann ich bestimmte Benachrichtigungen deaktivieren?

Ja. **Profil → Benachrichtigungen** → einzelne Ereignistypen an- oder abschalten.

---

## Technisches

### Welche Browser werden unterstützt?

- **Empfohlen:** Chrome 120+, Edge 120+, Firefox 120+
- **Eingeschränkt:** Safari 17+ (PWA und Web Push nur mit Einschränkungen)
- **Nicht unterstützt:** Internet Explorer

### Funktioniert das Dashboard auf dem Handy?

Ja, das Dashboard ist vollständig responsive. Für die beste Erfahrung empfehlen wir die PWA-Installation.

### Was tun bei einem Fehler oder einem Bug?

1. Seite neu laden (F5)
2. Browser-Cache leeren (Strg+Shift+R / Cmd+Shift+R)
3. Falls das Problem bleibt: Screenshot machen und beim Admin melden

### Wie lange sind meine Daten gespeichert?

Alle Daten bleiben mindestens bis zum Ende der Saison erhalten. Alte Saisons werden archiviert (nicht gelöscht). Personenbezogene Daten können auf DSGVO-Anfrage gelöscht werden (Admin kontaktieren).

---

## Admin-FAQ

### Wie setze ich das Passwort eines Benutzers zurück?

**Admin → Benutzer → Benutzer auswählen → Passwort zurücksetzen** → Der Benutzer erhält eine E-Mail mit einem Reset-Link.

### Wie archiviere ich eine Saison?

**Admin → Saisons → Saison auswählen → Archivieren** → Archivierte Saisons sind schreibgeschützt aber weiterhin einsehbar.

### Wie ändere ich die aktive Saison?

**Admin → Saisons → Neue/andere Saison → „Als aktiv setzen"** → Das Dashboard zeigt ab sofort die neue aktive Saison.

### Wie sehe ich wer einen Score geändert hat?

**Admin → System → Audit-Log → Filter: Aktion = score.updated** → Zeigt alle Score-Korrekturen mit Benutzer, Zeitstempel, altem und neuem Wert.

### Kann ich Test-Daten / Demo-Daten laden?

Nein, das System hat keine eingebaute Demo-Daten-Funktion. Für Testzwecke empfiehlt sich eine separate Staging-Instanz (Docker Compose mit eigener Datenbank).
