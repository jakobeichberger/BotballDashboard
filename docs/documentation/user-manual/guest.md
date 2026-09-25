# Gast-Handbuch und öffentliche Anzeige

Es gibt zwei Arten, das Dashboard nur zu lesen:

| | Öffentliche Event-Seite | Gast-Konto (Rolle `guest`) |
|---|---|---|
| Login | nein | ja |
| Adresse | `/public/<event-slug>` | `/events/<id>/…` |
| Inhalt | nur, was die Organisation freigegeben hat | Dashboard, Teams, Bot-Galerie, Zeitplan, Wertung, Rangliste & Ergebnisse, Deadlines (alles nur lesend) |
| Gedacht für | Zuschauer, Beamer, Großbildschirm | Eltern, Schulen, Partner mit Konto |

---

## Öffentliche Event-Seite

Adresse: `https://<domain>/public/<event-slug>`. Den Slug vergibt die Organisation in der Event-Verwaltung.

Die Seite ist nur erreichbar, wenn das Event den Status `published`, `live` oder `completed` hat. Welche Bereiche erscheinen, entscheiden die Freigaben des Events:

| Bereich | Freigabe |
|---|---|
| Rangliste | Scoreboard |
| Nächste Matches (Zeitplan) und Bracket | Zeitplan |
| Detailergebnisse (Runden, Tische, Punkte; ohne Übungsläufe) | Ergebnisse |
| Ankündigungen (nur Zielgruppe „alle") | Ankündigungen |

Ist nichts freigegeben, zeigt die Seite „Dieses Event ist nicht öffentlich verfügbar". Nie öffentlich sind:

- Kontaktdaten und E-Mail-Adressen;
- Papers und Reviews;
- Druckaufträge;
- interne Notizen;
- Übungsläufe;
- Scouting.

### Live und Großbildschirm

- Die Seite hält eine Live-Verbindung. Neue Wertungen, Zeitplanänderungen und Ankündigungen erscheinen ohne Neuladen. Der Verbindungsstatus steht oben: „Verbunden" oder „Getrennt".
- **Rotation:** Die Seite wechselt automatisch zwischen den freigegebenen Bereichen. Mit Pause/Play schaltest du die Rotation um, mit den Bereichs-Buttons springst du direkt.
- **Vollbild**-Button für Beamer und Fernseher.
- **QR-Code:** Die Seite zeigt einen QR-Code auf sich selbst. So können Zuschauer die Rangliste am Handy öffnen. Als Bild ist er auch unter `/api/v1/public/events/<slug>/qr.svg` abrufbar, z. B. für Plakate.

---

## Gast-Konto

Mit der Rolle `guest` (`scoring:read`, `teams:read`, `seasons:read`, `events:read`, `dashboard:read`):

- **Dashboard:** Überblick und Ankündigungen.
- **Teams** und **Bot-Galerie** (nur veröffentlichte Bots), ohne Kontaktdaten und Mitglieder-E-Mails.
- **Zeitplan** mit Bracket.
- **Wertung**, schreibgeschützt: „Du kannst Wertungen ansehen, hast aber keine Berechtigung zum Speichern."
- **Rangliste & Ergebnisse** mit Exporten.
- **Deadlines** mit iCal-Abo.

Weil Gäste `scoring:read` haben, stehen auch **OCR-Prüfung** und **Scouting** in der Navigation. Beide sind nur lesbar. Scouting-Notizen und -Beobachtungen sind für Gäste leer, weil sie an eigene Teams gebunden sind. Paper, 3D-Druck, Performance und Statistik bleiben verborgen.

---

## Als App installieren

Die öffentliche Seite und das Dashboard lassen sich als App auf den Startbildschirm legen: im Browser „Zum Startbildschirm hinzufügen" bzw. „Installieren".
