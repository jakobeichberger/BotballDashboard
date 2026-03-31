# Modul 02 – Authentifizierung & Rechtesystem

**Status:** [ ] Offen  
**Typ:** Kern  
**Kommuniziert mit:** Allen Backend-Modulen

---

## Beschreibung

Zentrales Auth-System für den gesamten Kern und alle Plugins. Verwaltet Benutzer, Rollen und Berechtigungen. Rollen sind erweiterbar – neue Module können eigene Rollen per Manifest mitbringen.

---

## Features

### Benutzerverwaltung
- Registrierung (E-Mail + Passwort)
- Login mit JWT-Token (Access + Refresh Token)
- Passwort-Reset per E-Mail
- Profilverwaltung (Name, E-Mail, Avatar)
- Account deaktivieren / löschen (DSGVO)

### Rollen & Berechtigungen
Initiale Rollen:

| Rolle | Beschreibung |
|---|---|
| `admin` | Vollzugriff auf alle Module und Einstellungen |
| `juror` | Darf Scores eingeben und korrigieren (Scoring-Modul) |
| `reviewer` | Darf Papers bewerten und Revisionen anfordern (Paper-Review-Modul) |
| `mentor` | Betreuer eines oder mehrerer Teams, Lesezugriff auf Teamdaten |
| `guest` | Nur Lesezugriff auf öffentliche Inhalte (Ranglisten, Ergebnisse) |

- Rollen können Benutzern direkt oder über eine Gruppe zugewiesen werden
- Plugins können eigene Rollen per `manifest.json` registrieren
- **Juror*innen und Reviewer*innen müssen keine Teammitglieder sein** – sie können externe Personen sein (z.B. Lehrpersonen anderer Schulen, KIPR-Volunteers, externe Experten). Ein Account kann ohne jede Teamzugehörigkeit nur mit der Rolle `juror` oder `reviewer` existieren.
- Berechtigungen sind fein granular: z.B. `scoring:write`, `paper:review`, `team:edit`

### Token-Verwaltung
- JWT Access Token (kurzlebig, z.B. 15 Minuten)
- Refresh Token (langlebig, z.B. 30 Tage, in HTTP-Only Cookie)
- Token-Revokation bei Logout oder Passwortänderung

### Sicherheit & Compliance
- Passwörter mit bcrypt gehasht
- DSGVO-konform: Recht auf Auskunft, Löschung, Export der eigenen Daten
- Audit Trail: Jede Aktion wird mit User-ID und Timestamp geloggt
- Rate-Limiting auf Login-Endpunkten gegen Brute-Force

---

## API-Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| POST | `/auth/register` | Neuen Benutzer registrieren |
| POST | `/auth/login` | Login, gibt JWT zurück |
| POST | `/auth/logout` | Logout, invalidiert Token |
| POST | `/auth/refresh` | Access Token erneuern |
| POST | `/auth/password-reset` | Passwort-Reset anfordern |
| GET | `/auth/me` | Eigenes Profil abrufen |
| PUT | `/auth/me` | Eigenes Profil bearbeiten |
| GET | `/admin/users` | Alle Benutzer auflisten (Admin) |
| PUT | `/admin/users/:id/roles` | Rollen eines Benutzers setzen (Admin) |

---

## Schnittstellen zu anderen Modulen

| Richtung | Modul | Art |
|---|---|---|
| → | Alle Backend-Module | JWT-Middleware (jeder Request wird geprüft) |
| ← | Scoring-Modul | Registriert Rolle `juror` |
| ← | Paper-Review-Modul | Registriert Rolle `reviewer` |
| ← | 3D-Druck-Modul | Registriert Rolle `print_manager` |

---

## Entschiedene Fragen
- [x] **Social Login:** Kein OAuth2 / Social Login – nur E-Mail + Passwort
- [x] **Admin-Oberfläche:** Eigene Admin-UI zur Benutzerverwaltung (nicht nur API)
