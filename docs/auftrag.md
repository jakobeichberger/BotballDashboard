# Auftragsbeschreibung: Botball-Auswertungssystem

## Ausgangslage und Zielsetzung

Die KISS Institute for Practical Robotics organisiert Botball‑Wettbewerbe; Schülerteams bauen autonome Roboter und treten bei Seeding‑ und Double‑Elimination‑Wettkämpfen gegeneinander an. Die Regeln und Bewertungsblätter ändern sich jedes Jahr, die Auswertung erfolgt aktuell manuell und ist fehleranfällig. Ziel ist die Entwicklung eines Systems zur automatisierten Scoring‑Auswertung, Team‑ und Saison‑Verwaltung über mehrere Jahre.

## Aufgabenstellung

1. **Automatische Erfassung und Auswertung der Scoring‑Blätter**  
   – Module zur Erfassung handschriftlicher Scoring‑Sheets über Foto oder PDF.  
   – OCR‑basierte Erkennung der Punktzahlen und Multiplikatoren mit Plausibilitätsprüfung.  
   – Abbildung der offiziellen Berechnungsregeln (Seeding‑Durchschnitt, Double Elimination, Dokumentation).

2. **Team‑ und Turniermanagement**  
   – Webbasierte Verwaltungsoberfläche für Teams (Name, Nummer, Mitglieder, Kontakte) und Turniere (Seeding‑Runden, Double Elimination).  
   – Rollen-/Rechtesystem für Admins, Juror*innen, Mentor*innen und Gäste.  
   – Generierung von Turnierplänen und Brackets; Deadlines und Benachrichtigungen.

3. **Saisonverwaltung**  
   – Anlegen und Verwalten separater Saisonobjekte (z. B. 2025, 2026).  
   – Möglichkeit zum Kopieren (Vorlage) und Archivieren vergangener Saisons.  
   – Verknüpfung der Teamhistorie über mehrere Jahre sowie Mehrjahresanalysen.

4. **Dashboards und Berichte**  
   – Live‑Ranglisten und detaillierte Auswertungen pro Team.  
   – Statistikmodule zur Analyse von Trends und zur Erkennung von Anomalien.  
   – Export von Daten als PDF, CSV oder Webansicht.

5. **Optional: mobile App und Live‑Scoreboard**  
   – Mobile Anwendung zur direkten Erfassung der Scores am Spielfeldrand.  
   – Öffentliche Live‑Anzeige der Ergebnisse auf Displays.

## Erwartetes Ergebnis

Das Ergebnis ist eine lauffähige Web‑Anwendung (inkl. optionaler Mobile‑App), die alle oben beschriebenen Funktionen erfüllt und modular konfigurierbar ist, um jährlich wechselnde Regeln zu integrieren. Eine Dokumentation, Benutzerhandbuch sowie Präsentation der Software gehören zum Abschluss.

## Rahmenbedingungen

- **Technologieauswahl:** Die konkrete Technologie (z. B. Django, Node.js, Datenbank, OCR) wird von den Schüler:innen erarbeitet, sollte jedoch eine robuste Web‑Applikation ermöglichen.  
- **Projektorganisation:** Arbeitsteilung innerhalb des Teams (OCR‑Modul, Backend, Frontend, Saisonverwaltung, Tests).  
- **Betreuung:** Regelmäßige Abstimmungen mit der betreuenden Lehrkraft und dem Auftraggeber.

