from typing import Annotated

from fastapi import APIRouter, Depends, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, require_permission
from core.config import get_settings
from core.database import get_db
from modules.auth import service
from modules.auth.schemas import (
    LoginRequest,
    PushSubscriptionCreate,
    RefreshRequest,
    RoleCreate,
    RoleDetailResponse,
    TokenResponse,
    UserCreate,
    UserListItem,
    UserPasswordChange,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

REFRESH_COOKIE = "refresh_token"


# ── Login / Logout ────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, response: Response, db: Annotated[AsyncSession, Depends(get_db)]
):
    user = await service.authenticate_user(db, body.email, body.password)
    access_token, refresh_token = await service.create_tokens(db, user)
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        httponly=True,
        secure=not settings.is_dev,
        samesite="strict",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/api/auth",
    )
    return TokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request, response: Response, db: Annotated[AsyncSession, Depends(get_db)]
):
    # Accept token from cookie or body
    refresh_token = request.cookies.get(REFRESH_COOKIE) or (await request.body() and RefreshRequest.model_validate_json(await request.body())).refresh_token
    access_token, new_refresh = await service.refresh_tokens(db, refresh_token)
    response.set_cookie(
        REFRESH_COOKIE,
        new_refresh,
        httponly=True,
        secure=not settings.is_dev,
        samesite="strict",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/api/auth",
    )
    return TokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/logout", status_code=204)
async def logout(
    request: Request, response: Response, db: Annotated[AsyncSession, Depends(get_db)]
):
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        await service.revoke_refresh_token(db, token)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


# ── Current user ──────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(current_user=Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    update_data = body.model_dump(exclude_none=True, exclude={"role_ids"})
    return await service.update_user(db, current_user.id, **update_data)


@router.post("/me/password", status_code=204)
async def change_password(
    body: UserPasswordChange,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.change_password(db, current_user.id, body.current_password, body.new_password)


# ── Push subscriptions ────────────────────────────────────────────────────────

@router.post("/me/push-subscriptions", status_code=201)
async def subscribe_push(
    body: PushSubscriptionCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.save_push_subscription(
        db, current_user.id, body.endpoint, body.p256dh, body.auth, body.user_agent
    )
    return {"status": "subscribed"}


@router.delete("/me/push-subscriptions", status_code=204)
async def unsubscribe_push(
    body: PushSubscriptionCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_push_subscription(db, current_user.id, body.endpoint)


# ── Admin: Users ──────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserListItem])
async def list_users(
    _=Depends(require_permission("users:read")), db: AsyncSession = Depends(get_db)
):
    return await service.list_users(db)


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    _=Depends(require_permission("users:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_user(db, body.email, body.display_name, body.password, body.role_ids)


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    _=Depends(require_permission("users:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_user(db, user_id)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UserUpdate,
    _=Depends(require_permission("users:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_user(db, user_id, **body.model_dump(exclude_none=True))


# ── Admin: Roles ──────────────────────────────────────────────────────────────

@router.get("/roles", response_model=list[RoleDetailResponse])
async def list_roles(
    _=Depends(require_permission("roles:read")), db: AsyncSession = Depends(get_db)
):
    return await service.list_roles(db)


@router.post("/roles", response_model=RoleDetailResponse, status_code=201)
async def create_role(
    body: RoleCreate,
    _=Depends(require_permission("roles:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_role(db, body.name, body.description, body.permission_names)
