# Todo – offene Aufgaben

Stand: 2026-09-25, Migration `0030`. Hier steht nur, was im Code **nachweislich noch fehlt**. Erledigtes steht in [done.md](done.md), die Einordnung der Audit-Befunde in [audit-2026-09.md](audit-2026-09.md).

---

## Funktionen

- [ ] **Score-Sheet 2026: Punktwerte.** Die Vorlage enthält nur die Struktur aus dem Game Review. Das offizielle Score-Sheet 2026 mit Punktwerten liegt nicht in `docs/assets`; die Organisation trägt die Werte im Schema-Editor ein, sobald es vorliegt.

## Bewusst nicht geplant

- Laufzeit-Plugins, `manifest.json`: Es bleibt bei der statischen Registry.
- Dashboard-Widgets aus der Registry: Die Dashboards wählen ihre Abschnitte selbst nach Rolle (`pages/dashboard`).
- Eigener OCR-Dienst: Die OCR läuft im Worker.
- Audit- oder Error-Log-Oberfläche: Die Daten liegen in `audit_logs` und in den Container-Logs.
- Einladungs-Links und Selbstregistrierung: Konten legen Admins an.
- Prettier: ESLint und `ruff format` genügen.
