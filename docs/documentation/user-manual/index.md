# BotballDashboard – Benutzerhandbuch

Willkommen im BotballDashboard. Dieses Handbuch erklärt die Bedienung aller Module für alle Benutzerrollen.

---

## Inhaltsverzeichnis

- [Rollen im System](#rollen)
- [Erster Login](#erster-login)
- [Navigation](#navigation)
- [Sprache & Design](#sprache--design)
- [Benachrichtigungen & PWA](#benachrichtigungen)
- [PDF- und CSV-Export](#export)
- [Profilverwaltung](#profil)
- [Module im Überblick](#module)
- [FAQ](faq.md)

---

## Rollen {#rollen}

| Rolle | Beschreibung | Handbuch |
|---|---|---|
| **Admin** | Vollzugriff – verwaltet Saisons, Teams, Benutzer, alle Module | [Admin-Handbuch](admin.md) |
| **Juror** | Gibt Scores ein und korrigiert diese während des Turniers | [Juror-Handbuch](juror.md) |
| **Reviewer** | Bewertet eingereichte Papers, fordert Revisionen an | [Reviewer-Handbuch](reviewer.md) |
| **Mentor** | Betreut ein oder mehrere Teams, Lesezugriff auf Teamdaten | [Mentor-Handbuch](mentor.md) |
| **Gast** | Nur Lesezugriff auf öffentliche Inhalte | [Gast-Ansicht](guest.md) |

> Rollen können kombiniert werden: Eine Person kann gleichzeitig Mentor und Reviewer sein.

---

## Erster Login {#erster-login}

1. URL des BotballDashboard im Browser öffnen
2. E-Mail-Adresse und Passwort eingeben
3. Bei erstem Login: Passwort aus Einladungs-E-Mail verwenden und anschließend sofort ändern

### Passwort vergessen

Auf der Login-Seite „Passwort vergessen" klicken → E-Mail mit Reset-Link kommt binnen weniger Minuten.

---

## Navigation {#navigation}

### Desktop (Laptop/PC)
- **Sidebar links:** Hauptnavigation mit allen Modulen
- **Topbar:** Sprachumschalter (DE | EN), Dark/Light Mode, Benachrichtigungen, Profil

### Mobil (Handy/Tablet)
- **Hamburger-Menü** (☰) oben links → öffnet Navigation
- **Bottom-Navigation** für häufig genutzte Bereiche (Score eingeben, Matches)

---

## Sprache & Design {#sprache--design}

- **Sprache:** Topbar → Flagge/Sprachkürzel → `DE` oder `EN` auswählen
- **Dark/Light Mode:** Topbar → Mond/Sonne-Icon
- Beide Einstellungen werden gespeichert und bleiben nach dem Logout erhalten.

---

## Benachrichtigungen & PWA {#benachrichtigungen}

Das BotballDashboard kann Push-Benachrichtigungen auf dem Gerät senden:

1. Beim ersten Login erscheint eine Anfrage: „Benachrichtigungen erlauben?"
2. Diese bestätigen
3. Ab sofort kommen Benachrichtigungen bei wichtigen Events (neues Match, Paper-Status, Druckjob fertig)

**PWA installieren** für beste Erfahrung:
- **Android/Chrome:** Menü → „Zum Startbildschirm hinzufügen"
- **iOS/Safari:** Teilen-Symbol → „Zum Home-Bildschirm"

---

## PDF- und CSV-Export {#export}

Alle wichtigen Daten können als **PDF** (druckfertig, mit Logo und Tabellen) oder **CSV** (für Excel/Sheets) heruntergeladen werden.

### Verfügbare Exporte

| Modul | Formate | Berechtigung |
|---|---|---|
| Rangliste (Scoring) | PDF, CSV | `scoring:read` oder `dashboard:read` |
| Wertungen (alle Matches) | CSV | `scoring:read` |
| Paper-Review-Übersicht | PDF, CSV | `papers:admin` |
| 3D-Druck-Report | PDF | `printing:admin` |
| Team-Liste | PDF, CSV | `teams:read` |

### So wird exportiert

1. In das jeweilige Modul navigieren (z.B. **Scoring → Rangliste**)
2. Auf den **PDF**- oder **CSV**-Button oben rechts klicken
3. Der Download startet automatisch

> CSV-Dateien sind UTF-8 (mit BOM) kodiert und öffnen sich direkt in Excel ohne Zeichensatz-Probleme.

---

## Profilverwaltung {#profil}

**Profil → Mein Konto:**
- Name und E-Mail ändern
- Passwort ändern
- Benachrichtigungseinstellungen
- Sprache und Dark/Light Mode-Präferenz
- Geräteverwaltung (Push-Abonnements pro Gerät)

---

## Module im Überblick {#module}

| Modul | Beschreibung | Verfügbar für |
|---|---|---|
| **Dashboard** | Saison-Übersicht, Announcements, Stats | Alle eingeloggten Benutzer |
| **Scoring** | Score-Eingabe, Rangliste, Live-Scoreboard | Juror, Admin |
| **Paper-Review** | Paper einreichen, bewerten, Revisionen | Mentor (einreichen), Reviewer (bewerten), Admin |
| **3D-Druck** | Druckjobs beantragen und verwalten | Mentor (beantragen), Admin (verwalten) |
| **Teams** | Teamdaten einsehen und verwalten | Alle eingeloggten Benutzer (je nach Rolle) |
| **Saisons** | Saison- und Phasenverwaltung | Admin |
| **Benutzerverwaltung** | Benutzer einladen, Rollen vergeben | Admin |
| **Exporte** | PDF- und CSV-Downloads für alle Module | Je nach Modul-Berechtigung |
| **Öffentliches Scoreboard** | Live-Rangliste ohne Login | Öffentlich / Gast |

---

Weiterführende Dokumentation: [FAQ](faq.md) | [Admin-Handbuch](admin.md) | [Juror-Handbuch](juror.md) | [Reviewer-Handbuch](reviewer.md) | [Mentor-Handbuch](mentor.md) | [Gast-Ansicht](guest.md)
