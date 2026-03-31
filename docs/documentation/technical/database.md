# Datenbankschema

Alle Tabellen mit ihren wichtigsten Feldern, Relationen und Constraints.

---

## Core-Modul

### `users`
```sql
id            UUID PRIMARY KEY
email         VARCHAR(255) UNIQUE NOT NULL
password_hash VARCHAR(255) NOT NULL
name          VARCHAR(255) NOT NULL
language      VARCHAR(5) DEFAULT 'de'        -- 'de' | 'en'
theme         VARCHAR(10) DEFAULT 'system'   -- 'light' | 'dark' | 'system'
active        BOOLEAN DEFAULT true
created_at    TIMESTAMPTZ DEFAULT now()
last_login_at TIMESTAMPTZ
```

### `roles`
```sql
id          UUID PRIMARY KEY
name        VARCHAR(100) UNIQUE NOT NULL
description TEXT
```

### `permissions`
```sql
id   UUID PRIMARY KEY
key  VARCHAR(100) UNIQUE NOT NULL   -- z.B. 'scoring:write'
```

### `user_roles` (M:N)
```sql
user_id UUID REFERENCES users(id)
role_id UUID REFERENCES roles(id)
PRIMARY KEY (user_id, role_id)
```

### `role_permissions` (M:N)
```sql
role_id       UUID REFERENCES roles(id)
permission_id UUID REFERENCES permissions(id)
PRIMARY KEY (role_id, permission_id)
```

### `push_subscriptions`
```sql
id          UUID PRIMARY KEY
user_id     UUID REFERENCES users(id)
endpoint    TEXT NOT NULL
p256dh      TEXT NOT NULL
auth        TEXT NOT NULL
user_agent  TEXT
created_at  TIMESTAMPTZ DEFAULT now()
```

### `refresh_tokens`
```sql
id         UUID PRIMARY KEY
user_id    UUID REFERENCES users(id)
token_hash VARCHAR(255) NOT NULL
expires_at TIMESTAMPTZ NOT NULL
created_at TIMESTAMPTZ DEFAULT now()
revoked    BOOLEAN DEFAULT false
```

---

## Saison & Team

### `seasons`
```sql
id          UUID PRIMARY KEY
name        VARCHAR(255) NOT NULL
year        INTEGER NOT NULL
description TEXT
status      VARCHAR(20) DEFAULT 'draft'   -- draft | active | finished | archived
created_at  TIMESTAMPTZ DEFAULT now()
```

### `teams`
```sql
id         UUID PRIMARY KEY
name       VARCHAR(255) NOT NULL
number     VARCHAR(50)
school     VARCHAR(255)
country    VARCHAR(100)
created_at TIMESTAMPTZ DEFAULT now()
```

### `team_seasons`
```sql
id           UUID PRIMARY KEY
team_id      UUID REFERENCES teams(id)
season_id    UUID REFERENCES seasons(id)
team_type    VARCHAR(20) NOT NULL   -- 'botball' | 'open'
fee_status   VARCHAR(20) DEFAULT 'pending'   -- pending | paid
kit_status   VARCHAR(20)                      -- not_sent | sent | received (nur botball)
paper_required BOOLEAN DEFAULT true
created_at   TIMESTAMPTZ DEFAULT now()
UNIQUE (team_id, season_id)
```

### `team_mentors`
```sql
team_id   UUID REFERENCES teams(id)
user_id   UUID REFERENCES users(id)
season_id UUID REFERENCES seasons(id)
PRIMARY KEY (team_id, user_id, season_id)
```

---

## Scoring-Modul

### `competition_levels`
```sql
id                      UUID PRIMARY KEY
season_id               UUID REFERENCES seasons(id)
name                    VARCHAR(100) NOT NULL   -- 'ECER' | 'GCER'
order                   INTEGER NOT NULL
qualifies_from_level_id UUID REFERENCES competition_levels(id)
```

### `phases`
```sql
id                   UUID PRIMARY KEY
competition_level_id UUID REFERENCES competition_levels(id)
type                 VARCHAR(20) NOT NULL   -- 'preparation' | 'tournament'
name                 VARCHAR(255)
start_date           DATE
end_date             DATE
```

### `scoring_schemas`
```sql
id        UUID PRIMARY KEY
season_id UUID REFERENCES seasons(id)
level_id  UUID REFERENCES competition_levels(id)
fields    JSONB NOT NULL   -- Array von ScoringField-Objekten
```

### `tournaments`
```sql
id       UUID PRIMARY KEY
phase_id UUID REFERENCES phases(id)
type     VARCHAR(30) NOT NULL   -- test_run | seeding | double_elim | alliance
name     VARCHAR(255)
date     DATE
```

### `external_teams`
```sql
id        UUID PRIMARY KEY
season_id UUID REFERENCES seasons(id)
name      VARCHAR(255) NOT NULL
number    VARCHAR(50)
school    VARCHAR(255)
source    VARCHAR(20)   -- 'observed' | 'official'
```

### `matches`
```sql
id             UUID PRIMARY KEY
tournament_id  UUID REFERENCES tournaments(id)
round          INTEGER
status         VARCHAR(20) DEFAULT 'scheduled'   -- scheduled | running | done
team_a_id      UUID NOT NULL
team_a_type    VARCHAR(20) NOT NULL   -- 'internal' | 'external'
team_b_id      UUID
team_b_type    VARCHAR(20)
score_a        NUMERIC(10,2)
score_b        NUMERIC(10,2)
winner_id      UUID
created_at     TIMESTAMPTZ DEFAULT now()
```

### `scores`
```sql
id               UUID PRIMARY KEY
match_id         UUID REFERENCES matches(id)
team_id          UUID NOT NULL
team_type        VARCHAR(20) NOT NULL
raw_values       JSONB NOT NULL
calculated_total NUMERIC(10,2)
notes            TEXT
ocr_source_file  TEXT
submitted_by     UUID REFERENCES users(id)
submitted_at     TIMESTAMPTZ DEFAULT now()
```

### `team_cards`
```sql
id            UUID PRIMARY KEY
team_id       UUID NOT NULL
season_id     UUID REFERENCES seasons(id)
tournament_id UUID REFERENCES tournaments(id)
card_type     VARCHAR(10) NOT NULL   -- 'yellow' | 'red'
reason        TEXT NOT NULL
issued_by     UUID REFERENCES users(id)
issued_at     TIMESTAMPTZ DEFAULT now()
```

### `qualified_teams`
```sql
team_id              UUID REFERENCES teams(id)
from_level_id        UUID REFERENCES competition_levels(id)
to_level_id          UUID REFERENCES competition_levels(id)
qualified_by         UUID REFERENCES users(id)
qualified_at         TIMESTAMPTZ DEFAULT now()
PRIMARY KEY (team_id, to_level_id)
```

---

## Paper-Review-Modul

### `papers`
```sql
id         UUID PRIMARY KEY
team_id    UUID REFERENCES teams(id)
season_id  UUID REFERENCES seasons(id)
title      VARCHAR(500)
category   VARCHAR(100)
status     VARCHAR(30) DEFAULT 'submitted'
           -- submitted | under_review | revision_requested
           -- resubmitted | accepted | rejected
created_at TIMESTAMPTZ DEFAULT now()
```

### `paper_versions`
```sql
id          UUID PRIMARY KEY
paper_id    UUID REFERENCES papers(id)
version     INTEGER NOT NULL
file_url    TEXT NOT NULL
uploaded_by UUID REFERENCES users(id)
uploaded_at TIMESTAMPTZ DEFAULT now()
```

### `paper_reviews`
```sql
id               UUID PRIMARY KEY
paper_id         UUID REFERENCES papers(id)
paper_version_id UUID REFERENCES paper_versions(id)
reviewer_id      UUID REFERENCES users(id)
scores           JSONB   -- { relevanz: 8, qualitaet: 7, ... }
overall_score    NUMERIC(5,2)
comment          TEXT NOT NULL
internal_note    TEXT
decision         VARCHAR(20)   -- 'accept' | 'revise' | 'reject'
submitted_at     TIMESTAMPTZ
```

### `paper_reviewer_assignments`
```sql
paper_id    UUID REFERENCES papers(id)
reviewer_id UUID REFERENCES users(id)
assigned_by UUID REFERENCES users(id)
assigned_at TIMESTAMPTZ DEFAULT now()
PRIMARY KEY (paper_id, reviewer_id)
```

### `paper_deadlines`
```sql
id           UUID PRIMARY KEY
season_id    UUID REFERENCES seasons(id)
type         VARCHAR(50) NOT NULL
             -- official_submission | official_final
             -- internal_draft | internal_review | internal_revision | internal_final
deadline     DATE NOT NULL
is_hard_block BOOLEAN DEFAULT false
```

---

## 3D-Druck-Modul

### `printers`
```sql
id             UUID PRIMARY KEY
name           VARCHAR(255) NOT NULL
manufacturer   VARCHAR(100)
model          VARCHAR(100)
location       VARCHAR(255)
adapter_type   VARCHAR(20) NOT NULL   -- bambu | octoprint | prusa
adapter_config BYTEA NOT NULL         -- verschlüsselt (Fernet)
status         VARCHAR(20) DEFAULT 'offline'
active         BOOLEAN DEFAULT true
```

### `print_jobs`
```sql
id                          UUID PRIMARY KEY
team_id                     UUID REFERENCES teams(id)
season_id                   UUID REFERENCES seasons(id)
file_url                    TEXT NOT NULL
file_name                   VARCHAR(255) NOT NULL
material                    VARCHAR(50)
priority                    VARCHAR(20) DEFAULT 'normal'
comment                     TEXT
status                      VARCHAR(20) DEFAULT 'requested'
printer_id                  UUID REFERENCES printers(id)
requested_at                TIMESTAMPTZ DEFAULT now()
approved_at                 TIMESTAMPTZ
started_at                  TIMESTAMPTZ
finished_at                 TIMESTAMPTZ
progress_percent            INTEGER
estimated_remaining_seconds INTEGER
filament_used_grams         NUMERIC(8,2)
error_message               TEXT
approved_by                 UUID REFERENCES users(id)
rejection_reason            TEXT
```

### `team_season_print_quotas`
```sql
id                UUID PRIMARY KEY
team_id           UUID REFERENCES teams(id)
season_id         UUID REFERENCES seasons(id)
soft_limit_hours  NUMERIC(6,2)
hard_limit_hours  NUMERIC(6,2)
soft_limit_grams  NUMERIC(8,2)
hard_limit_grams  NUMERIC(8,2)
soft_limit_jobs   INTEGER
hard_limit_jobs   INTEGER
used_hours        NUMERIC(6,2) DEFAULT 0
used_grams        NUMERIC(8,2) DEFAULT 0
used_jobs         INTEGER DEFAULT 0
UNIQUE (team_id, season_id)
```

---

## System-Tabellen

### `error_logs`
```sql
id              UUID PRIMARY KEY
timestamp       TIMESTAMPTZ DEFAULT now()
level           VARCHAR(20) NOT NULL   -- ERROR | CRITICAL
module          VARCHAR(100)
event           VARCHAR(200)
user_id         UUID REFERENCES users(id)
request_path    TEXT
request_method  VARCHAR(10)
error_type      VARCHAR(200)
error_message   TEXT NOT NULL
stack_trace     TEXT
resolved        BOOLEAN DEFAULT false
resolved_by     UUID REFERENCES users(id)
resolved_at     TIMESTAMPTZ
resolution_note TEXT
```

### `audit_logs`
```sql
id          UUID PRIMARY KEY
timestamp   TIMESTAMPTZ DEFAULT now()
user_id     UUID REFERENCES users(id)
user_email  VARCHAR(255)
action      VARCHAR(200) NOT NULL
entity_type VARCHAR(100)
entity_id   UUID
old_value   JSONB
new_value   JSONB NOT NULL
ip_address  INET
```

### `schema_versions`
```sql
version     INTEGER PRIMARY KEY
applied_at  TIMESTAMPTZ DEFAULT now()
description TEXT
```

---

## Indizes (wichtigste)

```sql
-- Häufige Queries optimieren
CREATE INDEX idx_matches_tournament ON matches(tournament_id);
CREATE INDEX idx_scores_match ON scores(match_id);
CREATE INDEX idx_papers_season ON papers(season_id);
CREATE INDEX idx_print_jobs_team_season ON print_jobs(team_id, season_id);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX idx_error_logs_resolved ON error_logs(resolved, timestamp DESC);
```
