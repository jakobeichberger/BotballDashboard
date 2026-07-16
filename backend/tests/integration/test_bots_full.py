"""Integration tests for the bot gallery (own + external teams).

The admin fixture is a superuser and bypasses permission checks; own-team
scoping itself is covered by tests/unit/test_team_access.py.
"""
import pytest

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class TestBotCrud:
    @pytest.mark.asyncio
    async def test_create_team_bot(self, client, auth_headers, season, team):
        r = await client.post("/api/bots", headers=auth_headers, json={
            "name": "RoboLion X1", "team_id": team.id, "season_id": season.id,
            "description": "Unser Bot", "functionality": "Differentialantrieb, Servo-Greifer",
            "drive_type": "Differential", "sensors": "2x IR",
        })
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "RoboLion X1"
        assert body["team_id"] == team.id
        assert body["external_team_name"] is None
        assert body["functionality"].startswith("Differential")

    @pytest.mark.asyncio
    async def test_create_external_bot(self, client, auth_headers, season):
        r = await client.post("/api/bots", headers=auth_headers, json={
            "name": "Zurich Crusher", "external_team_name": "Team Zurich", "season_id": season.id,
        })
        assert r.status_code == 201
        assert r.json()["team_id"] is None
        assert r.json()["external_team_name"] == "Team Zurich"

    @pytest.mark.asyncio
    async def test_owner_required(self, client, auth_headers):
        r = await client.post("/api/bots", headers=auth_headers, json={"name": "Orphan"})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_owner_exclusive(self, client, auth_headers, team):
        r = await client.post("/api/bots", headers=auth_headers, json={
            "name": "Both", "team_id": team.id, "external_team_name": "X",
        })
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_get_missing_404(self, client, auth_headers):
        r = await client.get("/api/bots/nope", headers=auth_headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_update_and_delete(self, client, auth_headers, team, db):
        c = await client.post("/api/bots", headers=auth_headers, json={"name": "Tmp", "team_id": team.id})
        bid = c.json()["id"]
        await db.commit()

        p = await client.patch(f"/api/bots/{bid}", headers=auth_headers,
                               json={"name": "Renamed", "functionality": "Neu"})
        assert p.status_code == 200
        assert p.json()["name"] == "Renamed"
        await db.commit()

        d = await client.delete(f"/api/bots/{bid}", headers=auth_headers)
        assert d.status_code == 204
        await db.commit()
        assert (await client.get(f"/api/bots/{bid}", headers=auth_headers)).status_code == 404


class TestBotFilters:
    @pytest.mark.asyncio
    async def test_filter_internal_vs_external(self, client, auth_headers, season, team, db):
        await client.post("/api/bots", headers=auth_headers, json={"name": "Mine", "team_id": team.id, "season_id": season.id})
        await client.post("/api/bots", headers=auth_headers, json={"name": "Theirs", "external_team_name": "Ext", "season_id": season.id})
        await db.commit()

        all_bots = await client.get("/api/bots", headers=auth_headers)
        assert len(all_bots.json()) == 2

        internal = await client.get("/api/bots?external=false", headers=auth_headers)
        assert [b["name"] for b in internal.json()] == ["Mine"]

        external = await client.get("/api/bots?external=true", headers=auth_headers)
        assert [b["name"] for b in external.json()] == ["Theirs"]

        by_team = await client.get(f"/api/bots?team_id={team.id}", headers=auth_headers)
        assert [b["name"] for b in by_team.json()] == ["Mine"]

        by_season = await client.get(f"/api/bots?season_id={season.id}", headers=auth_headers)
        assert len(by_season.json()) == 2


class TestBotImage:
    @pytest.mark.asyncio
    async def test_upload_valid_png(self, client, auth_headers, team, db):
        c = await client.post("/api/bots", headers=auth_headers, json={"name": "ImgBot", "team_id": team.id})
        bid = c.json()["id"]
        await db.commit()

        r = await client.post(f"/api/bots/{bid}/image", headers=auth_headers,
                              files={"file": ("bot.png", PNG, "image/png")})
        assert r.status_code == 200
        assert r.json()["image_name"] == "bot.png"

    @pytest.mark.asyncio
    async def test_upload_rejects_non_image(self, client, auth_headers, team, db):
        c = await client.post("/api/bots", headers=auth_headers, json={"name": "BadImg", "team_id": team.id})
        bid = c.json()["id"]
        await db.commit()

        r = await client.post(f"/api/bots/{bid}/image", headers=auth_headers,
                              files={"file": ("evil.exe", b"MZ not an image", "image/png")})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_image_404_when_none_uploaded(self, client, auth_headers, team, db):
        c = await client.post("/api/bots", headers=auth_headers, json={"name": "NoImg", "team_id": team.id})
        bid = c.json()["id"]
        await db.commit()
        r = await client.get(f"/api/bots/{bid}/image", headers=auth_headers)
        assert r.status_code == 404
