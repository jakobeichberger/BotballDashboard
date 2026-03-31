# Todo – Offene Module

## Modul-Übersicht & Kommunikation

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                         │
│  Dashboard │ Turnier-UI │ Team-UI │ Scoring-UI │ Admin-UI      │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST API / WebSocket
┌────────────────────────────▼────────────────────────────────────┐
│                        Backend (API)                            │
│  Auth │ Teams │ Turniere │ Saisons │ Scoring-Engine │ Export    │
└──┬──────┬──────────┬──────────┬──────────┬───────────────────┬─┘
   │      │          │          │          │                   │
   ▼      ▼          ▼          ▼          ▼                   ▼
 Auth   Team-DB  Turnier-DB  Saison-DB  Scoring-DB         OCR-Modul
 (JWT)  (PG)     (PG)        (PG)       (PG)               (Tesseract
                                                            + OpenCV)
```

---

## [ ] Modul 1: Projekt-Setup & Infrastruktur
**Beschreibung:** Grundgerüst des gesamten Projekts – Tech-Stack, Ordnerstruktur, Docker, CI/CD.  
**Kommuniziert mit:** Allen anderen Modulen (Basis)  
**Aufgaben:**
- [ ] Tech-Stack festlegen (React, Django/FastAPI oder Node.js, PostgreSQL)
- [ ] Monorepo-Struktur anlegen (`/frontend`, `/backend`, `/ocr`, `/docs`)
- [ ] Docker & Docker-Compose für lokale Entwicklung
- [ ] CI/CD-Pipeline (GitHub Actions)
- [ ] Linter, Formatter, Pre-commit Hooks

---

## [ ] Modul 2: Authentifizierung & Rechtesystem
**Beschreibung:** Login, Registrierung, JWT-/OAuth2-basierte Auth, Rollenkonzept.  
**Kommuniziert mit:** Allen Backend-Modulen (jeder API-Call prüft Token & Rolle)  
**Rollen:** Admin, Juror, Mentor, Gast  
**Aufgaben:**
- [ ] User-Modell & Rollen-Modell (DB)
- [ ] Registrierung & Login (JWT)
- [ ] Middleware zur Rollenprüfung auf allen Endpunkten
- [ ] Passwort-Reset per E-Mail
- [ ] DSGVO-konforme Datenspeicherung (Audit Trail)

---

## [ ] Modul 3: Saisonverwaltung
**Beschreibung:** Anlegen, Bearbeiten, Archivieren und Klonen von Saisons (z. B. 2025, 2026).  
**Kommuniziert mit:**
- Modul 4 (Teams): Teams werden einer Saison zugeordnet
- Modul 5 (Turniere): Turniere gehören zu einer Saison
- Modul 6 (Scoring-Engine): Scoring-Vorlagen sind saisonspezifisch
**Aufgaben:**
- [ ] Saison-Datenmodell (ID, Name, Jahr, Status: aktiv/archiviert)
- [ ] CRUD-API für Saisons
- [ ] Saison klonen (Struktur & Konfiguration übernehmen)
- [ ] Saison archivieren & schreibschützen
- [ ] Saisonübergreifende Team-Verknüpfung

---

## [ ] Modul 4: Teamverwaltung
**Beschreibung:** Teams anlegen, bearbeiten, Mitglieder & Betreuer verwalten, Teamhistorie.  
**Kommuniziert mit:**
- Modul 3 (Saisons): Team ist einer oder mehreren Saisons zugeordnet
- Modul 5 (Turniere): Teams nehmen an Turnieren teil
- Modul 7 (Dashboard): Teamstatistiken werden angezeigt
**Aufgaben:**
- [ ] Team-Datenmodell (Nummer, Name, Schule, Mitglieder, Betreuer)
- [ ] CRUD-API für Teams
- [ ] Teamhistorie über mehrere Saisons
- [ ] Upload von Projektplänen & Dokumenten pro Team
- [ ] Teilnahmegebühren & Kit-Versandstatus verwalten

---

## [ ] Modul 5: Turnier- & Spielplanverwaltung
**Beschreibung:** Seeding-Runden, Double-Elimination-Brackets, Alliance-Matches, Zeitpläne.  
**Kommuniziert mit:**
- Modul 3 (Saisons): Turnier gehört zu einer Saison
- Modul 4 (Teams): Teams werden Matches zugeordnet
- Modul 6 (Scoring-Engine): Ergebnisse der Matches werden berechnet
- Modul 7 (Dashboard): Live-Ranglisten & Brackets werden angezeigt
- Frontend via WebSocket: Live-Updates während des Turniers
**Aufgaben:**
- [ ] Datenmodell: Turnier, Runde, Match, Bracket-Knoten
- [ ] Automatische Generierung von Double-Elimination-Brackets
- [ ] Seeding-Rundenplan & Alliance-Matches
- [ ] Terminverwaltung & Deadlines
- [ ] E-Mail/Push-Benachrichtigungen bei Planänderungen
- [ ] WebSocket-Endpunkt für Live-Updates

---

## [ ] Modul 6: Scoring-Engine
**Beschreibung:** Konfigurierbare Bewertungsregeln, Berechnung der Punkte nach offiziellen Formeln, Plausibilitätsprüfung.  
**Kommuniziert mit:**
- Modul 3 (Saisons): Scoring-Vorlagen sind saisonspezifisch
- Modul 5 (Turniere): Ergebnisse werden Matches zugeordnet
- Modul 8 (OCR): Empfängt erkannte Werte zur Weiterverarbeitung
- Modul 7 (Dashboard): Liefert berechnete Scores
**Aufgaben:**
- [ ] Konfigurierbares Scoring-Sheet-Schema (YAML/JSON oder grafischer Editor)
- [ ] Berechnung: Seeding-Score (Summe beider Seiten), Durchschnitt bester 2 Runs
- [ ] Berechnung: Double-Elimination (nur Sieg/Niederlage)
- [ ] Berechnung: Dokumentationspunkte & Gesamtscore
- [ ] Plausibilitätsprüfung (Maximalwerte, unrealistische Einträge)
- [ ] API-Endpunkt: Score einreichen, korrigieren, abrufen
- [ ] Audit Trail (wer hat wann welchen Score geändert)

---

## [ ] Modul 7: Dashboard & Visualisierung
**Beschreibung:** Live-Ranglisten, Teamdetailansichten, Statistiken, Mehrjahrestrends, Exports.  
**Kommuniziert mit:**
- Modul 5 (Turniere): Bracket- und Rundendaten
- Modul 6 (Scoring-Engine): Aktuelle und historische Scores
- Modul 4 (Teams): Teamdaten & Historie
- Frontend via WebSocket: Echtzeit-Updates
**Aufgaben:**
- [ ] Live-Rangliste (Seeding, Double-Elimination, Alliance)
- [ ] Team-Detailansicht (Punkte pro Aufgabensegment, Rundenvergleich)
- [ ] Statistikmodule: Graphen (Chart.js/D3.js), Boxplots, Heatmaps
- [ ] Mehrjahresanalysen & Trendauswertungen
- [ ] Export: PDF-Berichte, CSV/Excel, Webansicht
- [ ] Öffentliches Live-Scoreboard (WebSocket, für Großbildschirme)

---

## [ ] Modul 8: OCR-Modul
**Beschreibung:** Upload und automatische Erkennung von handschriftlichen Scoring-Sheets via Foto oder PDF.  
**Kommuniziert mit:**
- Modul 6 (Scoring-Engine): Gibt erkannte Werte zur Berechnung weiter
- Frontend: Upload-Oberfläche & manuelle Korrektur
**Aufgaben:**
- [ ] Bild- und PDF-Upload-API
- [ ] Bildvorverarbeitung mit OpenCV (Kontrast, Entzerrung, Rauschen)
- [ ] OCR-Pipeline mit Tesseract
- [ ] Verbesserung durch CNN/vortrainiertes Modell für Handschrift
- [ ] Rückgabe erkannter Felder + Konfidenzwerte
- [ ] Manuelle Korrekturoberfläche für unsichere Erkennungen
- [ ] Offline-Unterstützung / Sync für mobile Nutzung

---

## [ ] Modul 9: Mobile App / PWA
**Beschreibung:** Smartphone-App für Juror*innen zur Erfassung von Scores direkt am Spielfeld.  
**Kommuniziert mit:**
- Modul 8 (OCR): Foto-Upload direkt aus der App
- Modul 6 (Scoring-Engine): Score-Übermittlung nach Sync
- Backend-API: Synchronisation nach Wiederherstellung der Verbindung
**Aufgaben:**
- [ ] Progressive Web App (PWA) oder natives Flutter-Projekt
- [ ] Offline-Modus: Scores lokal speichern
- [ ] Synchronisation nach Wiederherstellung der Internetverbindung
- [ ] Kamera-Integration für OCR-Upload

---

## [ ] Modul 10: Testing
**Beschreibung:** Unit-, Integrations- und End-to-End-Tests für alle Module.  
**Kommuniziert mit:** Allen Modulen  
**Aufgaben:**
- [ ] Testframework einrichten (Jest/Vitest für Frontend, pytest für Backend)
- [ ] Unit-Tests: Scoring-Engine (Berechnungen & Plausibilitätsprüfung)
- [ ] Unit-Tests: OCR-Pipeline
- [ ] Integrationstests: Alle API-Endpunkte
- [ ] End-to-End-Tests: Kompletter Scoring-Workflow mit echten Sheets
- [ ] Coverage-Reports einrichten

---

## [ ] Modul 11: Dokumentation
**Beschreibung:** Technische Doku, Benutzerhandbuch, Abschlusspräsentation.  
**Kommuniziert mit:** Allen Modulen (beschreibt diese)  
**Aufgaben:**
- [ ] Technische Systemdokumentation (Architektur, API-Referenz)
- [ ] Benutzerhandbuch für Admins, Juror*innen, Mentoren
- [ ] Abschlusspräsentation (Diplomarbeit)
- [ ] Lessons Learned / Reflexion
