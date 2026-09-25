# Self-Improvement – Learnings & Verbesserungen

Dieses Dokument protokolliert was ich im Laufe des Projekts lerne, welche Fehler ich gemacht habe und wie ich mich verbessern kann.

---

## PDF-Verarbeitung

**Problem:** Die PDFs im Repository verwenden eingebettete TrueType-Fonts mit eigener Glyph-Codierung. Standard-Python-Ansätze (zlib-Dekompression + Regex) reichen nicht aus – der Text wird als Glyph-IDs ausgegeben, nicht als lesbarer Text.

**Was funktioniert hat:** Beim `2024-Call-for-Papers.pdf` konnte ich teilweise Text extrahieren, weil diese Datei einige Streams mit direkt lesbaren ASCII-Strings enthält.

**Was nicht funktioniert:** `pypdf`, `pdfminer.six` – scheitern beide an einem kaputten `cryptography`-Modul (`_cffi_backend` fehlt) in dieser Umgebung.

**Lösung für die Zukunft:**
- `poppler-utils` installieren → `pdftotext` Kommandozeilentool
- oder `pymupdf` (fitz) in einer sauberen Python-Umgebung
- Bei neuen Sessions zuerst prüfen: `which pdftotext` oder `python3 -c "import fitz"`

---

## Repository-Synchronisation

**Problem:** Der lokale Branch war hinter `origin/main` – Dateien die auf GitHub existierten, waren lokal nicht vorhanden.

**Lösung:** Immer zuerst `git fetch origin main && git merge origin/main` ausführen bevor ich Dateien im Repository suche.

**Regel für mich:** Wenn der User sagt „ich habe eine Datei hochgeladen" → zuerst `git fetch + merge`, dann erst suchen.

---

## Architekturverständnis

**Gelernt:** Das Projekt ist eine Diplomarbeit. Ursprünglich war eine Plugin-Architektur mit Manifesten geplant. Umgesetzt ist ein **modularer Monolith mit statischer Registry**:
- **Backend:** `backend/core/modules.py` listet alle Router. Fachmodule mit Event-Schalter (Paper, Druck, Bots) bekommen einen Modul-Guard. Es gibt keine `manifest.json` und keine Laufzeit-Plugins.
- **Frontend:** `frontend/src/core/plugins.ts` legt Routen, Navigation, Rechte und Modul-Schalter fest.
- **Eventzentriert:** Die Saison ist das Regelwerk (Module, Formeln, Tie-Breaker, Termine). Wertungen, Ranglisten, Kontingente und Ankündigungen hängen am **Event**. Die Oberfläche läuft unter `/events/:eventId/…`.
- **Modul-Aktivierung pro Event:** `Event.active_modules` zusammen mit den Saison-Flags `use_*` (`modules/events/module_access.py`).
- **Hintergrundarbeit:** Celery-Worker und -Beat übernehmen OCR, Drucker-Polling, Outbox-Zustellung und Erinnerungen. Einen separaten OCR-Dienst gibt es nicht.
- **Live:** Redis Pub/Sub, veröffentlicht nach dem Commit. WebSockets: `/api/v1/public/events/{slug}/ws` (öffentlich) und `/api/v1/events/{event_id}/ws` (angemeldet).
- **Wertung:** strukturierte Score-Sheets (`scoring/sheet.py`, gespiegelt in `calculator.ts`) und die Formel-Engine (`formula.py`, `formula_engine.py`) für die Gesamtwertung.
- **Lebenszyklus:** Archivierte Saisons und Events sind über `ensure_writable` schreibgeschützt.

**Wichtig für Planung:**
- Ein neues Modul braucht genau einen Registry-Eintrag pro Seite, eine Migration mit fortlaufender Nummer und Rechte-Tests.
- Dokumentation muss gegen den Code geprüft werden. `done.md` und Commit-Nachrichten sind kein Beleg (siehe `audit-2026-09.md`).
- Migrationen aus parallelen Branches können dieselbe Nummer tragen, ohne dass Git einen Konflikt meldet (PR #23). Vor dem Merge die Alembic-Kette prüfen.

---

## Botball-Wettbewerb (fachliches Wissen)

**Saison-Struktur:**
- Saison = 1 Kalenderjahr (z.B. 2024, 2025, 2026)
- Jede Saison hat ein neues Thema und neue Scoring-Sheets
- Teams haben 7–9 Wochen Bauzeit nach dem Educator Workshop (Jan–März)

**Turnierformat:**
- **Seeding-Runden:** Team läuft alleine, Score = Summe beider Spielfeldhälften. Die Rangliste nimmt den Ø der besten 2 Läufe. DQ zählt 0, negative Scores zählen 0, Ränge gelten je Kategorie.
- **Double-Elimination:** K.o.-System, 2 Niederlagen = ausgeschieden; nur Sieg/Niederlage zählt (nicht Punktehöhe)
- **Alliance-Matches:** 2 Teams kooperieren (v.a. bei GCER). Der Score ist die Summe beider Seiten.
- **Dokumentation:** Projektplan, Code-Doku, Präsentation → fließt in Gesamtscore ein

**ECER Paper-Prozess (aus 2024 Call for Papers):**
- Track: ECER Engineering (alle Disziplinen inkl. Software)
- Struktur: Concept/Design → Implementation → Results/Conclusion
- Format: A4, 2-spaltig, 10pt, single-spaced
- Einreichung: PDF via moodle.pria.at
- Deadline 2024: 1. April 2024
- Ausgewählte Papers: Präsentation + 5 min Q&A
- Score Calculation: Papers fließen in Gesamtbewertung ein

---

## Kommunikationshinweise

**Gelernt:** Der User kommuniziert auf Deutsch, antwortet kurz und direkt. Nachrichten können abgeschnitten sein (z.B. „eigenst" = „eigenständige Module"). Im Zweifelsfall kurz nachfragen statt falsch annehmen.

---

## Offene Fragen / Dinge die ich noch lernen muss

- [x] Paper-Bewertungskriterien: fünf Kriterien (Inhalt, Umsetzung, Ergebnisse, Sprache, Format), je 0–10, dazu ein Formalabzug.
- [x] Scoring-Sheet-Struktur 2024/2025: als strukturierte Vorlagen umgesetzt. Für 2026 fehlen die exakten Punktwerte (siehe `open-questions.md`).
- [x] Einreichungsplattform: Das System ersetzt Moodle.
- [x] Reviewer pro Paper: beliebig viele, kein Blind Review gegenüber der Organisation.
- [x] Gesamtscore-Formel: als konfigurierbare Formel-Sets umgesetzt (ECER 2025, Regional 2026, GCER 2026).
- [x] 3D-Drucker: Bambu Lab, OctoPrint, manuelle Drucker.
