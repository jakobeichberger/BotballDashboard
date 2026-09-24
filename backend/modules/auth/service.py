import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core import token_denylist
from core.audit import AuditLog
from core.auth import create_access_token, create_refresh_token, decode_token
from core.config import get_settings
from core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from modules.auth.models import (
    PasswordResetToken,
    Permission,
    PushSubscription,
    RefreshToken,
    Role,
    User,
    UserRole,
)
from modules.auth.password_policy import password_problem

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
    user.last_login = datetime.now(UTC)
    return user


async def create_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    access_token = create_access_token(user.id, {"tv": user.token_version or 0})
    refresh_token = create_refresh_token(user.id)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_token(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
    )
    return access_token, refresh_token


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
    payload = decode_token(refresh_token, expected_type="refresh")
    user_id: str = payload["sub"]

    token_hash = _hash_token(refresh_token)
    token_result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(UTC),
        )
    )
    stored = token_result.scalar_one_or_none()
    if not stored:
        raise UnauthorizedError("Invalid or expired refresh token")

    # Rotate: revoke old, issue new
    stored.revoked = True
    user_result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = user_result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("User not found")

    return await create_tokens(db, user)


async def deny_access_token(token: str) -> None:
    """Deny-list an access token until its expiry (logout of this session).

    An invalid or expired token needs nothing: it is rejected anyway. So is
    one without jti (issued before the deny-list existed; it expires soon).
    """
    try:
        payload = decode_token(token, expected_type="access")
    except UnauthorizedError:
        return
    jti = payload.get("jti")
    if jti:
        await token_denylist.deny(str(jti), payload.get("exp"))


async def revoke_refresh_token(db: AsyncSession, token: str) -> None:
    token_hash = _hash_token(token)
    await db.execute(delete(RefreshToken).where(RefreshToken.token_hash == token_hash))


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

    # autoflush is off, so the UserRole inserts must reach the DB before the
    # refresh re-SELECTs, otherwise the response reports no roles at all.
    await db.flush()
    await db.refresh(user, ["roles"])
    return user


async def update_user(db: AsyncSession, user_id: str, **kwargs) -> User:
    user = await get_user(db, user_id)
    role_ids = kwargs.pop("role_ids", None)

    if kwargs.get("is_active") is False and user.is_active:
        # Deactivation must end every session right away, not after the
        # access token's 15 minutes.
        await revoke_all_sessions(db, user)

    for key, value in kwargs.items():
        if value is not None:
            setattr(user, key, value)

    if role_ids is not None:
        await db.execute(delete(UserRole).where(UserRole.user_id == user_id))
        for role_id in role_ids:
            db.add(UserRole(user_id=user_id, role_id=role_id))
        # autoflush is off, so the new UserRole rows must reach the DB before
        # the refresh re-SELECTs — the DELETE above already ran, so without
        # this the response shows the roles removed and not re-added.
        await db.flush()

    await db.refresh(user, ["roles"])
    return user


async def change_password(
    db: AsyncSession, user_id: str, current_password: str, new_password: str
) -> None:
    user = await get_user(db, user_id)
    if not verify_password(current_password, user.hashed_password):
        raise BadRequestError("Current password is incorrect")
    await set_password(db, user, new_password)


def ensure_password_policy(user: User, password: str) -> None:
    problem = password_problem(password, user.email)
    if problem:
        raise ValidationError(problem)


async def revoke_all_sessions(db: AsyncSession, user: User) -> None:
    """End every session of ``user``: refresh tokens and issued access tokens."""
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
    user.token_version = (user.token_version or 0) + 1
    await db.flush()


async def set_password(db: AsyncSession, user: User, new_password: str) -> None:
    """Set a new password and end all sessions (change, reset and admin set).

    A password change is how a user locks out whoever learned the old one;
    every session opened with it (refresh tokens live 30 days, access tokens
    15 minutes) must end.
    """
    ensure_password_policy(user, new_password)
    user.hashed_password = hash_password(new_password)
    await revoke_all_sessions(db, user)


async def change_email(
    db: AsyncSession, user_id: str, new_email: str, current_password: str
) -> User:
    user = await get_user(db, user_id)
    if not verify_password(current_password, user.hashed_password):
        raise BadRequestError("Current password is incorrect")
    new_email = new_email.lower()
    if new_email != user.email:
        existing = await db.execute(select(User.id).where(User.email == new_email))
        if existing.first():
            raise ConflictError("Email already registered")
        user.email = new_email
    await db.flush()
    await db.refresh(user, ["roles"])
    return user


# ── Password reset ────────────────────────────────────────────────────────────

PASSWORD_RESET_TTL = timedelta(hours=1)
# A new reset mail for the same account is sent at most this often.
PASSWORD_RESET_RESEND_AFTER = timedelta(minutes=1)


def _aware(value: datetime) -> datetime:
    # SQLite hands back naive datetimes even for timezone=True columns.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def request_password_reset(db: AsyncSession, email: str) -> tuple[User, str] | None:
    """Issue a reset token for an active account.

    Returns ``(user, token)`` for the caller to mail, or None when nothing is
    to be sent (unknown/inactive address, or a token was issued moments ago).
    The HTTP answer is the same either way, so addresses cannot be probed.
    """
    result = await db.execute(
        select(User).where(User.email == email.strip().lower(), User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if not user or user.anonymized_at is not None:
        return None
    now = datetime.now(UTC)
    recent = await db.execute(
        select(PasswordResetToken.created_at)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .order_by(PasswordResetToken.created_at.desc())
        .limit(1)
    )
    last = recent.scalar_one_or_none()
    if last is not None and now - _aware(last) < PASSWORD_RESET_RESEND_AFTER:
        return None
    # Only the newest link is valid.
    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)
        )
    )
    token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(token),
            expires_at=now + PASSWORD_RESET_TTL,
            created_at=now,
        )
    )
    await db.flush()
    return user, token


async def confirm_password_reset(db: AsyncSession, token: str, new_password: str) -> User:
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_token(token))
    )
    stored = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if stored is None or stored.used_at is not None or _aware(stored.expires_at) <= now:
        raise BadRequestError("Invalid or expired reset link")
    user = await get_user(db, stored.user_id)
    if not user.is_active or user.anonymized_at is not None:
        raise BadRequestError("Invalid or expired reset link")
    await set_password(db, user, new_password)
    stored.used_at = now
    return user


# ── Account deletion / export (DSGVO) ─────────────────────────────────────────


async def anonymize_user(db: AsyncSession, user: User) -> None:
    """Remove all personal data of ``user`` but keep the row.

    Scores entered, reviews, status changes and print jobs reference users.id;
    deleting the row would either fail or rewrite history. Instead the row is
    turned into an anonymous account that can never log in again.
    """
    from modules.teams.models import TeamMember

    if user.anonymized_at is not None:
        return
    old_email = user.email
    # Team member records are the team's data; drop only the link to the
    # account and the address of the person whose account this was.
    members = await db.execute(select(TeamMember).where(TeamMember.user_id == user.id))
    for member in members.scalars().all():
        member.user_id = None
        if member.email and member.email.lower() == old_email:
            member.email = None

    await db.execute(delete(PushSubscription).where(PushSubscription.user_id == user.id))
    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    await db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    await revoke_all_sessions(db, user)

    user.email = f"deleted-{user.id}@deleted.invalid"
    user.display_name = "Gelöschter Benutzer"
    # Random, never-disclosed secret: the account can no longer log in.
    user.hashed_password = hash_password(secrets.token_urlsafe(32))
    user.is_active = False
    user.is_superuser = False
    user.last_login = None
    user.anonymized_at = datetime.now(UTC)
    await db.flush()


async def delete_own_account(db: AsyncSession, user_id: str, current_password: str) -> None:
    user = await get_user(db, user_id)
    if not verify_password(current_password, user.hashed_password):
        raise BadRequestError("Current password is incorrect")
    await anonymize_user(db, user)


async def admin_delete_user(db: AsyncSession, acting_user_id: str, user_id: str) -> None:
    if acting_user_id == user_id:
        raise ConflictError("Use DELETE /auth/me to delete your own account")
    await anonymize_user(db, await get_user(db, user_id))


def _columns(obj: Any, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        attr.key: getattr(obj, attr.key)
        for attr in obj.__mapper__.column_attrs
        if attr.key not in exclude
    }


async def export_user_data(db: AsyncSession, user_id: str) -> dict[str, Any]:
    """Everything stored about the user (Art. 15/20 DSGVO), as plain data."""
    from modules.bots.models import Bot
    from modules.dashboard.models import NotificationRead
    from modules.paper_review.models import Paper, PaperReview
    from modules.printing.models import PrintJob
    from modules.scoring.models import Match
    from modules.teams.models import Team, TeamMember

    user = await get_user(db, user_id)

    async def rows(query, exclude: tuple[str, ...] = ()) -> list[dict[str, Any]]:
        return [_columns(item, exclude) for item in (await db.execute(query)).scalars().all()]

    memberships = await db.execute(
        select(TeamMember, Team)
        .join(Team, Team.id == TeamMember.team_id)
        .where(TeamMember.user_id == user_id)
    )
    return {
        "exported_at": datetime.now(UTC),
        "profile": _columns(user, exclude=("hashed_password", "token_version")),
        "roles": [role.name for role in user.roles],
        "permissions": sorted(await get_user_permissions(db, user_id)),
        "team_memberships": [
            {**_columns(member), "team_name": team.name} for member, team in memberships.all()
        ],
        "sessions": await rows(
            select(RefreshToken).where(RefreshToken.user_id == user_id),
            exclude=("token_hash",),
        ),
        "push_subscriptions": await rows(
            select(PushSubscription).where(PushSubscription.user_id == user_id),
            exclude=("p256dh", "auth"),
        ),
        "notification_reads": await rows(
            select(NotificationRead).where(NotificationRead.user_id == user_id)
        ),
        "matches_entered": await rows(select(Match).where(Match.entered_by == user_id)),
        "papers_submitted": await rows(
            select(Paper).where(Paper.submitted_by == user_id), exclude=("file_url",)
        ),
        "paper_reviews": await rows(select(PaperReview).where(PaperReview.reviewer_id == user_id)),
        "print_jobs_submitted": await rows(
            select(PrintJob).where(PrintJob.submitted_by == user_id), exclude=("file_url",)
        ),
        "bots_created": await rows(select(Bot).where(Bot.created_by == user_id)),
        "audit_log": await rows(
            select(AuditLog).where(AuditLog.user_id == user_id).order_by(AuditLog.created_at)
        ),
    }


# ── Roles ─────────────────────────────────────────────────────────────────────


async def list_roles(db: AsyncSession) -> list[Role]:
    result = await db.execute(
        select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
    )
    return list(result.scalars().all())


async def list_permissions(db: AsyncSession) -> list[Permission]:
    result = await db.execute(select(Permission).order_by(Permission.name))
    return list(result.scalars().all())


async def create_role(
    db: AsyncSession, name: str, description: str | None, permission_names: list[str]
) -> Role:
    existing = await db.execute(select(Role).where(Role.name == name))
    if existing.scalar_one_or_none():
        raise ConflictError("Role name already exists")

    role = Role(name=name, description=description)
    # Assign permissions on the transient object so no lazy-load of the
    # (empty) collection is triggered in the async context.
    if permission_names:
        perms = await db.execute(select(Permission).where(Permission.name.in_(permission_names)))
        role.permissions = list(perms.scalars().all())

    db.add(role)
    await db.flush()

    # Reload with permissions eagerly loaded so response serialization
    # doesn't trigger a lazy load (MissingGreenlet).
    result = await db.execute(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role.id)
    )
    return result.scalar_one()


# Permissions the system "admin" role can never lose: without them nobody could
# repair the user and role configuration any more.
ADMIN_CRITICAL_PERMISSIONS = frozenset({"users:read", "users:write", "roles:read", "roles:write"})


async def update_role_permissions(
    db: AsyncSession,
    role_id: str,
    permission_names: list[str],
    description: str | None = None,
) -> Role:
    result = await db.execute(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise NotFoundError("Role not found")

    wanted = set(permission_names)
    perms = list(
        (await db.execute(select(Permission).where(Permission.name.in_(wanted)))).scalars().all()
    )
    unknown = wanted - {perm.name for perm in perms}
    if unknown:
        raise ValidationError(f"Unknown permissions: {', '.join(sorted(unknown))}")
    if role.is_system and role.name == "admin":
        missing = ADMIN_CRITICAL_PERMISSIONS - wanted
        if missing:
            raise ForbiddenError(f"The admin role must keep: {', '.join(sorted(missing))}")

    role.permissions = perms
    if description is not None:
        role.description = description
    await db.flush()
    result = await db.execute(
        select(Role)
        .options(selectinload(Role.permissions))
        .where(Role.id == role.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


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
        # The same browser endpoint may be reused by another signed-in user.
        sub.user_id = user_id
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
