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

**Gelernt:** Das Projekt ist eine Diplomarbeit mit Plugin-Architektur:
- **Kern:** Team- & Saisonverwaltung
- **Plugins:** Scoring, Paper-Review, 3D-Druck (und künftige Module)
- Jedes Plugin registriert sich über ein Manifest und bringt eigene Routen, UI-Komponenten und Rollen mit

**Wichtig für Planung:** Neue Module dürfen den Kern nicht verändern müssen. Die Schnittstellen zwischen Kern und Plugins müssen von Anfang an sauber definiert sein.

---

## Botball-Wettbewerb (fachliches Wissen)

**Saison-Struktur:**
- Saison = 1 Kalenderjahr (z.B. 2024, 2025, 2026)
- Jede Saison hat ein neues Thema und neue Scoring-Sheets
- Teams haben 7–9 Wochen Bauzeit nach dem Educator Workshop (Jan–März)

**Turnierformat:**
- **Seeding-Runden:** Team läuft alleine, Score = Summe beider Spielfeldhälften; Durchschnitt der besten 2 von 3 Runs
- **Double-Elimination:** K.o.-System, 2 Niederlagen = ausgeschieden; nur Sieg/Niederlage zählt (nicht Punktehöhe)
- **Alliance-Matches:** 2 Teams kooperieren (v.a. bei GCER)
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

- [ ] Genaue Paper-Bewertungskriterien (Punkte, Kategorien) aus den 2025/2026 CfP Dokumenten
- [ ] Genaue Scoring-Sheet-Struktur 2024/2025/2026 (Aufgabenkategorien, Multiplikatoren)
- [ ] Ob `moodle.pria.at` weiterhin die Einreichungsplattform ist oder abgelöst wird (→ unser System übernimmt das)
- [ ] Anzahl der Reviewer pro Paper, ob blind review oder offen
- [ ] Präzise Gesamtscore-Formel (Seeding + Double-Elimination + Dokumentation)
- [ ] Welche 3D-Drucker konkret im Einsatz sind (Hersteller/Modelle)
