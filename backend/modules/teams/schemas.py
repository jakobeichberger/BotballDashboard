from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from modules.seasons.categories import CategoryKey


class TeamMemberCreate(BaseModel):
    name: str
    email: str | None = None
    role: str = "member"
    user_id: str | None = None


class TeamMemberUpdate(BaseModel):
    """Partial update; an explicit ``user_id: null`` unlinks the account."""

    name: str | None = None
    email: str | None = None
    role: str | None = None
    user_id: str | None = None


class TeamMemberResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    email: str | None
    role: str
    user_id: str | None


class TeamCreate(BaseModel):
    name: str
    team_number: str | None = None
    school: str | None = None
    city: str | None = None
    country: str = "DE"
    competition_level_id: str | None = None
    notes: str | None = None
    members: list[TeamMemberCreate] = []


# Team fields a mentor may keep up to date for their own team. The team number,
# the competition level, the active flag and the organizers' notes are the
# organizers' call (teams:admin).
MENTOR_TEAM_FIELDS = frozenset({"name", "school", "city", "country"})


class TeamUpdate(BaseModel):
    name: str | None = None
    team_number: str | None = None
    school: str | None = None
    city: str | None = None
    country: str | None = None
    competition_level_id: str | None = None
    is_active: bool | None = None
    notes: str | None = None

    @field_validator("name", "country", "is_active")
    @classmethod
    def required_values_must_not_be_null(cls, value: str | bool | None) -> str | bool:
        if value is None:
            raise ValueError("Value must not be null")
        return value


class TeamResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    team_number: str | None
    school: str | None
    city: str | None
    country: str
    competition_level_id: str | None
    is_active: bool
    notes: str | None
    created_at: datetime
    members: list[TeamMemberResponse]


class TeamListItem(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    team_number: str | None
    school: str | None
    city: str | None
    country: str
    competition_level_id: str | None
    is_active: bool


class TeamSeasonRegistrationCreate(BaseModel):
    team_id: str
    season_id: str
    competition_level_id: str | None = None
    notes: str | None = None


# A key of the season's category registry, checked against it by the service.
TeamCategory = CategoryKey
FeeStatus = Literal["pending", "paid", "waived"]
KitStatus = Literal["not_sent", "sent", "received"]


class TeamSeasonRegistrationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    team_id: str
    season_id: str
    competition_level_id: str | None
    registered_at: datetime
    confirmed: bool
    notes: str | None
    category: str = "botball"
    fee_status: str = "pending"
    kit_status: str = "not_sent"
    paper_required: bool = True
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None


# Registration fields a mentor may keep up to date for their own team. Type,
# fee, kit, confirmation and organizer notes are the organizers' call.
MENTOR_SEASON_FIELDS = frozenset({"contact_name", "contact_email", "contact_phone", "address"})


class TeamSeasonUpdate(BaseModel):
    """PUT /teams/{id}/seasons/{season_id}: partial update of a registration."""

    category: TeamCategory | None = None
    competition_level_id: str | None = None
    fee_status: FeeStatus | None = None
    kit_status: KitStatus | None = None
    paper_required: bool | None = None
    confirmed: bool | None = None
    notes: str | None = None
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=2000)

    @field_validator("category", "fee_status", "kit_status", "paper_required", "confirmed")
    @classmethod
    def required_values_must_not_be_null(cls, value):
        if value is None:
            raise ValueError("Value must not be null")
        return value


class TeamSeasonMemberEntry(BaseModel):
    member_id: str
    role: str | None = Field(default=None, max_length=100)


class TeamSeasonRosterUpdate(BaseModel):
    """The complete roster of a season; members left out are removed."""

    members: list[TeamSeasonMemberEntry]


class TeamSeasonMemberResponse(BaseModel):
    id: str
    member_id: str
    name: str
    team_role: str
    role: str | None


# ── Documents ─────────────────────────────────────────────────────────────────

DocumentCategory = Literal["project_plan", "presentation", "code_documentation", "other"]


class TeamDocumentVersionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    version_number: int
    file_name: str
    media_type: str
    file_size_bytes: int
    comment: str | None
    uploaded_by: str | None
    uploaded_at: datetime


class TeamDocumentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    team_id: str
    season_id: str | None
    title: str
    category: str
    description: str | None
    current_version: int
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    versions: list[TeamDocumentVersionResponse]


class TeamDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    category: DocumentCategory | None = None
    description: str | None = None
    season_id: str | None = None


# ── 3D-print compliance ───────────────────────────────────────────────────────


class ComplianceItemCreate(BaseModel):
    season_id: str
    label: str = Field(min_length=1, max_length=500)
    description: str | None = None
    sort_order: int = 0


class ComplianceItemUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class ComplianceItemResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    label: str
    description: str | None
    sort_order: int
    is_active: bool


class ComplianceCheckUpdate(BaseModel):
    checked: bool
    note: str | None = Field(default=None, max_length=2000)


class ComplianceVerify(BaseModel):
    verified: bool = True


class ComplianceEntry(BaseModel):
    item: ComplianceItemResponse
    checked: bool
    note: str | None
    checked_by: str | None
    checked_at: datetime | None
    verified_by: str | None
    verified_at: datetime | None


class ComplianceStatusResponse(BaseModel):
    team_id: str
    season_id: str
    items: list[ComplianceEntry]
    total: int
    checked: int
    verified: int
    complete: bool
    is_verified: bool


class TeamEventHistoryResponse(BaseModel):
    event_id: str
    event_name: str
    season_id: str
    season_name: str
    season_year: int
    category: str
    rank: int | None
    seed_score: float | None
    best_score: float | None
    rounds_played: int
