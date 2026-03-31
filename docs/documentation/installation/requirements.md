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

- Öffentlich erreichbare IP oder Domain (für externes Scoreboard)
- Offene Ports: `80` (HTTP), `443` (HTTPS), optional `22` (SSH)
- Interner Zugriff auf Drucker-APIs (gleiche Netzwerk-Segment oder VPN)

---

## Software-Abhängigkeiten (werden automatisch via Docker installiert)

| Komponente | Version | Zweck |
|---|---|---|
| Docker | 24.x+ | Container-Runtime |
| Docker Compose | 2.x+ | Multi-Container-Orchestrierung |
| PostgreSQL | 16 | Datenbank (läuft im Container) |
| Python | 3.11+ | Backend (läuft im Container) |
| Node.js | 20 LTS | Frontend-Build (läuft im Container) |

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
| Node.js | 20 LTS |
| pnpm | 8.x+ |
| Python | 3.11+ |
| Docker + Docker Compose | aktuell |
| Git | 2.x+ |

### Optionale Tools

- `poppler-utils` – für OCR-Vorverarbeitung von PDF-Score-Sheets
- `make` – für vereinfachte Build-Befehle (Makefile vorhanden)

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
