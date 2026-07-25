"""Regression tests for create endpoints.

Each test here covers a bug where a service `db.add()`ed a row and returned it
without flushing, so FastAPI serialized the object while `id` and the
Python/server-side defaults were still None and the response 500'd with a
ResponseValidationError.
"""

import pytest


class TestPaperCreate:
    @pytest.mark.asyncio
    async def test_create_paper_returns_201(self, client, auth_headers, season, team):
        resp = await client.post(
            "/api/papers",
            headers=auth_headers,
            json={"season_id": season.id, "team_id": team.id, "title": "Vision Paper"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"]
        assert body["status"] == "draft"
        assert body["created_at"] is not None


class TestPrintingCreate:
    @pytest.mark.asyncio
    async def test_create_printer_returns_201(self, client, auth_headers):
        resp = await client.post(
            "/api/printing/printers",
            headers=auth_headers,
            json={"name": "Bambu X1C", "printer_type": "bambu"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"]
        assert body["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_print_job_returns_201(self, client, auth_headers, season, team):
        resp = await client.post(
            "/api/printing/jobs",
            headers=auth_headers,
            json={
                "team_id": team.id,
                "season_id": season.id,
                "file_name": "bracket.3mf",
                "material": "PLA",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"]
        assert body["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_spool_returns_201(self, client, auth_headers):
        resp = await client.post(
            "/api/printing/spools",
            headers=auth_headers,
            json={"material": "PETG", "initial_grams": 750.0},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"]
        assert body["remaining_grams"] == 750.0


class TestTeamMemberCreate:
    @pytest.mark.asyncio
    async def test_add_member_returns_201(self, client, auth_headers, team):
        resp = await client.post(
            f"/api/teams/{team.id}/members",
            headers=auth_headers,
            json={"name": "Ada Lovelace", "role": "member"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["id"]


class TestRoleCreate:
    @pytest.mark.asyncio
    async def test_create_role_without_permissions(self, client, auth_headers):
        """Serializing role.permissions used to trigger a lazy load in async context."""
        resp = await client.post(
            "/api/auth/roles",
            headers=auth_headers,
            json={"name": "observer", "description": "read only"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"]
        assert body["permissions"] == []

    @pytest.mark.asyncio
    async def test_create_role_with_permissions(self, client, auth_headers, db):
        from modules.auth.models import Permission

        db.add(Permission(name="teams:read", description="read teams"))
        await db.flush()

        resp = await client.post(
            "/api/auth/roles",
            headers=auth_headers,
            json={"name": "viewer", "permission_names": ["teams:read"]},
        )
        assert resp.status_code == 201, resp.text
        assert [p["name"] for p in resp.json()["permissions"]] == ["teams:read"]


class TestUserRoleAssignment:
    @pytest.mark.asyncio
    async def test_created_user_response_includes_roles(self, client, auth_headers, db):
        """UserRole rows must be flushed before refresh, or the response shows []."""
        from modules.auth.models import Role

        role = Role(name="mentor", description="team mentor")
        db.add(role)
        await db.flush()

        resp = await client.post(
            "/api/auth/users",
            headers=auth_headers,
            json={
                "email": "mentor@test.com",
                "display_name": "Mentor",
                "password": "password123",
                "role_ids": [role.id],
            },
        )
        assert resp.status_code == 201, resp.text
        assert [r["name"] for r in resp.json()["roles"]] == ["mentor"]
