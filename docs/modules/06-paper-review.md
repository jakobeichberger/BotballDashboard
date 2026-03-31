# Modul 06 – Paper-Review-Modul

**Status:** [ ] Offen  
**Typ:** Plugin  
**Registriert beim Kern via:** `modules/paper-review/manifest.json`  
**Kommuniziert mit:** Saisonverwaltung, Teamverwaltung, Auth

---

## Beschreibung

Eigenständiges Plugin für die Verwaltung und Bewertung der ECER-Papers. Teams reichen ihre Papers ein, Reviewer vergeben strukturiertes Feedback und Benotungen, bei Bedarf werden Revisionen angefordert. Unterstützt mehrere Reviewrunden pro Paper.

---

## Hintergrund (aus Call for Papers 2024–2026)

### Paper-Struktur (alle Jahre identisch)
Abstract → Introduction → (State of the Art / Literature Review) → Concept/Design → Implementation → Results/Conclusion

### Format (alle Jahre identisch)
- IEEE A4-Template (Word, LaTeX oder Typst)
- 2-spaltig, single-spaced, 10pt
- Max. 5 Seiten inkl. Abbildungen & Referenzen
- Formatverstöße oder KI-Missbrauch → Punktabzug bis 100% / Ablehnung

### Themen-Schwerpunkte (jährlich wechselnd)
| Saison | Hauptthema | Dauerthemen |
|---|---|---|
| 2024 | Software Development Practices | Embracing Educational Robotics, Engineering, STEM Projects |
| 2025 | Artificial Intelligence | Embracing Educational Robotics, Engineering, STEM Projects |
| 2026 | Multi Agent Systems | Embracing Educational Robotics, Engineering, STEM Projects |

### Offizielle Deadlines
| | 2024 | 2025 | 2026 |
|---|---|---|---|
| Einreichung | 10. März | 9. März | 15. März |
| Annahme-Benachrichtigung | 24. März | 23. März | 29. März |
| Final Submission | 1. April | 30. März | 5. April |

### Einreichungsplattform
- Bisher: moodle.pria.at → wird durch dieses Modul abgelöst

### Präsentation
- Ausgewählte Papers: bis 10 Min. Vortrag + 5 Min. Q&A
- Auswahl durch Program Committee

### Score-Relevanz
```
AdaptedDocScore = ½ × DocScore + ½ × PaperScore
PriaOpenOverall = DEScore + SeedScore + ½ × PaperScore
```

---

## Features

### Team-Typen & Paper-Pflicht

| Team-Typ | Paper-Pflicht (offiziell) | Paper-Pflicht (bei uns) | Score-Auswirkung |
|---|---|---|---|
| Botball | Empfohlen, freiwillig | **Pflicht** | AdaptedDocScore = ½·DocScore + ½·PaperScore |
| Open (PRIA Open) | Pflicht | **Pflicht** | PRIA Overall = DE + Seeding + ½·PaperScore |

> Beide Team-Typen müssen bei uns ein Paper einreichen. Das System erzwingt dies über eine Pflichtprüfung vor Ablauf der internen Paper-Deadline.

### Paper-Einreichung (Team-Seite)
- PDF-Upload des Papers (max. Dateigröße konfigurierbar)
- Pflichtfelder: Titel, Autoren, Abstract, Saison, Kategorie, **Team-Typ** (automatisch aus Teammitgliedschaft)
- Versionierung: Teams können überarbeitete Versionen hochladen
- Status-Tracking: Team sieht aktuellen Status seines Papers jederzeit
- Deadline-Enforcement: Upload nach offizieller Deadline nicht mehr möglich (außer Admin-Override)
- **Pflichtwarnung:** Teams ohne eingreichtes Paper erhalten ab einer konfigurierbaren Vorwarnung (z.B. 7 Tage vor Deadline) tägliche Erinnerungen

### Paper-Status-Workflow

```
submitted → under_review → revision_requested → resubmitted → accepted | rejected
                        ↘ accepted | rejected
```

### Reviewer-Zuweisung (Admin-Seite)
- Manuelle Zuweisung: Admin weist Paper einem oder mehreren Reviewern zu
- Automatische Zuweisung: Round-Robin oder nach Expertise-Tags
- Konfliktprüfung: Reviewer darf kein Paper der eigenen Schule bewerten
- Reviewer-Pool verwaltbar: welche Benutzer haben die Rolle `reviewer`?
- **Reviewer müssen keine Teammitglieder sein** – externe Personen (Lehrpersonen anderer Schulen, KIPR-Volunteers, Experten) können als Reviewer eingeladen werden. Sie benötigen nur einen Account mit Rolle `reviewer`, keine Teamzugehörigkeit.

### Review-Formular (Reviewer-Seite)
- Strukturiertes Feedback mit Bewertungskategorien:
  - Inhaltliche Qualität (Concept/Design)
  - Technische Umsetzung (Implementation)
  - Ergebnisse & Schlussfolgerungen (Results/Conclusion)
  - Sprachliche Qualität
  - Formale Anforderungen (Format, Länge)
- Pro Kategorie: Note (1–5 oder Punkte) + Freitext-Kommentar
- Gesamtnote + Empfehlung: `accept` / `minor_revision` / `major_revision` / `reject`
- Revisions-Anforderung: Reviewer beschreibt konkret was geändert werden soll

### Revisions-Workflow
- Reviewer fordert Revision an → Team erhält Benachrichtigung
- Team lädt überarbeitete Version hoch
- Reviewer bewertet neue Version (kann vorherige Reviews einsehen)
- Mehrere Revisions-Runden möglich

### Versionierung
- Alle eingereichten Versionen werden gespeichert
- Alle Reviews zu jeder Version bleiben erhalten
- Diff-Ansicht zwischen Versionen (falls technisch machbar)

### Deadline-Verwaltung

Das System unterscheidet zwischen **offiziellen Deadlines** (vom Veranstalter KIPR/PRIA vorgegeben) und **internen Deadlines** (von uns selbst für den internen Review-Prozess gesetzt):

| Deadline-Typ | Beschreibung | Wer setzt sie |
|---|---|---|
| `official_submission` | Offizielle Einreichungsfrist des Veranstalters | Admin (aus CfP übernommen) |
| `official_final` | Finale offizielle Abgabefrist nach Revision | Admin |
| `internal_draft` | Interne Frist für erste Paper-Entwürfe der Teams | Admin |
| `internal_review` | Interne Frist bis wann Reviewer ihre Reviews abgegeben haben sollen | Admin |
| `internal_revision` | Interne Frist für Team-Revisionen nach internem Review | Admin |
| `internal_final` | Interne finale Abgabe vor der offiziellen Deadline | Admin |

- Interne Deadlines liegen typischerweise **vor** den offiziellen Deadlines (Puffer für Korrekturen)
- Pro Saison können beliebig viele interne Deadlines angelegt werden
- Alle Deadlines sind im Kalender / Dashboard-Widget sichtbar
- Automatische Erinnerungen: 7 Tage, 3 Tage, 1 Tag vor jeder Deadline
- Nach Ablauf einer internen Deadline: Warnhinweis im Dashboard (kein hard Block, Admin kann verlängern)
- Nach Ablauf der offiziellen Deadline: Upload gesperrt (außer Admin-Override)

### Benachrichtigungen
- E-Mail bei: neuer Reviewer-Zuweisung, neuem Review, Revisions-Anforderung, Status-Änderung
- Automatische Erinnerungen vor allen Deadlines (intern + offiziell)
- Optional: Push-Benachrichtigung (PWA)

### Admin-Übersicht
- Alle Papers einer Saison mit aktuellem Status
- Welche Papers warten noch auf Review?
- Statistiken: Durchschnittsnoten, Annahme-/Ablehnungsquote

### Export
- Bewertungszusammenfassung pro Paper als PDF
- Alle Reviews einer Saison als CSV
- Angenommene Papers als Liste (für Konferenzprogramm)

---

## Datenmodell

```
PaperDeadline {
  id, season_id, type: official_submission|official_final|internal_draft|
                        internal_review|internal_revision|internal_final,
  date: datetime, label: string, is_hard_block: boolean
}

Paper {
  id, season_id, team_id, title, authors: string[],
  abstract, category, status, submitted_at,
  current_version_id
}

PaperVersion {
  id, paper_id, version_number, file_url,
  submitted_at, submitted_by
}

Review {
  id, paper_version_id, reviewer_id,
  scores: ReviewScore[], overall_score,
  recommendation: accept|minor_revision|major_revision|reject,
  revision_notes, submitted_at
}

ReviewScore {
  category, score, comment
}
```

---

## API-Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| POST | `/papers` | Paper einreichen |
| GET | `/papers` | Papers auflisten (gefiltert nach Rolle) |
| GET | `/papers/:id` | Paper-Details abrufen |
| POST | `/papers/:id/versions` | Neue Version hochladen |
| POST | `/papers/:id/assign` | Reviewer zuweisen (Admin) |
| POST | `/papers/:id/reviews` | Review einreichen (Reviewer) |
| GET | `/papers/:id/reviews` | Reviews abrufen |
| PUT | `/papers/:id/status` | Status manuell setzen (Admin) |

---

## Schnittstellen zu anderen Modulen

| Richtung | Modul | Art |
|---|---|---|
| ← | Saisonverwaltung | `season_id`, Deadlines |
| ← | Teamverwaltung | `team_id` für Paper-Zuweisung |
| ← | Auth | Rolle `reviewer` für Zugriffskontrolle |
| → | Dashboard | Paper-Statistiken, Bewertungsübersicht |
| → | Scoring-Modul | Dokumentationspunkte fließen in Gesamtscore ein |
