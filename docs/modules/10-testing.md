# Modul 10 – Testing

**Status:** [ ] Offen  
**Typ:** Querschnittsmodul  
**Kommuniziert mit:** Allen Modulen

---

## Beschreibung

Testinfrastruktur und Teststrategie für den gesamten Kern und alle Plugins. Umfasst Unit-, Integrations- und End-to-End-Tests sowie automatische Coverage-Reports in der CI/CD-Pipeline.

---

## Teststrategie

### Test-Pyramide

```
         /\
        /E2E\          ← Wenige, kritische User-Flows
       /------\
      /Integrat.\      ← API-Endpunkte, Modul-Zusammenspiel
     /------------\
    /  Unit Tests  \   ← Viele, schnelle, isolierte Tests
   /________________\
```

### Frameworks

| Bereich | Framework |
|---|---|
| Frontend Unit & Integration | Vitest + React Testing Library |
| Frontend E2E | Playwright |
| Backend Unit | pytest |
| Backend Integration | pytest + httpx (FastAPI TestClient) |
| Coverage | pytest-cov (Backend), Vitest Coverage (Frontend) |

---

## Unit-Tests

### Scoring-Engine
- Seeding-Score-Berechnung (Summe beider Seiten)
- Seeding-Durchschnitt (beste 2 von N)
- Double-Elimination-Logik (Sieg/Niederlage)
- Gesamtscore-Formel
- Plausibilitätsprüfung (Maximalwert-Überschreitung, negative Werte)
- Konfigurierbare Schemas (verschiedene Saisons)

### Paper-Review-Workflow
- Status-Übergänge (submitted → under_review → revision_requested → ...)
- Berechtigungsprüfungen (Reviewer darf nur zugewiesene Papers sehen)
- Konfliktprüfung (Reviewer darf nicht eigene Schule bewerten)

### 3D-Druck-Adapter
- Mock-Drucker für Bambu, Prusa, OctoPrint
- Job-Queue-Logik (Prioritäten, FIFO)
- Status-Übergänge (requested → approved → printing → done)

### Auth
- Token-Generierung und -Validierung
- Rollen-Berechtigungen
- Token-Revokation

---

## Integrationstests

### API-Endpunkte (alle Module)
- Happy Path: korrekte Anfragen geben erwartete Responses
- Error Cases: fehlende Felder, ungültige IDs, falsche Rollen → 4xx Responses
- Authentifizierung: unauthentifizierte Requests → 401, falsche Rolle → 403

### Modul-Zusammenspiel
- Score einreichen → Rangliste aktualisiert sich
- Paper eingereicht → Reviewer-Benachrichtigung ausgelöst
- Druckjob genehmigt → Adapter aufgerufen

---

## End-to-End-Tests

### Kritische User-Flows (Playwright)
- Kompletter Scoring-Workflow: Login als Juror → Match auswählen → Score eingeben → Rangliste prüfen
- Paper-Review-Zyklus: Team reicht Paper ein → Reviewer bewertet → Revision → Team lädt neue Version hoch
- Druckjob-Flow: Team beantragt Job → Admin genehmigt → Drucker-Mock bestätigt fertig → Benachrichtigung
- Admin: Neue Saison anlegen → Teams anmelden → Module aktivieren

---

## Coverage-Ziele

| Bereich | Ziel |
|---|---|
| Scoring-Engine (Berechnungen) | 100% |
| Paper-Review-Workflow | ≥ 90% |
| Auth & Berechtigungen | ≥ 90% |
| API-Endpunkte (Integration) | ≥ 80% |
| Frontend-Komponenten | ≥ 70% |

---

## CI/CD-Integration
- Die CI wird **manuell gestartet** (Actions → CI → „Run workflow“); Pushes und Pull Requests starten sie bewusst nicht. Vor einem Merge wird sie auf dem Branch ausgelöst.
- Ein Lauf führt Unit-, Integrations- und PostgreSQL/Redis-Tests, die Frontend-Tests und die komplette Playwright-Suite (Desktop und `@mobile`) aus.
- Coverage-Reports werden als Artefakt gespeichert.
- Der Lauf schlägt fehl, wenn die Coverage unter die Schwelle fällt (Backend `fail_under` in `backend/pyproject.toml`, Frontend `thresholds` in `frontend/vitest.config.ts`).

## Backend-Testumgebung
- In-Memory-SQLite; das Schema wird einmal pro Testprozess angelegt. Jeder Test läuft in einer äußeren Transaktion, die danach zurückgerollt wird; die Session arbeitet mit SAVEPOINTs, daher bleiben auch `commit()`/`rollback()` im getesteten Code isoliert.
- `tests/conftest.py` setzt `BCRYPT_ROUNDS=4` und `LOG_LEVEL=WARNING`.
- `pytest -n auto` verteilt die Suite auf alle Kerne (pytest-xdist); die CI nutzt das.
