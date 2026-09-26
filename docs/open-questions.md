# Offene Fragen

Protokoll der Fachfragen aus der Planung. Beantwortete Fragen sind abgehakt. Wo die Antwort umgesetzt ist, steht die Stelle im Code dabei (Stand: Migration `0034`). Neue offene Punkte gehören nach [todo.md](todo.md).

---

## Infrastruktur und Tech-Stack

- [x] **Backend-Framework:** FastAPI (async, Pydantic, OpenAPI). Umgesetzt.
- [x] **Monorepo-Tool:** kein Workspace-Tool nötig. `backend/` mit pip, `frontend/` mit pnpm.
- [x] **Hosting:** Self-hosted auf Proxmox, Docker Compose, Traefik. Umgesetzt mit `scripts/proxmox-setup.sh`, `scripts/update.sh` und `scripts/verify-deployment.sh`.

## Auth und Rechte

- [x] **Social Login:** nein, nur E-Mail und Passwort. Passwort-Reset per E-Mail ist umgesetzt (`/api/auth/password-reset/*`).
- [x] **Admin-Oberfläche:** eigene UI. Umgesetzt unter `/settings/*`: Benutzer, Rollen mit editierbaren Rechten, Saisons, Stufen, Drucker, Ankündigungen.

## Scoring

- [x] **Gesamtscore-Formel:** aus den PDFs übernommen. Umgesetzt als konfigurierbare Formel-Sets (`modules/scoring/formula_engine.py`) mit den Presets ECER 2025/2026, Regional 2026, GCER 2026, Aerial und JBC. Wo ECER-Amendments und veröffentlichte Ergebnisse 2026 abweichen, gibt es beide Lesarten als Vorlage.
- [x] **Scoring-Sheet-Felder 2024/2025:** vollständig. Umgesetzt als strukturierte Vorlagen (`modules/scoring/sheet_templates.py`).
- [x] **Scoring-Sheet-Felder 2026:** vollständig aus dem offiziellen Score-Sheet und Game Review v1.4. Umgesetzt als Vorlage `botball_2026` (`modules/scoring/sheet_templates.py`); alle 13 offiziellen Scoring Examples sind Testfälle.
- [x] **Yellow/Red Card:** in `docs/modules/05-scoring.md` dokumentiert. Die Wirkung ist umgesetzt: DQ-Runde = 0, rote Karte ⇒ Team ohne Rang. Gesetzt werden die Karten im Dialog „Strafen und Karten“ der Wertung (`MatchPenaltyDialog`).
- [x] **3D-Druck-Regeln für Roboterteile:** 2025 max. 4 Teile PLA, 2026 max. 6 Teile PLA/PETG. Umgesetzt über Kontingente pro Event und Team und die Druck-Checkliste pro Saison.
- [x] **GCER-Qualifikation:** 1–2 Teams, manuelle Freigabe durch Admins. Umgesetzt: `POST /api/scoring/levels/{id}/qualify`, Qualifikationspanel in der Event-Verwaltung, Registrierung der Qualifizierten.
- [x] **Alliance-Matches bei GCER:** pro Turnierphase aktivierbar. Umgesetzt als Phasentyp `alliance`; Partnerpaare, deren Score die Summe beider Seiten ist.
- [x] **Sichtbarkeit der Vorbereitung:** Teams sehen nur eigene Übungsläufe. Umgesetzt mit `matches.is_practice`. Übungsläufe zählen nirgends für Ranglisten.

## Paper-Review

- [x] **Paper-Struktur und Format:** IEEE A4, 2-spaltig, max. 5 Seiten. Formverstöße werden als **Formalabzug** erfasst.
- [x] **Einreichung:** im System statt über Moodle. Umgesetzt mit Versionen, Deadlines und Sperre nach Abgabe.
- [x] **Präsentation:** ausgewählte Papers 10 Min. + 5 Min. Q&A. Wird außerhalb des Systems organisiert.
- [x] **Paper-Kategorien 2026:** fachliche Info. Das System bildet sie nicht als eigenes Feld ab.
- [x] **Score-Integration:** `AdaptedDocScore = ½·DocScore + ½·PaperScore`, `PriaOpenOverall = DE + Seeding + ½·PaperScore`. Umgesetzt im Standard-Formel-Set (ECER 2025).
- [x] **Deadlines 2026:** Einreichung 15. März, Annahme 29. März, Final 5. April. Pflegbar als offizielle und interne Paper-Deadlines pro Saison (`/api/papers/deadlines`).
- [x] **Reviewer pro Paper:** beliebig viele, Admin entscheidet. Umgesetzt, dazu eine automatische Zuweisung bis N.
- [x] **Blind Review:** nein gegenüber der Organisation. Teams sehen ihr Feedback ohne Namen der Reviewer.
- [x] **Interne Review-Runden:** beliebig viele. Umgesetzt über `revision_number` und Versionen.

## 3D-Druck

- [x] **Drucker-Inventar:** Bambu Lab, OctoPrint und manuelle Drucker. Adapter umgesetzt (`modules/printing/adapters.py`).
- [x] **Credentials:** Fernet-verschlüsselt in der Datenbank.
- [x] **Limits pro Team:** Soft-Limit (Warnung) und Hard-Limit (Teile, optional Gramm). Umgesetzt pro Event und Team. Zeitlimits in Stunden gibt es nicht.
- [x] **Filament-Tracking:** pro Job, Team (Kontingent) und Spule.

## Allgemein

- [x] **PDF-Lesbarkeit:** `poppler-utils` (pdftotext) im Backend-Image.
- [x] **Mehrsprachigkeit:** Deutsch und Englisch mit Umschalter, gespeichert im Konto. Viele Seiten sind noch nicht übersetzt (todo.md).
- [x] **Benachrichtigungen:** SMTP für E-Mail, Web Push (VAPID). Einstellungen pro Kategorie, Benachrichtigungszentrale. Scheitert SMTP, wird SendGrid als Rückfall genutzt, wenn `SENDGRID_API_KEY` gesetzt ist. Mailgun ist nicht eingebunden. Ohne `SMTP_HOST` werden keine E-Mails verschickt.
- [x] **Öffentliches Scoreboard:** interne Ranglisten und eine öffentliche Event-Seite `/public/<slug>` mit Freigaben pro Bereich, Live-Stream und QR-Code. Eine getrennte, extern gehostete Version gibt es nicht. Die öffentliche Seite läuft in derselben Installation.
- [x] **Dark/Light Mode:** Systemeinstellung, Umschalter, im Profil gespeichert.
