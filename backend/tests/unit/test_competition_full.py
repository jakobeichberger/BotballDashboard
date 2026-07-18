"""
Unit tests for competition scoring service logic.

Covers:
  - helper functions: _avg_best_n, _normalize
  - DE upsert (insert then update same team), bulk DE bracket A/B scoring
  - Aerial upsert (best-of-2 score computation), bulk aerial ranking
  - Documentation upsert (doc_score = avg of parts/100), bulk doc ranking
  - get_de_results / get_aerial_results / get_doc_scores filtering by season
  - get_overall_ranking combining enabled modules + ordering
  - get_aerial_ranking ordering and team enrichment
"""

import pytest

from modules.scoring import competition_service as svc
from modules.teams.models import Team, TeamSeasonRegistration

# ── Fixtures ──────────────────────────────────────────────────────────────────


async def _register_team(db, season_id, name, category="botball"):
    t = Team(name=name, country="DE")
    db.add(t)
    await db.flush()
    reg = TeamSeasonRegistration(team_id=t.id, season_id=season_id, category=category)
    db.add(reg)
    await db.flush()
    return t


# ── Helper functions ──────────────────────────────────────────────────────────


class TestAvgBestN:
    def test_empty_returns_zero(self):
        assert svc._avg_best_n([]) == 0.0

    def test_all_none_returns_zero(self):
        assert svc._avg_best_n([None, None]) == 0.0

    def test_best_two_of_many(self):
        # best 2 of [10, 8, 6, 4] = (10 + 8) / 2 = 9
        assert svc._avg_best_n([4.0, 10.0, 6.0, 8.0]) == 9.0

    def test_single_value_keeps_full_value(self):
        assert svc._avg_best_n([10.0]) == 10.0

    def test_ignores_none_values(self):
        assert svc._avg_best_n([10.0, None, 6.0]) == 8.0

    def test_custom_n(self):
        # best 3 of [9, 8, 7, 1] = 24 / 3 = 8
        assert svc._avg_best_n([9.0, 8.0, 7.0, 1.0], n=3) == 8.0


class TestNormalize:
    def test_empty(self):
        assert svc._normalize([]) == []

    def test_all_none(self):
        assert svc._normalize([None, None]) == [0.0, 0.0]

    def test_max_zero(self):
        assert svc._normalize([0.0, 0.0]) == [0.0, 0.0]

    def test_scales_to_max(self):
        assert svc._normalize([10.0, 5.0]) == [1.0, 0.5]

    def test_none_becomes_zero(self):
        assert svc._normalize([10.0, None]) == [1.0, 0.0]


# ── Double Elimination ────────────────────────────────────────────────────────


class TestDEUpsert:
    @pytest.mark.asyncio
    async def test_insert_then_update_same_team(self, db, season, team):
        row = await svc.upsert_de_result(
            db, season.id, {"team_id": team.id, "bracket": "A", "de_rank": 1, "de_score": 1.0}
        )
        assert row.id is not None
        assert row.bracket == "A"
        assert row.de_rank == 1

        # Upsert again for same team → updates, not inserts a second row
        updated = await svc.upsert_de_result(
            db, season.id, {"team_id": team.id, "bracket": "B", "de_rank": 3, "de_score": 0.5}
        )
        assert updated.id == row.id
        assert updated.bracket == "B"
        assert updated.de_rank == 3

        results = await svc.get_de_results(db, season.id)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_de_results_filters_by_season(self, db, season, team):
        await svc.upsert_de_result(
            db, season.id, {"team_id": team.id, "bracket": "A", "de_rank": 1}
        )
        # Different season id returns nothing
        assert await svc.get_de_results(db, "nonexistent-season") == []
        assert len(await svc.get_de_results(db, season.id)) == 1


class TestBulkDEResults:
    @pytest.mark.asyncio
    async def test_bracket_score_computed_per_bracket(self, db, season):
        t1 = await _register_team(db, season.id, "T1")
        t2 = await _register_team(db, season.id, "T2")
        t3 = await _register_team(db, season.id, "T3")

        entries = [
            {"team_id": t1.id, "bracket": "A", "de_rank": 1},
            {"team_id": t2.id, "bracket": "A", "de_rank": 2},
            {"team_id": t3.id, "bracket": "A", "de_rank": 3},
        ]
        rows = await svc.bulk_upsert_de_results(db, season.id, entries)
        by_team = {r.team_id: r for r in rows}
        # rank 1 → 1.0, rank 2 → 0.5, rank 3 → 0.0  (1 - (rank-1)/(max-1))
        assert by_team[t1.id].bracket_score == 1.0
        assert by_team[t2.id].bracket_score == 0.5
        assert by_team[t3.id].bracket_score == 0.0

    @pytest.mark.asyncio
    async def test_single_team_in_bracket_gets_full_score(self, db, season):
        t1 = await _register_team(db, season.id, "Solo")
        rows = await svc.bulk_upsert_de_results(
            db, season.id, [{"team_id": t1.id, "bracket": "B", "de_rank": 1}]
        )
        assert rows[0].bracket_score == 1.0

    @pytest.mark.asyncio
    async def test_two_brackets_scored_independently(self, db, season):
        a1 = await _register_team(db, season.id, "A1")
        a2 = await _register_team(db, season.id, "A2")
        b1 = await _register_team(db, season.id, "B1")
        entries = [
            {"team_id": a1.id, "bracket": "A", "de_rank": 1},
            {"team_id": a2.id, "bracket": "A", "de_rank": 2},
            {"team_id": b1.id, "bracket": "B", "de_rank": 1},
        ]
        rows = await svc.bulk_upsert_de_results(db, season.id, entries)
        by_team = {r.team_id: r for r in rows}
        assert by_team[a1.id].bracket_score == 1.0
        assert by_team[a2.id].bracket_score == 0.0
        # Single team in bracket B → 1.0
        assert by_team[b1.id].bracket_score == 1.0


# ── Aerial ────────────────────────────────────────────────────────────────────


class TestAerialUpsert:
    @pytest.mark.asyncio
    async def test_score_is_avg_best_two_runs(self, db, season, team):
        row = await svc.upsert_aerial_result(
            db,
            season.id,
            {"team_id": team.id, "run1": 10.0, "run2": 4.0, "run3": 8.0, "run4": 2.0},
        )
        # best 2 of (10, 4, 8, 2) = (10 + 8) / 2 = 9.0
        assert row.score == 9.0

    @pytest.mark.asyncio
    async def test_partial_runs(self, db, season, team):
        row = await svc.upsert_aerial_result(db, season.id, {"team_id": team.id, "run1": 6.0})
        # A single available run retains its full value.
        assert row.score == 6.0

    @pytest.mark.asyncio
    async def test_no_runs_score_zero(self, db, season, team):
        row = await svc.upsert_aerial_result(db, season.id, {"team_id": team.id})
        assert row.score == 0.0

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_and_recomputes(self, db, season, team):
        first = await svc.upsert_aerial_result(
            db, season.id, {"team_id": team.id, "run1": 10.0, "run2": 10.0}
        )
        assert first.score == 10.0
        second = await svc.upsert_aerial_result(
            db, season.id, {"team_id": team.id, "run1": 2.0, "run2": 2.0}
        )
        assert second.id == first.id
        assert second.score == 2.0
        assert len(await svc.get_aerial_results(db, season.id)) == 1


class TestBulkAerialResults:
    @pytest.mark.asyncio
    async def test_ranked_by_score_descending(self, db, season):
        t1 = await _register_team(db, season.id, "Low")
        t2 = await _register_team(db, season.id, "High")
        entries = [
            {"team_id": t1.id, "run1": 2.0, "run2": 2.0},  # score 2.0
            {"team_id": t2.id, "run1": 10.0, "run2": 8.0},  # score 9.0
        ]
        rows = await svc.bulk_upsert_aerial_results(db, season.id, entries)
        by_team = {r.team_id: r for r in rows}
        assert by_team[t2.id].rank == 1
        assert by_team[t1.id].rank == 2


# ── Documentation ─────────────────────────────────────────────────────────────


class TestDocUpsert:
    @pytest.mark.asyncio
    async def test_doc_score_is_avg_of_parts_over_100(self, db, season, team):
        row = await svc.upsert_doc_score(
            db,
            season.id,
            {"team_id": team.id, "part1": 90.0, "part2": 60.0, "part3": 30.0},
        )
        # avg(90, 60, 30) = 60 → /100 = 0.6
        assert row.doc_score == pytest.approx(0.6)

    @pytest.mark.asyncio
    async def test_partial_parts(self, db, season, team):
        row = await svc.upsert_doc_score(db, season.id, {"team_id": team.id, "part1": 80.0})
        assert row.doc_score == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_onsite_only_score(self, db, season, team):
        row = await svc.upsert_doc_score(db, season.id, {"team_id": team.id, "onsite": 50.0})
        assert row.doc_score == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, db, season, team):
        first = await svc.upsert_doc_score(db, season.id, {"team_id": team.id, "part1": 100.0})
        second = await svc.upsert_doc_score(db, season.id, {"team_id": team.id, "part1": 50.0})
        assert second.id == first.id
        assert second.doc_score == pytest.approx(0.5)
        assert len(await svc.get_doc_scores(db, season.id)) == 1


class TestBulkDocScores:
    @pytest.mark.asyncio
    async def test_ranked_by_doc_score_descending(self, db, season):
        t1 = await _register_team(db, season.id, "Worse")
        t2 = await _register_team(db, season.id, "Better")
        entries = [
            {"team_id": t1.id, "part1": 40.0},  # 0.4
            {"team_id": t2.id, "part1": 90.0},  # 0.9
        ]
        rows = await svc.bulk_upsert_doc_scores(db, season.id, entries)
        by_team = {r.team_id: r for r in rows}
        assert by_team[t2.id].doc_rank == 1
        assert by_team[t1.id].doc_rank == 2


# ── Overall Ranking ───────────────────────────────────────────────────────────


class TestOverallRanking:
    @pytest.mark.asyncio
    async def test_empty_when_no_teams(self, db, season):
        result = await svc.get_overall_ranking(db, season.id, False, False, False, False)
        assert result == []

    @pytest.mark.asyncio
    async def test_combines_de_and_doc_scores_and_orders(self, db, season):
        t1 = await _register_team(db, season.id, "T1")
        t2 = await _register_team(db, season.id, "T2")

        # DE scores
        await svc.upsert_de_result(
            db, season.id, {"team_id": t1.id, "bracket": "A", "de_score": 0.3}
        )
        await svc.upsert_de_result(
            db, season.id, {"team_id": t2.id, "bracket": "A", "de_score": 0.9}
        )
        # Doc scores
        await svc.upsert_doc_score(db, season.id, {"team_id": t1.id, "part1": 100.0})  # 1.0
        await svc.upsert_doc_score(db, season.id, {"team_id": t2.id, "part1": 10.0})  # 0.1

        entries = await svc.get_overall_ranking(
            db,
            season.id,
            use_seeding=False,
            use_double_elimination=True,
            use_paper_scoring=False,
            use_documentation_scoring=True,
        )
        by_team = {e["team_id"]: e for e in entries}
        # t1 overall = 0.3 + 1.0 = 1.3; t2 = 0.9 + 0.1 = 1.0
        assert by_team[t1.id]["overall_score"] == pytest.approx(1.3)
        assert by_team[t2.id]["overall_score"] == pytest.approx(1.0)
        assert by_team[t1.id]["rank"] == 1
        assert by_team[t2.id]["rank"] == 2
        # Disabled modules are None
        assert by_team[t1.id]["seeding_score"] is None
        assert by_team[t1.id]["paper_score"] is None
        assert by_team[t1.id]["de_score"] == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_missing_module_data_defaults_to_zero(self, db, season):
        await _register_team(db, season.id, "T1")
        # No DE result rows at all but module enabled → defaults 0.0
        entries = await svc.get_overall_ranking(
            db,
            season.id,
            use_seeding=False,
            use_double_elimination=True,
            use_paper_scoring=False,
            use_documentation_scoring=False,
        )
        assert entries[0]["overall_score"] == 0.0
        assert entries[0]["de_score"] == 0.0
        assert entries[0]["category"] == "botball"


class TestAerialRanking:
    @pytest.mark.asyncio
    async def test_orders_and_enriches_with_team_name(self, db, season):
        t1 = await _register_team(db, season.id, "Falcon")
        t2 = await _register_team(db, season.id, "Eagle")
        await svc.upsert_aerial_result(
            db, season.id, {"team_id": t1.id, "run1": 4.0, "run2": 4.0}
        )  # score 4
        await svc.upsert_aerial_result(
            db, season.id, {"team_id": t2.id, "run1": 10.0, "run2": 10.0}
        )  # score 10

        ranking = await svc.get_aerial_ranking(db, season.id)
        assert ranking[0]["team_id"] == t2.id
        assert ranking[0]["team_name"] == "Eagle"
        assert ranking[0]["rank"] == 1
        assert ranking[0]["score"] == 10.0
        assert ranking[1]["team_id"] == t1.id
        assert ranking[1]["rank"] == 2

    @pytest.mark.asyncio
    async def test_empty_ranking(self, db, season):
        assert await svc.get_aerial_ranking(db, season.id) == []
