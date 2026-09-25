from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from modules.auth.password_policy import check_password

Language = Literal["de", "en"]
Theme = Literal["light", "dark", "system"]

# ── Auth ──────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    email: str  # str not EmailStr: login shouldn't reject unusual addresses (e.g. .local TLD)
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


# ── Users ─────────────────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str
    password: str
    role_ids: list[str] = []

    @model_validator(mode="after")
    def password_strength(self) -> "UserCreate":
        check_password(self.password, str(self.email))
        return self


class UserUpdate(BaseModel):
    display_name: str | None = None
    preferred_language: Language | None = None
    theme: Theme | None = None
    is_active: bool | None = None
    role_ids: list[str] | None = None


class MeUpdate(BaseModel):
    """Self-service profile update. Deliberately excludes privilege fields
    (is_active, role_ids) so a user can never escalate or lock themselves out."""

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    preferred_language: Language | None = None
    theme: Theme | None = None


def _new_password(v: str) -> str:
    # The e-mail comparison needs the account and happens in the service.
    return check_password(v)


class NotificationPreferences(BaseModel):
    """Push delivery per notification category (see modules.dashboard.notifications)."""

    match_soon: bool = True
    score_corrected: bool = True
    deadlines: bool = True
    paper_status: bool = True
    print_status: bool = True
    announcements: bool = True


class NotificationPreferencesUpdate(BaseModel):
    match_soon: bool | None = None
    score_corrected: bool | None = None
    deadlines: bool | None = None
    paper_status: bool | None = None
    print_status: bool | None = None
    announcements: bool | None = None


class UserPasswordChange(BaseModel):
    current_password: str
    new_password: str

    _strength = field_validator("new_password")(_new_password)


class EmailChange(BaseModel):
    new_email: EmailStr
    current_password: str


class PasswordResetRequest(BaseModel):
    email: str  # str, not EmailStr: the answer must not depend on the format


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: str

    _strength = field_validator("new_password")(_new_password)


class AdminPasswordSet(BaseModel):
    new_password: str

    _strength = field_validator("new_password")(_new_password)


class AccountDelete(BaseModel):
    current_password: str


class RoleResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    description: str | None


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    email: str
    display_name: str
    is_active: bool
    is_superuser: bool
    preferred_language: str
    theme: str
    created_at: datetime
    last_login: datetime | None
    roles: list[RoleResponse]


class CurrentUserResponse(UserResponse):
    permissions: list[str]


class UserListItem(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    email: str
    display_name: str
    is_active: bool
    is_superuser: bool = False
    roles: list[RoleResponse]
    # Effective permissions through the roles, so clients can pick users by
    # what they may do (e.g. papers:review) instead of by role name.
    permissions: list[str] = []


# ── Roles ─────────────────────────────────────────────────────────────────────


class RoleCreate(BaseModel):
    name: str
    description: str | None = None
    permission_names: list[str] = []


class RolePermissionsUpdate(BaseModel):
    permission_names: list[str]
    description: str | None = None


class RoleDetailResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    description: str | None
    is_system: bool
    permissions: list[RoleResponse]


class PermissionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    description: str | None


# ── Push subscriptions ────────────────────────────────────────────────────────


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    user_agent: str | None = None
