from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import get_settings
from core.database import get_db
from core.exceptions import ForbiddenError, UnauthorizedError

settings = get_settings()

ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)


# ── Token creation ────────────────────────────────────────────────────────────


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire, "type": "access", **(extra or {})}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    # jti makes each refresh token unique, even if more than one token for the
    # same user is issued within the same second.
    payload = {"sub": subject, "exp": expire, "type": "refresh", "jti": str(uuid4())}
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
    from modules.auth.models import Role, User

    if not credentials:
        raise UnauthorizedError()

    payload = decode_token(credentials.credentials)
    user_id: str = payload.get("sub", "")

    result = await db.execute(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.id == user_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("User not found or inactive")
    return user


def permissions_of(user) -> set[str]:
    """Permission names of an already-loaded user.

    get_current_user selectinloads roles and their permissions, so this needs no
    query — re-fetching them here doubled the round trips of every
    authenticated request.
    """
    return {perm.name for role in user.roles for perm in role.permissions}


async def _permissions_for(db: AsyncSession, user) -> set[str]:
    """Permissions of `user`, without a query when they are already loaded.

    Users from get_current_user carry their roles and permissions; a user loaded
    any other way would otherwise trigger a lazy load from async code
    (MissingGreenlet), so fall back to querying for those.
    """
    state = sa_inspect(user)
    if "roles" not in state.unloaded and all(
        "permissions" not in sa_inspect(role).unloaded for role in user.roles
    ):
        return permissions_of(user)
    from modules.auth.service import get_user_permissions

    return await get_user_permissions(db, user.id)


def require_permission(*permissions: str):
    """Dependency factory – raises 403 if user lacks ALL listed permissions."""

    async def _check(
        current_user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        # Superusers bypass all permission checks – independent of whether the
        # permission table is populated.
        if current_user.is_superuser:
            return current_user

        user_perms = permissions_of(current_user)
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
        if current_user.is_superuser:
            return current_user

        user_perms = permissions_of(current_user)
        if not any(p in user_perms for p in permissions):
            raise ForbiddenError("Insufficient permissions")
        return current_user

    return _check


async def has_elevated_access(db, user, elevated_permission: str | tuple[str, ...]) -> bool:
    """True for superusers and holders of any of the given permissions."""
    if user.is_superuser:
        return True
    wanted = (elevated_permission,) if isinstance(elevated_permission, str) else elevated_permission
    held = await _permissions_for(db, user)
    return any(p in held for p in wanted)


async def own_team_ids(db, user) -> set[str]:
    """Ids of the teams `user` is a member of (a mentor's own teams)."""
    from modules.teams.models import TeamMember

    result = await db.execute(select(TeamMember.team_id).where(TeamMember.user_id == user.id))
    return set(result.scalars().all())


async def assert_team_access(
    db, user, team_id: str, elevated_permission: str | tuple[str, ...]
) -> None:
    """Authorize an action scoped to a single team.

    Superusers and holders of ``elevated_permission`` (e.g. an organizer with
    ``scoring:admin`` / ``papers:admin``; a tuple means any of them) may act on
    any team. Everyone else – typically a mentor doing self-service – must be a
    member of ``team_id``.
    """
    if await has_elevated_access(db, user, elevated_permission):
        return

    if team_id not in await own_team_ids(db, user):
        raise ForbiddenError("You may only access your own team")
