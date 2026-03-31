# Plugin-Entwicklung

Anleitung zum Entwickeln eigener Module (Plugins) für das BotballDashboard.

---

## Grundprinzip

Das BotballDashboard verwendet ein Plugin-System: Der Core (Auth, Saison, Teams, Dashboard) ist fest. Alle weiteren Funktionen (Scoring, Paper-Review, 3D-Druck) sind Plugins die eigenständig entwickelt, aktiviert und deaktiviert werden können.

```
botballdashboard/
  backend/
    core/                  ← Core-Modul (nicht verändern)
    modules/
      scoring/             ← Bestehendes Plugin
      paper-review/        ← Bestehendes Plugin
      3d-print/            ← Bestehendes Plugin
      mein-plugin/         ← Eigenes neues Plugin hier
  frontend/
    src/
      modules/
        scoring/
        paper-review/
        3d-print/
        mein-plugin/       ← Frontend-Teil des Plugins
```

---

## Backend-Plugin anlegen

### 1. Ordner und manifest.json erstellen

```
backend/modules/mein-plugin/
  __init__.py
  manifest.json
  routes.py
  models.py
  schemas.py
  service.py
```

**manifest.json:**
```json
{
  "id": "mein-plugin",
  "name": "Mein Plugin",
  "version": "1.0.0",
  "description": "Beschreibung was das Plugin macht",
  "author": "Name",
  "permissions": [
    "mein-plugin:read",
    "mein-plugin:write",
    "mein-plugin:admin"
  ],
  "db_tables": ["meine_tabelle"],
  "dashboard_widgets": ["mein-widget"],
  "api_prefix": "/mein-plugin",
  "requires": []
}
```

### 2. Datenbankmodell (models.py)

```python
from sqlalchemy import Column, String, UUID, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base
import uuid

class MeinModel(Base):
    __tablename__ = "meine_tabelle"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id"), nullable=False)
    name = Column(String(255), nullable=False)

    season = relationship("Season")
```

### 3. Pydantic-Schemas (schemas.py)

```python
from pydantic import BaseModel
from uuid import UUID

class MeinModelCreate(BaseModel):
    name: str
    season_id: UUID

class MeinModelResponse(BaseModel):
    id: UUID
    name: str
    season_id: UUID

    model_config = {"from_attributes": True}
```

### 4. Routen (routes.py)

```python
from fastapi import APIRouter, Depends
from core.auth import require_permission
from core.database import get_db
from . import schemas, service

router = APIRouter(prefix="/mein-plugin", tags=["mein-plugin"])

@router.get("/items", response_model=list[schemas.MeinModelResponse])
@require_permission("mein-plugin:read")
async def list_items(db=Depends(get_db)):
    return await service.get_all(db)

@router.post("/items", response_model=schemas.MeinModelResponse, status_code=201)
@require_permission("mein-plugin:write")
async def create_item(data: schemas.MeinModelCreate, db=Depends(get_db)):
    return await service.create(db, data)
```

### 5. Alembic-Migration erstellen

```bash
# Nach dem Erstellen des Modells:
alembic revision --autogenerate -m "add mein_plugin tables"
alembic upgrade head
```

---

## Frontend-Plugin anlegen

### Struktur

```
frontend/src/modules/mein-plugin/
  index.tsx            ← Einstiegspunkt + Plugin-Registrierung
  pages/
    MeinPluginPage.tsx
  components/
    MeinWidget.tsx     ← Dashboard-Widget
  api/
    meinPlugin.ts      ← API-Client-Funktionen
  i18n/
    de.json            ← Deutsche Übersetzungen
    en.json            ← Englische Übersetzungen
```

### Plugin registrieren (index.tsx)

```typescript
import { PluginDefinition } from '@/core/plugins'
import MeinPluginPage from './pages/MeinPluginPage'
import MeinWidget from './components/MeinWidget'

const plugin: PluginDefinition = {
  id: 'mein-plugin',
  name: { de: 'Mein Plugin', en: 'My Plugin' },
  routes: [
    {
      path: '/mein-plugin',
      component: MeinPluginPage,
      permission: 'mein-plugin:read',
      label: { de: 'Mein Plugin', en: 'My Plugin' },
      icon: 'puzzle',
    },
  ],
  dashboardWidgets: [
    {
      id: 'mein-widget',
      component: MeinWidget,
      defaultSize: 'medium',
      permission: 'mein-plugin:read',
    },
  ],
  i18n: {
    de: () => import('./i18n/de.json'),
    en: () => import('./i18n/en.json'),
  },
}

export default plugin
```

### Dashboard-Widget (components/MeinWidget.tsx)

```typescript
import { useQuery } from '@tanstack/react-query'
import { fetchItems } from '../api/meinPlugin'

export default function MeinWidget() {
  const { data, isLoading } = useQuery({
    queryKey: ['mein-plugin', 'items'],
    queryFn: fetchItems,
  })

  if (isLoading) return <div>Lädt...</div>

  return (
    <div className="card">
      <h3>Mein Widget</h3>
      {data?.map(item => <div key={item.id}>{item.name}</div>)}
    </div>
  )
}
```

---

## Plugin aktivieren

Ein Plugin kann pro Saison aktiviert/deaktiviert werden:

1. **Admin → Saisons → Saison → Module → Plugin aktivieren**
2. Beim nächsten Seitenaufruf erscheint das Plugin in der Navigation

Alternativ in der Datenbank:
```sql
INSERT INTO season_modules (season_id, module_id, active)
VALUES ('<season-uuid>', 'mein-plugin', true);
```

---

## Nützliche Core-Utilities

```python
# Auth
from core.auth import require_permission, get_current_user

# Datenbank
from core.database import get_db, Base

# Logging
from core.logging import get_logger
logger = get_logger("mein-plugin")
logger.info("event", extra={"key": "value"})

# Fehler
from core.exceptions import NotFoundError, ForbiddenError
raise NotFoundError("Item nicht gefunden")

# Audit-Log
from core.audit import log_action
await log_action(db, user_id=user.id, action="mein-plugin.item.created",
                 entity_type="MeinModel", entity_id=item.id, new_value=item.dict())

# E-Mail
from core.notifications import send_email
await send_email(to=user.email, template="mein-plugin/benachrichtigung",
                 context={"item": item})
```
