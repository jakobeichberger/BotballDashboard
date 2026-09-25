# Todo – offene Aufgaben

Stand: 2026-09-25, Commit `aa61752`, Migration `0029`. Hier steht nur, was im Code **nachweislich noch fehlt**. Erledigtes steht in [done.md](done.md), die Einordnung der Audit-Befunde in [audit-2026-09.md](audit-2026-09.md).

---

## Funktionen

- [ ] **OCR-Anker und Prüfregeln ohne Editor.** Der Layout-Editor der Score-Sheet-Vorlagen setzt Seitengröße und Feldbereiche; `anchors` und `validation_rules` bleiben beim Speichern unverändert. Der Worker nutzt beide derzeit auch nicht (die Seite wird über die größte Kontur ausgerichtet).
- [ ] **i18n unvollständig.** Nur `DashboardPage`, `PublicEventPage` und `EventScoringPage` (plus Layout und Komponenten) nutzen `useTranslation`. 27 Seiten enthalten fest deutschen Text. Die Rückfallsprache ist `de` (`frontend/src/i18n/config.ts`), laut Spezifikation Englisch.
- [ ] **Registry-Felder ungenutzt.** `dashboardWidgets` und `translations` in `frontend/src/core/plugins.ts` liest keine Komponente. Entweder anbinden oder entfernen.
- [ ] **Score-Sheet 2026.** Die Vorlage enthält nur die Struktur aus dem Game Review. Die Punktwerte trägt die Organisation im Schema-Editor ein.

## Qualität und Betrieb

- [ ] **E2E in CI:** Nur `frontend/e2e/platform.spec.ts` läuft. `auth`, `gallery` und `scoring` brauchen Seed-Daten, die `backend/scripts/seed_e2e.py` nicht anlegt.
- [ ] **Keine Coverage-Schwellen.** Das Backend läuft mit `--cov`, aber ohne `fail_under`. Vitest hat keine thresholds. Prettier gibt es nicht (Pre-commit: ruff, eslint, shellcheck, YAML).
- [ ] **Passwort-Policy:** mindestens 10 Zeichen, kein Wiederholungszeichen, nicht die E-Mail. Es gibt keine Prüfung gegen bekannte geleakte Passwörter.
- [ ] **Off-site-Backup** ist dokumentiert (`BACKUP_HOST_DIR` plus rsync/rclone per Cron, siehe [operations.md](operations.md)), wird aber nicht von der Installation eingerichtet.

## Bewusst nicht geplant

- Laufzeit-Plugins, `manifest.json`: Es bleibt bei der statischen Registry.
- Eigener OCR-Dienst: Die OCR läuft im Worker.
- Audit- oder Error-Log-Oberfläche: Die Daten liegen in `audit_logs` und in den Container-Logs.
- Einladungs-Links und Selbstregistrierung: Konten legen Admins an.
