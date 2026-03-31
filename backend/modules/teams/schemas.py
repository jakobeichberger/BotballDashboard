from datetime import datetime
from pydantic import BaseModel


class TeamMemberCreate(BaseModel):
    name: str
    email: str | None = None
    role: str = "member"
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


class TeamUpdate(BaseModel):
    name: str | None = None
    team_number: str | None = None
    school: str | None = None
    city: str | None = None
    country: str | None = None
    competition_level_id: str | None = None
    is_active: bool | None = None
    notes: str | None = None


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


class TeamSeasonRegistrationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    team_id: str
    season_id: str
    competition_level_id: str | None
    registered_at: datetime
    confirmed: bool
    notes: str | None
