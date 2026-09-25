from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from modules.seasons.categories import CategoryKey

SeasonStatus = Literal["draft", "active", "finished", "archived"]


class SeasonPhaseCreate(BaseModel):
    name: str
    phase_type: str
    sort_order: int = 0
    rounds: int = 3
    start_date: date | None = None
    end_date: date | None = None


class SeasonPhaseResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    phase_type: str
    sort_order: int
    is_active: bool
    rounds: int
    start_date: date | None
    end_date: date | None


class SeasonCreate(BaseModel):
    name: str
    year: int
    game_theme: str | None = None
    # Creating a season as active deactivates the previously active one, exactly
    # like PUT /seasons/{id}/activate.
    is_active: bool = False
    # Defaults to "active" for an active season and "draft" otherwise.
    status: SeasonStatus | None = None
    # The setup wizard creates its own event right after the season; it passes
    # False so the season does not end up with a second, auto-generated event.
    create_default_event: bool = True
    registration_open: date | None = None
    registration_close: date | None = None
    event_start: date | None = None
    event_end: date | None = None
    paper_submission_deadline: date | None = None
    print_submission_deadline: date | None = None
    notes: str | None = None
    phases: list[SeasonPhaseCreate] = []
    # modules
    use_seeding: bool = True
    use_double_elimination: bool = False
    use_paper_scoring: bool = False
    use_documentation_scoring: bool = False
    use_aerial: bool = False
    active_categories: list[str] = ["botball"]


class SeasonUpdate(BaseModel):
    name: str | None = None
    game_theme: str | None = None
    is_active: bool | None = None
    status: SeasonStatus | None = None
    registration_open: date | None = None
    registration_close: date | None = None
    event_start: date | None = None
    event_end: date | None = None
    paper_submission_deadline: date | None = None
    print_submission_deadline: date | None = None
    notes: str | None = None
    # modules
    use_seeding: bool | None = None
    use_double_elimination: bool | None = None
    use_paper_scoring: bool | None = None
    use_documentation_scoring: bool | None = None
    use_aerial: bool | None = None
    active_categories: list[str] | None = None


class SeasonResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    year: int
    game_theme: str | None
    is_active: bool
    status: str
    registration_open: date | None
    registration_close: date | None
    event_start: date | None
    event_end: date | None
    paper_submission_deadline: date | None
    print_submission_deadline: date | None
    notes: str | None
    # modules
    use_seeding: bool
    use_double_elimination: bool
    use_paper_scoring: bool
    use_documentation_scoring: bool
    use_aerial: bool
    active_categories: list[str]
    created_at: datetime
    phases: list[SeasonPhaseResponse]


class SeasonListItem(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    year: int
    game_theme: str | None
    is_active: bool
    status: str
    event_start: date | None
    event_end: date | None


class CompetitionLevelResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    code: str
    description: str | None
    is_active: bool
    order: int = 0
    qualifies_from_level_id: str | None = None


class CompetitionLevelCreate(BaseModel):
    name: str
    code: str
    description: str | None = None
    order: int = Field(default=0, ge=0, le=100)
    qualifies_from_level_id: str | None = None


class CompetitionLevelUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    description: str | None = None
    is_active: bool | None = None
    order: int | None = Field(default=None, ge=0, le=100)
    # Explicit null clears the qualification source.
    qualifies_from_level_id: str | None = None


class SeasonEventCreate(BaseModel):
    title: str
    event_type: str = "deadline"  # deadline | event
    event_date: date
    description: str | None = None


class SeasonEventResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    title: str
    event_type: str
    event_date: date
    description: str | None


class SeasonClone(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    year: int = Field(ge=2000, le=2100)


# ── Category registry ─────────────────────────────────────────────────────────


class SeasonCategoryEntry(BaseModel):
    """One category of the season's registry (see modules.seasons.categories)."""

    model_config = {"from_attributes": True}

    key: CategoryKey
    label_de: str = Field(min_length=1, max_length=100)
    label_en: str = Field(min_length=1, max_length=100)
    kind: Literal["botball", "open", "aerial", "jbc", "custom"] = "custom"
    formula_preset: str | None = Field(default=None, max_length=50)
    run_count: int | None = Field(default=None, ge=1, le=20)
    counted_runs: int | None = Field(default=None, ge=1, le=20)
    rank_per_bracket: bool = False
    sort_order: int | None = None

    @model_validator(mode="after")
    def counted_within_runs(self) -> "SeasonCategoryEntry":
        if self.run_count and self.counted_runs and self.counted_runs > self.run_count:
            raise ValueError("counted_runs must not exceed run_count")
        return self
