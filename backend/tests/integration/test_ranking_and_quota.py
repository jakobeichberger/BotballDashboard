"""Regression tests for two bugs found in the branch review:

  - _refresh_ranks skipped its filter when the level was NULL, so a level's
    1..n and the season-wide 1..n overwrote each other and teams could share a
    rank (order depending on which match was entered last).
  - deleting a team's last match removed its ranking row but left a hole in the
    numbering (…1, 2, 4).
  - team_season_print_quotas had no unique constraint, so check-then-insert
    could produce duplicate rows and permanently break reads.
"""
import pytest

from modules.scoring.models import ScoringSchema
from modules.seasons.models import CompetitionLevel
from modules.teams.models import Team


@pytest.fixture
async def schema(db, season):
    db.add(ScoringSchema(season_id=season.id, fields=[{"key": "pts", "multiplier": 1}], is_active=True))
    await db.commit()


async def _team(db, name):
    t = Team(name=name, country="DE")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def _level(db, name, code):
    lvl = CompetitionLevel(name=name, code=code)
    db.add(lvl)
    await db.commit()
    await db.refresh(lvl)
    return lvl


class TestRanksArePerCompetitionLevel:
    @pytest.mark.asyncio
    async def test_levels_are_ranked_independently_and_uniquely(
        self, client, auth_headers, db, season, schema
    ):
        junior = await _level(db, "Junior", "JR2")
        a = await _team(db, "NoLevel A")
        b = await _team(db, "NoLevel B")
        c = await _team(db, "Junior C")
        d = await _team(db, "Junior D")

        async def score(team, pts, level_id=None):
            r = await client.post(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers,
                                  json={"team_id": team.id, "round_number": 1,
                                        "competition_level_id": level_id, "raw_scores": {"pts": pts}})
            assert r.status_code == 201

        await score(a, 90)
        await score(b, 50)
        await score(c, 80, junior.id)
        await score(d, 70, junior.id)
        await db.commit()

        rows = (await client.get(f"/api/scoring/seasons/{season.id}/ranking", headers=auth_headers)).json()
        by_team = {r["team_id"]: r for r in rows}

        # Teams without a level form their own group, ranked 1..n by seed.
        assert by_team[a.id]["rank"] == 1
        assert by_team[b.id]["rank"] == 2
        # The junior level is numbered independently — and consistently.
        assert by_team[c.id]["rank"] == 1
        assert by_team[d.id]["rank"] == 2

        # Within a level ranks must be unique (the bug produced collisions there).
        junior_rows = (await client.get(
            f"/api/scoring/seasons/{season.id}/ranking?competition_level_id={junior.id}",
            headers=auth_headers)).json()
        junior_ranks = [r["rank"] for r in junior_rows]
        assert sorted(junior_ranks) == [1, 2]
        assert len(set(junior_ranks)) == len(junior_ranks)

    @pytest.mark.asyncio
    async def test_a_teams_rank_ignores_teams_in_other_levels(
        self, client, auth_headers, db, season, schema
    ):
        """Order matters: the level team is scored FIRST, then the level-less one.

        The old code skipped the filter for a NULL level, so this second
        recompute renumbered *every* row in the season by score — pushing the
        level-less team to rank 2 behind a junior team it never competed with.
        """
        junior = await _level(db, "Junior", "JR3")
        c = await _team(db, "Junior HighScorer")
        await client.post(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers,
                          json={"team_id": c.id, "round_number": 1,
                                "competition_level_id": junior.id, "raw_scores": {"pts": 99}})
        await db.commit()

        a = await _team(db, "Solo NoLevel")
        await client.post(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers,
                          json={"team_id": a.id, "round_number": 1, "raw_scores": {"pts": 10}})
        await db.commit()

        rows = (await client.get(f"/api/scoring/seasons/{season.id}/ranking", headers=auth_headers)).json()
        by_team = {r["team_id"]: r["rank"] for r in rows}
        assert by_team[a.id] == 1, "a higher-scoring team in another level must not push this one down"
        assert by_team[c.id] == 1


class TestRankGapClosed:
    @pytest.mark.asyncio
    async def test_deleting_a_teams_last_match_renumbers_the_rest(
        self, client, auth_headers, db, season, schema
    ):
        a = await _team(db, "Keeps")
        b = await _team(db, "Leaves")
        c = await _team(db, "Trails")
        created = {}
        for team, pts in ((a, 100), (b, 50), (c, 10)):
            r = await client.post(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers,
                                  json={"team_id": team.id, "round_number": 1, "raw_scores": {"pts": pts}})
            created[team.id] = r.json()["id"]
        await db.commit()

        # b (rank 2) drops out entirely -> c must move up from 3 to 2.
        d = await client.delete(f"/api/scoring/matches/{created[b.id]}", headers=auth_headers)
        assert d.status_code == 204
        await db.commit()

        rows = (await client.get(f"/api/scoring/seasons/{season.id}/ranking", headers=auth_headers)).json()
        by_team = {r["team_id"]: r["rank"] for r in rows}
        assert b.id not in by_team
        assert by_team[a.id] == 1
        assert by_team[c.id] == 2, "rank numbering must not keep a hole"


class TestQuotaIsUniquePerTeamSeason:
    @pytest.mark.asyncio
    async def test_repeated_reads_reuse_one_row(self, client, auth_headers, db, season, team):
        first = await client.get(f"/api/printing/quotas?team_id={team.id}&season_id={season.id}",
                                 headers=auth_headers)
        await db.commit()
        second = await client.get(f"/api/printing/quotas?team_id={team.id}&season_id={season.id}",
                                  headers=auth_headers)
        assert first.status_code == second.status_code == 200
        assert first.json()["id"] == second.json()["id"]

    @pytest.mark.asyncio
    async def test_model_declares_the_unique_constraint(self):
        from sqlalchemy import UniqueConstraint

        from modules.printing.models import TeamSeasonPrintQuota

        uniques = [
            tuple(c.name for c in con.columns)
            for con in TeamSeasonPrintQuota.__table__.constraints
            if isinstance(con, UniqueConstraint)
        ]
        assert ("team_id", "season_id") in uniques
