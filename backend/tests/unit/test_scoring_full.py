"""Additional unit tests for the core scoring service.

Covers compute_match_total edge cases plus the full service layer:
create/get/list/update/delete/confirm match and ranking computation.
These complement (do not duplicate) tests/unit/test_scoring.py.
"""
import pytest

from modules.scoring.models import Match, Ranking, ScoringSchema
from modules.scoring.service import (
    compute_match_total,
    compute_seed_score,
    create_match,
    get_match,
    list_matches,
    update_match,
    delete_match,
    confirm_match,
    get_ranking,
    get_active_schema,
    _recompute_ranking,
    _refresh_ranks,
)
from core.exceptions import NotFoundError


# ── helpers ─────────────────────────────────────────────────────────────────

async def _make_team(db, name="Team X", country="DE"):
    from modules.teams.models import Team
    t = Team(name=name, country=country)
    db.add(t)
    await db.flush()
    return t


async def _make_schema(db, season_id, fields, version=1, is_active=True, level_id=None):
    s = ScoringSchema(
        season_id=season_id,
        competition_level_id=level_id,
        fields=fields,
        version=version,
        is_active=is_active,
    )
    db.add(s)
    await db.flush()
    return s


# ── compute_match_total edge cases (not covered by test_scoring.py) ──────────

class TestComputeMatchTotalEdge:
    def test_negative_value_with_multiplier(self):
        schema = [{"key": "penalty", "multiplier": 5}]
        assert compute_match_total({"penalty": -3}, schema) == -15.0

    def test_missing_multiplier_key_defaults_to_one(self):
        # field present in schema but has no "multiplier" key
        schema = [{"key": "a"}]
        assert compute_match_total({"a": 7}, schema) == 7.0

    def test_string_numeric_value_is_coerced(self):
        schema = [{"key": "a", "multiplier": 2}]
        assert compute_match_total({"a": "10"}, schema) == 20.0

    def test_rounding_half_even_behaviour(self):
        # 0.1 * 3 = 0.30000000000000004 → rounds to 0.3
        schema = [{"key": "a", "multiplier": 0.1}]
        assert compute_match_total({"a": 3}, schema) == 0.3

    def test_rounding_to_two_decimals_value(self):
        schema = [{"key": "a", "multiplier": 1}]
        # 1.005 famously stored as 1.00499...; round() yields 1.0 here
        assert compute_match_total({"a": 1.005}, schema) == 1.0

    def test_large_numbers(self):
        schema = [{"key": "a", "multiplier": 1000}]
        assert compute_match_total({"a": 1234}, schema) == 1234000.0

    def test_empty_schema_all_fields_default_multiplier(self):
        scores = {"a": 2, "b": 3}
        assert compute_match_total(scores, []) == 5.0


class TestComputeSeedScoreEdge:
    def test_two_negative_scores(self):
        assert compute_seed_score([-10.0, -20.0]) == -15.0

    def test_unsorted_input_picks_top_two(self):
        assert compute_seed_score([1.0, 50.0, 49.0, 2.0]) == 49.5


# ── get_active_schema ────────────────────────────────────────────────────────

class TestGetActiveSchema:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_schema(self, db, season):
        assert await get_active_schema(db, season.id) is None

    @pytest.mark.asyncio
    async def test_returns_active_over_inactive(self, db, season):
        # Only one schema may be active at a time (scalar_one_or_none); the
        # active one is returned regardless of the inactive older version.
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 1}],
                           version=1, is_active=False)
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 2}],
                           version=2, is_active=True)
        schema = await get_active_schema(db, season.id)
        assert schema is not None
        assert schema.version == 2
        assert schema.is_active is True

    @pytest.mark.asyncio
    async def test_ignores_inactive_schema(self, db, season):
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 9}],
                           version=5, is_active=False)
        assert await get_active_schema(db, season.id) is None


# ── create_match ─────────────────────────────────────────────────────────────

class TestCreateMatch:
    @pytest.mark.asyncio
    async def test_total_computed_from_schema(self, db, season, team):
        await _make_schema(db, season.id, [
            {"key": "a", "multiplier": 2},
            {"key": "b", "multiplier": 10},
        ])
        data = {
            "season_id": season.id,
            "team_id": team.id,
            "round_number": 1,
            "raw_scores": {"a": 5, "b": 3},  # 5*2 + 3*10 = 40
        }
        match = await create_match(db, data, entered_by="user-1")
        assert match.total_score == 40.0
        assert match.entered_by == "user-1"
        assert match.id is not None

    @pytest.mark.asyncio
    async def test_total_zero_without_schema(self, db, season, team):
        data = {
            "season_id": season.id,
            "team_id": team.id,
            "round_number": 1,
            "raw_scores": {"a": 5, "b": 3},  # no schema → default mult 1 → 8
        }
        match = await create_match(db, data, entered_by="user-1")
        # No schema means every field defaults to multiplier 1
        assert match.total_score == 8.0

    @pytest.mark.asyncio
    async def test_creation_inserts_ranking_row(self, db, season, team):
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 1}])
        data = {
            "season_id": season.id, "team_id": team.id,
            "round_number": 1, "raw_scores": {"a": 50},
        }
        await create_match(db, data, entered_by="u")
        await db.commit()

        ranking = await get_ranking(db, season.id)
        assert len(ranking) == 1
        assert ranking[0].team_id == team.id
        assert ranking[0].rank == 1
        assert ranking[0].seed_score == 50.0
        assert ranking[0].best_score == 50.0
        assert ranking[0].average_score == 50.0
        assert ranking[0].rounds_played == 1

    @pytest.mark.asyncio
    async def test_multiple_matches_same_team_aggregate(self, db, season, team):
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 1}])
        for v in (90, 80, 70):
            await create_match(db, {
                "season_id": season.id, "team_id": team.id,
                "round_number": 1, "raw_scores": {"a": v},
            }, entered_by="u")
        await db.commit()

        ranking = await get_ranking(db, season.id)
        assert len(ranking) == 1
        r = ranking[0]
        assert r.rounds_played == 3
        assert r.best_score == 90.0
        assert r.seed_score == 85.0  # avg(90, 80)
        assert r.average_score == pytest.approx((90 + 80 + 70) / 3)


# ── get / list ───────────────────────────────────────────────────────────────

class TestGetAndList:
    @pytest.mark.asyncio
    async def test_get_match_returns_match(self, db, season, team):
        m = await create_match(db, {
            "season_id": season.id, "team_id": team.id,
            "round_number": 1, "raw_scores": {},
        }, entered_by="u")
        fetched = await get_match(db, m.id)
        assert fetched.id == m.id

    @pytest.mark.asyncio
    async def test_get_match_missing_raises(self, db):
        with pytest.raises(NotFoundError):
            await get_match(db, "does-not-exist")

    @pytest.mark.asyncio
    async def test_list_filters_by_team(self, db, season):
        t1 = await _make_team(db, "T1")
        t2 = await _make_team(db, "T2")
        await create_match(db, {"season_id": season.id, "team_id": t1.id,
                                "round_number": 1, "raw_scores": {}}, "u")
        await create_match(db, {"season_id": season.id, "team_id": t2.id,
                                "round_number": 1, "raw_scores": {}}, "u")
        only_t1 = await list_matches(db, season.id, team_id=t1.id)
        assert len(only_t1) == 1
        assert only_t1[0].team_id == t1.id

    @pytest.mark.asyncio
    async def test_list_ordered_by_round(self, db, season, team):
        await create_match(db, {"season_id": season.id, "team_id": team.id,
                                "round_number": 3, "raw_scores": {}}, "u")
        await create_match(db, {"season_id": season.id, "team_id": team.id,
                                "round_number": 1, "raw_scores": {}}, "u")
        matches = await list_matches(db, season.id)
        assert [m.round_number for m in matches] == [1, 3]

    @pytest.mark.asyncio
    async def test_list_empty_for_other_season(self, db, season, team):
        await create_match(db, {"season_id": season.id, "team_id": team.id,
                                "round_number": 1, "raw_scores": {}}, "u")
        assert await list_matches(db, "other-season") == []


# ── update_match ─────────────────────────────────────────────────────────────

class TestUpdateMatch:
    @pytest.mark.asyncio
    async def test_update_raw_scores_recomputes_total(self, db, season, team):
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 3}])
        m = await create_match(db, {
            "season_id": season.id, "team_id": team.id,
            "round_number": 1, "raw_scores": {"a": 1},  # total 3
        }, "u")
        assert m.total_score == 3.0

        updated = await update_match(db, m.id, raw_scores={"a": 10})  # total 30
        assert updated.total_score == 30.0

    @pytest.mark.asyncio
    async def test_update_total_propagates_to_ranking(self, db, season, team):
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 1}])
        m = await create_match(db, {
            "season_id": season.id, "team_id": team.id,
            "round_number": 1, "raw_scores": {"a": 10},
        }, "u")
        await update_match(db, m.id, raw_scores={"a": 99})
        await db.commit()

        ranking = await get_ranking(db, season.id)
        assert ranking[0].best_score == 99.0
        assert ranking[0].seed_score == 99.0

    @pytest.mark.asyncio
    async def test_update_notes_only_keeps_total(self, db, season, team):
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 2}])
        m = await create_match(db, {
            "season_id": season.id, "team_id": team.id,
            "round_number": 1, "raw_scores": {"a": 4},  # total 8
        }, "u")
        updated = await update_match(db, m.id, notes="hello")
        assert updated.notes == "hello"
        assert updated.total_score == 8.0

    @pytest.mark.asyncio
    async def test_disqualify_drops_from_seed_aggregate(self, db, season, team):
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 1}])
        m1 = await create_match(db, {"season_id": season.id, "team_id": team.id,
                                     "round_number": 1, "raw_scores": {"a": 100}}, "u")
        await create_match(db, {"season_id": season.id, "team_id": team.id,
                                "round_number": 2, "raw_scores": {"a": 40}}, "u")
        # Disqualify the high-scoring match and flush so the recompute SELECT
        # observes the change, then recompute the ranking aggregate.
        m1.is_disqualified = True
        await db.flush()
        await _recompute_ranking(db, season.id, team.id, None)
        await db.commit()

        ranking = await get_ranking(db, season.id)
        assert ranking[0].rounds_played == 1
        assert ranking[0].best_score == 40.0

    @pytest.mark.asyncio
    async def test_update_missing_match_raises(self, db):
        with pytest.raises(NotFoundError):
            await update_match(db, "nope", notes="x")


# ── confirm_match ────────────────────────────────────────────────────────────

class TestConfirmMatch:
    @pytest.mark.asyncio
    async def test_confirm_sets_confirmed_fields(self, db, season, team):
        m = await create_match(db, {"season_id": season.id, "team_id": team.id,
                                    "round_number": 1, "raw_scores": {}}, "u")
        assert m.confirmed_by is None
        assert m.confirmed_at is None

        confirmed = await confirm_match(db, m.id, confirmed_by="admin-7")
        assert confirmed.confirmed_by == "admin-7"
        assert confirmed.confirmed_at is not None

    @pytest.mark.asyncio
    async def test_confirm_missing_match_raises(self, db):
        with pytest.raises(NotFoundError):
            await confirm_match(db, "ghost", confirmed_by="x")


# ── delete_match ─────────────────────────────────────────────────────────────

class TestDeleteMatch:
    @pytest.mark.asyncio
    async def test_delete_only_match_removes_ranking(self, db, season, team):
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 1}])
        m = await create_match(db, {"season_id": season.id, "team_id": team.id,
                                    "round_number": 1, "raw_scores": {"a": 10}}, "u")
        await db.commit()
        assert len(await get_ranking(db, season.id)) == 1

        await delete_match(db, m.id)
        await db.commit()
        # No remaining matches → ranking row deleted.
        assert await get_ranking(db, season.id) == []

    @pytest.mark.asyncio
    async def test_delete_one_of_many_keeps_ranking(self, db, season, team):
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 1}])
        m1 = await create_match(db, {"season_id": season.id, "team_id": team.id,
                                     "round_number": 1, "raw_scores": {"a": 100}}, "u")
        await create_match(db, {"season_id": season.id, "team_id": team.id,
                                "round_number": 2, "raw_scores": {"a": 50}}, "u")
        await db.commit()

        await delete_match(db, m1.id)
        await db.commit()
        ranking = await get_ranking(db, season.id)
        assert len(ranking) == 1
        assert ranking[0].rounds_played == 1
        assert ranking[0].best_score == 50.0

    @pytest.mark.asyncio
    async def test_delete_missing_match_raises(self, db):
        with pytest.raises(NotFoundError):
            await delete_match(db, "missing")


# ── ranking ordering / refresh ───────────────────────────────────────────────

class TestRankingOrdering:
    @pytest.mark.asyncio
    async def test_three_teams_ranked_by_seed(self, db, season):
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 1}])
        teams = {}
        # seed = avg(top 2)
        plan = {
            "Low":  [10, 10],   # seed 10
            "High": [100, 90],  # seed 95
            "Mid":  [60, 50],   # seed 55
        }
        for name, scores in plan.items():
            t = await _make_team(db, name)
            teams[name] = t
            for i, s in enumerate(scores, start=1):
                await create_match(db, {"season_id": season.id, "team_id": t.id,
                                        "round_number": i, "raw_scores": {"a": s}}, "u")
        await db.commit()

        ranking = await get_ranking(db, season.id)
        ordered_ids = [r.team_id for r in ranking]
        assert ordered_ids == [teams["High"].id, teams["Mid"].id, teams["Low"].id]
        assert [r.rank for r in ranking] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_ranks_reorder_when_team_improves(self, db, season):
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 1}])
        a = await _make_team(db, "A")
        b = await _make_team(db, "B")
        await create_match(db, {"season_id": season.id, "team_id": a.id,
                                "round_number": 1, "raw_scores": {"a": 50}}, "u")
        b_match = await create_match(db, {"season_id": season.id, "team_id": b.id,
                                          "round_number": 1, "raw_scores": {"a": 40}}, "u")
        await db.commit()

        ranking = await get_ranking(db, season.id)
        assert ranking[0].team_id == a.id

        # B improves dramatically and overtakes A.
        await update_match(db, b_match.id, raw_scores={"a": 200})
        await db.commit()
        ranking = await get_ranking(db, season.id)
        assert ranking[0].team_id == b.id
        assert ranking[1].team_id == a.id

    @pytest.mark.asyncio
    async def test_refresh_ranks_directly(self, db, season):
        a = await _make_team(db, "A")
        b = await _make_team(db, "B")
        db.add(Ranking(season_id=season.id, team_id=a.id, rank=0,
                       seed_score=10.0, best_score=10, average_score=10, rounds_played=1))
        db.add(Ranking(season_id=season.id, team_id=b.id, rank=0,
                       seed_score=99.0, best_score=99, average_score=99, rounds_played=1))
        await db.flush()
        await _refresh_ranks(db, season.id, None)
        await db.flush()  # persist the new rank values before re-reading
        ranking = await get_ranking(db, season.id)
        assert ranking[0].team_id == b.id  # higher seed → rank 1
        assert ranking[0].rank == 1
        assert ranking[1].rank == 2

    @pytest.mark.asyncio
    async def test_all_matches_disqualified_removes_ranking(self, db, season, team):
        await _make_schema(db, season.id, [{"key": "a", "multiplier": 1}])
        m = await create_match(db, {"season_id": season.id, "team_id": team.id,
                                    "round_number": 1, "raw_scores": {"a": 10}}, "u")
        await db.commit()
        assert len(await get_ranking(db, season.id)) == 1

        m.is_disqualified = True
        await db.flush()
        await _recompute_ranking(db, season.id, team.id, None)
        await db.commit()
        # No eligible matches left → ranking row removed.
        assert await get_ranking(db, season.id) == []
