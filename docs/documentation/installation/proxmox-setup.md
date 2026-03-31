# Proxmox-Setup

Installation und Betrieb des BotballDashboard auf einer Proxmox-Umgebung.

---

## Empfohlene Proxmox-Architektur

```
Proxmox Host
├── VM: botball-app          (Ubuntu 22.04, Docker Compose)
│   ├── Container: backend   (FastAPI)
│   ├── Container: frontend  (Nginx + React)
│   └── Container: traefik   (Reverse Proxy + SSL)
│
└── LXC: botball-db          (PostgreSQL, persistentes Volume)
    └── /var/lib/postgresql  → Proxmox Storage (ZFS/LVM)
```

> Die Datenbank in einem eigenen LXC zu betreiben ermöglicht unabhängige Snapshots und einfacheres Backup.

---

## Schritt 1: Proxmox-VM anlegen

### VM-Einstellungen
- **OS:** Ubuntu 22.04 LTS (ISO von ubuntu.com)
- **CPU:** 4 vCores
- **RAM:** 8 GB
- **Disk 1 (System):** 40 GB (SSD-Storage)
- **Disk 2 (Daten/Uploads):** 50 GB (kann später erweitert werden)
- **Netzwerk:** VirtIO, Bridge zu LAN

```bash
# Nach der VM-Installation: Docker installieren
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker compose version   # Prüfen ob Compose verfügbar ist
```

---

## Schritt 2: Datenspeicher einrichten

```bash
# Zweite Disk für Daten mounten
sudo mkfs.ext4 /dev/vdb
sudo mkdir -p /data
echo '/dev/vdb /data ext4 defaults 0 2' | sudo tee -a /etc/fstab
sudo mount -a

# Upload-Verzeichnis und DB-Volume-Pfad
sudo mkdir -p /data/uploads /data/db
sudo chown -R 1000:1000 /data/uploads
```

In `docker-compose.yml` dann:

```yaml
volumes:
  db_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/db
  uploads:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/uploads
```

---

## Schritt 3: Traefik als Reverse Proxy

Traefik übernimmt SSL-Terminierung (Let's Encrypt) und Routing:

```yaml
# traefik/docker-compose.yml
services:
  traefik:
    image: traefik:v3
    command:
      - --providers.docker=true
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
      - --certificatesresolvers.letsencrypt.acme.email=admin@meineschule.at
      - --certificatesresolvers.letsencrypt.acme.storage=/certs/acme.json
      - --certificatesresolvers.letsencrypt.acme.tlschallenge=true
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - traefik_certs:/certs
```

---

## Schritt 4: Proxmox-Snapshots vor Updates

Vor jedem System-Update einen Proxmox-Snapshot anlegen:

```bash
# Manuell über Proxmox-WebUI oder CLI:
pvesh create /nodes/proxmox/qemu/100/snapshot \
  --snapname "before-update-$(date +%Y%m%d)" \
  --description "Pre-update snapshot"
```

> **Automatisierung:** Ein Cron-Job kann wöchentlich Snapshots anlegen und alte automatisch bereinigen.

---

## Schritt 5: Firewall-Regeln

```
Extern erreichbar:   Port 80, 443 (HTTP/HTTPS)
Nur intern:          Port 5432 (PostgreSQL), 8000 (Backend-Dev)
SSH:                 Port 22 (nur aus Verwaltungsnetz)
```

Proxmox Firewall-Regeln über die WebUI oder `/etc/pve/firewall/`.

---

## Backup-Strategie

### Datenbank-Backup (täglich)
```bash
# Cron: täglich 02:00 Uhr
0 2 * * * docker exec botball-db pg_dump -U botball botball_db \
  | gzip > /data/backups/db_$(date +\%Y\%m\%d).sql.gz

# Alte Backups bereinigen (älter als 30 Tage)
find /data/backups -name "db_*.sql.gz" -mtime +30 -delete
```

### Proxmox-Snapshot (wöchentlich)
```bash
# Cron auf Proxmox Host
0 3 * * 0 pvesh create /nodes/proxmox/qemu/100/snapshot \
  --snapname "weekly-$(date +\%Y\%W)"
```

### Upload-Dateien (täglich rsync)
```bash
rsync -av /data/uploads/ backup-server:/botball-uploads/
```

---

## Monitoring

```bash
# Container-Status prüfen
docker compose ps
docker stats

# Logs einsehen
docker compose logs backend --tail=100 -f
docker compose logs traefik --tail=50
```

Optionales Monitoring mit Uptime Kuma (läuft ebenfalls auf Proxmox):
- Überwacht URL-Verfügbarkeit und schickt Alerts bei Ausfall
