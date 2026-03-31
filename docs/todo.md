# Todo – Offene Module

## Architektur-Übersicht

Das System folgt einem **modularen Plugin-Prinzip**:
- **Kern** (Team- & Saisonverwaltung + Auth) steht hierarchisch ganz oben
- Alle Fachmodule (Scoring, Paper Review, 3D-Druck, ...) sind eigenständige, austauschbare Plugins
- Jedes Modul registriert sich beim Kern und kommuniziert ausschließlich über definierte Schnittstellen (REST-API / WebSocket / Event-Bus)
- Neue Module können jederzeit hinzugefügt werden, ohne den Kern oder andere Module zu verändern

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            KERN                                          │
│                                                                          │
│   ┌─────────────────────────┐   ┌──────────────────────────────────┐    │
│   │   Saisonverwaltung      │   │       Teamverwaltung             │    │
│   │  (Saisons, Archivierung,│◄──►  (Teams, Mitglieder, Betreuer,  │    │
│   │   Vorlagen, Klonen)     │   │   Historie, Dokumente)           │    │
│   └─────────────────────────┘   └──────────────────────────────────┘    │
│                    ▲                           ▲                         │
│                    └──────────────────────────┘                         │
│                         Authentifizierung & Rollen                      │
│                    (Admin, Juror, Reviewer, Mentor, Gast)               │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  Modul-Registry / Plugin-API
          ┌─────────────────────┼──────────────────────┐
          │                     │                      │
          ▼                     ▼                      ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐
│  Scoring-Modul   │  │ Paper-Review-    │  │  3D-Druck-Modul          │
│                  │  │ Modul            │  │                          │
│ - Scoring Sheets │  │ - Paper-Upload   │  │ - Druckjob-Verwaltung    │
│ - Formeln        │  │ - Reviewer-Zuw.  │  │ - Drucker-Adapter        │
│ - Live-Rangliste │  │ - Benotung       │  │   (Bambu, Prusa, etc.)   │
│ - OCR-Upload     │  │ - Revisions-     │  │ - Statusanzeige          │
│                  │  │   Verwaltung     │  │ - Queue-Verwaltung       │
└──────────────────┘  └──────────────────┘  └──────────────────────────┘
          │                     │                      │
          └─────────────────────┴──────────────────────┘
                                │
                    ┌───────────▼────────────┐
                    │  Frontend (React)       │
                    │  Pro Modul eigene UI-   │
                    │  Komponenten / Views    │
                    └────────────────────────┘
```

---

## [ ] Modul 1: Projekt-Setup & Infrastruktur
**Beschreibung:** Grundgerüst – Tech-Stack, Ordnerstruktur, Docker, CI/CD, Plugin-Mechanismus.  
**Kommuniziert mit:** Allen anderen Modulen (Basis für alles)  
**Aufgaben:**
- [ ] Tech-Stack festlegen (React, Django/FastAPI oder Node.js, PostgreSQL)
- [ ] Monorepo-Struktur anlegen (`/core`, `/modules/scoring`, `/modules/paper-review`, `/modules/print`, `/frontend`, `/docs`)
- [ ] Plugin-Registry definieren: Wie registrieren sich Module beim Kern? (z. B. Manifest-Datei pro Modul)
- [ ] Docker & Docker-Compose für lokale Entwicklung (DB als persistentes Volume)
- [ ] Datenbank-Migrationsstrategie: Alembic/Django Migrations, Rollback-fähig, Auto-Backup vor Deployment
- [ ] `migrate-then-start` Deployment-Pattern (Migrationen vor Backend-Start)
- [ ] Schema-Versionierung in DB (`schema_version`-Tabelle)
- [ ] CI/CD-Pipeline (GitHub Actions)
- [ ] Linter, Formatter, Pre-commit Hooks

---

## [ ] Modul 2: Authentifizierung & Rechtesystem
**Beschreibung:** Login, JWT-/OAuth2-Auth, Rollenkonzept. Rollen sind erweiterbar (neue Module können eigene Rollen mitbringen).  
**Kommuniziert mit:** Kern + allen Modulen (jeder API-Call prüft Token & Rolle)  
**Rollen (initial):** Admin, Juror, Reviewer, Mentor, Gast  
**Aufgaben:**
- [ ] User-Modell & erweiterbares Rollen-Modell (DB)
- [ ] Registrierung & Login (JWT)
- [ ] Middleware zur Rollenprüfung auf allen Endpunkten
- [ ] Passwort-Reset per E-Mail
- [ ] DSGVO-konforme Datenspeicherung & Audit Trail

---

## [ ] Modul 3: Saisonverwaltung  *(Kern)*
**Beschreibung:** Anlegen, Bearbeiten, Archivieren und Klonen von Saisons. Alle Fachmodule referenzieren eine Saison.  
**Kommuniziert mit:**
- Modul 4 (Teams): Teams werden einer Saison zugeordnet
- Scoring-Modul: Scoring-Vorlagen sind saisonspezifisch
- Paper-Review-Modul: Papers gehören zu einer Saison
- 3D-Druck-Modul: Druckjobs können einer Saison zugeordnet werden
**Aufgaben:**
- [ ] Saison-Datenmodell (ID, Name, Jahr, Status: aktiv/archiviert)
- [ ] CRUD-API für Saisons
- [ ] Saison klonen (Struktur & Konfiguration übernehmen)
- [ ] Saison archivieren & schreibschützen
- [ ] Modul-Konfiguration pro Saison (welche Module sind aktiv?)

---

## [ ] Modul 4: Teamverwaltung  *(Kern)*
**Beschreibung:** Teams anlegen, Mitglieder & Betreuer verwalten, Teamhistorie über mehrere Saisons.  
**Kommuniziert mit:**
- Modul 3 (Saisons): Team ist einer oder mehreren Saisons zugeordnet
- Scoring-Modul: Teams haben Scores in Turnieren
- Paper-Review-Modul: Teams reichen Papers ein
- 3D-Druck-Modul: Teams stellen Druckanfragen
**Aufgaben:**
- [ ] Team-Datenmodell (Nummer, Name, Schule, Mitglieder, Betreuer)
- [ ] CRUD-API für Teams
- [ ] Teamhistorie über mehrere Saisons
- [ ] Upload von Projektplänen & Dokumenten pro Team
- [ ] Teilnahmegebühren & Kit-Versandstatus verwalten

---

## [ ] Modul 5: Scoring-Modul  *(Plugin)*
**Beschreibung:** Zwei-Phasen-Bewertungssystem: interne Vorbereitungsphase (Testläufe) + offizielle ECER-Turnierphase. Performance-Dashboard, Gegner-Scouting, OCR-Upload.  
**Registriert sich beim Kern via:** Modul-Manifest → liefert eigene API-Routen, UI-Komponenten und Rollen (Juror)  
**Kommuniziert mit:**
- Modul 3 (Saisons): Scoring-Vorlagen und Phasen sind saisonspezifisch
- Modul 4 (Teams): Scores werden Teams zugeordnet
- Frontend: WebSocket für Live-Ranglisten & Scoreboard
**Aufgaben:**
- [ ] Phasen-Modell: Phase 1 (Preparations/intern) und Phase 2 (ECER/offiziell) pro Saison
- [ ] Phase 1: Flexible Testläufe für alle eigenen Teams dokumentieren
- [ ] Phase 2: Seeding, Double-Elimination, Alliance-Matches
- [ ] Externe Gegner-Teams erfassen (Scouting) mit eigenen beobachteten Scores
- [ ] Performance-Dashboard: Teamvergleich, Verlaufsgraph, Stärken/Schwächen-Analyse
- [ ] Gegner-Analyse: Ranking inkl. externer Teams, Turnierpositions-Einschätzung
- [ ] Konfigurierbares Scoring-Sheet-Schema (YAML/JSON oder grafischer Editor)
- [ ] Berechnung: Seeding-Score, Durchschnitt bester 2 Runs, Double-Elimination, Gesamtscore
- [ ] Plausibilitätsprüfung (Maximalwerte, unrealistische Einträge)
- [ ] Kommentarfeld pro Lauf (Notizen zu Problemen)
- [ ] Audit Trail für Score-Änderungen
- [ ] OCR-Upload: Bild/PDF → Tesseract + OpenCV → manuelle Korrektur
- [ ] Live-Rangliste & öffentliches Scoreboard via WebSocket
- [ ] Export: PDF, CSV (inkl. Phasenvergleich und Scouting-Bericht)

---

## [ ] Modul 6: Paper-Review-Modul  *(Plugin)*
**Beschreibung:** Teams laden ihre Papers (Projektdokumentation) hoch. Reviewer geben strukturiertes Feedback, Benotungen und verlangen ggf. Revisionen.  
**Registriert sich beim Kern via:** Modul-Manifest → liefert eigene API-Routen, UI-Komponenten und Rollen (Reviewer)  
**Kommuniziert mit:**
- Modul 3 (Saisons): Papers gehören zu einer Saison
- Modul 4 (Teams): Paper wird einem Team zugeordnet
- Modul 2 (Auth): Nur Reviewer können Benotungen vergeben; Teams sehen nur eigene Papers  
**Aufgaben:**
- [ ] Datenmodell: Paper (Titel, Version, Datei, Status), Review (Benotung, Kommentare, Revisionspflicht)
- [ ] Paper-Upload durch Teams (PDF)
- [ ] Zuweisung von Reviewern zu Papers (manuell oder automatisch)
- [ ] Review-Formular: strukturiertes Feedback mit Kategorien & Gesamtnote
- [ ] Revisions-Workflow: Reviewer fordert Revision an → Team lädt neue Version hoch → erneutes Review
- [ ] Versionierung: alle Paper-Versionen und zugehörigen Reviews einsehbar
- [ ] Statusübersicht für Admins (welche Papers sind noch nicht reviewed?)
- [ ] Benachrichtigungen: E-Mail/Push bei neuem Review oder Revisionsanforderung
- [ ] Export: Bewertungszusammenfassung als PDF

---

## [ ] Modul 7: 3D-Druck-Modul  *(Plugin)*
**Beschreibung:** Verwaltung von 3D-Druckjobs über mehrere Drucker verschiedener Hersteller. Teams stellen Anfragen, Admins verwalten die Queue.  
**Registriert sich beim Kern via:** Modul-Manifest → liefert eigene API-Routen, UI-Komponenten und Rollen  
**Kommuniziert mit:**
- Modul 4 (Teams): Druckjob wird einem Team zugeordnet
- Modul 3 (Saisons): Druckjobs optional einer Saison zugeordnet
- Drucker-Adapter-Layer: Abstraktion für verschiedene Hersteller-APIs
**Drucker-Adapter (Hersteller-Abstraktion):**
- Gemeinsames Interface: `status()`, `sendJob()`, `cancelJob()`, `getProgress()`
- Adapter pro Hersteller, z. B.:
  - Bambu Lab (X1, P1 – via Bambu Cloud API / MQTT)
  - Prusa (Connect API)
  - Generisch (OctoPrint REST-API als Fallback)
**Aufgaben:**
- [ ] Datenmodell: Drucker (Name, Hersteller, Modell, Status), Druckjob (Datei, Team, Priorität, Status, Fortschritt)
- [ ] Drucker-Adapter-Interface definieren (einheitliche Schnittstelle für alle Hersteller)
- [ ] Adapter implementieren: Bambu Lab
- [ ] Adapter implementieren: Prusa Connect
- [ ] Adapter implementieren: OctoPrint (generischer Fallback)
- [ ] Druckjob-Queue mit Prioritäten & Statusverfolgung
- [ ] Echtzeit-Statusanzeige pro Drucker (Fortschritt, verbleibende Zeit)
- [ ] Team-seitige Anfrage: STL/3MF hochladen + Kommentar
- [ ] Admin-seitige Freigabe & Zuweisung zu einem Drucker
- [ ] Benachrichtigung bei Job-Abschluss oder Fehler

---

## [ ] Modul 8: Dashboard & Visualisierung
**Beschreibung:** Übergreifendes Dashboard. Aggregiert Daten aus allen aktiven Modulen und zeigt sie je nach Rolle an.  
**Kommuniziert mit:** Kern + allen aktiven Modulen (liest deren Daten via API)  
**Aufgaben:**
- [ ] Modulares Dashboard: Widgets werden von Modulen registriert
- [ ] Rollensensitive Ansicht (Admin sieht alles, Team nur eigene Daten)
- [ ] Statistiken & Graphen (Chart.js/D3.js)
- [ ] Mehrjahresvergleiche über Saisons
- [ ] Export: PDF-Berichte, CSV/Excel

---

## [ ] Modul 9: Mobile App / PWA
**Beschreibung:** Mobile Oberfläche für Juror*innen und Reviewer am Spielfeldrand.  
**Kommuniziert mit:** Backend-API (alle Module), Kamera für OCR-Upload  
**Aufgaben:**
- [ ] Progressive Web App (PWA) oder natives Flutter-Projekt
- [ ] Offline-Modus mit lokalem Speicher
- [ ] Synchronisation nach Wiederherstellung der Verbindung
- [ ] Kamera-Integration für OCR-Upload (Scoring-Modul)

---

## [ ] Modul 10: Testing
**Beschreibung:** Unit-, Integrations- und E2E-Tests für Kern und alle Module.  
**Kommuniziert mit:** Allen Modulen  
**Aufgaben:**
- [ ] Testframework einrichten (Jest/Vitest für Frontend, pytest für Backend)
- [ ] Unit-Tests: Scoring-Engine (Berechnungen & Plausibilitätsprüfung)
- [ ] Unit-Tests: Paper-Review-Workflow (Statübergänge, Berechtigungen)
- [ ] Unit-Tests: 3D-Druck-Adapter (Mock-Drucker)
- [ ] Integrationstests: Alle API-Endpunkte pro Modul
- [ ] E2E-Tests: Kompletter Scoring-Workflow, Paper-Review-Zyklus, Druckjob-Flow
- [ ] Coverage-Reports einrichten

---

## [ ] Modul 11: Dokumentation
**Beschreibung:** Technische Doku, Benutzerhandbuch, Abschlusspräsentation.  
**Kommuniziert mit:** Allen Modulen (beschreibt diese)  
**Aufgaben:**
- [ ] Technische Systemdokumentation (Architektur, Plugin-API-Referenz)
- [ ] Benutzerhandbuch pro Rolle (Admin, Juror, Reviewer, Team, Gast)
- [ ] Abschlusspräsentation (Diplomarbeit)
- [ ] Lessons Learned / Reflexion
