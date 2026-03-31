# Modul 09 – Mobile App / PWA

**Status:** [ ] Offen  
**Typ:** Frontend-Erweiterung (optional)  
**Kommuniziert mit:** Backend-API (alle Module), Kamera des Geräts

---

## Beschreibung

Mobile Oberfläche für Juror*innen und Reviewer direkt am Spielfeldrand oder Konferenztisch. Als Progressive Web App (PWA) ohne App-Store-Installation nutzbar. Unterstützt Offline-Modus mit automatischer Synchronisation.

---

## Features

### Progressive Web App (PWA)
- Installation auf iOS und Android ohne App Store
- Funktioniert im Browser (Chrome, Safari, Firefox)
- Home-Screen-Icon, Splash Screen
- Push-Benachrichtigungen (wo vom OS unterstützt)

### Offline-Modus
- Scores können ohne Internetverbindung eingegeben werden
- Daten werden lokal im Browser gespeichert (IndexedDB)
- Automatische Synchronisation sobald Verbindung wiederhergestellt
- Konflikt-Erkennung: Was passiert wenn derselbe Score offline und online geändert wird?

### Kamera-Integration (OCR-Upload)
- Foto des Scoring-Sheets direkt aus der App aufnehmen
- Bild wird an OCR-Pipeline gesendet (Scoring-Modul)
- Erkannte Werte werden im Formular vorausgefüllt
- Kamera-Zugriff erfordert Benutzer-Erlaubnis

### Scoring-Workflow (mobil optimiert)
- Vereinfachtes Scoring-Formular für Touch-Bedienung
- Große Eingabefelder, klare Buttons
- Swipe-Navigation zwischen Matches
- Bestätigung vor dem Absenden

### Paper-Review (mobil)
- Paper als PDF lesen direkt im Browser
- Review-Formular ausfüllen und absenden
- Revisions-Notizen schreiben

### Benachrichtigungen
- Push-Meldung bei: neuem Match, Score-Korrektur, neuem Paper, Druckjob fertig

---

## Technologie-Entscheidung

| Option | Vorteile | Nachteile |
|---|---|---|
| PWA (React) | Kein separates Projekt, shared codebase | Eingeschränkter Kamera-Zugriff auf iOS |
| Flutter | Native Performance, voller Kamera-Zugriff | Separates Projekt, andere Sprache (Dart) |

**Empfehlung:** PWA als erste Version, bei Bedarf Flutter-App später.

---

## Schnittstellen zu anderen Modulen

| Richtung | Modul | Art |
|---|---|---|
| → | Scoring-Modul | Score einreichen, OCR-Upload |
| → | Paper-Review-Modul | Reviews einreichen |
| → | Backend-API | Alle Daten via REST + WebSocket |
| ← | Auth | JWT-Token für alle Requests |
