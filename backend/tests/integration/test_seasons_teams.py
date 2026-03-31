"""Integration tests for Seasons and Teams API routes."""
import pytest


class TestSeasonsAPI:
    @pytest.mark.asyncio
    async def test_create_season(self, client, auth_headers):
        resp = await client.post("/api/seasons", headers=auth_headers, json={
            "name": "Botball 2026",
            "year": 2026,
            "game_theme": "Warehouse Havoc",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Botball 2026"
        assert data["year"] == 2026

    @pytest.mark.asyncio
    async def test_list_seasons(self, client, auth_headers):
        resp = await client.get("/api/seasons", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_activate_season(self, client, auth_headers):
        create_resp = await client.post("/api/seasons", headers=auth_headers, json={
            "name": "Season A", "year": 2025,
        })
        season_id = create_resp.json()["id"]

        activate_resp = await client.put(
            f"/api/seasons/{season_id}/activate", headers=auth_headers
        )
        assert activate_resp.status_code == 200
        assert activate_resp.json()["is_active"] is True

    @pytest.mark.asyncio
    async def test_get_active_season(self, client, auth_headers):
        resp = await client.get("/api/seasons/active", headers=auth_headers)
        assert resp.status_code == 200  # may be null body

    @pytest.mark.asyncio
    async def test_delete_inactive_season(self, client, auth_headers):
        create_resp = await client.post("/api/seasons", headers=auth_headers, json={
            "name": "Delete Me", "year": 2020,
        })
        season_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/seasons/{season_id}", headers=auth_headers)
        assert del_resp.status_code == 204

    @pytest.mark.asyncio
    async def test_seasons_requires_auth(self, client):
        resp = await client.get("/api/seasons")
        assert resp.status_code == 401


class TestTeamsAPI:
    @pytest.mark.asyncio
    async def test_create_team(self, client, auth_headers):
        resp = await client.post("/api/teams", headers=auth_headers, json={
            "name": "RoboKids Graz",
            "team_number": "GZ-01",
            "school": "HTL Graz",
            "city": "Graz",
            "country": "AT",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "RoboKids Graz"
        assert data["team_number"] == "GZ-01"

    @pytest.mark.asyncio
    async def test_list_teams(self, client, auth_headers):
        resp = await client.get("/api/teams", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_update_team(self, client, auth_headers):
        create_resp = await client.post("/api/teams", headers=auth_headers, json={
            "name": "Old Name", "country": "DE",
        })
        team_id = create_resp.json()["id"]

        update_resp = await client.patch(
            f"/api/teams/{team_id}",
            headers=auth_headers,
            json={"name": "New Name"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_season_registration(self, client, auth_headers):
        # Create season + team
        season_resp = await client.post("/api/seasons", headers=auth_headers, json={
            "name": "Reg Season", "year": 2026,
        })
        team_resp = await client.post("/api/teams", headers=auth_headers, json={
            "name": "Reg Team", "country": "DE",
        })
        season_id = season_resp.json()["id"]
        team_id = team_resp.json()["id"]

        reg_resp = await client.post("/api/teams/registrations", headers=auth_headers, json={
            "team_id": team_id,
            "season_id": season_id,
        })
        assert reg_resp.status_code == 201
        assert reg_resp.json()["confirmed"] is False
