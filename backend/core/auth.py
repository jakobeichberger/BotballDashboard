from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import Depends, Cookie
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import get_settings
from core.database import get_db
from core.exceptions import UnauthorizedError, ForbiddenError

settings = get_settings()

ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)


# ── Token creation ────────────────────────────────────────────────────────────

def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire, "type": "access", **(extra or {})}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise UnauthorizedError("Invalid or expired token")
    if payload.get("type") != expected_type:
        raise UnauthorizedError("Wrong token type")
    return payload


# ── Dependencies ──────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Dependency that returns the current authenticated User ORM object."""
    # Import here to avoid circular imports at module load time
    from modules.auth.models import User

    if not credentials:
        raise UnauthorizedError()

    payload = decode_token(credentials.credentials)
    user_id: str = payload.get("sub", "")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("User not found or inactive")
    return user


def require_permission(*permissions: str):
    """Dependency factory – raises 403 if user lacks ALL listed permissions."""

    async def _check(
        current_user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        from modules.auth.service import get_user_permissions

        user_perms = await get_user_permissions(db, current_user.id)
        missing = [p for p in permissions if p not in user_perms]
        if missing:
            raise ForbiddenError(f"Missing permissions: {', '.join(missing)}")
        return current_user

    return _check


def require_any_permission(*permissions: str):
    """Raises 403 if user has NONE of the listed permissions."""

    async def _check(
        current_user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        from modules.auth.service import get_user_permissions

        user_perms = await get_user_permissions(db, current_user.id)
        if not any(p in user_perms for p in permissions):
            raise ForbiddenError("Insufficient permissions")
        return current_user

    return _check
