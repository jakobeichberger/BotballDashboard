import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.auth import create_access_token, create_refresh_token, decode_token
from core.config import get_settings
from core.exceptions import BadRequestError, ConflictError, NotFoundError, UnauthorizedError
from modules.auth.models import Permission, RefreshToken, Role, User, UserRole, PushSubscription

settings = get_settings()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ── Permissions cache ─────────────────────────────────────────────────────────

async def get_user_permissions(db: AsyncSession, user_id: str) -> set[str]:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user = result.scalar_one_or_none()
    if not user:
        return set()
    if user.is_superuser:
        # superuser has all permissions
        all_perms = await db.execute(select(Permission.name))
        return {row[0] for row in all_perms.all()}
    perms: set[str] = set()
    for role in user.roles:
        for perm in role.permissions:
            perms.add(perm.name)
    return perms


# ── Auth ──────────────────────────────────────────────────────────────────────

async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(
        select(User)
        .where(User.email == email.lower(), User.is_active == True)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        raise UnauthorizedError("Invalid email or password")
    user.last_login = datetime.now(timezone.utc)
    return user


async def create_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    db.add(RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expire_days
        ),
    ))
    return access_token, refresh_token


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
    payload = decode_token(refresh_token, expected_type="refresh")
    user_id: str = payload["sub"]

    token_hash = _hash_token(refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    stored = result.scalar_one_or_none()
    if not stored:
        raise UnauthorizedError("Invalid or expired refresh token")

    # Rotate: revoke old, issue new
    stored.revoked = True
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("User not found")

    return await create_tokens(db, user)


async def revoke_refresh_token(db: AsyncSession, token: str) -> None:
    token_hash = _hash_token(token)
    await db.execute(
        delete(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )


# ── Users ─────────────────────────────────────────────────────────────────────

async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(
        select(User).options(selectinload(User.roles)).order_by(User.display_name)
    )
    return list(result.scalars().all())


async def get_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User not found")
    return user


async def create_user(
    db: AsyncSession, email: str, display_name: str, password: str, role_ids: list[str]
) -> User:
    existing = await db.execute(select(User).where(User.email == email.lower()))
    if existing.scalar_one_or_none():
        raise ConflictError("Email already registered")

    user = User(
        email=email.lower(),
        display_name=display_name,
        hashed_password=hash_password(password),
    )
    db.add(user)
    await db.flush()

    for role_id in role_ids:
        db.add(UserRole(user_id=user.id, role_id=role_id))

    await db.refresh(user, ["roles"])
    return user


async def update_user(
    db: AsyncSession, user_id: str, **kwargs
) -> User:
    user = await get_user(db, user_id)
    role_ids = kwargs.pop("role_ids", None)

    for key, value in kwargs.items():
        if value is not None:
            setattr(user, key, value)

    if role_ids is not None:
        await db.execute(delete(UserRole).where(UserRole.user_id == user_id))
        for role_id in role_ids:
            db.add(UserRole(user_id=user_id, role_id=role_id))

    await db.refresh(user, ["roles"])
    return user


async def change_password(
    db: AsyncSession, user_id: str, current_password: str, new_password: str
) -> None:
    user = await get_user(db, user_id)
    if not verify_password(current_password, user.hashed_password):
        raise BadRequestError("Current password is incorrect")
    user.hashed_password = hash_password(new_password)


# ── Roles ─────────────────────────────────────────────────────────────────────

async def list_roles(db: AsyncSession) -> list[Role]:
    result = await db.execute(
        select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
    )
    return list(result.scalars().all())


async def create_role(
    db: AsyncSession, name: str, description: str | None, permission_names: list[str]
) -> Role:
    existing = await db.execute(select(Role).where(Role.name == name))
    if existing.scalar_one_or_none():
        raise ConflictError("Role name already exists")

    role = Role(name=name, description=description)
    db.add(role)
    await db.flush()

    if permission_names:
        perms = await db.execute(
            select(Permission).where(Permission.name.in_(permission_names))
        )
        role.permissions = list(perms.scalars().all())

    return role


# ── Push subscriptions ────────────────────────────────────────────────────────

async def save_push_subscription(
    db: AsyncSession, user_id: str, endpoint: str, p256dh: str, auth: str, user_agent: str | None
) -> PushSubscription:
    # Upsert by endpoint
    existing = await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    )
    sub = existing.scalar_one_or_none()
    if sub:
        sub.p256dh = p256dh
        sub.auth = auth
        sub.user_agent = user_agent
        return sub

    sub = PushSubscription(
        user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth, user_agent=user_agent
    )
    db.add(sub)
    return sub


async def delete_push_subscription(db: AsyncSession, user_id: str, endpoint: str) -> None:
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user_id,
            PushSubscription.endpoint == endpoint,
        )
    )
