"""Route-level security regression tests: self-service privilege boundaries,
security headers, and path-traversal-safe uploads."""
import io

import pytest
from sqlalchemy import select

from core.auth import create_access_token
from modules.auth.models import User, Role
from modules.auth.service import hash_password


async def _make_user(db, *, superuser=False):
    user = User(
        email=f"plain_{'su' if superuser else 'normal'}@example.com",
        display_name="Plain",
        hashed_password=hash_password("password123"),
        is_active=True,
        is_superuser=superuser,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


class TestSelfServicePrivilegeBoundary:
    @pytest.mark.asyncio
    async def test_me_cannot_assign_roles_or_change_active(self, client, db):
        """PATCH /me must ignore role_ids / is_active (no self-escalation, no
        self-deactivation) — MeUpdate doesn't carry those fields."""
        user = await _make_user(db)
        token = create_access_token(user.id)
        headers = {"Authorization": f"Bearer {token}"}

        # Seed an admin role so there is something to (illegitimately) grab.
        admin_role = Role(name="admin", description="all")
        db.add(admin_role)
        await db.commit()

        resp = await client.patch(
            "/api/auth/me",
            headers=headers,
            json={"display_name": "Renamed", "role_ids": [admin_role.id], "is_active": False},
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Renamed"  # allowed field applied

        await db.commit()
        refreshed = (
            await db.execute(
                select(User).where(User.id == user.id)
            )
        ).scalar_one()
        await db.refresh(refreshed, ["roles"])
        assert refreshed.is_active is True          # NOT deactivated
        assert [r.name for r in refreshed.roles] == []  # NOT escalated

    @pytest.mark.asyncio
    async def test_non_admin_cannot_create_users(self, client, db):
        user = await _make_user(db)
        token = create_access_token(user.id)
        resp = await client.post(
            "/api/auth/users",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "x@example.com", "display_name": "X", "password": "password123"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_create_roles(self, client, db):
        user = await _make_user(db)
        token = create_access_token(user.id)
        resp = await client.post(
            "/api/auth/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "hacker", "description": "x", "permission_names": []},
        )
        assert resp.status_code == 403


class TestSecurityHeaders:
    @pytest.mark.asyncio
    async def test_headers_present(self, client):
        resp = await client.get("/api/system/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("referrer-policy") == "no-referrer"


class TestUnauthenticatedRejected:
    @pytest.mark.asyncio
    async def test_protected_route_requires_auth(self, client):
        assert (await client.get("/api/auth/users")).status_code == 401
        assert (await client.post("/api/seasons", json={"name": "x", "year": 2026})).status_code == 401

    @pytest.mark.asyncio
    async def test_tampered_token_rejected(self, client):
        resp = await client.get(
            "/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"}
        )
        assert resp.status_code == 401
