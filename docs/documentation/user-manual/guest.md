# Gast-Ansicht / Öffentliches Scoreboard

Dieses Handbuch beschreibt was ohne Login einsehbar ist und wie das öffentliche Scoreboard funktioniert.

---

## Öffentliche vs. Interne Ansicht

Das BotballDashboard hat zwei getrennte Bereiche:

| Bereich | Zugang | Inhalt |
|---|---|---|
| **Internes Dashboard** | Login erforderlich | Alle Daten – Scores, Papers, Druckjobs, Prep-Phase |
| **Öffentliches Scoreboard** | Ohne Login erreichbar | Nur freigegebene Turnierdaten |

Das öffentliche Scoreboard kann auf einer separaten Domain gehostet werden (z.B. `scoreboard.meineschule.at`).

---

## Öffentliches Scoreboard

### Was ist sichtbar?

- **Live-Rangliste:** Aktuelle Seeding-Platzierungen aller Teams (nach Abschluss der Seeding-Runden)
- **Double-Elimination-Bracket:** Turnierbaum mit aktuellen Ergebnissen
- **Team-Namen und Nummern:** Öffentliche Teamdaten
- **Aktuelle Phase:** Welche Runde läuft gerade?

### Was ist nicht sichtbar?

- Prep-Phase-Scores (interne Testläufe)
- Papers und Paper-Reviews
- Druckjobs
- Interne Notizen
- Scores anderer Teams in Echtzeit während des Spiels (erst nach Abschluss des Matches)

> Was genau öffentlich sichtbar ist, wird vom Admin konfiguriert.

---

## Live-Scoreboard (Großbildschirm)

Für die Anzeige auf einem Projektor oder TV beim Turnier:

- **URL:** `https://scoreboard.meineschule.at/live`
- Automatische Aktualisierung via WebSocket (kein Neuladen nötig)
- Vollbild-optimierte Ansicht (kein Header, kein Navigation)
- Zeigt: aktuelle Runde, laufendes Match, letzten Score, Rangliste

---

## PWA installieren (für bessere Erfahrung)

Das Scoreboard kann auch als App auf dem Handy installiert werden:

- **Android/Chrome:** Menü (⋮) → „Zum Startbildschirm hinzufügen"
- **iOS/Safari:** Teilen (□↑) → „Zum Home-Bildschirm"

Danach ist das Scoreboard offline als App verfügbar und aktualisiert sich automatisch sobald eine Verbindung besteht.
