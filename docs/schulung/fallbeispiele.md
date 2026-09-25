# Fallbeispiele aus dem Projekt

Echte Situationen aus der Entwicklung des BotballDashboards. Jede ist einem Buchstaben aus LEDVV zugeordnet.

## 1. „Testen auf Zeus“ – fehlende Lage

**Prompt:** „Testen auf Zeus“

**Was fehlte:** Was „Zeus“ ist (unser Proxmox-Server), wie man hinkommt und dass die KI dort gar keinen Zugriff hat.

**Folge:** Rückfragen, dann ein Umweg: Die KI hat lokal einen Docker-Server gestartet und die Installation dort durchgespielt.

**Besser:** „Teste die neue Version auf unserem Proxmox-Server Zeus ([Adresse], Zugang über [Weg]). Fertig, wenn alle Container laufen und `verify-deployment.sh` nur PASS meldet. Falls du Zeus nicht erreichst: sag es sofort und teste stattdessen lokal mit Docker.“

## 2. Der falsche Repo-Name – fehlende Versorgung

**Prompt:** „GitHub-Repo resquelog. Improved“

**Was fehlte:** Der exakte Name (Besitzer/Repo) und die Zugriffsrechte.

**Folge:** Fünf Fehlversuche. Am Ende kam die Design-Vorlage doch über die Webseite.

**Besser:** Den Link aus der Adresszeile kopieren. Und gleich sagen, was zu tun ist, wenn der Zugriff fehlt.

## 3. „CI nur manuell“ – fehlende Verbindung

**Situation:** Früh im Projekt wurde entschieden, dass die automatischen Tests auf GitHub (CI) nur manuell starten.

**Was fehlte:** Die Entscheidung stand nur im Chat, nicht in einer Datei im Projekt.

**Folge:** Ein späterer Agent kannte sie nicht, und die CI lief wieder automatisch. Sie musste zurückgestellt werden.

**Besser:** „Ab jetzt gilt: CI nur manuell. Schreib das in die Projektregeln.“ Agenten lesen eine Datei wie `CLAUDE.md` bei jedem Start.

## 4. Parallele Agenten auf altem Stand – fehlendes gemeinsames Lagebild

**Situation:** Mehrere Agenten haben gleichzeitig an Fix-Paketen gearbeitet. Zwei davon sind von einem älteren Code-Stand gestartet.

**Folge:** Beim Zusammenführen gab es Konflikte in 19 Dateien, die mit Nacharbeit gelöst werden mussten.

**Besser:** Im Auftrag den Ausgangsstand nennen (Branch und Commit) und einen Agenten bestimmen, der zusammenführt und prüft.

## 5. Wenn der Test lügt – Durchführung ohne echte Prüfung

**Situation:** Die Paper-Punkte gingen fast gar nicht in die Gesamtwertung ein: höchstens 0,005 statt 0,5 Punkte.

**Ursache:** Die Formel teilte durch 100, obwohl der Wert schon zwischen 0 und 1 lag. Der dazugehörige Test rechnete mit 80, einem Wert, den die App nie speichert.

**Gefunden:** Erst als eine KI den Auftrag bekam, alle Anforderungen gegen den Code zu prüfen.

**Lehre:** Grüne Tests beweisen nur, was sie wirklich testen. Realistische Werte verlangen.

## 6. Echte Ergebnisse nachrechnen – ein guter Entschluss

**Auftrag:** „Übernimm die offiziellen Regeln 2026. Fertig, wenn das Dashboard die veröffentlichten ECER-2026-Ergebnisse exakt nachrechnet.“

**Ergebnis:**

- Botball: 18 von 18 Plätzen stimmen.
- Paper: 26 von 26 Rängen stimmen.
- JBC: 14 von 14 Plätzen stimmen.
- Zwei Widersprüche zwischen den offiziellen Amendments und den veröffentlichten Ergebnissen hat der Agent gemeldet, statt zu raten.

**Lehre:** Ein messbares „Fertig, wenn …“ ist der stärkste Hebel für Qualität.

## 7. Erst lesen, dann ändern

**Auftrag 1:** „Suche nach Verbesserungen“. Die Agenten durften nichts ändern und haben 59 belegte Befunde geliefert.

**Auftrag 2:** Danach kam „Alles beheben“, aufgeteilt in vier Pakete, jedes mit Tests.

**Ergebnis:** 1 679 Backend-Tests grün.

**Lehre:** Einen Plan zu korrigieren kostet einen Satz. Falschen Code zu korrigieren kostet eine Stunde.
