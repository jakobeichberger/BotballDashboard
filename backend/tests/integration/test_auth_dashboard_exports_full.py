"""Integration tests for auth, dashboard, and exports HTTP routes.

All routes are mounted under /api. Superusers bypass permission checks;
non-superusers need explicit Role+Permission rows seeded in the test DB.
Complements (does not duplicate) tests/integration/test_auth_routes.py.
"""
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from core.auth import ALGORITHM, create_access_token
from core.config import get_settings
from modules.auth.models import Permission, RefreshToken, Role, RolePermission, User, UserRole
from modules.auth.service import create_user, hash_password

_settings = get_settings()


async def _seed_refresh_token(db, user_id: str, *, expire_days: int) -> str:
    """Mint a refresh token with an explicit expiry and persist its row.

    A long expiry keeps the seeded token's JWT (and hash) distinct from the
    shorter-lived token the refresh route mints on rotation, avoiding a
    same-second byte-identical UNIQUE collision on refresh_tokens.token_hash.
    """
    expire = datetime.now(timezone.utc) + timedelta(days=expire_days)
    token = jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh"},
        _settings.jwt_secret_key,
        algorithm=ALGORITHM,
    )
    db.add(RefreshToken(
        user_id=user_id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=expire,
    ))
    await db.commit()
    return token


# ── Fixtures: non-superuser users with seeded permissions ─────────────────────

async def _make_user(db, email, *, superuser=False, active=True) -> User:
    user = User(
        email=email.lower(),
        display_name=email.split("@")[0],
        hashed_password=hash_password("password123"),
        is_active=active,
        is_superuser=superuser,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _grant(db, user: User, *perm_names: str, role_name: str | None = None) -> Role:
    """Create permissions + a role bearing them and attach to the user."""
    role = Role(name=role_name or f"role-{user.id[:8]}")
    db.add(role)
    await db.flush()
    for name in perm_names:
        perm = Permission(name=name)
        db.add(perm)
        await db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(user_id=user.id, role_id=role.id))
    await db.commit()
    return role


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


# ── Auth: login / refresh / logout cookie flow ────────────────────────────────

class TestAuthFlow:
    @pytest.mark.asyncio
    async def test_login_sets_refresh_cookie(self, client, db):
        await create_user(db, "cookie@example.com", "Cookie", "password123", [])
        await db.commit()
        resp = await client.post(
            "/api/auth/login",
            json={"email": "cookie@example.com", "password": "password123"},
        )
        assert resp.status_code == 200
        assert "refresh_token" in resp.cookies

    @pytest.mark.asyncio
    async def test_refresh_via_cookie_returns_new_access_token(self, client, db):
        user = await create_user(db, "ref@example.com", "Ref", "password123", [])
        await db.commit()
        token = await _seed_refresh_token(db, user.id, expire_days=365)
        # Set the cookie on the client jar so the refresh route reads it from
        # request.cookies (the production cookie-based refresh path).
        client.cookies.set("refresh_token", token)
        resp = await client.post("/api/auth/refresh")
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    @pytest.mark.asyncio
    async def test_refresh_via_json_body(self, client, db):
        user = await create_user(db, "refbody@example.com", "RefBody", "password123", [])
        await db.commit()
        token = await _seed_refresh_token(db, user.id, expire_days=365)
        client.cookies.clear()  # force the route to read the JSON body
        resp = await client.post("/api/auth/refresh", json={"refresh_token": token})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_refresh_without_token_returns_401(self, client):
        client.cookies.clear()
        resp = await client.post("/api/auth/refresh")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_invalid_email_format_returns_401(self, client):
        resp = await client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "x"}
        )
        assert resp.status_code == 401


# ── /me self-service ──────────────────────────────────────────────────────────

class TestMeRoutes:
    @pytest.mark.asyncio
    async def test_patch_me_updates_profile(self, client, db):
        user = await _make_user(db, "me@example.com")
        resp = await client.patch(
            "/api/auth/me", headers=_headers(user),
            json={"display_name": "Updated Name", "theme": "dark"},
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Updated Name"
        assert resp.json()["theme"] == "dark"

    @pytest.mark.asyncio
    async def test_change_password_success_then_old_password_fails(self, client, db):
        user = await _make_user(db, "mepw@example.com")
        resp = await client.post(
            "/api/auth/me/password", headers=_headers(user),
            json={"current_password": "password123", "new_password": "brandnewpass"},
        )
        assert resp.status_code == 204
        # Old password no longer works.
        bad = await client.post(
            "/api/auth/login",
            json={"email": "mepw@example.com", "password": "password123"},
        )
        assert bad.status_code == 401
        good = await client.post(
            "/api/auth/login",
            json={"email": "mepw@example.com", "password": "brandnewpass"},
        )
        assert good.status_code == 200

    @pytest.mark.asyncio
    async def test_change_password_wrong_current_returns_400(self, client, db):
        user = await _make_user(db, "mepw2@example.com")
        resp = await client.post(
            "/api/auth/me/password", headers=_headers(user),
            json={"current_password": "wrong", "new_password": "brandnewpass"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_change_password_too_short_returns_422(self, client, db):
        user = await _make_user(db, "mepw3@example.com")
        resp = await client.post(
            "/api/auth/me/password", headers=_headers(user),
            json={"current_password": "password123", "new_password": "short"},
        )
        assert resp.status_code == 422


# ── Push subscriptions over HTTP ──────────────────────────────────────────────

class TestPushSubscriptionRoutes:
    @pytest.mark.asyncio
    async def test_subscribe_returns_status_subscribed(self, client, db):
        user = await _make_user(db, "push@example.com")
        resp = await client.post(
            "/api/auth/me/push-subscriptions", headers=_headers(user),
            json={"endpoint": "https://push/ep", "p256dh": "p", "auth": "a"},
        )
        assert resp.status_code == 201
        assert resp.json() == {"status": "subscribed"}

    @pytest.mark.asyncio
    async def test_unsubscribe_returns_204(self, client, db):
        user = await _make_user(db, "push2@example.com")
        await client.post(
            "/api/auth/me/push-subscriptions", headers=_headers(user),
            json={"endpoint": "https://push/ep2", "p256dh": "p", "auth": "a"},
        )
        resp = await client.request(
            "DELETE", "/api/auth/me/push-subscriptions", headers=_headers(user),
            json={"endpoint": "https://push/ep2", "p256dh": "p", "auth": "a"},
        )
        assert resp.status_code == 204


# ── Admin user/role management permissions ────────────────────────────────────

class TestUserManagementPermissions:
    @pytest.mark.asyncio
    async def test_non_superuser_without_perm_gets_403(self, client, db):
        user = await _make_user(db, "noperm@example.com")
        resp = await client.get("/api/auth/users", headers=_headers(user))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_user_with_users_read_perm_can_list(self, client, db):
        user = await _make_user(db, "reader@example.com")
        await _grant(db, user, "users:read")
        resp = await client.get("/api/auth/users", headers=_headers(user))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_users_read_does_not_grant_write(self, client, db):
        user = await _make_user(db, "readonly@example.com")
        await _grant(db, user, "users:read")
        resp = await client.post(
            "/api/auth/users", headers=_headers(user),
            json={"email": "x@example.com", "display_name": "X", "password": "password123"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_user_with_users_write_can_create(self, client, db):
        user = await _make_user(db, "writer@example.com")
        await _grant(db, user, "users:write")
        resp = await client.post(
            "/api/auth/users", headers=_headers(user),
            json={
                "email": "created@example.com",
                "display_name": "Created",
                "password": "password123",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["email"] == "created@example.com"

    @pytest.mark.asyncio
    async def test_create_user_short_password_returns_422(self, client, auth_headers):
        resp = await client.post(
            "/api/auth/users", headers=auth_headers,
            json={"email": "short@example.com", "display_name": "S", "password": "short"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_and_update_user_as_admin(self, client, db, auth_headers):
        target = await _make_user(db, "target@example.com")
        get_resp = await client.get(f"/api/auth/users/{target.id}", headers=auth_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["email"] == "target@example.com"

        patch_resp = await client.patch(
            f"/api/auth/users/{target.id}", headers=auth_headers,
            json={"display_name": "Renamed", "is_active": False},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["display_name"] == "Renamed"
        assert patch_resp.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_get_unknown_user_returns_404(self, client, auth_headers):
        resp = await client.get("/api/auth/users/missing-id", headers=auth_headers)
        assert resp.status_code == 404


class TestRoleManagementPermissions:
    @pytest.mark.asyncio
    async def test_list_roles_requires_roles_read(self, client, db):
        user = await _make_user(db, "norole@example.com")
        resp = await client.get("/api/auth/roles", headers=_headers(user))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_list_roles_as_admin_returns_seeded_roles(self, client, db, auth_headers):
        # Seed a role + permission directly (POST /roles serialization of the
        # permissions relationship is exercised separately at the service layer).
        perm = Permission(name="teams:read")
        role = Role(name="seeded-role", description="desc")
        db.add(perm)
        db.add(role)
        await db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
        await db.commit()

        listing = await client.get("/api/auth/roles", headers=auth_headers)
        assert listing.status_code == 200
        seeded = next(r for r in listing.json() if r["name"] == "seeded-role")
        assert {p["name"] for p in seeded["permissions"]} == {"teams:read"}

    @pytest.mark.asyncio
    async def test_create_role_requires_roles_write(self, client, db):
        # Permission gating runs before the request body, so this is a clean 403.
        user = await _make_user(db, "rolewriter@example.com")
        resp = await client.post(
            "/api/auth/roles", headers=_headers(user),
            json={"name": "blocked", "permission_names": []},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_duplicate_role_returns_409(self, client, db, auth_headers):
        # Seed the conflicting role directly; create_role raises ConflictError
        # before touching the permissions relationship.
        db.add(Role(name="dupe"))
        await db.commit()
        resp = await client.post(
            "/api/auth/roles", headers=auth_headers,
            json={"name": "dupe", "permission_names": []},
        )
        assert resp.status_code == 409


# ── Deactivated user token rejection ──────────────────────────────────────────

class TestInactiveUser:
    @pytest.mark.asyncio
    async def test_inactive_user_token_rejected(self, client, db):
        user = await _make_user(db, "inactive@example.com", active=False)
        resp = await client.get("/api/auth/me", headers=_headers(user))
        assert resp.status_code == 401


# ── Dashboard: announcements + stats ──────────────────────────────────────────

class TestDashboardAnnouncements:
    @pytest.mark.asyncio
    async def test_create_announcement_requires_dashboard_write(self, client, db):
        user = await _make_user(db, "dashnoperm@example.com")
        resp = await client.post(
            "/api/dashboard/announcements", headers=_headers(user),
            json={"title": "Hi", "body": "Body"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_publish_then_list_flow(self, client, db, auth_headers):
        # Create (unpublished by default)
        create = await client.post(
            "/api/dashboard/announcements", headers=auth_headers,
            json={"title": "Welcome", "body": "Season opening", "audience": "all"},
        )
        assert create.status_code == 201
        ann = create.json()
        assert ann["is_published"] is False

        # Unpublished announcements are not listed.
        empty = await client.get("/api/dashboard/announcements", headers=auth_headers)
        assert empty.status_code == 200
        assert all(a["id"] != ann["id"] for a in empty.json())

        # Publish, then it shows up.
        pub = await client.put(
            f"/api/dashboard/announcements/{ann['id']}/publish", headers=auth_headers
        )
        assert pub.status_code == 200
        assert pub.json()["is_published"] is True
        assert pub.json()["published_at"] is not None

        # The test override of get_db does not auto-commit per request, so flush
        # the shared session before the next read query (autoflush is off).
        await db.commit()
        listed = await client.get("/api/dashboard/announcements", headers=auth_headers)
        assert any(a["id"] == ann["id"] for a in listed.json())

    @pytest.mark.asyncio
    async def test_list_announcements_filtered_by_season(self, client, db, auth_headers, season):
        create = await client.post(
            "/api/dashboard/announcements", headers=auth_headers,
            json={"title": "S", "body": "B", "season_id": season.id},
        )
        ann_id = create.json()["id"]
        await client.put(
            f"/api/dashboard/announcements/{ann_id}/publish", headers=auth_headers
        )
        await db.commit()  # flush publish state before re-querying
        # Matching season returns it.
        match = await client.get(
            "/api/dashboard/announcements", headers=auth_headers,
            params={"season_id": season.id},
        )
        assert any(a["id"] == ann_id for a in match.json())
        # Non-matching season filters it out.
        other = await client.get(
            "/api/dashboard/announcements", headers=auth_headers,
            params={"season_id": "some-other-season"},
        )
        assert all(a["id"] != ann_id for a in other.json())

    @pytest.mark.asyncio
    async def test_publish_unknown_announcement_returns_404(self, client, auth_headers):
        resp = await client.put(
            "/api/dashboard/announcements/missing/publish", headers=auth_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_announcements_requires_auth(self, client):
        resp = await client.get("/api/dashboard/announcements")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_non_superuser_with_write_can_create(self, client, db):
        user = await _make_user(db, "dashwrite@example.com")
        await _grant(db, user, "dashboard:write")
        resp = await client.post(
            "/api/dashboard/announcements", headers=_headers(user),
            json={"title": "From reviewer", "body": "Body"},
        )
        assert resp.status_code == 201


class TestDashboardStats:
    @pytest.mark.asyncio
    async def test_stats_requires_dashboard_read(self, client, db):
        user = await _make_user(db, "statsnoperm@example.com")
        resp = await client.get("/api/dashboard/stats", headers=_headers(user))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_stats_without_season_returns_zeros(self, client, auth_headers):
        resp = await client.get("/api/dashboard/stats", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == {"teams": 0, "papers": 0, "print_jobs": 0, "matches": 0}

    @pytest.mark.asyncio
    async def test_stats_counts_registered_teams(self, client, db, auth_headers, season, team):
        from modules.teams.models import TeamSeasonRegistration

        db.add(TeamSeasonRegistration(team_id=team.id, season_id=season.id))
        await db.commit()
        resp = await client.get(
            "/api/dashboard/stats", headers=auth_headers, params={"season_id": season.id}
        )
        assert resp.status_code == 200
        assert resp.json()["teams"] == 1

    @pytest.mark.asyncio
    async def test_stats_non_superuser_with_read_perm(self, client, db, season):
        user = await _make_user(db, "statsread@example.com")
        await _grant(db, user, "dashboard:read")
        resp = await client.get(
            "/api/dashboard/stats", headers=_headers(user), params={"season_id": season.id}
        )
        assert resp.status_code == 200


# ── Exports: CSV + PDF for a season ───────────────────────────────────────────

class TestExports:
    @pytest.mark.asyncio
    async def test_teams_csv_has_header_and_content_type(self, client, auth_headers, season):
        resp = await client.get(f"/api/exports/seasons/{season.id}/teams.csv", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        # CSV header row (utf-8-sig BOM tolerated).
        assert "Name" in resp.text and "Nummer" in resp.text

    @pytest.mark.asyncio
    async def test_teams_csv_includes_registered_team(self, client, db, auth_headers, season, team):
        from modules.teams.models import TeamSeasonRegistration

        db.add(TeamSeasonRegistration(team_id=team.id, season_id=season.id))
        await db.commit()
        resp = await client.get(f"/api/exports/seasons/{season.id}/teams.csv", headers=auth_headers)
        assert resp.status_code == 200
        assert team.name in resp.text

    @pytest.mark.asyncio
    async def test_ranking_csv(self, client, auth_headers, season):
        resp = await client.get(
            f"/api/exports/seasons/{season.id}/ranking.csv", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "Rang" in resp.text

    @pytest.mark.asyncio
    async def test_matches_csv(self, client, auth_headers, season):
        resp = await client.get(
            f"/api/exports/seasons/{season.id}/matches.csv", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "Match-ID" in resp.text

    @pytest.mark.asyncio
    async def test_papers_csv(self, client, auth_headers, season):
        resp = await client.get(
            f"/api/exports/seasons/{season.id}/papers.csv", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "Titel" in resp.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["teams", "ranking", "papers", "printing"])
    async def test_pdf_exports(self, client, auth_headers, season, kind):
        resp = await client.get(
            f"/api/exports/seasons/{season.id}/{kind}.pdf", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.content[:4] == b"%PDF"

    @pytest.mark.asyncio
    async def test_export_unknown_season_returns_404(self, client, auth_headers):
        resp = await client.get(
            "/api/exports/seasons/missing/teams.csv", headers=auth_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_export_requires_auth(self, client, season):
        resp = await client.get(f"/api/exports/seasons/{season.id}/teams.csv")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_export_requires_permission_for_non_superuser(self, client, db, season):
        user = await _make_user(db, "exportnoperm@example.com")
        resp = await client.get(
            f"/api/exports/seasons/{season.id}/teams.csv", headers=_headers(user)
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_export_allowed_with_teams_read_permission(self, client, db, season):
        user = await _make_user(db, "exportperm@example.com")
        await _grant(db, user, "teams:read")
        resp = await client.get(
            f"/api/exports/seasons/{season.id}/teams.csv", headers=_headers(user)
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_ranking_csv_allowed_with_any_of_two_permissions(self, client, db, season):
        # require_any_permission("scoring:read", "dashboard:read") — having just one suffices.
        user = await _make_user(db, "anyperm@example.com")
        await _grant(db, user, "dashboard:read")
        resp = await client.get(
            f"/api/exports/seasons/{season.id}/ranking.csv", headers=_headers(user)
        )
        assert resp.status_code == 200
