# Konfigurationsreferenz

Alle Konfigurationsoptionen des BotballDashboard. Die Konfiguration erfolgt über eine `.env`-Datei im Projektstamm.

---

## .env Übersicht

```bash
cp .env.example .env
# Dann .env mit einem Editor öffnen und anpassen
```

---

## Datenbank

| Variable | Pflicht | Standard | Beschreibung |
|---|---|---|---|
| `POSTGRES_HOST` | ✓ | `db` | Hostname des PostgreSQL-Containers |
| `POSTGRES_PORT` | | `5432` | PostgreSQL-Port |
| `POSTGRES_DB` | ✓ | `botball` | Datenbankname |
| `POSTGRES_USER` | ✓ | `botball` | Datenbankbenutzer |
| `POSTGRES_PASSWORD` | ✓ | – | Datenbankpasswort (sicher wählen!) |
| `DATABASE_URL` | | _(auto)_ | Wird automatisch aus den obigen Werten gebaut |

---

## Sicherheit

| Variable | Pflicht | Standard | Beschreibung |
|---|---|---|---|
| `SECRET_KEY` | ✓ | – | App-Secret für Verschlüsselung (min. 32 Zeichen, zufällig) |
| `JWT_SECRET` | ✓ | – | Secret für JWT-Token-Signierung |
| `JWT_ACCESS_EXPIRE_MINUTES` | | `15` | Gültigkeitsdauer Access-Token in Minuten |
| `JWT_REFRESH_EXPIRE_DAYS` | | `30` | Gültigkeitsdauer Refresh-Token in Tagen |
| `ALLOWED_HOSTS` | ✓ | – | Komma-getrennte Liste erlaubter Domains |
| `CORS_ORIGINS` | ✓ | – | Erlaubte CORS-Origins (Frontend-URL) |

Zufälligen Secret Key generieren:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Domain & URLs

| Variable | Pflicht | Standard | Beschreibung |
|---|---|---|---|
| `DOMAIN` | ✓ | – | Haupt-Domain (z.B. `dashboard.meineschule.at`) |
| `PUBLIC_SCOREBOARD_DOMAIN` | | – | Domain für öffentliches Scoreboard (optional) |
| `BACKEND_URL` | | _(auto)_ | Backend-API-URL, normalerweise aus DOMAIN abgeleitet |
| `FRONTEND_URL` | | _(auto)_ | Frontend-URL |

---

## E-Mail / SMTP

| Variable | Pflicht | Standard | Beschreibung |
|---|---|---|---|
| `SMTP_HOST` | ✓ | – | SMTP-Server-Hostname |
| `SMTP_PORT` | | `587` | SMTP-Port (587 = STARTTLS, 465 = SSL) |
| `SMTP_USER` | ✓ | – | SMTP-Benutzername |
| `SMTP_PASSWORD` | ✓ | – | SMTP-Passwort |
| `SMTP_FROM` | ✓ | – | Absender-Adresse (z.B. `BotballDashboard <noreply@schule.at>`) |
| `SMTP_USE_TLS` | | `true` | STARTTLS aktivieren |
| `EMAIL_FALLBACK_PROVIDER` | | – | `sendgrid` oder `mailgun` als Fallback |
| `SENDGRID_API_KEY` | | – | SendGrid API-Key (nur wenn Fallback = sendgrid) |
| `MAILGUN_API_KEY` | | – | Mailgun API-Key (nur wenn Fallback = mailgun) |
| `MAILGUN_DOMAIN` | | – | Mailgun-Domain |

---

## Datei-Uploads

| Variable | Pflicht | Standard | Beschreibung |
|---|---|---|---|
| `UPLOAD_PATH` | | `/app/uploads` | Pfad für hochgeladene Dateien (im Container) |
| `MAX_UPLOAD_SIZE_MB` | | `50` | Maximale Upload-Größe in MB |
| `ALLOWED_UPLOAD_TYPES` | | `pdf,stl,3mf` | Erlaubte Dateiendungen (komma-getrennt) |

---

## OCR-Service

| Variable | Pflicht | Standard | Beschreibung |
|---|---|---|---|
| `OCR_ENABLED` | | `true` | OCR-Funktionalität aktivieren |
| `OCR_SERVICE_URL` | | `http://ocr:8001` | URL des OCR-Service-Containers |

---

## Benachrichtigungen / Push

| Variable | Pflicht | Standard | Beschreibung |
|---|---|---|---|
| `VAPID_PRIVATE_KEY` | | – | VAPID Private Key für Web Push (generieren mit `pywebpush`) |
| `VAPID_PUBLIC_KEY` | | – | VAPID Public Key (wird an Frontend gegeben) |
| `VAPID_CLAIM_EMAIL` | | – | E-Mail-Adresse für VAPID-Claims |

VAPID-Keys generieren:
```bash
docker compose exec backend python -c "
from py_vapid import Vapid
v = Vapid()
v.generate_keys()
print('Private:', v.private_key)
print('Public:', v.public_key)
"
```

---

## Sprache & Lokalisierung

| Variable | Pflicht | Standard | Beschreibung |
|---|---|---|---|
| `DEFAULT_LANGUAGE` | | `de` | Standard-Sprache (`de` oder `en`) |
| `TIMEZONE` | | `Europe/Vienna` | Zeitzone für Deadlines und Logs |

---

## Feature Flags

| Variable | Pflicht | Standard | Beschreibung |
|---|---|---|---|
| `FEATURE_PAPER_REVIEW` | | `true` | Paper-Review-Modul aktivieren |
| `FEATURE_3D_PRINT` | | `true` | 3D-Druck-Modul aktivieren |
| `FEATURE_OCR` | | `true` | OCR-Upload aktivieren |
| `FEATURE_PUBLIC_SCOREBOARD` | | `true` | Öffentliches Scoreboard aktivieren |
| `FEATURE_PWA_PUSH` | | `true` | PWA Push-Benachrichtigungen aktivieren |

---

## Entwicklung

| Variable | Pflicht | Standard | Beschreibung |
|---|---|---|---|
| `DEBUG` | | `false` | Debug-Modus (nie in Produktion!) |
| `LOG_LEVEL` | | `info` | Log-Level (`debug`, `info`, `warning`, `error`) |
| `DEV_RELOAD` | | `false` | Hot-Reload im Backend (nur Entwicklung) |

---

## Vollständiges .env.example

```env
# === Datenbank ===
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=botball
POSTGRES_USER=botball
POSTGRES_PASSWORD=CHANGE_ME

# === Sicherheit ===
SECRET_KEY=CHANGE_ME_MIN_32_CHARS
JWT_SECRET=CHANGE_ME_ANOTHER_SECRET
JWT_ACCESS_EXPIRE_MINUTES=15
JWT_REFRESH_EXPIRE_DAYS=30

# === Domain ===
DOMAIN=dashboard.meineschule.at
PUBLIC_SCOREBOARD_DOMAIN=scoreboard.meineschule.at
ALLOWED_HOSTS=dashboard.meineschule.at,scoreboard.meineschule.at
CORS_ORIGINS=https://dashboard.meineschule.at

# === E-Mail ===
SMTP_HOST=mail.meineschule.at
SMTP_PORT=587
SMTP_USER=dashboard@meineschule.at
SMTP_PASSWORD=CHANGE_ME
SMTP_FROM=BotballDashboard <dashboard@meineschule.at>
SMTP_USE_TLS=true

# === Uploads ===
UPLOAD_PATH=/app/uploads
MAX_UPLOAD_SIZE_MB=50

# === Sprache & Zeit ===
DEFAULT_LANGUAGE=de
TIMEZONE=Europe/Vienna

# === Features ===
FEATURE_PAPER_REVIEW=true
FEATURE_3D_PRINT=true
FEATURE_OCR=true
FEATURE_PUBLIC_SCOREBOARD=true
FEATURE_PWA_PUSH=true

# === Entwicklung (in Produktion auf false lassen!) ===
DEBUG=false
LOG_LEVEL=info
```
