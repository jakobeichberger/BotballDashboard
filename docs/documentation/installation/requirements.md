# Systemanforderungen

---

## Server (Produktivbetrieb)

### Empfohlene Hardware (Proxmox-VM)

| Komponente | Minimum | Empfohlen |
|---|---|---|
| CPU | 2 vCores | 4 vCores |
| RAM | 4 GB | 8 GB |
| Speicher (System + Docker) | 20 GB SSD | 40 GB SSD |
| Speicher (Datenbank + Uploads) | 20 GB | 50 GB+ (abhängig von Upload-Volumen) |

> **Hinweis:** Die Datenbank und Upload-Dateien sollten auf einem separaten persistenten Volume liegen. Bei Proxmox empfiehlt sich ein eigener Datensatz (ZFS/LVM) für den `/data`-Mount.

### Betriebssystem

- Ubuntu 22.04 LTS oder 24.04 LTS (empfohlen)
- Debian 12
- Jedes Linux-System mit Docker-Unterstützung

### Netzwerk

- Domain mit DNS-Eintrag auf den Server; Let's Encrypt (TLS-Challenge) braucht Port `443` aus dem Internet
- Offene Ports: `80` (HTTP → Umleitung), `443` (HTTPS), optional `22` (SSH, nur Verwaltungsnetz)
- Prometheus (`9090`) und Alertmanager (`9093`) lauschen nur auf `127.0.0.1` (Zugriff per SSH-Tunnel)
- Interner Zugriff auf Drucker-APIs (gleiche Netzwerk-Segment oder VPN)

---

## Software-Abhängigkeiten

| Komponente | Version | Zweck |
|---|---|---|
| Docker | 24.x+ | Container-Runtime (Host) |
| Docker Compose Plugin | 2.20+ | `docker compose`, Profile und `env_file`-Optionen (Host) |
| PostgreSQL | 16 | Datenbank (Container) |
| Redis | 7 | Celery-Broker, Rate-Limits (Container) |
| Python | 3.11 | Backend, Worker, Beat, Backup (Container) |
| Node.js + pnpm | 24 LTS + pnpm 10.x | Frontend-Build: im Container, auf Proxmox-LXC auf dem Host (das Setup-Skript installiert Node 24 und pnpm 10.29.3) |
| age | 1.x | Backup-Schlüsselpaar erzeugen (Host, `apt install age`) |
| Python 3 | 3.9+ | Hilfsskripte des Setups (Host) |

### Auf dem Host-System manuell installieren

```bash
# Docker installieren (Ubuntu)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Docker Compose Plugin prüfen
docker compose version
```

---

## Lokale Entwicklungsumgebung

| Komponente | Version |
|---|---|
| Node.js | 24 LTS |
| pnpm | 10.x (`packageManager` in `frontend/package.json`: 10.29.3, per `corepack enable`) |
| Python | 3.11+ |
| Docker + Docker Compose | aktuell |
| Git | 2.x+ |

### Optionale Tools

- `poppler-utils` – für OCR-Vorverarbeitung von PDF-Score-Sheets
- `make` – für vereinfachte Build-Befehle (Makefile vorhanden)
- `pre-commit` – führt ruff, eslint und shellcheck vor jedem Commit aus (siehe README)

---

## Browser-Unterstützung (Frontend)

| Browser | Mindestversion |
|---|---|
| Chrome / Chromium | 110+ |
| Firefox | 110+ |
| Safari | 16.4+ (für PWA Push-Notifications) |
| Edge | 110+ |
| Safari Mobile (iOS) | 16.4+ |
| Chrome Mobile (Android) | 110+ |

> PWA-Installation und Push-Benachrichtigungen erfordern HTTPS und einen modernen Browser.

---

## 3D-Drucker-Anforderungen

| Drucker-Typ | Voraussetzung |
|---|---|
| Bambu Lab (X1C, P1S, A1, …) | Bambu Cloud Zugang oder lokales LAN-Modus |
| Ender / generisch | OctoPrint installiert und erreichbar |
| Prusa | Prusa Connect Zugang |

Alle Drucker müssen vom Server-Netzwerk aus erreichbar sein (gleicher LAN-Segment oder VPN).
