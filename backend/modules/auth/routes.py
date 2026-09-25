from html import escape
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, permissions_of, require_permission
from core.config import get_settings
from core.database import get_db
from core.logging import get_logger
from core.rate_limit import rate_limit
from modules.auth import service
from modules.auth.schemas import (
    AccountDelete,
    AdminPasswordSet,
    CurrentUserResponse,
    EmailChange,
    LoginRequest,
    MeUpdate,
    NotificationPreferences,
    NotificationPreferencesUpdate,
    PasswordResetConfirm,
    PasswordResetRequest,
    PermissionResponse,
    PushSubscriptionCreate,
    RoleCreate,
    RoleDetailResponse,
    RolePermissionsUpdate,
    TokenResponse,
    UserCreate,
    UserListItem,
    UserPasswordChange,
    UserResponse,
    UserUpdate,
)
from modules.dashboard.notifications import normalize_preferences

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
logger = get_logger(__name__)

REFRESH_COOKIE = "refresh_token"


def _mail_enabled() -> bool:
    # Same rule as the account-creation mail: no real mail in development.
    return bool(settings.smtp_host) and not settings.is_dev


async def send_password_reset_email(email: str, display_name: str, token: str) -> None:
    """Mail the single-use reset link (background task)."""
    link = f"{settings.app_base_url.rstrip('/')}/reset-password?token={quote(token)}"
    if not _mail_enabled():
        # Development: there is no mail server, so the link goes to the log.
        logger.info("password_reset_link", email=email, link=link)
        return
    from core.notifications import send_email

    name = escape(display_name)
    await send_email(
        email,
        "BotballDashboard: Passwort zurücksetzen / reset your password",
        f"<p>Hallo {name},</p>"
        f'<p>über diesen Link kannst du ein neues Passwort setzen: <a href="{escape(link)}">'
        f"{escape(link)}</a></p><p>Der Link ist eine Stunde gültig und nur einmal "
        "verwendbar. Wenn du das nicht angefordert hast, ignoriere diese E-Mail.</p>"
        f"<p>Hello {name}, use the link above to set a new password. It is valid for one "
        "hour and can be used once.</p>",
        f"Hallo {display_name},\n\nneues Passwort setzen (1 Stunde gültig, einmal "
        f"verwendbar):\n{link}\n\nHello {display_name}, use this link to set a new "
        "password (valid for one hour, single use).",
    )


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        httponly=True,
        secure=not settings.is_dev,
        samesite="strict",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/api/auth",
    )


# ── Login / Logout ────────────────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("login", 10, 60))],
)
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


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("refresh", 30, 60))],
)
async def refresh(
    request: Request, response: Response, db: Annotated[AsyncSession, Depends(get_db)]
):
    # Accept token from cookie or JSON body (read body only once)
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        try:
            body = await request.json()
            refresh_token = body.get("refresh_token")
        except Exception:
            refresh_token = None
    if not refresh_token:
        from core.exceptions import UnauthorizedError

        raise UnauthorizedError("Refresh token required")
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
    # The access token presented with the logout would otherwise stay valid
    # until it expires; deny it. Only this session ends, other devices stay
    # signed in (a password change ends all of them via token_version).
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        await service.deny_access_token(authorization.split(" ", 1)[1])
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


# ── Current user ──────────────────────────────────────────────────────────────


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    permissions = await service.get_user_permissions(db, current_user.id)
    return {
        **{
            column.name: getattr(current_user, column.name)
            for column in current_user.__table__.columns
        },
        "roles": current_user.roles,
        "permissions": sorted(permissions),
    }


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: MeUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # MeUpdate cannot carry role_ids / is_active, so self-escalation is
    # structurally impossible.
    update_data = body.model_dump(exclude_none=True)
    return await service.update_user(db, current_user.id, **update_data)


@router.post(
    "/me/password",
    status_code=204,
    dependencies=[Depends(rate_limit("password-change", 10, 60))],
)
async def change_password(
    body: UserPasswordChange,
    response: Response,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.change_password(db, current_user.id, body.current_password, body.new_password)
    # All sessions were revoked (the current access token included); keep only
    # this device signed in. The client picks up a fresh access token through
    # /auth/refresh with this cookie.
    _access_token, refresh_token = await service.create_tokens(db, current_user)
    _set_refresh_cookie(response, refresh_token)


@router.post(
    "/me/email",
    response_model=UserResponse,
    dependencies=[Depends(rate_limit("email-change", 10, 60))],
)
async def change_email(
    body: EmailChange,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.change_email(
        db, current_user.id, str(body.new_email), body.current_password
    )


@router.get("/me/export")
async def export_my_data(
    current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """All personal data stored about the caller (DSGVO Art. 15/20)."""
    data = await service.export_user_data(db, current_user.id)
    return JSONResponse(
        jsonable_encoder(data),
        headers={"Content-Disposition": 'attachment; filename="my-botball-data.json"'},
    )


@router.delete(
    "/me",
    status_code=204,
    dependencies=[Depends(rate_limit("account-delete", 5, 60))],
)
async def delete_my_account(
    body: AccountDelete,
    response: Response,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete (anonymise) the caller's account. Requires the current password."""
    await service.delete_own_account(db, current_user.id, body.current_password)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


# ── Password reset (public) ───────────────────────────────────────────────────


@router.post(
    "/password-reset/request",
    status_code=204,
    dependencies=[Depends(rate_limit("password-reset", 5, 900))],
)
async def request_password_reset(
    body: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Always 204, whether or not the address belongs to an account."""
    issued = await service.request_password_reset(db, body.email)
    if issued:
        user, token = issued
        background_tasks.add_task(send_password_reset_email, user.email, user.display_name, token)


@router.post(
    "/password-reset/confirm",
    status_code=204,
    dependencies=[Depends(rate_limit("password-reset-confirm", 10, 900))],
)
async def confirm_password_reset(body: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    await service.confirm_password_reset(db, body.token, body.new_password)


# ── Notification preferences ──────────────────────────────────────────────────


@router.get("/me/notification-preferences", response_model=NotificationPreferences)
async def get_notification_preferences(current_user=Depends(get_current_user)):
    return normalize_preferences(current_user.notification_preferences)


@router.put("/me/notification-preferences", response_model=NotificationPreferences)
async def update_notification_preferences(
    body: NotificationPreferencesUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    merged = {
        **normalize_preferences(current_user.notification_preferences),
        **body.model_dump(exclude_none=True),
    }
    # Reassign (not mutate) so SQLAlchemy notices the JSON change.
    current_user.notification_preferences = merged
    await db.flush()
    return merged


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
    return [
        UserListItem.model_validate(user).model_copy(
            update={"permissions": sorted(permissions_of(user))}
        )
        for user in await service.list_users(db)
    ]


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    background_tasks: BackgroundTasks,
    _=Depends(require_permission("users:write")),
    db: AsyncSession = Depends(get_db),
):
    user = await service.create_user(
        db, body.email, body.display_name, body.password, body.role_ids
    )
    if settings.smtp_host and not settings.is_dev:
        from core.notifications import send_email

        background_tasks.add_task(
            send_email,
            body.email,
            "BotballDashboard account created",
            f"<p>Hello {body.display_name},</p><p>Your BotballDashboard account was created.</p>",
            f"Hello {body.display_name}, your BotballDashboard account was created.",
        )
    return user


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


@router.post("/users/{user_id}/password", status_code=204)
async def admin_set_password(
    user_id: str,
    body: AdminPasswordSet,
    _=Depends(require_permission("users:write")),
    db: AsyncSession = Depends(get_db),
):
    """Set a user's password (e.g. after a lost password) and end their sessions."""
    user = await service.get_user(db, user_id)
    await service.set_password(db, user, body.new_password)


@router.delete("/users/{user_id}", status_code=204)
async def admin_delete_user(
    user_id: str,
    current_user=Depends(require_permission("users:write")),
    db: AsyncSession = Depends(get_db),
):
    """Delete (anonymise) a user account; its history stays attributed to it."""
    await service.admin_delete_user(db, current_user.id, user_id)


# ── Admin: Roles ──────────────────────────────────────────────────────────────


@router.get("/roles", response_model=list[RoleDetailResponse])
async def list_roles(
    _=Depends(require_permission("roles:read")), db: AsyncSession = Depends(get_db)
):
    return await service.list_roles(db)


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    _=Depends(require_permission("roles:read")), db: AsyncSession = Depends(get_db)
):
    return await service.list_permissions(db)


@router.post("/roles", response_model=RoleDetailResponse, status_code=201)
async def create_role(
    body: RoleCreate,
    _=Depends(require_permission("roles:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_role(db, body.name, body.description, body.permission_names)


@router.put("/roles/{role_id}", response_model=RoleDetailResponse)
async def update_role(
    role_id: str,
    body: RolePermissionsUpdate,
    _=Depends(require_permission("roles:write")),
    db: AsyncSession = Depends(get_db),
):
    """Replace a role's permissions (the admin role keeps its critical ones)."""
    return await service.update_role_permissions(
        db, role_id, body.permission_names, body.description
    )
