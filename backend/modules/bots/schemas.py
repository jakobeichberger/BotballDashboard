from datetime import datetime

from pydantic import BaseModel, model_validator


class BotCreate(BaseModel):
    name: str
    team_id: str | None = None
    external_team_name: str | None = None
    season_id: str | None = None
    description: str | None = None
    functionality: str | None = None
    drive_type: str | None = None
    sensors: str | None = None

    @model_validator(mode="after")
    def _owner_required(self):
        if not self.team_id and not self.external_team_name:
            raise ValueError("Either team_id or external_team_name is required")
        if self.team_id and self.external_team_name:
            raise ValueError("Provide either team_id or external_team_name, not both")
        return self


class BotUpdate(BaseModel):
    name: str | None = None
    season_id: str | None = None
    description: str | None = None
    functionality: str | None = None
    drive_type: str | None = None
    sensors: str | None = None
    is_published: bool | None = None


class BotResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    team_id: str | None
    external_team_name: str | None
    season_id: str | None
    description: str | None
    functionality: str | None
    drive_type: str | None
    sensors: str | None
    is_published: bool
    image_name: str | None
    created_at: datetime
    updated_at: datetime
