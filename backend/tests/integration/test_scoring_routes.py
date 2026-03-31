"""Integration tests for Scoring API routes."""
import pytest


class TestMatchCreation:
    @pytest.mark.asyncio
    async def test_create_match(self, client, auth_headers, season, team):
        resp = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={
                "team_id": team.id,
                "round_number": 1,
                "raw_scores": {"task_a": 10, "task_b": 5},
                "notes": "Clean run",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["team_id"] == team.id
        assert data["round_number"] == 1

    @pytest.mark.asyncio
    async def test_list_matches_for_season(self, client, auth_headers, season, team):
        # Create a match first
        await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {}},
        )

        resp = await client.get(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        matches = resp.json()
        assert isinstance(matches, list)
        assert len(matches) >= 1

    @pytest.mark.asyncio
    async def test_get_ranking_public(self, client, season):
        """Ranking endpoint is public (no auth required)."""
        resp = await client.get(f"/api/scoring/seasons/{season.id}/ranking")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_ranking_updates_after_match(self, client, auth_headers, season, team):
        await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {}, "total_score": 150},
        )

        resp = await client.get(f"/api/scoring/seasons/{season.id}/ranking")
        ranking = resp.json()
        assert len(ranking) >= 1
        assert any(r["team_id"] == team.id for r in ranking)

    @pytest.mark.asyncio
    async def test_match_requires_auth(self, client, season, team):
        resp = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            json={"team_id": team.id, "round_number": 1, "raw_scores": {}},
        )
        assert resp.status_code == 401


class TestMatchUpdate:
    @pytest.mark.asyncio
    async def test_update_match_notes(self, client, auth_headers, season, team):
        create_resp = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {}},
        )
        match_id = create_resp.json()["id"]

        update_resp = await client.patch(
            f"/api/scoring/matches/{match_id}",
            headers=auth_headers,
            json={"notes": "Updated note"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["notes"] == "Updated note"

    @pytest.mark.asyncio
    async def test_delete_match(self, client, auth_headers, season, team):
        create_resp = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {}},
        )
        match_id = create_resp.json()["id"]

        del_resp = await client.delete(
            f"/api/scoring/matches/{match_id}",
            headers=auth_headers,
        )
        assert del_resp.status_code == 204
