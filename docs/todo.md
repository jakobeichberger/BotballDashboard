# Todo – offene Aufgaben

Stand: 2026-09-25, Migration `0030`. Hier steht nur, was im Code **nachweislich noch fehlt**. Erledigtes steht in [done.md](done.md), die Einordnung der Audit-Befunde in [audit-2026-09.md](audit-2026-09.md).

---

## Funktionen

- [ ] **Score-Sheet 2026: Punktwerte.** Die Vorlage enthält nur die Struktur aus dem Game Review. Das offizielle Score-Sheet 2026 mit Punktwerten liegt nicht in `docs/assets`; die Organisation trägt die Werte im Schema-Editor ein, sobald es vorliegt.

## Abhängigkeiten: bewusst zurückgestellte Major-Updates

Minor- und Patch-Stände sind aktuell (September 2026). Diese Majors warten auf das geplante Design-Refresh, weil sie Komponenten, Routing, Styles oder Formularvalidierung breit ändern und zusammen mit dem neuen Design getestet werden sollen. Dependabot ignoriert sie bis dahin (`.github/dependabot.yml`).

- [ ] **React 19** (`react`, `react-dom`, `@types/react*`, dazu `@testing-library/react` 16): neue Ref- und Form-APIs, entfernte Legacy-APIs.
- [ ] **React Router 7** (`react-router-dom`): neues Paket `react-router`, geänderte Data-APIs. Behebt zwei moderate Advisories (Open Redirect in `<Link>`, Constructor Injection), die `pnpm audit` meldet.
- [ ] **Vite 8** mit `@vitejs/plugin-react` 6 und `vite-plugin-pwa` 1: neuer Bundler (Rolldown), geänderte Plugin-API. Bis dahin ist esbuild per Override auf `^0.25` gehalten; esbuild 0.28 bricht den Service-Worker-Build von Vite 6.
- [ ] **Vitest 5** mit `@vitest/coverage-v8` 5 (behebt die moderate Path-Traversal-Advisory des Dev-Servers).
- [ ] **Tailwind CSS 4**: CSS-first-Konfiguration statt `tailwind.config.ts`.
- [ ] **Zod 4** mit `@hookform/resolvers` 5: geänderte Fehler- und Schema-APIs.
- [ ] Weitere Majors ohne Zwang zum Wechsel: `date-fns` 4, `i18next` 26 / `react-i18next` 17, `recharts` 3, `zustand` 5, `lucide-react` 1, `jsdom` 30, `jest-axe` 11, TypeScript 7, ESLint 10 (die CI nutzt ESLint 9 mit Flat Config).

Backend:

- [ ] **bcrypt 5** lehnt Passwörter über 72 Byte mit `ValueError` ab (4.x kürzt still). Vorher braucht die Passwort-Richtlinie eine Obergrenze oder ein Pre-Hashing; bis dahin bleibt bcrypt 4.3.
- [ ] **Node.js 24** (aktuelles LTS) nach dem Design-Refresh; CI, Images und `proxmox-setup.sh` nutzen Node 22 (LTS bis April 2027).

## Bewusst nicht geplant

- Laufzeit-Plugins, `manifest.json`: Es bleibt bei der statischen Registry.
- Dashboard-Widgets aus der Registry: Die Dashboards wählen ihre Abschnitte selbst nach Rolle (`pages/dashboard`).
- Eigener OCR-Dienst: Die OCR läuft im Worker.
- Audit- oder Error-Log-Oberfläche: Die Daten liegen in `audit_logs` und in den Container-Logs.
- Einladungs-Links und Selbstregistrierung: Konten legen Admins an.
- Prettier: ESLint und `ruff format` genügen.
