"""Integration tests for authentication API routes."""
import pytest
from modules.auth.service import create_user


class TestLoginLogout:
    @pytest.mark.asyncio
    async def test_login_returns_access_token(self, client, db):
        await create_user(db, "user@test.com", "Test User", "password123", [])
        await db.commit()

        resp = await client.post("/api/auth/login", json={
            "email": "user@test.com",
            "password": "password123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "refresh_token" not in data  # cookie, not body

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(self, client, db):
        await create_user(db, "user2@test.com", "Test User", "correct", [])
        await db.commit()

        resp = await client.post("/api/auth/login", json={
            "email": "user2@test.com",
            "password": "wrong",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_returns_204(self, client, db, admin_token):
        resp = await client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_me_returns_current_user(self, client, auth_headers, admin_user):
        resp = await client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == admin_user.email
        assert data["is_superuser"] is True

    @pytest.mark.asyncio
    async def test_me_without_token_returns_401(self, client):
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401


class TestUserManagement:
    @pytest.mark.asyncio
    async def test_list_users_requires_auth(self, client):
        resp = await client.get("/api/auth/users")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_users_as_admin(self, client, auth_headers, admin_user):
        resp = await client.get("/api/auth/users", headers=auth_headers)
        assert resp.status_code == 200
        users = resp.json()
        assert isinstance(users, list)
        assert any(u["email"] == admin_user.email for u in users)

    @pytest.mark.asyncio
    async def test_create_user_as_admin(self, client, auth_headers):
        resp = await client.post("/api/auth/users", headers=auth_headers, json={
            "email": "newuser@test.com",
            "display_name": "New User",
            "password": "newpassword",
            "role_ids": [],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "newuser@test.com"

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email_returns_409(self, client, auth_headers, admin_user):
        resp = await client.post("/api/auth/users", headers=auth_headers, json={
            "email": admin_user.email,
            "display_name": "Dupe",
            "password": "pass",
        })
        assert resp.status_code == 409


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        resp = await client.get("/api/system/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
