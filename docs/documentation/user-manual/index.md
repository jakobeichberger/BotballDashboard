# BotballDashboard – Benutzerhandbuch

Das BotballDashboard verwaltet Botball-Turniere, von der Saisonplanung über die Wertung am Spieltisch bis zu Paper-Review und 3D-Druck. Dieses Kapitel gilt für alle Rollen. Die Details stehen in den Rollen-Handbüchern.

| Handbuch | Für |
|---|---|
| [Admin](admin.md) | Organisation: Benutzer, Saisons, Events, Wertungsregeln, Paper- und Druckprozess |
| [Juror](juror.md) | Wertung am Spieltisch, Bestätigung, Brackets |
| [Reviewer](reviewer.md) | Begutachtung der Papers |
| [Mentor](mentor.md) | Team-Betreuung: eigenes Team, Wertungen, Paper, 3D-Druck, Scouting |
| [Gast](guest.md) | Lesender Zugang und öffentliche Anzeige |
| [FAQ](faq.md) | Häufige Fragen |

---

## Inhaltsverzeichnis

1. [Grundprinzip: alles hängt am Event](#grundprinzip-alles-hängt-am-event)
2. [Rollen](#rollen)
3. [Anmelden und Passwort vergessen](#anmelden-und-passwort-vergessen)
4. [Navigation](#navigation)
5. [Profil](#profil)
6. [Benachrichtigungen](#benachrichtigungen)
7. [Offline und Handy (PWA)](#offline-und-handy-pwa)
8. [Exporte](#exporte)
9. [Öffentliche Anzeige](#öffentliche-anzeige)

---

## Grundprinzip: alles hängt am Event

Eine **Saison** enthält das Regelwerk eines Jahres: aktive Module, Kategorien, Formeln, Tie-Breaker, Score-Sheet-Vorlagen und Termine. Ein **Event** ist ein konkretes Turnier dieser Saison, z. B. ein Regionalturnier, ECER oder GCER.

Die Oberfläche ist eventzentriert. Alle Arbeitsseiten liegen unter `/events/<Event-ID>/…`, etwa `/events/…/scoring` oder `/events/…/papers`. Oben in der Seitenleiste wählst du das Event. Nach dem Login öffnet sich automatisch das laufende Event (Status `live`) oder, wenn keines läuft, das erste. Gibt es noch gar kein Event, landen Organisatoren im Einrichtungsassistenten (`/setup`).

Welche Bereiche ein Event hat, legt die Organisation pro Event fest. Mögliche Module sind Seeding, Double Elimination, Paper, Dokumentation, Aerial, 3D-Druck und Bot-Galerie. Ein abgeschaltetes Modul verschwindet aus der Navigation. Wer die Seite direkt aufruft, sieht „Dieses Modul ist für dieses Event nicht aktiv".

---

## Rollen

Die Rechte der fünf Standardrollen werden bei der Installation angelegt (Migrationen `0002`–`0017`). Admins können sie ändern und eigene Rollen anlegen.

| Recht | admin | juror | reviewer | mentor | guest |
|---|:-:|:-:|:-:|:-:|:-:|
| Dashboard ansehen (`dashboard:read`) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Saisons und Termine ansehen (`seasons:read`) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Events ansehen (`events:read`) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Event verwalten: Phasen, Teams, Zeiten (`events:write`) | ✅ | ✅ | – | – | – |
| Zeitplan erzeugen, Setzliste, Event löschen (`events:admin`) | ✅ | – | – | – | – |
| Teams ansehen (`teams:read`) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Eigenes Team pflegen (`teams:write`) | ✅ | – | – | ✅ | – |
| Teams anlegen/löschen, Konten verknüpfen (`teams:admin`) | ✅ | – | – | – | – |
| Wertungen ansehen (`scoring:read`) | ✅ | ✅ | – | ✅ | ✅ |
| Wertungen erfassen (`scoring:write`) | ✅ | ✅ | – | ✅ ¹ | – |
| Bestätigen, korrigieren, DE/Aerial/Doku, Statistik (`scoring:admin`) | ✅ | ✅ | – | – | – |
| Punkteformeln (`scoring:formulas`) | ✅ | – | – | – | – |
| Papers lesen (`papers:read`) | ✅ | – | ✅ | ✅ ¹ | – |
| Paper einreichen (`papers:write`) | ✅ | – | – | ✅ ¹ | – |
| Papers begutachten (`papers:review`) | ✅ | – | ✅ | – | – |
| Paper-Prozess steuern (`papers:admin`) | ✅ | – | – | – | – |
| Druckjobs ansehen/einreichen (`printing:read/write`) | ✅ | – | – | ✅ ¹ | – |
| Drucker, Kontingente, Freigaben (`printing:admin`) | ✅ | – | – | – | – |
| Ankündigungen (`dashboard:write`) | ✅ | – | – | – | – |
| Benutzer und Rollen (`users:*`, `roles:*`) | ✅ | – | – | – | – |

¹ Nur für das eigene Team. Das eigene Team ist jedes Team, in dem dein Benutzerkonto als Mitglied verknüpft ist. Die Verknüpfung setzt die Organisation.

---

## Anmelden und Passwort vergessen

Konten legt die Organisation an. Eine Selbstregistrierung gibt es nicht. Bei eingerichtetem Mailserver bekommst du eine Hinweis-Mail. Das Passwort teilt dir die Organisation mit.

**Passwort vergessen:**

1. Auf der Login-Seite **„Passwort vergessen?"** wählen.
2. E-Mail-Adresse eingeben. Du bekommst einen Link, der **eine Stunde gültig** und nur einmal verwendbar ist. Aus Datenschutzgründen sagt die Seite nicht, ob die Adresse existiert.
3. Über den Link ein neues Passwort setzen. Danach sind alle bisherigen Sitzungen beendet.

Ohne eingerichteten Mailserver kommt keine E-Mail an. Dann setzt ein Admin das Passwort unter **Einstellungen → Benutzer**.

**Passwort-Regeln:** mindestens 10 Zeichen und höchstens 72 Byte (etwa 72 Buchstaben ohne Umlaute; Umlaute zählen doppelt, Emojis vierfach), nicht nur ein wiederholtes Zeichen, nicht die eigene E-Mail-Adresse und kein bekanntes oder geleaktes Passwort wie `password123` oder `qwertzuiop` (Groß-/Kleinschreibung zählt dabei nicht).

Das Zugangs-Token läuft nach 15 Minuten ab und wird automatisch erneuert, solange die Anmeldung gültig ist (bis zu 30 Tage). **Abmelden** beendet nur die Sitzung auf diesem Gerät.

---

## Navigation

- **Seitenleiste:** Event-Auswahl, darunter die Bereiche, für die du Rechte hast und die im Event aktiv sind. Auf dem Handy öffnet das Menü-Symbol die Leiste.
- **Kopfzeile:**
  - Glocke mit der Benachrichtigungszentrale;
  - Push aktivieren;
  - Sprache (Deutsch/English);
  - Design (hell/dunkel/System);
  - Abmelden;
  - Link zum Profil.
- Links auf Teams, Papers oder Druckjobs öffnen die Detailseite im aktuellen Event.

Übliche Bereiche:

- Dashboard, Deadlines;
- Teams, Bot-Galerie;
- Zeitplan, Wertung, OCR-Prüfung, Scouting, Rangliste & Ergebnisse, Performance, Statistik & Anomalien, Punkteformeln;
- Paper-Review, 3D-Druck;
- Event-Verwaltung, Admin-Einstellungen.

Du siehst nur, wofür deine Rolle Rechte hat.

---

## Profil

Unter **Profil** (Link in der Kopfzeile, `/events/…/profile`):

| Abschnitt | Inhalt |
|---|---|
| Profildaten | Anzeigename |
| Darstellung | Theme hell / dunkel / System. Wird im Konto gespeichert und gilt auf allen Geräten. |
| Sprache | Deutsch / English, ebenfalls im Konto gespeichert. Einige Seiten sind noch nur auf Deutsch. |
| E-Mail-Adresse | Ändern, mit Passwort bestätigen |
| Passwort | Ändern; alle anderen Sitzungen werden beendet |
| Benachrichtigungen | Push pro Kategorie ein/aus (siehe unten), Push für dieses Gerät aktivieren |
| Datenschutz | **Datenexport** (alle über dich gespeicherten Daten als JSON) und **Konto löschen**. Die Löschung anonymisiert das Konto und verlangt das Passwort. Historische Einträge wie Wertungen bleiben ohne Personenbezug erhalten. |

---

## Benachrichtigungen

- **Benachrichtigungszentrale** (Glocke): die letzten Meldungen, die an dich oder an alle gingen. Du kannst einzelne oder alle als gelesen markieren.
- **Push** (Web Push): pro Gerät aktivieren, im Profil oder in der Kopfzeile. Voraussetzung ist, dass die Installation VAPID-Schlüssel hat. Kategorien, jede einzeln abschaltbar:

| Kategorie | Beispiele |
|---|---|
| Match beginnt bald | Aufruf und Zeitplanänderungen deiner Matches |
| Score korrigiert | eine Wertung deines Teams wurde nachträglich geändert |
| Deadlines & Erinnerungen | Saison- und Paper-Deadlines 7, 3 und 1 Tag vorher, Review-Erinnerungen |
| Paper-Status | Einreichung, Zuweisung, Entscheidung |
| Druckaufträge | genehmigt, gestartet, fertig, fehlgeschlagen |
| Ankündigungen | veröffentlichte Ankündigungen der Organisation |

- **E-Mail:** Deadline-Erinnerungen gehen auch per E-Mail an die Teammitglieder, wenn ein Mailserver eingerichtet ist. Ebenso die Hinweis-Mail bei Kontoanlage und der Passwort-Reset-Link.
- **Kalender:** Unter **Deadlines** kannst du einen persönlichen iCal-Feed abonnieren (siehe [Mentor-Handbuch](mentor.md#deadlines-und-kalender)).

---

## Offline und Handy (PWA)

Das Dashboard lässt sich als App installieren: im Browser „Zum Startbildschirm hinzufügen" bzw. „Installieren". Die Seiten sind für Handy und Tablet ausgelegt.

**Ohne Verbindung:**

- Ein Banner zeigt: „Keine Verbindung – Wertungen werden lokal gespeichert, alle anderen Änderungen sind bis zur Wiederverbindung gesperrt."
- **Wertungen** (Event-Wertung, Wettbewerbs- und Übungsläufe) werden auf dem Gerät zwischengespeichert. Sie werden automatisch übertragen:
  - beim Wiederverbinden;
  - beim App-Start;
  - jede Minute.
- Nur dein eigenes Konto überträgt deine gespeicherten Wertungen. Doppelte Übertragungen sind ausgeschlossen, jede Wertung hat einen eindeutigen Schlüssel.
- Die Kopfzeile zeigt, wie viele Wertungen warten oder fehlgeschlagen sind. Bei einem **Konflikt** (das Match wurde inzwischen anders gewertet) oder einem Fehler kannst du je Eintrag erneut senden, trotzdem speichern oder verwerfen.
- Zuletzt geladene Seiten (Event, Teams, Zeitplan, Schema) bleiben lesbar. Alle anderen Änderungen sind offline gesperrt.

---

## Exporte

Export-Buttons gibt es auf den jeweiligen Seiten:

| Wo | Was | Recht |
|---|---|---|
| Rangliste & Ergebnisse | Seeding-Rangliste CSV/PDF, Gesamtwertung CSV/PDF (mit allen Formelwerten), Wertungen CSV | `scoring:read` |
| Paper-Review | Paper-Übersicht CSV/PDF, Reviews CSV | `papers:admin` |
| 3D-Druck | Druckbericht PDF | `printing:admin` |
| Teams | Teamliste CSV/PDF; Mehrjahresvergleich aller Teams CSV (nur mit `scoring:admin` oder `teams:admin`) | `teams:read` |
| Team-Detail | Team-Bericht PDF, Historie CSV | `teams:read` |
| Statistik | Läufe CSV | `scoring:admin` |
| Scouting | Scouting-Bericht PDF | `scoring:read` |

CSV-Dateien sind UTF-8 mit BOM und lassen sich direkt in Excel öffnen.

---

## Öffentliche Anzeige

Für Zuschauer und Großbildschirme gibt es pro Event eine Seite ohne Login: `https://<domain>/public/<event-slug>`. Sie ist erreichbar, sobald das Event den Status `published`, `live` oder `completed` hat. Angezeigt wird nur, was die Organisation freigegeben hat: Rangliste, Zeitplan und Bracket, Detailergebnisse, Ankündigungen. Die Seite aktualisiert sich live und rotiert zwischen den Bereichen. Einen QR-Code auf die Seite zeigt sie selbst an. Details: [Gast-Handbuch](guest.md).
