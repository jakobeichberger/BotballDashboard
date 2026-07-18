"""Comprehensive unit tests for the auth module (service + core helpers).

Exercises token creation/refresh/decode, permission resolution, user CRUD,
password change, role creation, and push-subscription persistence at the
service layer. Complements (does not duplicate) tests/unit/test_auth.py.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt
from sqlalchemy import select

from core.auth import (
    ALGORITHM,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from core.config import get_settings
from core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
)
from modules.auth.models import (
    Permission,
    PushSubscription,
    RefreshToken,
    Role,
    RolePermission,
    User,
    UserRole,
)
from modules.auth.service import (
    authenticate_user,
    change_password,
    create_role,
    create_tokens,
    create_user,
    delete_push_subscription,
    get_user,
    get_user_permissions,
    list_roles,
    list_users,
    refresh_tokens,
    revoke_refresh_token,
    save_push_subscription,
    update_user,
    verify_password,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _seed_permissions(db, names: list[str]) -> dict[str, Permission]:
    perms = {n: Permission(name=n) for n in names}
    for p in perms.values():
        db.add(p)
    await db.flush()
    return perms


async def _seed_role_with_perms(db, role_name: str, perm_names: list[str]) -> Role:
    perms = await _seed_permissions(db, perm_names)
    role = Role(name=role_name)
    db.add(role)
    await db.flush()
    for p in perms.values():
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    await db.flush()
    return role


async def _plain_user(db, email="plain@example.com", password="password123") -> User:
    user = await create_user(db, email, "Plain User", password, [])
    await db.commit()
    return user


async def _reset(db) -> None:
    """Commit and detach all objects so the next read loads fresh state.

    Tests share a single session (unlike production, where each request gets
    its own). Detaching mirrors a fresh request so that ``selectinload`` eager
    loads run against the DB instead of returning stale cached relationships.
    """
    await db.commit()
    db.expunge_all()


_settings = get_settings()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _make_refresh_token(subject: str, expire_days: int) -> str:
    """Mint a refresh token with an explicit expiry (mirrors core.auth encoding)."""
    expire = datetime.now(UTC) + timedelta(days=expire_days)
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, _settings.jwt_secret_key, algorithm=ALGORITHM)


# ── Token helpers (core.auth) ─────────────────────────────────────────────────


class TestTokenHelpers:
    def test_access_and_refresh_tokens_differ(self):
        access = create_access_token("u1")
        refresh = create_refresh_token("u1")
        assert access != refresh
        assert decode_token(access, "access")["type"] == "access"
        assert decode_token(refresh, "refresh")["type"] == "refresh"

    def test_access_token_carries_extra_claims(self):
        token = create_access_token("u1", extra={"scope": "admin"})
        payload = decode_token(token, "access")
        assert payload["scope"] == "admin"
        assert payload["sub"] == "u1"

    def test_decode_refresh_as_access_raises(self):
        refresh = create_refresh_token("u1")
        with pytest.raises(UnauthorizedError):
            decode_token(refresh, "access")

    def test_decode_garbage_raises(self):
        with pytest.raises(UnauthorizedError):
            decode_token("garbage")


# ── Permission resolution ─────────────────────────────────────────────────────


class TestGetUserPermissions:
    @pytest.mark.asyncio
    async def test_superuser_returns_all_seeded_permissions(self, db, admin_user):
        await _seed_permissions(db, ["a:read", "b:write", "c:admin"])
        await db.commit()
        perms = await get_user_permissions(db, admin_user.id)
        assert perms == {"a:read", "b:write", "c:admin"}

    @pytest.mark.asyncio
    async def test_role_based_user_returns_only_role_permissions(self, db):
        role = await _seed_role_with_perms(db, "reviewer", ["papers:read", "papers:write"])
        # An unrelated permission that the user should NOT have.
        await _seed_permissions(db, ["users:write"])
        user = await create_user(db, "rev@example.com", "Rev", "password123", [role.id])
        user_id = user.id
        await _reset(db)

        perms = await get_user_permissions(db, user_id)
        assert perms == {"papers:read", "papers:write"}

    @pytest.mark.asyncio
    async def test_user_with_no_roles_has_no_permissions(self, db):
        await _seed_permissions(db, ["x:read"])
        user = await _plain_user(db)
        perms = await get_user_permissions(db, user.id)
        assert perms == set()

    @pytest.mark.asyncio
    async def test_unknown_user_returns_empty_set(self, db):
        assert await get_user_permissions(db, "does-not-exist") == set()


# ── Authentication ────────────────────────────────────────────────────────────


class TestAuthenticateUser:
    @pytest.mark.asyncio
    async def test_email_is_case_insensitive(self, db):
        await _plain_user(db, email="mixed@example.com")
        user = await authenticate_user(db, "MIXED@EXAMPLE.COM", "password123")
        assert user.email == "mixed@example.com"

    @pytest.mark.asyncio
    async def test_sets_last_login(self, db):
        await _plain_user(db, email="ll@example.com")
        user = await authenticate_user(db, "ll@example.com", "password123")
        assert user.last_login is not None

    @pytest.mark.asyncio
    async def test_unknown_email_raises(self, db):
        with pytest.raises(UnauthorizedError):
            await authenticate_user(db, "nobody@example.com", "password123")

    @pytest.mark.asyncio
    async def test_inactive_user_cannot_authenticate(self, db):
        user = await _plain_user(db, email="inactive@example.com")
        user.is_active = False
        await db.commit()
        with pytest.raises(UnauthorizedError):
            await authenticate_user(db, "inactive@example.com", "password123")


# ── Refresh token lifecycle ───────────────────────────────────────────────────


class TestRefreshTokens:
    @pytest.mark.asyncio
    async def test_create_tokens_persists_refresh_token_hash(self, db):
        user = await _plain_user(db, email="rt@example.com")
        access, refresh = await create_tokens(db, user)
        await db.commit()
        assert access and refresh
        rows = (await db.execute(select(RefreshToken))).scalars().all()
        assert len(rows) == 1
        # Raw refresh token is never stored verbatim.
        assert rows[0].token_hash != refresh

    @pytest.mark.asyncio
    async def test_refresh_rotates_and_revokes_old_token(self, db):
        user = await _plain_user(db, email="rotate@example.com")
        # Seed a refresh token with a far-future exp so its JWT (and hash) is
        # guaranteed distinct from the rotated token minted by refresh_tokens,
        # which uses the default (shorter) expiry. This avoids a same-second
        # byte-identical-token UNIQUE collision on refresh_tokens.token_hash.
        seed = _make_refresh_token(user.id, expire_days=365)
        db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=_token_hash(seed),
                expires_at=datetime.now(UTC) + timedelta(days=365),
            )
        )
        await db.commit()

        new_access, new_refresh = await refresh_tokens(db, seed)
        await db.commit()
        assert new_refresh != seed

        # The seeded token's row is now revoked; reusing it fails.
        stored = (
            await db.execute(
                select(RefreshToken).where(RefreshToken.token_hash == _token_hash(seed))
            )
        ).scalar_one()
        assert stored.revoked is True

        with pytest.raises(UnauthorizedError):
            await refresh_tokens(db, seed)

    @pytest.mark.asyncio
    async def test_refresh_with_unknown_token_raises(self, db):
        user = await _plain_user(db, email="unknown-rt@example.com")
        # Valid signature but never stored in DB.
        bogus = create_refresh_token(user.id)
        with pytest.raises(UnauthorizedError):
            await refresh_tokens(db, bogus)

    @pytest.mark.asyncio
    async def test_revoke_refresh_token_deletes_row(self, db):
        user = await _plain_user(db, email="revoke@example.com")
        _, refresh = await create_tokens(db, user)
        await db.commit()
        await revoke_refresh_token(db, refresh)
        await db.commit()
        rows = (await db.execute(select(RefreshToken))).scalars().all()
        assert rows == []


# ── User CRUD ─────────────────────────────────────────────────────────────────


class TestUserCrud:
    @pytest.mark.asyncio
    async def test_create_user_with_roles_attaches_them(self, db):
        role = await _seed_role_with_perms(db, "juror", ["scoring:write"])
        role_id = role.id
        user = await create_user(db, "j@example.com", "Juror", "password123", [role.id])
        user_id = user.id
        await _reset(db)
        fetched = await get_user(db, user_id)
        assert {r.id for r in fetched.roles} == {role_id}

    @pytest.mark.asyncio
    async def test_duplicate_email_case_insensitive_conflict(self, db):
        await _plain_user(db, email="dup@example.com")
        with pytest.raises(ConflictError):
            await create_user(db, "DUP@EXAMPLE.COM", "Dup", "password123", [])

    @pytest.mark.asyncio
    async def test_get_user_unknown_raises_not_found(self, db):
        with pytest.raises(NotFoundError):
            await get_user(db, "missing")

    @pytest.mark.asyncio
    async def test_list_users_sorted_by_display_name(self, db):
        await create_user(db, "z@example.com", "Zara", "password123", [])
        await create_user(db, "a@example.com", "Aaron", "password123", [])
        await db.commit()
        users = await list_users(db)
        names = [u.display_name for u in users]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_update_user_changes_fields_and_ignores_none(self, db):
        user = await _plain_user(db, email="upd@example.com")
        updated = await update_user(
            db, user.id, display_name="Renamed", theme=None, is_active=False
        )
        await db.commit()
        assert updated.display_name == "Renamed"
        assert updated.is_active is False

    @pytest.mark.asyncio
    async def test_update_user_replaces_roles(self, db):
        role_a = await _seed_role_with_perms(db, "role-a", ["a:read"])
        role_b = await _seed_role_with_perms(db, "role-b", ["b:read"])
        role_b_id = role_b.id
        user = await create_user(db, "roles@example.com", "Roles", "password123", [role_a.id])
        user_id = user.id
        await _reset(db)

        await update_user(db, user_id, role_ids=[role_b_id])
        await _reset(db)

        fetched = await get_user(db, user_id)
        assert {r.id for r in fetched.roles} == {role_b_id}
        # The old association row is gone.
        ur = (await db.execute(select(UserRole).where(UserRole.user_id == user_id))).scalars().all()
        assert {row.role_id for row in ur} == {role_b_id}


# ── Password change ───────────────────────────────────────────────────────────


class TestChangePassword:
    @pytest.mark.asyncio
    async def test_change_password_updates_hash(self, db):
        user = await _plain_user(db, email="pw@example.com")
        await change_password(db, user.id, "password123", "newpassword456")
        await db.commit()
        refreshed = await get_user(db, user.id)
        assert verify_password("newpassword456", refreshed.hashed_password)
        assert not verify_password("password123", refreshed.hashed_password)

    @pytest.mark.asyncio
    async def test_change_password_wrong_current_raises(self, db):
        user = await _plain_user(db, email="pw2@example.com")
        with pytest.raises(BadRequestError):
            await change_password(db, user.id, "wrongcurrent", "newpassword456")


# ── Roles ─────────────────────────────────────────────────────────────────────


class TestRoles:
    @pytest.mark.asyncio
    async def test_create_role_without_permissions_persists(self, db):
        role = await create_role(db, "manager", "Team manager", [])
        role_id = role.id
        await _reset(db)
        roles = await list_roles(db)
        manager = next(r for r in roles if r.id == role_id)
        assert manager.name == "manager"
        assert manager.description == "Team manager"
        assert manager.permissions == []

    @pytest.mark.asyncio
    async def test_list_roles_reflects_attached_permissions(self, db):
        # Attach permissions via the association table (the data-layer contract
        # that get_user_permissions / list_roles read from).
        role = await _seed_role_with_perms(db, "manager2", ["teams:read", "teams:write"])
        role_id = role.id
        await _reset(db)
        roles = await list_roles(db)
        manager = next(r for r in roles if r.id == role_id)
        assert {p.name for p in manager.permissions} == {"teams:read", "teams:write"}

    @pytest.mark.asyncio
    async def test_create_role_duplicate_name_conflict(self, db):
        await create_role(db, "dupe-role", None, [])
        await db.commit()
        with pytest.raises(ConflictError):
            await create_role(db, "dupe-role", None, [])

    @pytest.mark.asyncio
    async def test_list_roles_sorted_by_name(self, db):
        await create_role(db, "zeta", None, [])
        await create_role(db, "alpha", None, [])
        await db.commit()
        roles = await list_roles(db)
        names = [r.name for r in roles]
        assert names == sorted(names)


# ── Push subscriptions ────────────────────────────────────────────────────────


class TestPushSubscriptions:
    @pytest.mark.asyncio
    async def test_save_creates_subscription(self, db):
        user = await _plain_user(db, email="push@example.com")
        await save_push_subscription(
            db, user.id, "https://push/endpoint-1", "p256", "auth", "agent"
        )
        await db.commit()
        rows = (await db.execute(select(PushSubscription))).scalars().all()
        assert len(rows) == 1
        assert rows[0].endpoint == "https://push/endpoint-1"

    @pytest.mark.asyncio
    async def test_save_upserts_by_endpoint(self, db):
        user = await _plain_user(db, email="push2@example.com")
        await save_push_subscription(db, user.id, "https://push/ep", "p1", "a1", "agent")
        await db.commit()
        await save_push_subscription(db, user.id, "https://push/ep", "p2", "a2", "agent2")
        await db.commit()
        rows = (await db.execute(select(PushSubscription))).scalars().all()
        assert len(rows) == 1  # updated, not duplicated
        assert rows[0].p256dh == "p2"
        assert rows[0].auth == "a2"

    @pytest.mark.asyncio
    async def test_delete_removes_only_matching_endpoint(self, db):
        user = await _plain_user(db, email="push3@example.com")
        await save_push_subscription(db, user.id, "https://push/keep", "p", "a", None)
        await save_push_subscription(db, user.id, "https://push/drop", "p", "a", None)
        await db.commit()
        await delete_push_subscription(db, user.id, "https://push/drop")
        await db.commit()
        rows = (await db.execute(select(PushSubscription))).scalars().all()
        assert [r.endpoint for r in rows] == ["https://push/keep"]
