from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str  # str not EmailStr: login shouldn't reject unusual addresses (e.g. .local TLD)
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Users ─────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    display_name: str
    password: str
    role_ids: list[str] = []

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserUpdate(BaseModel):
    display_name: str | None = None
    preferred_language: str | None = None
    theme: str | None = None
    is_active: bool | None = None
    role_ids: list[str] | None = None


class UserPasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


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


class UserListItem(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    email: str
    display_name: str
    is_active: bool
    roles: list[RoleResponse]


# ── Roles ─────────────────────────────────────────────────────────────────────

class RoleCreate(BaseModel):
    name: str
    description: str | None = None
    permission_names: list[str] = []


class RoleDetailResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    description: str | None
    is_system: bool
    permissions: list[RoleResponse]


# ── Push subscriptions ────────────────────────────────────────────────────────

class PushSubscriptionCreate(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    user_agent: str | None = None
