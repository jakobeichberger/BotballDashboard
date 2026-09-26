# Todo – offene Aufgaben

Stand: 2026-09-26, Migration `0034`. Hier steht nur, was im Code **nachweislich noch fehlt**. Erledigtes steht in [done.md](done.md), die Einordnung der Audit-Befunde in [audit-2026-09.md](audit-2026-09.md).

---

## Funktionen

- [x] **Score-Sheet 2026: Punktwerte.** Vorlage `botball_2026` mit allen Werten und Multiplikatoren des offiziellen Score-Sheets (`docs/assets/2026-Botball-Seeding-Score-Sheet.pdf`), Tie-Breaker nach Game Review v1.4.

## Abhängigkeiten

Alle Abhängigkeiten sind auf dem neuesten stabilen Stand (September 2026), Betas und Release-Candidates ausgenommen:

- [x] **Frontend:** React 19, React Router 8, Vite 8 (mit `@vitejs/plugin-react` 6 und `vite-plugin-pwa` 1), Vitest 5, Tailwind CSS 4, Zod 4, i18next 26, recharts 3, zustand 5, lucide-react 1, ESLint 10, TypeScript 7 für `tsc`. Der esbuild-Override ist entfallen.
- [x] **Backend:** Python 3.14, bcrypt 5 (Passwörter höchstens 72 Byte, alte Hashes verifizieren weiter), OpenCV 5, reportlab 5, alle übrigen Pakete auf dem neuesten stabilen Stand.
- [x] **Laufzeit und Betrieb:** Node.js 24, PostgreSQL 18 mit automatischer Migration bestehender 16er-Installationen (`scripts/postgres-upgrade.sh`), Redis 8, Prometheus 3.15, Alertmanager 0.34, Blackbox-Exporter 0.28.

Bewusst nicht auf dem neuesten Stand, jeweils mit Grund:

- **pydantic 2.13 / pydantic-core 2.46:** Die nächste Version 2.14 gibt es nur als Beta.
- **TypeScript 6 als Bibliothek:** `tsc` läuft mit TypeScript 7, aber typescript-eslint und openapi-typescript brauchen die JavaScript-API, die es in 7 nicht mehr gibt. Dependabot ignoriert TypeScript-Majors, bis typescript-eslint 7 unterstützt.
- **@types/node 24:** passend zur Laufzeit Node 24.

## Bewusst nicht geplant

- Laufzeit-Plugins, `manifest.json`: Es bleibt bei der statischen Registry.
- Dashboard-Widgets aus der Registry: Die Dashboards wählen ihre Abschnitte selbst nach Rolle (`pages/dashboard`).
- Eigener OCR-Dienst: Die OCR läuft im Worker.
- Audit- oder Error-Log-Oberfläche: Die Daten liegen in `audit_logs` und in den Container-Logs.
- Einladungs-Links und Selbstregistrierung: Konten legen Admins an.
- Prettier: ESLint und `ruff format` genügen.
