# Admin-Handbuch

Das Admin-Konto hat Vollzugriff auf alle Module und Einstellungen. Dieses Handbuch beschreibt alle Admin-Funktionen.

---

## Inhaltsverzeichnis

- [Benutzerverwaltung](#benutzerverwaltung)
- [Rechteverwaltung](#rechteverwaltung)
- [Saisonverwaltung](#saisonverwaltung)
- [Scoring](#scoring)
- [Paper-Review](#paper-review)
- [3D-Druck](#3d-druck)
- [Exporte](#exporte)
- [Systemeinstellungen](#systemeinstellungen)
- [Logging & Fehler-Überwachung](#logging)

---

## Benutzerverwaltung {#benutzerverwaltung}

### Benutzer einladen
1. **Admin → Benutzer → Benutzer einladen**
2. E-Mail-Adresse eingeben
3. Rolle(n) zuweisen (Admin, Juror, Reviewer, Mentor, Gast)
4. Einladungs-E-Mail wird automatisch versandt
5. Benutzer setzt beim ersten Login sein Passwort

### Rollen zuweisen / ändern
- **Admin → Benutzer → Benutzer auswählen → Rollen bearbeiten**
- Mehrere Rollen gleichzeitig möglich
- Änderungen gelten sofort (ohne Neustart)

### Benutzer deaktivieren
- Deaktivierte Benutzer können sich nicht mehr einloggen
- Daten bleiben erhalten (DSGVO: kein Löschen ohne Anfrage)
- **Admin → Benutzer → Benutzer auswählen → Deaktivieren**

---

## Rechteverwaltung {#rechteverwaltung}

### Granulare Berechtigungen

Rechte können pro Benutzer oder pro Gruppe/Rolle vergeben werden. Jedes Recht hat das Format `modul:aktion`:

**Scoring-Modul:**
| Recht | Beschreibung |
|---|---|
| `scoring:read` | Scores und Ranglisten einsehen |
| `scoring:write` | Scores eingeben und bearbeiten |
| `scoring:admin` | Schema bearbeiten, Phases verwalten, Teams qualifizieren |
| `scoring:delete` | Scores löschen (Audit-Log bleibt erhalten) |

**Paper-Review-Modul:**
| Recht | Beschreibung |
|---|---|
| `papers:read` | Papers einsehen (eigenes Team oder alle) |
| `papers:submit` | Paper einreichen (Team-Seite) |
| `papers:review` | Reviews schreiben, Revisionen anfordern |
| `papers:assign` | Reviewer einem Paper zuweisen |
| `papers:admin` | Status manuell setzen, Deadlines verwalten, Exporte |

**3D-Druck-Modul:**
| Recht | Beschreibung |
|---|---|
| `printing:request` | Druckjob beantragen |
| `printing:manage` | Jobs genehmigen, ablehnen, Drucker zuweisen |
| `printing:admin` | Drucker hinzufügen/entfernen, Limits setzen, Credentials verwalten, Exporte |

**Teamverwaltung:**
| Recht | Beschreibung |
|---|---|
| `teams:read` | Teamdaten einsehen, Team-Listen exportieren |
| `teams:write` | Teamdaten bearbeiten |
| `teams:admin` | Teams anlegen, löschen, Saison-Anmeldung |

**Saisonverwaltung:**
| Recht | Beschreibung |
|---|---|
| `seasons:read` | Saison-Informationen einsehen |
| `seasons:write` | Saisons anlegen, bearbeiten |
| `seasons:admin` | Saisons archivieren, aktive Saison setzen |

**Dashboard & Systemverwaltung:**
| Recht | Beschreibung |
|---|---|
| `dashboard:read` | Dashboard und Statistiken einsehen, Ranglisten exportieren |
| `dashboard:write` | Announcements erstellen und verwalten |
| `users:read` | Benutzerliste einsehen |
| `users:write` | Benutzer einladen, Rollen vergeben |
| `users:admin` | Benutzer deaktivieren, Passwort-Reset erzwingen |

### Vordefinierte Rollen (Gruppen)

| Rolle | Enthaltene Rechte |
|---|---|
| **Admin** | Alle Rechte |
| **Juror** | `scoring:read`, `scoring:write`, `teams:read` |
| **Reviewer** | `papers:read`, `papers:review`, `teams:read` |
| **Mentor** | `teams:read`, `papers:read`, `papers:submit`, `printing:request`, `scoring:read` |
| **Gast** | `scoring:read`, `dashboard:read`, `teams:read` |

### Benutzerdefinierte Rollen anlegen
1. **Admin → Rechteverwaltung → Neue Rolle**
2. Name und Beschreibung eingeben
3. Einzelne Rechte per Checkbox auswählen
4. Rolle Benutzern zuweisen

> Tipp: Benutzer können Mitglied mehrerer Rollen sein. Die Rechte werden addiert (keine Konflikte).

---

## Saisonverwaltung {#saisonverwaltung}

### Neue Saison anlegen
1. **Admin → Saisons → Neue Saison**
2. Name (z.B. „ECER 2026"), Jahr, Beschreibung
3. Wettbewerbs-Stufen anlegen (z.B. ECER, GCER, Junior)
4. Phasen pro Stufe definieren (Preparations, Tournament)
5. Aktive Module auswählen (Scoring, Paper-Review, 3D-Druck)
6. Saison auf „Aktiv" setzen

### Saison aus Vorjahr kopieren
- **Admin → Saisons → Saison auswählen → Kopieren**
- Übernimmt: Strukturkonfiguration, Scoring-Schema-Vorlage, Modul-Aktivierungen
- Übernimmt **nicht:** Teams, Scores, Papers, Druckjobs

### Scoring-Schema einer Saison bearbeiten
- **Admin → Saisons → Saison → Scoring → Schema bearbeiten**
- Felder hinzufügen: Name, Multiplikator, Maximalwert, Typ (Anzahl / Ja-Nein)
- Schema-Formel: `Gesamt = Σ (Feldwert × Multiplikator)`
- GCER-Schema: „Von ECER klonen" → unabhängige Kopie die separat bearbeitet werden kann

### Deadlines verwalten
- **Admin → Saisons → Saison → Deadlines**
- Automatische Erinnerungen: 7 Tage, 3 Tage, 1 Tag vor jeder Deadline

---

## Scoring {#scoring}

### Match anlegen (Turnierphase)
- **Scoring → Turnierphase → Match anlegen**
- Team auswählen, Runde und Tisch eingeben

### Score korrigieren
- **Scoring → Match → Score → Bearbeiten**
- Korrekturgrund eingeben (Pflichtfeld für Audit-Trail)
- Originalwert bleibt im Audit-Log erhalten

### Teams für GCER qualifizieren
- **Scoring → ECER → Qualifikation → Teams verwalten**
- Teams auswählen und als qualifiziert markieren
- Qualifizierte Teams werden automatisch für GCER freigeschaltet

### Yellow/Red Card vergeben
- **Scoring → Turnier → Team → Karte vergeben**
- Gelbe Karte: Verwarnung
- Rote Karte: sofortige DQ aus dem gesamten Turnier

### Score-Sheets verwalten
- **Scoring → Score-Sheets verwalten**
- Score-Sheet-Vorlagen anlegen, bearbeiten, löschen
- Vorlagen sind mit dem Scoring-Schema der Saison verknüpft

---

## Paper-Review {#paper-review}

### Reviewer zuweisen
- **Paper-Review → Papers → Paper auswählen → Reviewer zuweisen**
- Einen oder mehrere Reviewer aus dem Reviewer-Pool auswählen
- Automatische Benachrichtigung an die zugewiesenen Reviewer

### Paper-Status manuell setzen
- **Paper-Review → Papers → Paper auswählen → Status ändern**
- Nur in Ausnahmefällen (normalerweise läuft Status über Reviewer-Aktionen)

### Deadline verlängern
- **Paper-Review → Deadlines → Deadline auswählen → Verlängern**
- Neue Datum eingeben, Begründung optional
- Betroffene Teams werden per E-Mail informiert

---

## 3D-Druck {#3d-druck}

### Drucker hinzufügen
1. **3D-Druck → Drucker → Drucker hinzufügen**
2. Name, Hersteller, Modell, Standort
3. Verbindungsparameter eingeben (API-Key, IP-Adresse)
   > API-Keys werden verschlüsselt (Fernet/AES-128) gespeichert und sind nach dem Speichern nicht mehr einsehbar
4. Verbindung testen → Statusanzeige

### Team-Limits setzen
- **3D-Druck → Limits → Team auswählen → Limits bearbeiten**
- Soft Limit (Warnung): Druckzeit in Stunden, Filament in Gramm, Anzahl Jobs
- Hard Limit (Blockieren): gleiche Dimensionen
- Limits gelten pro Saison

### Druckjob genehmigen / ablehnen
- **3D-Druck → Queue → Job auswählen**
- Genehmigen + Drucker zuweisen → Job wird automatisch an Drucker gesendet
- Ablehnen + Begründung eingeben → Team wird per E-Mail informiert

---

## Exporte {#exporte}

Als Admin stehen alle Exporte zur Verfügung:

| Export | Format | Pfad |
|---|---|---|
| Rangliste | PDF, CSV | Scoring → Rangliste → Export-Buttons |
| Alle Wertungen (Matches) | CSV | Scoring → Matches → Export |
| Paper-Review-Übersicht | PDF, CSV | Paper-Review → Übersicht → Export |
| 3D-Druck-Report | PDF | 3D-Druck → Bericht → Export |
| Team-Liste | PDF, CSV | Teams → Export-Buttons |

**PDF-Exporte** sind A4-formatiert mit Logo-Header und druckfertigen Tabellen.
**CSV-Exporte** sind UTF-8 (BOM) kodiert und öffnen sich direkt in Excel.

---

## Systemeinstellungen {#systemeinstellungen}

### E-Mail-Konfiguration testen
- **Admin → System → E-Mail → Test-E-Mail senden**

### Backup manuell auslösen
- **Admin → System → Backup → Jetzt sichern**
- Download als SQL-Dump (gezippt)

---

## Logging & Fehler-Überwachung {#logging}

### Application Log

**Admin → System → Logs**

- **Filter:** Level (DEBUG / INFO / WARNING / ERROR / CRITICAL), Modul, Zeitraum, Benutzer
- **Suche:** Freitext-Suche in Log-Nachrichten
- **Export:** Als CSV für Zeitraum herunterladen

Typische Log-Einträge:
| Level | Beispiel |
|---|---|
| INFO | Benutzer eingeloggt, Score eingegeben, Druckjob gestartet |
| WARNING | Soft-Limit erreicht, Drucker nicht erreichbar (Retry) |
| ERROR | Drucker-API-Fehler, E-Mail-Versand fehlgeschlagen |
| CRITICAL | Datenbankverbindung verloren |

### Audit-Log

**Admin → System → Audit-Log**

Unveränderliches Protokoll aller sicherheitsrelevanten Aktionen:

| Aktion | Wann protokolliert |
|---|---|
| `score.submitted` / `score.updated` | Score eingegeben oder korrigiert (mit altem + neuem Wert) |
| `paper.status_changed` | Paper-Status geändert |
| `user.created` / `user.deactivated` | Benutzer angelegt oder deaktiviert |
| `user.role_changed` | Rolle eines Benutzers geändert |
| `card.issued` | Yellow/Red Card vergeben |
| `team.qualified` | Team für GCER qualifiziert |
| `printer.credentials_updated` | Drucker-Zugangsdaten geändert |
| `season.archived` | Saison archiviert |

- **Filter:** Benutzer, Aktion, Zeitraum, Entity-Typ
- **Export:** Als CSV (für Jahres-Berichte, DSGVO-Anfragen)
- Einträge können **nicht gelöscht oder bearbeitet** werden
