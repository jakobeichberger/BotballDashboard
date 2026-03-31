# Offene Fragen

Fragen die noch nicht beantwortet wurden. Werden hier protokolliert und nach Beantwortung in die jeweiligen Modul-Dokumente übernommen.

---

## Infrastruktur & Tech-Stack

- [ ] **Backend-Framework:** Django REST Framework oder FastAPI?
- [ ] **Monorepo-Tool:** Turborepo, Nx oder einfaches Workspace-Setup?
- [ ] **Hosting:** Wo wird das System deployed? Eigener Server, Cloud (AWS/Azure/GCP), oder Schul-Infrastruktur?

---

## Auth & Rechtesystem

- [ ] **Social Login:** Soll OAuth2 / Login via Google oder Microsoft unterstützt werden?
- [ ] **Admin-Oberfläche:** Reicht eine API zur Benutzerverwaltung oder soll es eine eigene Admin-UI geben?

---

## Scoring-Modul

- [ ] **Scoring-Sheet-Details 2025/2026:** Genaue Aufgabenkategorien, Felder und Multiplikatoren aus den Game-Review-PDFs (aktuell nicht lesbar, benötigt `poppler-utils`)
- [ ] **Gesamtscore-Formel:** Genaue Formel für die Kombination aus Seeding + Double-Elimination + Dokumentationspunkten (saisonabhängig – aus Regelwerk entnehmen)
- [ ] **GCER Qualifikationsschwelle:** Wie viele Teams qualifizieren sich von der ECER für die GCER? Feste Anzahl oder Prozentwert?
- [ ] **Alliance-Matches bei GCER:** Gibt es bei der GCER immer Alliance-Matches oder nur manchmal?
- [ ] **Öffentlichkeit der Prep-Phase:** Sollen Scores aus der Vorbereitungsphase nur für Admins/Mentoren sichtbar sein, oder auch für die Teams selbst?

---

## Paper-Review-Modul

- [ ] **Bewertungskriterien 2025/2026:** Genaue Kategorien und Punkteverteilung aus den Call-for-Papers-PDFs (aktuell nicht lesbar)
- [ ] **Anzahl Reviewer pro Paper:** Wie viele Reviewer werden einem Paper zugewiesen? (1, 2, oder mehr?)
- [ ] **Blind Review:** Ist der Review-Prozess blind (Reviewer sieht nicht welches Team das Paper eingereicht hat)?
- [ ] **Einreichungsplattform:** Wird `moodle.pria.at` vollständig durch unser System abgelöst oder parallel betrieben?
- [ ] **Präsentationsauswahl:** Nach welchem Kriterium werden Papers für die Präsentation (Vortrag + Q&A) ausgewählt? Nur beste Note oder auch andere Faktoren?
- [ ] **Paper-Kategorien:** Gibt es neben ECER Engineering weitere Tracks/Kategorien?
- [ ] **Interne Review-Deadlines:** Wie viele interne Review-Runden sind typischerweise geplant pro Saison?

---

## 3D-Druck-Modul

- [ ] **Drucker-Inventar:** Welche 3D-Drucker sind konkret im Einsatz? (Hersteller, Modell, Anzahl)
- [ ] **Credentials-Verwaltung:** Sollen Drucker-API-Keys in der Datenbank (verschlüsselt) oder als Umgebungsvariablen gespeichert werden?
- [ ] **Limits pro Team:** Gibt es ein maximales Druckvolumen / maximale Druckzeit pro Team und Saison?
- [ ] **Filament-Tracking:** Soll der Materialverbrauch (Filamentmenge) pro Job und Drucker getrackt werden?

---

## Allgemein

- [ ] **PDF-Lesbarkeit:** `poppler-utils` auf dem System installieren (`apt install poppler-utils`) damit die Game-Review- und Call-for-Papers-PDFs ausgewertet werden können
- [ ] **Mehrsprachigkeit:** Wird die Oberfläche nur auf Deutsch sein oder auch auf Englisch (für internationale Teilnehmer bei GCER)?
- [ ] **Benachrichtigungen:** E-Mail-Provider für automatische Benachrichtigungen – eigener SMTP-Server oder Dienst wie SendGrid/Mailgun?
- [ ] **Öffentliches Scoreboard:** Soll das Live-Scoreboard passwortgeschützt sein oder komplett öffentlich (z.B. für Zuschauer)?
