# Mentor-Handbuch

Dieses Handbuch richtet sich an Team-Betreuer (Mentoren), die eines oder mehrere Teams betreuen und den Fortschritt im Dashboard verfolgen.

---

## Übersicht Mentor-Funktionen

| Funktion | Wo |
|---|---|
| Team-Scores einsehen | Scoring → Mein Team |
| Testlauf-Entwicklung verfolgen | Scoring → Vorbereitungsphase |
| Paper einreichen | Paper-Review → Paper einreichen |
| Paper-Status verfolgen | Paper-Review → Meine Papers |
| Druckjob beantragen | 3D-Druck → Neuer Druckjob |
| Druckjob-Status verfolgen | 3D-Druck → Meine Jobs |
| Deadlines im Blick behalten | Dashboard → Saison-Übersicht |

---

## Dashboard – Saison-Übersicht

Die Startseite zeigt nach dem Login alle relevanten Informationen auf einen Blick:

- **Aktuelle Phase:** Welche Phase ist gerade aktiv (Vorbereitung / Turnier / GCER)?
- **Nächste Deadlines:** Alle kommenden Deadlines (Paper, Turnier, intern) mit Tagen-Countdown
- **Team-Status:** Letzter Testlauf-Score, Paper-Status, offene Druckjobs
- **Benachrichtigungen:** Ungelesene Nachrichten (Druckjob genehmigt, Paper-Revision angefordert, ...)

---

## Scoring – Vorbereitungsphase

Während der internen Testläufe können Mentoren die Entwicklung ihres Teams verfolgen:

1. **Scoring → Vorbereitungsphase → Mein Team**
2. Alle bisher dokumentierten Testläufe mit Datum und Score
3. **Verlaufsgraph:** Score-Entwicklung über alle Testläufe
4. **Segmentanalyse:** Welche Aufgabenbereiche laufen gut, welche schlecht?
5. Kommentare der Jurors zu jedem Lauf lesbar

> Scores anderer Teams in der Vorbereitungsphase sind nicht sichtbar – nur die eigenen.

---

## Paper-Review

### Paper einreichen

1. **Paper-Review → Paper einreichen**
2. PDF-Datei hochladen (max. 5 Seiten, IEEE-Format)
3. Kategorie auswählen (z.B. Multi Agent Systems, Engineering, ...)
4. Absenden → Paper erhält Status `Eingereicht`

**Voraussetzungen:**
- PDF-Format, IEEE A4-Template
- Max. 5 Seiten inkl. Abbildungen und Referenzen
- Pflichtabschnitte: Abstract, Introduction, Concept/Design, Implementation, Results/Conclusion

### Paper-Status verfolgen

| Status | Bedeutung | Aktion nötig? |
|---|---|---|
| `Eingereicht` | Wartet auf Zuweisung zu Reviewer | Nein |
| `In Review` | Reviewer bewertet gerade | Nein |
| `Revision angefordert` | Feedback vorhanden, Überarbeitung nötig | ✓ Ja |
| `Überarbeitung eingereicht` | Wartet auf erneuten Review | Nein |
| `Akzeptiert` | Paper angenommen | Nein |
| `Abgelehnt` | Paper nicht angenommen | – |

### Revision einreichen

1. Push-Benachrichtigung oder E-Mail: „Revision angefordert"
2. **Paper-Review → Meine Papers → Paper → Feedback lesen**
3. Paper überarbeiten (außerhalb des Systems)
4. **Überarbeitete Version hochladen**
5. Status wechselt zu `Überarbeitung eingereicht`

> Es gibt keine feste Anzahl an Revisions-Runden – der Prozess wiederholt sich bis zur Annahme oder Ablehnung.

---

## 3D-Druck

### Druckjob beantragen

1. **3D-Druck → Neuer Druckjob**
2. STL- oder 3MF-Datei hochladen
3. Material angeben (PLA, PETG, ...)
4. Priorität: Normal / Hoch
5. Kommentar (optional): z.B. „Bitte 0.15mm Layer Height, Infill 20%"
6. Absenden → Job erhält Status `Angefragt`

**Wichtige Hinweise (Wettbewerbs-Regeln):**
- Für Roboterteile: STL-Datei muss auch in der Perioddokumentation (Periode 3) eingereicht werden
- 2026: max. 6 Teile zwischen beiden Robotern, PLA oder PETG, grauskalig
- Maximalgröße pro Teil: 220 × 220 × 250 mm (Ender 3 V3 SE Volumen)

### Druckjob-Status verfolgen

| Status | Bedeutung |
|---|---|
| `Angefragt` | Wartet auf Admin-Freigabe |
| `Genehmigt` | Freigegeben, wartet auf Drucker-Zuweisung |
| `In Queue` | Drucker zugewiesen, wartet auf freien Slot |
| `Wird gedruckt` | Druck läuft – Fortschritt in % sichtbar |
| `Fertig` | Druck abgeschlossen, abholen |
| `Fehlgeschlagen` | Druckfehler – neuen Job beantragen |
| `Abgelehnt` | Abgelehnt durch Admin (Begründung sichtbar) |

**Live-Fortschritt:** Während des Drucks wird Fortschritt in % und geschätzte Restzeit angezeigt.

### Drucklimits

Pro Saison gibt es konfigurierbare Limits:
- **Soft Limit (Warnung):** Hinweis erscheint, Drucken noch möglich
- **Hard Limit (Stopp):** Neue Jobs können nicht mehr beantragt werden

Aktuellen Verbrauch einsehen: **3D-Druck → Mein Verbrauch**

---

## Benachrichtigungen

Als Mentor erhältst du Benachrichtigungen bei:
- Paper-Revision angefordert
- Paper akzeptiert / abgelehnt
- Druckjob genehmigt / fertig / fehlgeschlagen / abgelehnt
- Deadline in 7 Tagen / 3 Tagen / 1 Tag

Benachrichtigungseinstellungen: **Profil → Benachrichtigungen**
