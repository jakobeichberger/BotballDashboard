"""Additional integration tests for the scoring match + ranking API.

These complement (do not duplicate) tests/integration/test_scoring_routes.py.
Routes are mounted under the /api prefix.
"""

import pytest
import pytest_asyncio

from core.auth import create_access_token

# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def scoring_schema(db, season):
    """An active scoring schema for the season so totals are deterministic."""
    from modules.scoring.models import ScoringSchema

    s = ScoringSchema(
        season_id=season.id,
        fields=[
            {"key": "task_a", "multiplier": 2},
            {"key": "task_b", "multiplier": 5},
        ],
        version=1,
        is_active=True,
    )
    db.add(s)
    await db.commit()
    return s


@pytest_asyncio.fixture
async def second_team(db):
    from modules.teams.models import Team

    t = Team(name="Test Team Beta", team_number="TTB-02", country="AT")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


@pytest_asyncio.fixture
async def limited_user(db):
    """A regular (non-superuser) user with no roles/permissions."""
    from modules.auth.models import User
    from modules.auth.service import hash_password

    u = User(
        email="limited@test.com",
        display_name="Limited",
        hashed_password=hash_password("pw"),
        is_active=True,
        is_superuser=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def limited_headers(limited_user):
    return {"Authorization": f"Bearer {create_access_token(limited_user.id)}"}


# ── creation + totals ────────────────────────────────────────────────────────


class TestCreateMatchRoute:
    @pytest.mark.asyncio
    async def test_total_computed_from_schema(
        self, client, auth_headers, season, team, scoring_schema
    ):
        resp = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={
                "team_id": team.id,
                "round_number": 1,
                "raw_scores": {"task_a": 10, "task_b": 4},
            },  # 10*2 + 4*5 = 40
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["total_score"] == 40.0
        assert data["season_id"] == season.id
        assert data["entered_by"] is not None
        assert data["confirmed_by"] is None

    @pytest.mark.asyncio
    async def test_body_season_id_overridden_by_path(self, client, auth_headers, season, team):
        # season_id in body should be ignored in favour of the URL path.
        resp = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={
                "season_id": "bogus-season",
                "team_id": team.id,
                "round_number": 1,
                "raw_scores": {},
            },
        )
        assert resp.status_code == 201
        assert resp.json()["season_id"] == season.id

    @pytest.mark.asyncio
    async def test_create_forbidden_without_permission(self, client, limited_headers, season, team):
        resp = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=limited_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {}},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_missing_team_id_422(self, client, auth_headers, season):
        resp = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"round_number": 1, "raw_scores": {}},
        )
        assert resp.status_code == 422


# ── bulk creation ────────────────────────────────────────────────────────────


class TestBulkCreate:
    @pytest.mark.asyncio
    async def test_bulk_creates_multiple_matches(
        self, client, auth_headers, season, team, second_team, scoring_schema
    ):
        resp = await client.post(
            f"/api/scoring/seasons/{season.id}/matches/bulk",
            headers=auth_headers,
            json={
                "entries": [
                    {
                        "team_id": team.id,
                        "round_number": 1,
                        "raw_scores": {"task_a": 5, "task_b": 2},
                    },  # 10+10=20
                    {
                        "team_id": second_team.id,
                        "round_number": 1,
                        "raw_scores": {"task_a": 1, "task_b": 1},
                    },  # 2+5=7
                ]
            },
        )
        assert resp.status_code == 201
        rows = resp.json()
        assert len(rows) == 2
        totals = {r["team_id"]: r["total_score"] for r in rows}
        assert totals[team.id] == 20.0
        assert totals[second_team.id] == 7.0

    @pytest.mark.asyncio
    async def test_bulk_updates_ranking(
        self, client, db, auth_headers, season, team, second_team, scoring_schema
    ):
        await client.post(
            f"/api/scoring/seasons/{season.id}/matches/bulk",
            headers=auth_headers,
            json={
                "entries": [
                    {
                        "team_id": team.id,
                        "round_number": 1,
                        "raw_scores": {"task_a": 50, "task_b": 0},
                    },  # 100
                    {
                        "team_id": second_team.id,
                        "round_number": 1,
                        "raw_scores": {"task_a": 10, "task_b": 0},
                    },  # 20
                ]
            },
        )
        # Flush pending rank updates to the DB (the test client shares this
        # session and does not commit per-request).
        await db.commit()
        resp = await client.get(f"/api/scoring/seasons/{season.id}/ranking")
        ranking = resp.json()
        assert len(ranking) == 2
        # Higher seed first.
        assert ranking[0]["team_id"] == team.id
        assert ranking[0]["rank"] == 1
        assert ranking[1]["team_id"] == second_team.id
        assert ranking[1]["rank"] == 2

    @pytest.mark.asyncio
    async def test_bulk_empty_entries(self, client, auth_headers, season):
        resp = await client.post(
            f"/api/scoring/seasons/{season.id}/matches/bulk",
            headers=auth_headers,
            json={"entries": []},
        )
        assert resp.status_code == 201
        assert resp.json() == []


# ── get / list ───────────────────────────────────────────────────────────────


class TestGetAndListRoutes:
    @pytest.mark.asyncio
    async def test_get_match_by_id(self, client, auth_headers, season, team):
        created = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {}},
        )
        match_id = created.json()["id"]
        resp = await client.get(f"/api/scoring/matches/{match_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == match_id

    @pytest.mark.asyncio
    async def test_get_match_404(self, client, auth_headers):
        resp = await client.get("/api/scoring/matches/nonexistent", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_filtered_by_team(self, client, auth_headers, season, team, second_team):
        await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {}},
        )
        await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": second_team.id, "round_number": 1, "raw_scores": {}},
        )
        resp = await client.get(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            params={"team_id": team.id},
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["team_id"] == team.id


# ── update / patch ───────────────────────────────────────────────────────────


class TestUpdateRoute:
    @pytest.mark.asyncio
    async def test_patch_raw_scores_recomputes_total(
        self, client, auth_headers, season, team, scoring_schema
    ):
        created = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={
                "team_id": team.id,
                "round_number": 1,
                "raw_scores": {"task_a": 1, "task_b": 0},
            },  # total 2
        )
        match_id = created.json()["id"]
        assert created.json()["total_score"] == 2.0

        resp = await client.patch(
            f"/api/scoring/matches/{match_id}",
            headers=auth_headers,
            json={"raw_scores": {"task_a": 10, "task_b": 2}},  # 20 + 10 = 30
        )
        assert resp.status_code == 200
        assert resp.json()["total_score"] == 30.0

    @pytest.mark.asyncio
    async def test_patch_recomputes_ranking(
        self, client, auth_headers, season, team, scoring_schema
    ):
        created = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {"task_a": 1, "task_b": 0}},
        )
        match_id = created.json()["id"]
        await client.patch(
            f"/api/scoring/matches/{match_id}",
            headers=auth_headers,
            json={"raw_scores": {"task_a": 50, "task_b": 0}},  # 100
        )
        resp = await client.get(f"/api/scoring/seasons/{season.id}/ranking")
        ranking = resp.json()
        assert ranking[0]["best_score"] == 100.0
        assert ranking[0]["seed_score"] == 100.0

    @pytest.mark.asyncio
    async def test_patch_missing_match_404(self, client, auth_headers):
        resp = await client.patch(
            "/api/scoring/matches/ghost", headers=auth_headers, json={"notes": "x"}
        )
        assert resp.status_code == 404


# ── confirm ──────────────────────────────────────────────────────────────────


class TestConfirmRoute:
    @pytest.mark.asyncio
    async def test_confirm_sets_confirmed_by(self, client, auth_headers, admin_user, season, team):
        created = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {}},
        )
        match_id = created.json()["id"]
        resp = await client.put(f"/api/scoring/matches/{match_id}/confirm", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["confirmed_by"] == admin_user.id
        assert body["confirmed_at"] is not None

    @pytest.mark.asyncio
    async def test_confirm_requires_admin_permission(
        self, client, limited_headers, auth_headers, season, team
    ):
        created = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {}},
        )
        match_id = created.json()["id"]
        resp = await client.put(f"/api/scoring/matches/{match_id}/confirm", headers=limited_headers)
        assert resp.status_code == 403


# ── delete ───────────────────────────────────────────────────────────────────


class TestDeleteRoute:
    @pytest.mark.asyncio
    async def test_delete_removes_match_and_ranking(self, client, auth_headers, season, team):
        created = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {"x": 10}},
        )
        match_id = created.json()["id"]
        # Ranking exists before delete.
        before = await client.get(f"/api/scoring/seasons/{season.id}/ranking")
        assert len(before.json()) == 1

        resp = await client.delete(f"/api/scoring/matches/{match_id}", headers=auth_headers)
        assert resp.status_code == 204

        # Match gone (404) and ranking removed.
        gone = await client.get(f"/api/scoring/matches/{match_id}", headers=auth_headers)
        assert gone.status_code == 404
        after = await client.get(f"/api/scoring/seasons/{season.id}/ranking")
        assert after.json() == []

    @pytest.mark.asyncio
    async def test_delete_requires_admin_permission(
        self, client, limited_headers, auth_headers, season, team
    ):
        created = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {}},
        )
        match_id = created.json()["id"]
        resp = await client.delete(f"/api/scoring/matches/{match_id}", headers=limited_headers)
        assert resp.status_code == 403


# ── ranking endpoints ────────────────────────────────────────────────────────


class TestRankingRoutes:
    @pytest.mark.asyncio
    async def test_ranking_public_no_auth(self, client, season):
        resp = await client.get(f"/api/scoring/seasons/{season.id}/ranking")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_ranking_orders_teams(
        self, client, db, auth_headers, season, team, second_team, scoring_schema
    ):
        # team total 100, second_team total 10
        await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {"task_a": 50, "task_b": 0}},
        )
        await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={
                "team_id": second_team.id,
                "round_number": 1,
                "raw_scores": {"task_a": 5, "task_b": 0},
            },
        )
        await db.commit()
        resp = await client.get(f"/api/scoring/seasons/{season.id}/ranking")
        ranking = resp.json()
        assert [r["team_id"] for r in ranking] == [team.id, second_team.id]
        assert [r["rank"] for r in ranking] == [1, 2]

    @pytest.mark.asyncio
    async def test_ranking_extended_includes_team_name(
        self, client, db, auth_headers, season, team, scoring_schema
    ):
        await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {"task_a": 10, "task_b": 0}},
        )
        await db.commit()
        resp = await client.get(f"/api/scoring/seasons/{season.id}/ranking/extended")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["team_name"] == team.name
        assert rows[0]["category"] == "botball"  # default when no registration
        assert rows[0]["rank"] == 1

    @pytest.mark.asyncio
    async def test_ranking_extended_category_filter_excludes(
        self, client, db, auth_headers, season, team, scoring_schema
    ):
        await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {"task_a": 10, "task_b": 0}},
        )
        await db.commit()
        # team has default category "botball"; filtering by "open" yields nothing.
        resp = await client.get(
            f"/api/scoring/seasons/{season.id}/ranking/extended",
            params={"category": "open"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_ranking_overall_returns_entries(
        self, client, db, auth_headers, season, team, scoring_schema
    ):
        # Overall ranking only includes teams registered for the season.
        from modules.teams.models import TeamSeasonRegistration

        db.add(
            TeamSeasonRegistration(
                team_id=team.id,
                season_id=season.id,
                category="botball",
                confirmed=True,
            )
        )
        await db.commit()

        await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "round_number": 1, "raw_scores": {"task_a": 10, "task_b": 0}},
        )
        await db.commit()
        resp = await client.get(f"/api/scoring/seasons/{season.id}/ranking/overall")
        assert resp.status_code == 200
        rows = resp.json()
        assert isinstance(rows, list)
        assert any(r["team_id"] == team.id for r in rows)
