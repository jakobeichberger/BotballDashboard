# Diplomarbeit: Automatisierte Auswertung und Verwaltung des Botball‑Wettbewerbs

## 1. Ausgangssituation und Hintergrund

Der **Botball‑Wettbewerb** ist eine internationale Robotik‑Challenge für Mittel‑ und Oberstufenklassen. Teams erhalten zu Beginn der Saison ein Robotik‑Kit (KIPR‑Wombat‑Controller, LEGO‑Teile, Motoren, Sensoren usw.) und bauen damit zwei autonome Roboter, die eine wechselnde Jahresaufgabe absolvieren. Die Saison startet jedes Jahr mit **Botball Educator Workshops** zwischen Januar und März, in denen Lehrkräfte und Mentoren geschult werden. Danach haben die Teams **sieben bis neun Wochen Zeit**, um ihre Roboter zu konstruieren, zu programmieren und das Dokumentationsmaterial online zu pflegen. Anschließend treten sie bei regionalen Turnieren an, um ihre Roboter vorzustellen und um Punkte zu kämpfen.

Die Turniere bestehen aus mehreren Runden:

- **Seeding‑Runden:** Teams laufen alleine auf dem Spielfeld. Die Punktzahl wird aus der Summe beider Spielfeldhälften berechnet, d. h. die erzielten Punkte auf der eigenen Seite plus die Punkte auf der gegenüberliegenden Seite【8243588275179†L861-L870】. Aus den drei Seeding‑Runden werden die **besten zwei Ergebnisse gemittelt**
- **Double‑Elimination‑Runden:** Im Anschluss treten die Teams im K.-o.-System gegeneinander an. Wer zweimal verliert, scheidet aus. Siege sind entscheidend; die Höhe der Punktzahl beeinflusst hier nicht die Platzierung.
- **Double Seeding & Alliance Matches:** Bei ausgewählten Turnieren (z. B. der Global Conference on Educational Robotics) gibt es Kopf‑an‑Kopf‑Seeding‑Runden und Kooperationsläufe, bei denen zwei Teams gemeinsam Punkte sammeln.
- **Dokumentation:** Zusätzlich zur Roboterleistung werden Projektplan, Code‑Dokumentation und Präsentation bewertet; diese fließt in das Gesamt­ergebnis ein.

Die Bewertung erfolgt anhand jährlicher **Scoring Sheets**, die Aufgabenbereiche wie „Botguy im Startfeld“, „sortierte Pompons“, „vollständige Tabletts“, „Getränke“ oder „Frittierstation“ enthalten. Für jedes Element wird die Anzahl der Objekte eingetragen und mit vordefinierten Multiplikatoren multipliziert. Ein Beispiel für das Seeding‑Punkteblatt 2025 zeigt zwei identische Spalten für „Side A“ und „Side B“; die addierten Punktzahlen beider Seiten ergeben das Rundenergebnis.

### Probleme der bisherigen Auswertung

1. **Manuelle Erfassung:** Punktblätter werden meist handschriftlich ausgefüllt und anschließend manuell in Tabellen übertragen – das ist zeitaufwendig und fehleranfällig.
2. **Komplexe Regeln:** Es gibt jährlich wechselnde Aufgaben und daraus resultierende neue Scoring‑Sheets, Multiplikatoren und Formeln. Die manuelle Berechnung (Seeding‑Durchschnitt, Double‑Elimination‑Formel, etc.) ist anfällig für Fehler.
3. **Unübersichtliche Ergebnisse:** Teams und Veranstalter haben kaum Überblick über Zwischenstände oder detaillierte Statistiken (z. B. Verteilung der Punkte auf einzelne Aufgabensegmente).
4. **Administrative Last:** Anmeldung, Teamverwaltung, Terminplanung, Deadlines und Kommunikation müssen separat organisiert werden.

## 2. Ziel der Diplomarbeit

Ziel des Projekts ist die Entwicklung einer **webbasierten Plattform**, die den Botball‑Wettbewerb in allen Phasen unterstützt. Kernstück ist die **automatisierte Auswertung der Scoring‑Sheets** aus Fotos oder PDF‑Scans. Darüber hinaus soll die Lösung die **Team‑ und Turnierverwaltung** erleichtern, die Berechnung der Gesamtpunktzahlen gemäß offizieller Formeln automatisieren und ein **Dashboard für Visualisierungen** bereitstellen. Das System muss flexibel genug sein, um sich jährlich an neue Scoring‑Sheets anzupassen.

## 3. Anforderungsanalyse und Funktionen

### 3.1 Erfassung und Auswertung der Scoring‑Sheets

- **Bild‑ und PDF‑Import:** Juror*innen laden Fotos oder gescannte PDFs der ausgefüllten Scoring‑Sheets hoch. Eine mobile App oder Weboberfläche soll den Upload direkt am Spielfeld ermöglichen.
- **Optische Zeichenerkennung (OCR):** Mithilfe von OCR und maschinellen Lernverfahren werden die handschriftlichen Einträge (Anzahlen und Notizen) gelesen und digital erfasst. Erkennungsschwierigkeiten (z. B. unleserliche Zahlen) werden durch visuelle Markierungen und manuelle Korrekturmöglichkeiten behandelt.
- **Flexible Sheet‑Vorlagen:** Da die Aufgaben jedes Jahr variieren, müssen Feldnamen, Multiplikatoren und Regeln über ein Konfigurationsmodul (z. B. YAML/JSON oder grafischer Editor) definiert werden können. So lässt sich der Bewertungsbogen für „Stack Attack 2026“ oder zukünftige Jahre ohne Programmieraufwand anpassen.
- **Berechnung nach offiziellen Formeln:** Das System implementiert die offiziellen Wertungsformeln:
  - Seeding‑Rundenscore = Summe der beiden Seiten; Durchschnitt der besten zwei Seeding‑Runden.
  - Double‑Elimination‑Runden werten nur Sieg/Niederlage; die Software verwaltet den Turnierbaum.
  - Gesamtpunkte: Kombination aus Seeding‑Punkten, Double‑Elimination‑Ergebnissen und Dokumentationspunkten (Formel aus dem Regelwerk).
- **Automatische Plausibilitätsprüfung:** Das System erkennt unrealistische Angaben (z. B. mehr Objekte als im Spiel vorhanden) und fordert zur Korrektur auf.

### 3.2 Team‑ und Turniermanagement

- **Teamverwaltung:** Anlegen und Bearbeiten von Teams mit Nummer, Name, Schulkontaktdaten, Mitgliedern und Betreuer*innen. Optionale Funktionen: Verwaltung von Teilnahmegebühren, Versandstatus des Kits, Upload von Projektplänen und Dokumenten.
- **Turnierplanung:** Erstellung von Zeitplänen für Seeding‑Runden, Double‑Elimination‑Brackets, Alliance‑Matches und Übungszeiten. Automatische Generierung der Turnierbäume und Veröffentlichung auf der Plattform.
- **Termine und Deadlines:** Übersicht über wichtige Termine (Registrierung, Abgabe der Dokumentation, Workshop‑Termine, regionale Turniere). Automatische Erinnerungen per E‑Mail/Push‑Benachrichtigung.
- **Rollen und Rechte:** Unterscheidung zwischen Administrator*innen, Juror*innen, Team‑Mentor*innen und Zuschauer*innen. Jeder sieht und bearbeitet nur die für ihn relevanten Daten.

### 3.3 Echtzeit‑Dashboard und Auswertungen

- **Ranglisten in Echtzeit:** Anzeige der aktuellen Platzierungen während der Seeding‑Runden, Double‑Elimination‑Phase und Alliance‑Matches. Berücksichtigung der offiziellen Regeln (z. B. Sortierung nach Durchschnittswert der besten Seeding‑Runs).
- **Detailansichten pro Team:** Aufschlüsselung, wie viele Punkte ein Team in jedem Aufgabensegment erzielt hat (z. B. Anzahl sortierter Pompons, erledigte Servierstationen). Vergleich verschiedener Runden eines Teams.
- **Statistische Analyse:** Graphen und Tabellen zur Verteilung der Punkte (z. B. Boxplots für alle Teams), Heatmaps der häufigsten Fehler, Analyse der Auswirkung einzelner Spielzüge auf das Gesamtergebnis. Erkennung von Trends über mehrere Jahre hinweg.
- **Historische Daten:** Archivierung der Ergebnisse früherer Saisons. So können Teams ihre Leistung im Laufe der Jahre vergleichen oder Trainer*innen Best‑Practice‑Beispiele extrahieren.
- **Exportfunktionen:** Generierung offizieller Ergebnislisten und PDF‑Berichte, Export in CSV/Excel zur Weiterverarbeitung oder Veröffentlichung auf der KIPR‑Webseite.

### 3.4 Erweiterte Features (Optionen für Mehrwert)

- **Mobile Scoring‑App:** Eine Smartphone‑App, mit der Juror*innen Ergebnisse direkt am Spielfeld fotografieren, scannen und hochladen können. Offline‑Funktionalität für Turniere ohne zuverlässige Internetverbindung; Synchronisation nach Wiederherstellung.
- **Live‑Anzeigetafel (Scoreboard):** Integration eines öffentlichen Displays, das die aktuellen Ergebnisse, nächsten Matches und Statistiken anzeigt. Durch Schnittstellen (z. B. WebSocket/API) können Veranstalter die Live‑Daten auf Großbildschirmen präsentieren.
- **Benutzerdefinierte Benachrichtigungen:** Teams erhalten Push‑Meldungen bei Änderungen des Turnierplans, Veröffentlichung neuer Regeln oder Ablauftermine. Juror*innen werden informiert, wenn neue Scoring‑Sheets zur Überprüfung bereitstehen.
- **Mehrsprachigkeit:** Die Oberfläche sollte mindestens Deutsch und Englisch unterstützen, um internationalen Teilnehmer*innen gerecht zu werden.
- **Sicherheits‑ und Compliance‑Funktionen:** Protokollierung aller Änderungen an Punktblättern (Audit Trail) und Rollenkonzepte zum Schutz sensibler Daten.
- **Integrationen:** 
  - **KIPR‑Daten:** Falls verfügbar, Anbindung an die offiziellen Score‑Listen oder Turniersoftware, um Daten zu synchronisieren. 
  - **Kamera‑Streams:** Für virtuelle Turniere (z. B. pandemiebedingte Remote‑Events), Unterstützung der vom Regelwerk geforderten zwei Kameras【8243588275179†L944-L949】 und Upload von Video‑Beweisen.
- **Analyse der „Spirit of Botball“‑Regeln:** Das System könnte ungewöhnliche Muster (z. B. extrem hohe Punktezahlen in Zusammenarbeit mit bestimmten Teams) markieren, um mögliche Regelverstöße (Koalitionen) zu erkennen【8243588275179†L893-L896】.

### 3.5 Saisonverwaltung über mehrere Jahre

Ein Botball‑Wettbewerb wird immer als „Saison“ organisiert, meist bezogen auf das Kalender‑ oder Schuljahr. Damit Veranstalter und Schulen ihre Turniere langfristig planen und historische Daten sauber trennen können, sollte das System eine **saisonübergreifende Verwaltung** ermöglichen:

- **Separate Saisonobjekte:** Jede Saison (z. B. 2025 oder 2026) wird als eigenes Objekt geführt, in dem Turniere, Scoring‑Sheets, Spielpläne und Teams getrennt voneinander verwaltet werden. So können mehrere Saisons parallel existieren, ohne dass Daten kollidieren.
- **Klonen und Vorlagen:** Admins können eine bestehende Saison als Vorlage verwenden, um Konfigurationen – wie Rollenrechte, Turnierstruktur oder Bewertungskategorien – in eine neue Saison zu übernehmen. Änderungen an der neuen Saison wirken sich nicht auf das Archiv aus.
- **Archivierung und Zugriff:** Abgeschlossene Saisons werden im System archiviert, bleiben aber über eine Liste abrufbar. Teams, Mentor*innen und Juror*innen können vergangene Ergebnisse einsehen, ohne dass laufende Turniere beeinflusst werden. Dies erleichtert z. B. die Vorbereitung auf das nächste Jahr und die Evaluation der eigenen Fortschritte.
- **Team‑Historie:** Teams können über mehrere Jahre hinweg verfolgt werden. Die Plattform verknüpft ihre Jahresstatistiken und ermöglicht einen Vergleich der Leistungsentwicklung oder der Erfolge in unterschiedlichen Jahren.
- **Saisonübergreifende Auswertungen:** Dashboards und Statistiken können aggregierte Analysen über mehrere Saisons hinweg erstellen (z. B. Durchschnitts‑Seeding‑Scores der letzten fünf Jahre). Dadurch lassen sich Trends erkennen, wie die Punkteverteilung sich verändert oder welche Aufgabenbereiche Teams langfristig Schwierigkeiten bereiten.
- **Registrierung und Rollout:** Für kommende Jahre können Saisonobjekte frühzeitig angelegt und für die Anmeldung freigeschaltet werden. Dies unterstützt eine frühzeitige Planung und erleichtert die Kommunikation zu Deadlines und Workshops.
- **Export von Mehrjahresdaten:** Neben den Jahresberichten können auch saisonübergreifende Berichte (z. B. Zusammenfassung der letzten drei Jahre) als PDF oder CSV exportiert werden, um Analysen im Unterricht oder bei Sponsorenpräsentationen zu nutzen.

## 4. Technische Umsetzung (Vorschlag)

1. **Architektur:** Web‑Applikation mit Micro‑Service‑Ansatz. Frontend in React oder Vue.js, Backend in Python (Django/FastAPI) oder Node.js. Mobile App als Progressive Web App oder natives Flutter‑Projekt.
2. **Datenbank:** Relationales DBMS (PostgreSQL) zur strukturierten Ablage von Teams, Turnieren, Score‑Sheets und Nutzer*innen. Historische Daten können versioniert gespeichert werden.
3. **OCR und Bildverarbeitung:** Einsatz von Open‑Source‑Bibliotheken wie **Tesseract OCR** für Texterkennung. Zur Verbesserung der Erkennung können neuronale Netze (CNNs) für Handschriftenerkennung trainiert oder vortrainierte Modelle verwendet werden (z. B. TensorFlow/Keras). Bildvorverarbeitung (Kontrastanpassung, Entzerrung) mit OpenCV.
4. **Konfigurierbare Scoring‑Engine:** Implementierung einer regelbasierten Engine, die die konfigurierten Aufgabenfelder, Multiplikatoren und Formeln interpretiert. Eine grafische Admin‑Oberfläche ermöglicht das Anlegen neuer Wettbewerbsjahre, das Definieren von Kategorien und das Einstellen der Scoring‑Formeln.
5. **Turnier‑/Bracket‑Generator:** Algorithmen zur Erstellung und Visualisierung von Double‑Elimination‑Brackets und Zeitplänen. Hier können bestehende Bibliotheken genutzt werden (z. B. „Challonge API“), oder eigenständig implementierte Bracket‑Logik.
6. **Dashboard und Datenvisualisierung:** Nutzung von Chart‑Bibliotheken wie Chart.js oder D3.js zur Darstellung von Diagrammen. Für komplexere Analysen kann Python/Pandas als Backend‑Analyse genutzt und die Ergebnisse über APIs bereitgestellt werden.
7. **Sicherheit:** Implementierung von OAuth2‑ oder JWT‑basierten Authentifizierungsmechanismen. Verschlüsselte Speicherung sensitiver Informationen. DSGVO‑Konformität (Betroffenenrechte, Datenschutz).
8. **Deployment:** Container‑basiertes Deployment (Docker/Kubernetes) für einfache Skalierung. Optionale Cloud‑Anbindung (z. B. AWS, Azure) für verteilte Turniere.

## 5. Projektablauf und Arbeitspakete

Eine Maturaklasse könnte das Projekt arbeitsteilig entwickeln. Ein Vorschlag für Arbeitspakete (abhängig von der Gruppenstärke):

1. **Anforderungsanalyse und Konzeption:** Recherche der Botball‑Regeln und Erstellung des Pflichtenhefts. Definition der Datenmodelle und Systemarchitektur.
2. **OCR‑Modul:** Prototypische Entwicklung der Bild‑ und PDF‑Verarbeitung, Training und Test der Texterkennung.
3. **Scoring‑Engine & Konfiguration:** Entwicklung des Moduls zur Interpretation der Scoring‑Sheets, inklusive Konfigurationsschnittstelle für neue Aufgabenjahre.
4. **Team‑ und Turniermanagement:** Implementierung der Datenbank und des Backends zur Verwaltung von Teams, Spielplänen und Brackets.
5. **Frontend / Benutzeroberflächen:** Entwicklung der Web‑Oberfläche und ggf. der mobilen App. Umsetzung der Dashboards und Scoreboards.
6. **Integration & Testing:** Zusammenführen der Module, End‑to‑End‑Tests mit echten Scoring‑Sheets, Usability‑Tests mit Juror*innen und Teams.
7. **Dokumentation und Präsentation:** Erstellung einer technischen Dokumentation, Benutzerhandbuch, Präsentation der Ergebnisse und Reflexion (Lessons Learned).

## 6. Erwartete Ergebnisse und Nutzen

- **Fehlerfreie und schnelle Auswertung:** Durch automatisierte OCR‑Erfassung und regelbasierte Berechnung werden Rechenfehler minimiert und Ergebnisse stehen sofort zur Verfügung.
- **Verbesserte Transparenz:** Teams und Veranstalter bekommen einen unmittelbaren Überblick über Ranglisten, detaillierte Punkteverteilung und Fortschritte im Turnier.
- **Flexibilität für kommende Jahre:** Dank des konfigurierbaren Scoring‑Moduls lässt sich das System einfach an neue Spielregeln anpassen, ohne großen Entwicklungsaufwand.
- **Effiziente Organisation:** Ein zentrales Tool für Team‑Verwaltung, Terminplanung, Deadlines und Kommunikation reduziert den administrativen Aufwand und verbessert die Zusammenarbeit.
- **Lern‑ und Analyseplattform:** Historische Daten und Statistiken fördern den Wissenstransfer zwischen Jahren und erhöhen die Qualität der Botball‑Projekte. Die Plattform kann darüber hinaus im Unterricht eingesetzt werden, um Datenanalyse‑ und Software‑Entwicklungskompetenzen zu fördern.

---
**Zusammenfassung:** Diese Diplomarbeit soll eine ganzheitliche Lösung zur Verwaltung des Botball‑Wettbewerbs entwickeln. Sie baut auf einer fundierten Analyse des Wettbewerbablaufs auf und integriert moderne Technologien zur automatischen Erfassung, Auswertung und Darstellung von Wettbewerbsergebnissen. Durch modulare Architektur und flexible Konfiguration bleibt die Lösung langfristig einsatzfähig und bildet einen wertvollen Beitrag für Schulen, die Robotikprojekte im Rahmen des Botball‑Programms durchführen.
