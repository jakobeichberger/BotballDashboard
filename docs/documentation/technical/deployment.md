# Deployment & Betrieb

---

## Docker Compose Struktur

```yaml
# docker-compose.yml (vereinfacht)
services:

  db:
    image: postgres:16-alpine
    volumes:
      - db_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    restart: unless-stopped

  backend:
    build: ./backend
    environment:
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db/${POSTGRES_DB}
    depends_on:
      - db
      - redis
    command: ["./scripts/migrate-then-start.sh"]
    labels:
      - "traefik.http.routers.backend.rule=Host(`${DOMAIN}`) && PathPrefix(`/api`)"
    restart: unless-stopped

  frontend:
    build: ./frontend
    labels:
      - "traefik.http.routers.frontend.rule=Host(`${DOMAIN}`)"
    restart: unless-stopped

  ocr:
    build: ./ocr-service
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    restart: unless-stopped

  traefik:
    image: traefik:v3
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - traefik_certs:/certs
    restart: unless-stopped

volumes:
  db_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/db
  traefik_certs:
```

---

## migrate-then-start.sh

```bash
#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Produktions-Deployment Schritt für Schritt

### Erstinstallation

```bash
# 1. Repo klonen
git clone https://github.com/jakobeichberger/botballdashboard.git /opt/botballdashboard
cd /opt/botballdashboard

# 2. Datenspeicher anlegen
sudo mkdir -p /data/{db,uploads,backups}
sudo chown -R 1000:1000 /data

# 3. Konfiguration
cp .env.example .env
nano .env   # Pflichtfelder ausfüllen

# 4. Starten
docker compose up -d

# 5. Admin anlegen
docker compose exec backend python manage.py create-admin \
  --email admin@meineschule.at --password sicheres_passwort

# 6. Status prüfen
docker compose ps
docker compose logs backend --tail=50
```

### Update

```bash
cd /opt/botballdashboard
git pull origin main
docker compose pull
docker compose up -d
```

---

## Monitoring

### Health-Check

```bash
curl https://dashboard.meineschule.at/api/system/health
# Response: {"status": "ok", "db": "ok", "redis": "ok", "version": "1.2.3"}
```

### Container-Status

```bash
docker compose ps
docker stats --no-stream
```

### Logs einsehen

```bash
# Alle Services
docker compose logs --tail=100 -f

# Nur Backend
docker compose logs backend --tail=100 -f

# Nur Fehler filtern
docker compose logs backend 2>&1 | grep -E "ERROR|CRITICAL"
```

### Optionales Monitoring mit Uptime Kuma

Uptime Kuma als separater Container auf Proxmox:

```yaml
services:
  uptime-kuma:
    image: louislam/uptime-kuma:1
    ports:
      - "3001:3001"
    volumes:
      - uptime_data:/app/data
```

Monitore einrichten:
- HTTP(s) auf `https://dashboard.meineschule.at/api/system/health`
- Alert per E-Mail oder Pushover bei Ausfall

---

## Backup & Restore

### Automatisches Datenbank-Backup (Cron)

```bash
# /etc/cron.d/botball-backup
0 2 * * * root docker exec botballdashboard-db-1 \
  pg_dump -U botball botball | gzip \
  > /data/backups/db_$(date +\%Y\%m\%d).sql.gz

# Backups älter als 30 Tage löschen
0 3 * * * root find /data/backups -name "db_*.sql.gz" -mtime +30 -delete
```

### Manuelles Backup

```bash
docker compose exec db pg_dump -U botball botball \
  | gzip > /data/backups/manual_$(date +%Y%m%d_%H%M).sql.gz
```

### Restore

```bash
# Datenbank stoppen
docker compose stop backend ocr

# Daten einspielen
gunzip < /data/backups/db_20260315.sql.gz \
  | docker compose exec -T db psql -U botball botball

# Wieder starten
docker compose start backend ocr
```

---

## SSL-Zertifikate

Traefik erneuert Let's Encrypt Zertifikate automatisch (spätestens 30 Tage vor Ablauf).

**Zertifikat-Status prüfen:**
```bash
docker compose exec traefik traefik version
cat /data/traefik/certs/acme.json | python3 -m json.tool | grep "main"
```

**Manuell erneuern erzwingen:**
```bash
docker compose restart traefik
```

---

## Sicherheits-Hinweise für Produktion

```bash
# .env niemals ins Git committen (bereits in .gitignore)
# Sichere Passwörter verwenden (min. 32 Zeichen für Secrets)
python3 -c "import secrets; print(secrets.token_hex(32))"

# Firewall: nur Ports 80, 443 extern öffnen
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 22/tcp   # SSH nur aus Verwaltungsnetz
ufw enable

# Regelmäßige Updates
apt update && apt upgrade -y
docker compose pull && docker compose up -d
```
