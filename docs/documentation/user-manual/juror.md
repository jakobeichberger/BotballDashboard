# Juror-Handbuch

Dieses Handbuch richtet sich an Schiedsrichter (Jurors), die während Testläufen und beim offiziellen Turnier Scores eingeben und verwalten.

---

## Übersicht Juror-Funktionen

| Funktion | Wo |
|---|---|
| Score eingeben | Scoring → Aktuelles Match |
| Match-Liste einsehen | Scoring → Turnier |
| Score korrigieren | Scoring → Match → Score → Bearbeiten |
| Yellow/Red Card vergeben | Scoring → Turnier → Team → Karte vergeben |
| Rangliste einsehen | Scoring → Rangliste |
| Rangliste exportieren | Scoring → Rangliste → PDF / CSV |

---

## Score eingeben

### Seeding-Runde

1. **Scoring → Turnier → Seeding → Runde auswählen**
2. Team aus der Liste auswählen (oder per QR-Code am Tisch scannen)
3. Score-Sheet-Felder eingeben:
   - Jedes Feld ist nach dem Spielbereich benannt (z.B. „Warehouse Floor – Sorted Cubes")
   - Zahlenwerte eingeben oder Ja/Nein-Felder anklicken
   - Das System berechnet den Gesamtscore automatisch in Echtzeit (Formel: `Σ Feldwert × Multiplikator`)
4. Optionales Kommentarfeld: Besonderheiten notieren (z.B. „Roboter hat sich vor Ende gestoppt")
5. **Absenden** → Score wird sofort gespeichert und in der Rangliste aktualisiert

> **Tipp:** Auf Mobilgeräten erscheint bei Nummernfeldern automatisch der Nummernblock.

### Double-Elimination-Match

1. **Scoring → Turnier → Double Elimination → Match auswählen**
2. Beide Teams sind vorbelegt (aus dem Bracket)
3. Scores für beide Seiten eingeben
4. Gewinner wird automatisch ermittelt (höherer Score gewinnt)
5. Bei Gleichstand: Tiebreaker-Reihenfolge wird angezeigt
6. **Absenden** → Bracket aktualisiert sich automatisch

---

## Score korrigieren

Wenn ein Score falsch eingegeben wurde:

1. **Scoring → Match → Score → Bearbeiten**
2. Korrekten Wert eingeben
3. **Korrekturgrund angeben** (Pflichtfeld) – z.B. „Ablese-Fehler bei Warehouse Floor"
4. Speichern

> Der ursprüngliche Score bleibt im Audit-Log erhalten. Korrekturen sind für Admins vollständig nachvollziehbar.

---

## Yellow/Red Card vergeben

Bei schwerwiegendem Fehlverhalten eines Teams:

1. **Scoring → Turnier → Team → Karte vergeben**
2. Kartentyp auswählen: **Gelb** (Verwarnung) oder **Rot** (sofortige DQ)
3. Begründung eingeben (Pflichtfeld)
4. Bestätigen

**Automatische Logik:**
- 2. Gelbe Karte → System schlägt automatisch Rote Karte vor
- Rote Karte → Team wird aus allen weiteren Runden und Awards ausgeschlossen

---

## Turnier-Ablauf-Checkliste (am Spieltisch)

Das System zeigt für jedes Match eine Schritt-für-Schritt-Checkliste:

**Seeding-Runde:**
```
[ ] Team am Tisch
[ ] Roboter aufgestellt
[ ] Setup-Phase gestartet (2 min)
    → Falls Fehler: [ ] 1. Fault notieren  [ ] 2. Fault → DQ
[ ] Judge hat Setup geprüft → OK
[ ] Hands-Off-Phase
[ ] Spiel gestartet
[ ] Score eingetragen
[ ] Team hat Score quittiert (Initial)
```

**Double Elimination:**
```
[ ] Beide Teams am Tisch
[ ] Parts Challenge? → [ ] Ja: Head Judge rufen  [ ] Nein: weiter
[ ] Setup-Phase (2 min)
    → Falls Fehler: [ ] 1. Fault  [ ] 2. Fault → DQ
[ ] Judge hat Setup geprüft → OK
[ ] Hands-Off-Phase
[ ] Spiel gestartet
[ ] Scores für beide Seiten eingetragen
[ ] Gewinner bestimmt
[ ] Beide Teams haben Score quittiert
```

---

## Rangliste & Live-Scoreboard

- **Scoring → Rangliste**: Aktuelle Seeding-Rangliste
  - Zeigt: Rang, Team, Seed-Score (Ø Top-2-Läufe), Best-Score, Durchschnitt, Anzahl Runden
  - **Export:** PDF-Button (druckfertige Rangliste) oder CSV-Button (für Excel)
- **Scoring → Bracket**: Double-Elimination-Bracket (interaktiv, zeigt aktuellen Stand)
- **Scoring → Live-Scoreboard**: Vollbildansicht für Großbildschirm (URL separat abrufbar)

### Seed-Score-Formel

Der Seed-Score ergibt sich aus dem **Durchschnitt der zwei besten Läufe** eines Teams:

```
Seed-Score = (bester Lauf + zweitbester Lauf) / 2
```

Teams mit nur einem Lauf erhalten diesen als Seed-Score.

---

## Rangliste exportieren

1. **Scoring → Rangliste**
2. **PDF**-Button: A4-PDF mit Logo-Header, Rang, Team, Scores – druckfertig
3. **CSV**-Button: Tabelle mit allen Wertungen für Excel/Sheets

Der Export enthält immer den Stand zum Zeitpunkt des Klickens.

---

## Offline-Nutzung

Falls die Internetverbindung am Spieltisch abbricht:

1. Scores werden lokal im Browser gespeichert (IndexedDB)
2. Sobald Verbindung wiederhergestellt: automatische Synchronisation
3. Hinweis-Banner oben: „Offline – Daten werden lokal gespeichert"

> Empfehlung: BotballDashboard als PWA installieren → bessere Offline-Unterstützung
