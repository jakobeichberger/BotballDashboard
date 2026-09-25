from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from modules.seasons.categories import CategoryKey

AwardSource = Literal[
    "overall", "seeding", "de", "doc", "adapted_doc", "paper", "aerial", "jbc", "paper_on_stage"
]


class AwardCategoryBase(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    kind: Literal["computed", "judged"] = "judged"
    source: AwardSource | None = None
    team_category: CategoryKey | None = None
    places: int = Field(default=1, ge=1, le=20)
    per_course: bool = False
    sort_order: int | None = None

    @model_validator(mode="after")
    def computed_needs_source(self) -> "AwardCategoryBase":
        if self.kind == "computed" and (not self.source or self.source == "paper_on_stage"):
            raise ValueError("A computed award needs a ranking source")
        if self.kind == "judged" and self.source not in (None, "paper_on_stage"):
            raise ValueError("A judged award takes no ranking source")
        return self


class AwardCategoryCreate(AwardCategoryBase):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=50)


class AwardCategoryUpdate(AwardCategoryBase):
    pass


class NominationCreate(BaseModel):
    team_id: str
    note: str | None = Field(default=None, max_length=2000)


class NominationResponse(BaseModel):
    id: str
    team_id: str
    team_name: str | None
    note: str | None
    nominated_by: str | None
    created_at: datetime


class Placement(BaseModel):
    team_id: str
    place: int = Field(ge=1, le=20)
    course: str | None = Field(default=None, max_length=8)
    note: str | None = Field(default=None, max_length=2000)


class AwardDecision(BaseModel):
    placements: list[Placement] = Field(default_factory=list, max_length=50)


class AwardResultResponse(BaseModel):
    team_id: str
    team_name: str | None
    team_number: str | None = None
    place: int
    course: str | None
    score: float | None
    note: str | None


class AwardResponse(BaseModel):
    id: str
    event_id: str
    key: str
    label: str
    description: str | None
    kind: str
    source: str | None
    team_category: str | None
    places: int
    per_course: bool
    sort_order: int
    nominations: list[NominationResponse] = []
    results: list[AwardResultResponse] = []


class EventAwardsResponse(BaseModel):
    event_id: str
    template: str | None
    published: bool
    published_at: datetime | None
    awards: list[AwardResponse]


class PublishRequest(BaseModel):
    published: bool


class TemplateInfo(BaseModel):
    id: str
    name: str
    awards: list[dict]


class PublicAward(BaseModel):
    key: str
    label: str
    results: list[AwardResultResponse]
