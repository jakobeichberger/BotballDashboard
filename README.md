# BotballDashboard

Webbasierte Plattform zur Verwaltung und Auswertung des Botball-Wettbewerbs. Modulare Plugin-Architektur mit Team- und Saisonverwaltung als Kern.

---

## Architektur

```
KERN
├── Saisonverwaltung   (Saisons, Archivierung, Vorlagen)
├── Teamverwaltung     (Teams, Mitglieder, Betreuer, Historie)
└── Auth               (Benutzer, Rollen, JWT)

PLUGINS (eigenständig, erweiterbar)
├── Scoring-Modul      (Turnierbewertung, OCR, Live-Ranglisten)
├── Paper-Review-Modul (Einreichung, Begutachtung, Revisionen)
└── 3D-Druck-Modul     (Druckjob-Verwaltung, Multi-Hersteller-Adapter)

ÜBERGREIFEND
├── Dashboard          (Visualisierungen, Live-Updates, Export)
├── Mobile / PWA       (Offline-fähige mobile Oberfläche)
├── Testing            (Unit, Integration, E2E)
└── Dokumentation
```

Jedes Plugin registriert sich über ein `manifest.json` beim Kern und bringt eigene API-Routen, UI-Komponenten und Rollen mit. Neue Module können hinzugefügt werden ohne den Kern zu verändern.

---

## Dokumentation

| Dokument | Beschreibung |
|---|---|
| [`docs/auftrag.md`](docs/auftrag.md) | Aufgabenstellung |
| [`docs/projektbeschreibung.md`](docs/projektbeschreibung.md) | Detaillierte Projektbeschreibung |
| [`docs/todo.md`](docs/todo.md) | Offene Aufgaben pro Modul |
| [`docs/done.md`](docs/done.md) | Erledigte Module |
| [`docs/self-improvement.md`](docs/self-improvement.md) | Learnings & Verbesserungen |

### Modul-Dokumentation

| # | Modul | Typ | Status |
|---|---|---|---|
| 01 | [Infrastruktur](docs/modules/01-infrastruktur.md) | Basis | [ ] Offen |
| 02 | [Auth & Rechtesystem](docs/modules/02-auth.md) | Kern | [ ] Offen |
| 03 | [Saisonverwaltung](docs/modules/03-saisonverwaltung.md) | Kern | [ ] Offen |
| 04 | [Teamverwaltung](docs/modules/04-teamverwaltung.md) | Kern | [ ] Offen |
| 05 | [Scoring-Modul](docs/modules/05-scoring.md) | Plugin | [ ] Offen |
| 06 | [Paper-Review-Modul](docs/modules/06-paper-review.md) | Plugin | [ ] Offen |
| 07 | [3D-Druck-Modul](docs/modules/07-3d-druck.md) | Plugin | [ ] Offen |
| 08 | [Dashboard & Visualisierung](docs/modules/08-dashboard.md) | Kern | [ ] Offen |
| 09 | [Mobile App / PWA](docs/modules/09-mobile-pwa.md) | Frontend | [ ] Offen |
| 10 | [Testing](docs/modules/10-testing.md) | Querschnitt | [ ] Offen |
| 11 | [Dokumentation](docs/modules/11-dokumentation.md) | Querschnitt | [ ] Offen |

---

## Referenzdokumente

| Datei | Beschreibung |
|---|---|
| [`docs/assets/2024-Call-for-Papers.pdf`](docs/assets/2024-Call-for-Papers.pdf) | Call for Papers 2024 |
| [`docs/assets/2024-Botball-Game-Review-v1.0.pdf`](docs/assets/2024-Botball-Game-Review-v1.0.pdf) | Game Review 2024 |
| [`docs/assets/2025 Call for Papers v1.0.pdf`](<docs/assets/2025 Call for Papers v1.0.pdf>) | Call for Papers 2025 |
| [`docs/assets/2025 Botball Game Review v1.2.pdf`](<docs/assets/2025 Botball Game Review v1.2.pdf>) | Game Review 2025 |
| [`docs/assets/2026 Call for Papers v1.0.pdf`](<docs/assets/2026 Call for Papers v1.0.pdf>) | Call for Papers 2026 |
| [`docs/assets/2026 Botball Game Review v1.3.pdf`](<docs/assets/2026 Botball Game Review v1.3.pdf>) | Game Review 2026 |
