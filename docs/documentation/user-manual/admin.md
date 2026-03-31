# Admin-Handbuch

Das Admin-Konto hat Vollzugriff auf alle Module und Einstellungen. Dieses Handbuch beschreibt alle Admin-Funktionen.

---

## Benutzerverwaltung

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

## Rechteverwaltung

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
| `paper:read` | Papers einsehen (eigenes Team oder alle) |
| `paper:submit` | Paper einreichen (Team-Seite) |
| `paper:review` | Reviews schreiben, Revisionen anfordern |
| `paper:assign` | Reviewer einem Paper zuweisen |
| `paper:admin` | Status manuell setzen, Deadlines verwalten |

**3D-Druck-Modul:**
| Recht | Beschreibung |
|---|---|
| `print:request` | Druckjob beantragen |
| `print:manage` | Jobs genehmigen, ablehnen, Drucker zuweisen |
| `print:admin` | Drucker hinzufügen/entfernen, Limits setzen, Credentials verwalten |

**Teamverwaltung:**
| Recht | Beschreibung |
|---|---|
| `team:read` | Teamdaten einsehen |
| `team:edit` | Teamdaten bearbeiten (eigenes Team: Mentor; alle: Admin) |
| `team:admin` | Teams anlegen, löschen, Saison-Anmeldung |

**Saisonverwaltung:**
| Recht | Beschreibung |
|---|---|
| `season:read` | Saison-Informationen einsehen |
| `season:admin` | Saisons anlegen, bearbeiten, archivieren |

**Systemverwaltung:**
| Recht | Beschreibung |
|---|---|
| `admin:users` | Benutzerverwaltung |
| `admin:roles` | Rollen und Rechte verwalten |
| `admin:system` | Systemeinstellungen, Logs |

### Vordefinierte Rollen (Gruppen)

Das System liefert sinnvolle Standardrollen mit vordefinierten Rechten:

| Rolle | Enthaltene Rechte |
|---|---|
| **Admin** | Alle Rechte |
| **Juror** | `scoring:read`, `scoring:write`, `team:read` |
| **Head Juror** | `scoring:read`, `scoring:write`, `scoring:delete`, `scoring:admin`, `team:read` |
| **Reviewer** | `paper:read`, `paper:review`, `team:read` |
| **Lead Reviewer** | `paper:read`, `paper:review`, `paper:assign`, `paper:admin`, `team:read` |
| **Mentor** | `team:read`, `team:edit` (nur eigene Teams), `paper:read` (eigene), `print:request`, `scoring:read` |
| **Print Manager** | `print:request`, `print:manage`, `print:admin` |
| **Gast** | `scoring:read` (nur öffentliche Daten), `team:read` (nur öffentliche) |

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
3. Wettbewerbs-Stufen anlegen (z.B. ECER, GCER)
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
- GCER-Schema: „Von ECER klonen" → unabhängige Kopie die separat bearbeitet werden kann

### Deadlines verwalten
- **Admin → Saisons → Saison → Deadlines**
- Deadline-Typen: `internal_draft`, `internal_review`, `internal_revision`, `internal_final`, `official_submission`, `official_final`
- Automatische Erinnerungen: 7 Tage, 3 Tage, 1 Tag vor jeder Deadline

---

## Scoring {#scoring}

### Testlauf dokumentieren (Vorbereitungsphase)
- **Scoring → Vorbereitungsphase → Neuer Testlauf**
- Team auswählen, Score eingeben, Notizen hinzufügen

### Match anlegen (Turnierphase)
- **Scoring → Turnierphase → Match anlegen**
- Typ: Seeding / Double Elimination / Alliance
- Teams auswählen (eigene und/oder externe Gegner)

### Score korrigieren
- **Scoring → Match → Score → Bearbeiten**
- Korrekturgrund eingeben (Pflichtfeld für Audit-Trail)
- Originalwert bleibt im Audit-Log erhalten

### Teams für GCER qualifizieren
- **Scoring → ECER → Qualifikation → Teams verwalten**
- 1–2 Teams auswählen und als qualifiziert markieren
- Qualifizierte Teams werden automatisch für GCER-Phasen freigeschaltet

### Yellow/Red Card vergeben
- **Scoring → Turnier → Team → Karte vergeben**
- Gelbe Karte: Verwarnung
- Rote Karte: sofortige DQ aus dem gesamten Turnier

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
3. Adapter-Typ auswählen: `Bambu`, `OctoPrint`, `Prusa`
4. Verbindungsparameter eingeben (API-Key, IP-Adresse)
   > API-Keys werden verschlüsselt gespeichert und sind nach dem Speichern nicht mehr einsehbar
5. Verbindung testen → Statusanzeige

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

## Systemeinstellungen

### E-Mail-Konfiguration testen
- **Admin → System → E-Mail → Test-E-Mail senden**

### Backup manuell auslösen
- **Admin → System → Backup → Jetzt sichern**
- Download als SQL-Dump (gezippt)

---

## Logging & Fehler-Überwachung

### Application Log

**Admin → System → Logs**

Zeigt alle Anwendungs-Ereignisse in Echtzeit:

- **Filter:** Level (DEBUG / INFO / WARNING / ERROR / CRITICAL), Modul, Zeitraum, Benutzer
- **Suche:** Freitext-Suche in Log-Nachrichten
- **Auto-Refresh:** Neue Einträge erscheinen automatisch (WebSocket)
- **Export:** Als CSV für Zeitraum herunterladen

Typische Log-Einträge:
| Level | Beispiel |
|---|---|
| INFO | Benutzer eingeloggt, Score eingegeben, Druckjob gestartet |
| WARNING | Soft-Limit erreicht, OCR-Erkennung unsicher, Drucker nicht erreichbar (Retry) |
| ERROR | Drucker-API-Fehler, DB-Query fehlgeschlagen, E-Mail-Versand fehlgeschlagen |
| CRITICAL | Datenbankverbindung verloren, Out-of-Memory |

### Error-Log

**Admin → System → Fehler**

Dedizierte Ansicht nur für `ERROR`- und `CRITICAL`-Einträge:

- Jeder Fehler enthält: Zeitstempel, Modul, Fehlermeldung, Stack Trace, betroffener Benutzer (wenn vorhanden)
- **Status:** Offen / Gelöst
- **Als gelöst markieren:** Fehler auswählen → „Gelöst" + optionale Notiz
- **Automatische E-Mail** an Admin bei CRITICAL-Fehlern

Workflow bei einem Fehler:
1. Admin erhält E-Mail (CRITICAL) oder sieht Eintrag im Dashboard
2. **Admin → System → Fehler → Fehler öffnen** → Stack Trace lesen
3. Problem beheben
4. **„Als gelöst markieren"** mit Erklärung

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
