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

- [x] **Gesamtscore-Formel:** ✅ Aus PDFs extrahiert – siehe `docs/modules/05-scoring.md`
- [x] **Scoring-Sheet-Felder 2024/2025:** ✅ Vollständig aus PDFs extrahiert – siehe `docs/modules/05-scoring.md`
- [ ] **Scoring-Sheet-Felder 2026:** Spielelemente aus Regeltext bekannt (Warehouse/Cubes/Poms/Pallets/Loading Docks/Packaging Bins/Drum Storage). Exakte Multiplikator-Werte liegen nur im grafischen Score-Sheet-PDF vor – manuelle Erfassung aus Dokument nötig.
- [x] **Yellow/Red Card System:** ✅ Dokumentiert in `docs/modules/05-scoring.md` – DQ-Status muss im Match-Datensatz speicherbar sein
- [x] **3D-Druck-Roboterteile-Regeln:** ✅ 2025: max. 4 Teile PLA; 2026: max. 6 Teile PLA/PETG. Dokumentiert in `docs/modules/04-teamverwaltung.md`
- [ ] **GCER Qualifikationsschwelle:** Wie viele Teams qualifizieren sich von der ECER für die GCER? Feste Anzahl oder Prozentwert?
- [ ] **Alliance-Matches bei GCER:** Gibt es bei der GCER immer Alliance-Matches oder nur manchmal?
- [ ] **Öffentlichkeit der Prep-Phase:** Sollen Scores aus der Vorbereitungsphase nur für Admins/Mentoren sichtbar sein, oder auch für die Teams selbst?

---

## Paper-Review-Modul

- [x] **Paper-Struktur:** ✅ Abstract → Introduction → (State of the Art) → Concept/Design → Implementation → Results/Conclusion
- [x] **Format:** ✅ IEEE A4-Template, 2-spaltig, 10pt, single-spaced, max. 5 Seiten inkl. Abbildungen & Referenzen
- [x] **Einreichung:** ✅ PDF via moodle.pria.at (wird durch unser System abgelöst)
- [x] **Präsentation:** ✅ Ausgewählte Papers: bis 10 Min. Vortrag + 5 Min. Q&A
- [x] **Paper-Kategorien 2026:** ✅ Multi Agent Systems / Embracing Educational Robotics / Engineering / STEM Projects
- [x] **Score-Integration:** ✅ `AdaptedDocScore = ½·DocScore + ½·PaperScore` / `PriaOpenOverall = DE + Seeding + ½·PaperScore`
- [x] **Deadlines 2026:** ✅ Einreichung 15. März, Annahme 29. März, Final 5. April
- [ ] **Anzahl Reviewer pro Paper:** Wie viele Reviewer werden einem Paper zugewiesen?
- [ ] **Blind Review:** Ist der Review-Prozess blind (Reviewer sieht nicht welches Team einreicht)?
- [ ] **Interne Review-Deadlines:** Wie viele interne Review-Runden sind typischerweise pro Saison geplant?

---

## 3D-Druck-Modul

- [ ] **Drucker-Inventar:** Welche 3D-Drucker sind konkret im Einsatz? (Hersteller, Modell, Anzahl)
- [ ] **Credentials-Verwaltung:** Sollen Drucker-API-Keys in der Datenbank (verschlüsselt) oder als Umgebungsvariablen gespeichert werden?
- [ ] **Limits pro Team:** Gibt es ein maximales Druckvolumen / maximale Druckzeit pro Team und Saison?
- [ ] **Filament-Tracking:** Soll der Materialverbrauch (Filamentmenge) pro Job und Drucker getrackt werden?

---

## Allgemein

- [x] **PDF-Lesbarkeit:** ✅ `poppler-utils` installiert
- [ ] **Mehrsprachigkeit:** Wird die Oberfläche nur auf Deutsch sein oder auch auf Englisch (für internationale Teilnehmer bei GCER)?
- [ ] **Benachrichtigungen:** E-Mail-Provider – eigener SMTP-Server oder Dienst wie SendGrid/Mailgun?
- [ ] **Öffentliches Scoreboard:** Soll das Live-Scoreboard passwortgeschützt sein oder komplett öffentlich?
