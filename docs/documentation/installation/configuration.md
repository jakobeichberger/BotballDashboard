# Konfigurationsreferenz

Die Anwendung liest ihre Konfiguration aus der `.env`-Datei im Projektverzeichnis. Ausgangspunkt ist `.env.example`. Im Produktionsmodus verweigert das Backend den Start, solange Beispielwerte oder zu kurze Secrets verwendet werden.

## Anwendung und Domain

| Variable | Standard | Beschreibung |
|---|---|---|
| `APP_ENV` | `production` | `development` oder `production` |
| `APP_SECRET_KEY` | – | Zufälliges Secret mit mindestens 24 Zeichen |
| `APP_BASE_URL` | – | Öffentliche HTTPS-URL |
| `ALLOWED_ORIGINS` | – | Komma-getrennte erlaubte CORS-Origins |
| `DOMAIN` | – | Hostname für die Traefik-Router |
| `TRAEFIK_EMAIL` | – | E-Mail für Let's Encrypt |

## PostgreSQL

| Variable | Standard | Beschreibung |
|---|---|---|
| `POSTGRES_HOST` | `db` | Datenbank-Host |
| `POSTGRES_PORT` | `5432` | Datenbank-Port |
| `POSTGRES_DB` | `botball` | Datenbankname |
| `POSTGRES_USER` | `botball` | Datenbankbenutzer |
| `POSTGRES_PASSWORD` | – | Sicheres Datenbankpasswort |
| `PGDATA_DRIVER_OPT_TYPE` | – | Für den Proxmox-Bind-Mount: `none` |
| `PGDATA_DRIVER_OPT_O` | – | Für den Proxmox-Bind-Mount: `bind` |
| `PGDATA_DRIVER_OPT_DEVICE` | – | Beispielsweise `/data/db` |

Die URL wird im Backend sicher aus den Einzelwerten zusammengesetzt. `DATABASE_URL` wird nicht benötigt.

## Authentifizierung

| Variable | Standard | Beschreibung |
|---|---|---|
| `JWT_SECRET_KEY` | – | Eigenständiges zufälliges JWT-Secret |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Lebensdauer des Access-Tokens |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Lebensdauer des Refresh-Tokens |

Secrets erzeugen:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## E-Mail

| Variable | Standard | Beschreibung |
|---|---|---|
| `SMTP_HOST` | leer | SMTP-Server; leer deaktiviert SMTP |
| `SMTP_PORT` | `587` | SMTP-Port |
| `SMTP_USER` | leer | SMTP-Benutzer |
| `SMTP_PASSWORD` | leer | SMTP-Passwort |
| `SMTP_FROM` | – | Absender |
| `SMTP_TLS` | `true` | STARTTLS verwenden |
| `SENDGRID_API_KEY` | leer | Optionaler Fallback |
| `SENDGRID_FROM` | leer | SendGrid-Absender |

## Web Push

| Variable | Standard | Beschreibung |
|---|---|---|
| `VAPID_PRIVATE_KEY` | `/app/vapid/private_key.pem` | Pfad zum privaten Schlüssel im Docker-Volume |
| `VAPID_PUBLIC_KEY` | leer | URL-safe Base64 Application Server Key fürs Frontend |
| `VAPID_ADMIN_EMAIL` | – | Kontaktadresse für VAPID-Claims |

Bei Docker-Installation erzeugt `make vapid-keys` das Schlüsselpaar. Das Proxmox-Setup erledigt diesen Schritt automatisch.

## Drucker und Dateien

| Variable | Standard | Beschreibung |
|---|---|---|
| `PRINTER_CREDENTIAL_ENCRYPTION_KEY` | – | Fernet-Schlüssel für Drucker-Credentials |
| `UPLOAD_DIR` | `/app/uploads` | Upload-Verzeichnis |
| `MAX_UPLOAD_SIZE_MB` | `20` | Maximale Uploadgröße |

Fernet-Schlüssel erzeugen:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Beispiel

```env
APP_ENV=production
APP_SECRET_KEY=<zufälliges Secret>
APP_BASE_URL=https://dashboard.meineschule.at
ALLOWED_ORIGINS=https://dashboard.meineschule.at

POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=botball
POSTGRES_USER=botball
POSTGRES_PASSWORD=<sicheres Passwort>

JWT_SECRET_KEY=<anderes zufälliges Secret>
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

VAPID_PRIVATE_KEY=/app/vapid/private_key.pem
VAPID_PUBLIC_KEY=<Application Server Key>
VAPID_ADMIN_EMAIL=admin@meineschule.at

PRINTER_CREDENTIAL_ENCRYPTION_KEY=<Fernet-Schlüssel>
UPLOAD_DIR=/app/uploads
MAX_UPLOAD_SIZE_MB=20

DOMAIN=dashboard.meineschule.at
TRAEFIK_EMAIL=admin@meineschule.at
```
