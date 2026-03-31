# Offene Fragen

Fragen die noch nicht beantwortet wurden. Werden hier protokolliert und nach Beantwortung in die jeweiligen Modul-Dokumente übernommen.

---

## Infrastruktur & Tech-Stack

- [x] **Backend-Framework:** ✅ FastAPI (async, Pydantic, automatische OpenAPI-Docs)
- [x] **Monorepo-Tool:** ✅ pnpm Workspaces (kein Turborepo/Nx-Overhead nötig)
- [x] **Hosting:** ✅ Self-hosted auf Proxmox, Docker Compose, Traefik als Reverse Proxy

---

## Auth & Rechtesystem

- [x] **Social Login:** ✅ Kein OAuth2 / Social Login – nur E-Mail + Passwort
- [x] **Admin-Oberfläche:** ✅ Eigene Admin-UI zur Benutzerverwaltung

---

## Scoring-Modul

- [x] **Gesamtscore-Formel:** ✅ Aus PDFs extrahiert – siehe `docs/modules/05-scoring.md`
- [x] **Scoring-Sheet-Felder 2024/2025:** ✅ Vollständig aus PDFs extrahiert – siehe `docs/modules/05-scoring.md`
- [ ] **Scoring-Sheet-Felder 2026:** Spielelemente bekannt, exakte Multiplikator-Werte werden über dynamische Admin-UI manuell eingetragen (kein Blocker)
- [x] **Yellow/Red Card System:** ✅ Dokumentiert in `docs/modules/05-scoring.md`
- [x] **3D-Druck-Roboterteile-Regeln:** ✅ 2025: max. 4 Teile PLA; 2026: max. 6 Teile PLA/PETG
- [x] **GCER Qualifikationsschwelle:** ✅ 1–2 Teams, manuelle Freigabe durch Admin
- [x] **Alliance-Matches bei GCER:** ✅ Nicht immer – aktivierbar pro Turnier-Phase durch Admin
- [x] **Öffentlichkeit der Prep-Phase:** ✅ Auch für Teams selbst sichtbar (nur eigene Scores, keine anderen Teams)

---

## Paper-Review-Modul

- [x] **Paper-Struktur:** ✅ Abstract → Introduction → (State of the Art) → Concept/Design → Implementation → Results/Conclusion
- [x] **Format:** ✅ IEEE A4-Template, 2-spaltig, 10pt, single-spaced, max. 5 Seiten inkl. Abbildungen & Referenzen
- [x] **Einreichung:** ✅ PDF via moodle.pria.at (wird durch unser System abgelöst)
- [x] **Präsentation:** ✅ Ausgewählte Papers: bis 10 Min. Vortrag + 5 Min. Q&A
- [x] **Paper-Kategorien 2026:** ✅ Multi Agent Systems / Embracing Educational Robotics / Engineering / STEM Projects
- [x] **Score-Integration:** ✅ `AdaptedDocScore = ½·DocScore + ½·PaperScore` / `PriaOpenOverall = DE + Seeding + ½·PaperScore`
- [x] **Deadlines 2026:** ✅ Einreichung 15. März, Annahme 29. März, Final 5. April
- [x] **Anzahl Reviewer pro Paper:** ✅ Beliebig viele – Admin entscheidet je Paper
- [x] **Blind Review:** ✅ Kein Blind Review – Reviewer sieht welches Team einreicht
- [x] **Interne Review-Runden:** ✅ Beliebig viele, auch unterschiedlich je Team

---

## 3D-Druck-Modul

- [x] **Drucker-Inventar:** ✅ ~5 Drucker (Bambu Lab, Ender/OctoPrint, ggf. Prusa). Adapter vorbereitet.
- [x] **Credentials-Verwaltung:** ✅ Verschlüsselt in DB, Installationsanleitung dokumentiert
- [x] **Limits pro Team:** ✅ Soft Limits (Warnung) + Hard Limits (Stop) in Stunden/Gramm/Jobs
- [x] **Filament-Tracking:** ✅ Ja – pro Job, Team und Saison

---

## Allgemein

- [x] **PDF-Lesbarkeit:** ✅ `poppler-utils` installiert
- [x] **Mehrsprachigkeit:** ✅ Deutsch + Englisch, 1-Klick-Umschalter, i18next
- [x] **Benachrichtigungen:** ✅ Primär eigener SMTP-Server + SendGrid/Mailgun als Fallback; PWA Push-Notifications via Web Push API
- [x] **Öffentliches Scoreboard:** ✅ Intern (hinter Login/Firewall) + separate öffentliche Version die extern gehostet werden kann
- [x] **Dark/Light Mode:** ✅ Systemeinstellung wird erkannt, manueller Umschalter, Einstellung im Profil gespeichert
