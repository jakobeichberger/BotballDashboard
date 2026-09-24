"""Unit tests for scoring calculations."""

import pytest

from modules.scoring.competition_service import aerial_score, documentation_score
from modules.scoring.service import (
    compute_match_total,
    compute_seed_score,
    official_run_score,
)


class TestComputeSeedScore:
    def test_empty_scores(self):
        assert compute_seed_score([]) == 0.0

    def test_single_score(self):
        assert compute_seed_score([100.0]) == 100.0

    def test_two_scores_averages_both(self):
        assert compute_seed_score([100.0, 80.0]) == 90.0

    def test_three_scores_uses_top_two(self):
        # Top 2: 100, 90 → avg = 95
        assert compute_seed_score([100.0, 90.0, 50.0]) == 95.0

    def test_five_scores_uses_top_two(self):
        # Top 2: 200, 180 → avg = 190
        result = compute_seed_score([200.0, 180.0, 160.0, 140.0, 120.0])
        assert result == 190.0

    def test_all_equal_scores(self):
        assert compute_seed_score([75.0, 75.0, 75.0]) == 75.0

    def test_zero_scores(self):
        assert compute_seed_score([0.0, 0.0, 0.0]) == 0.0

    def test_decimal_precision(self):
        result = compute_seed_score([100.0, 99.0, 98.0])
        assert result == 99.5


class TestCompetitionScores:
    def test_single_aerial_run_keeps_full_value(self):
        assert aerial_score([80.0, None, None, None]) == 80.0

    def test_aerial_is_the_mean_of_all_runs(self):
        # ECER 2025 ranked aerial on the mean of every run, not the best two.
        assert aerial_score([20.0, 100.0, 80.0, 0.0]) == 50.0

    def test_aerial_without_runs_has_no_score(self):
        assert aerial_score([None, None, None, None]) is None

    def test_documentation_weights_and_missing_parts(self):
        assert documentation_score(100, 100, 100, 100) == pytest.approx(1.0)
        # 0.2 * 1 + 0.2 * 0.5 + 0 (missing) + 0.4 * 0.5
        assert documentation_score(100, 50, None, 50) == pytest.approx(0.5)
        assert documentation_score(None, None, None, None) is None


class TestOfficialRunScore:
    def test_disqualified_round_counts_zero(self):
        assert official_run_score(250.0, True) == 0.0

    def test_negative_score_counts_zero(self):
        assert official_run_score(-30.0, False) == 0.0

    def test_regular_score_unchanged(self):
        assert official_run_score(123.0, False) == 123.0

    @pytest.mark.asyncio
    async def test_documentation_score_includes_onsite(self, db, season, team):
        from modules.scoring.competition_service import upsert_doc_score
        from modules.scoring.service import get_default_event

        score = await upsert_doc_score(
            db,
            await get_default_event(db, season.id),
            {
                "team_id": team.id,
                "part1": 100,
                "part2": 100,
                "part3": 100,
                "onsite": 0,
            },
        )
        # 0.2 + 0.2 + 0.2 + 0.4 * 0 — the onsite part weighs 4/10.
        assert score.doc_score == pytest.approx(0.6)


class TestComputeMatchTotal:
    def _schema(self, fields: list[dict]) -> list[dict]:
        return fields

    def test_empty_raw_scores(self):
        schema = [{"key": "a", "multiplier": 2}]
        assert compute_match_total({}, schema) == 0.0

    def test_single_field_no_multiplier(self):
        schema = [{"key": "task_1", "multiplier": 1}]
        assert compute_match_total({"task_1": 50}, schema) == 50.0

    def test_single_field_with_multiplier(self):
        schema = [{"key": "task_1", "multiplier": 3}]
        assert compute_match_total({"task_1": 10}, schema) == 30.0

    def test_multiple_fields(self):
        schema = [
            {"key": "a", "multiplier": 2},
            {"key": "b", "multiplier": 5},
            {"key": "c", "multiplier": 1},
        ]
        scores = {"a": 10, "b": 4, "c": 100}
        # 10*2 + 4*5 + 100*1 = 20 + 20 + 100 = 140
        assert compute_match_total(scores, schema) == 140.0

    def test_unknown_field_scores_nothing_when_a_schema_is_defined(self):
        # A defined schema is authoritative. raw_scores is client-supplied, so
        # letting an unknown key score with an implicit multiplier of 1 allowed
        # anyone who may enter a match to invent a field and score themselves
        # arbitrarily high. (With NO schema the sum-as-is fallback still
        # applies — see test_scoring_full.test_empty_schema_*.)
        schema = [{"key": "known", "multiplier": 3}]
        scores = {"known": 10, "unknown": 5}
        assert compute_match_total(scores, schema) == 30.0

    def test_zero_values(self):
        schema = [{"key": "a", "multiplier": 10}]
        assert compute_match_total({"a": 0}, schema) == 0.0

    def test_decimal_values(self):
        schema = [{"key": "a", "multiplier": 1.5}]
        result = compute_match_total({"a": 10}, schema)
        assert result == 15.0

    def test_result_is_rounded_to_two_decimals(self):
        schema = [{"key": "a", "multiplier": 1}]
        result = compute_match_total({"a": 1.005}, schema)
        assert len(str(result).split(".")[-1]) <= 2


class TestRankingLogic:
    """Tests for the complete ranking computation flow."""

    @pytest.mark.asyncio
    async def test_ranking_recomputed_after_match(self, db, season, team):
        from modules.scoring.service import create_match, get_ranking

        data = {
            "season_id": season.id,
            "team_id": team.id,
            "round_number": 1,
            "raw_scores": {},
        }
        # total_score is computed server-side from raw_scores; override it
        # afterwards to exercise the ranking logic with a known value.
        match = await create_match(db, data, team.id)
        match.total_score = 100.0
        await db.commit()

        ranking = await get_ranking(db, season.id)
        assert len(ranking) == 1
        assert ranking[0].team_id == team.id
        assert ranking[0].rank == 1

    @pytest.mark.asyncio
    async def test_multiple_teams_ranked_by_seed_score(self, db, season, event):
        from modules.scoring.models import Match
        from modules.scoring.service import _recompute_ranking, get_ranking
        from modules.teams.models import Team

        # Create two teams
        team_a = Team(name="Team A", country="DE")
        team_b = Team(name="Team B", country="DE")
        db.add_all([team_a, team_b])
        await db.flush()

        # Team A: scores 90, 80, 70 → seed = avg(90,80) = 85
        # Team B: scores 100, 50, 30 → seed = avg(100,50) = 75
        for score in [90.0, 80.0, 70.0]:
            m = Match(
                season_id=season.id,
                event_id=event.id,
                team_id=team_a.id,
                round_number=1,
                raw_scores={},
                total_score=score,
                is_disqualified=False,
                yellow_card=False,
                red_card=False,
            )
            db.add(m)
        for score in [100.0, 50.0, 30.0]:
            m = Match(
                season_id=season.id,
                event_id=event.id,
                team_id=team_b.id,
                round_number=1,
                raw_scores={},
                total_score=score,
                is_disqualified=False,
                yellow_card=False,
                red_card=False,
            )
            db.add(m)
        await db.flush()

        await _recompute_ranking(db, event.id, team_a.id, None)
        await _recompute_ranking(db, event.id, team_b.id, None)
        await db.commit()

        ranking = await get_ranking(db, season.id)
        assert ranking[0].team_id == team_a.id  # Team A: seed=85 > Team B: seed=75
        assert ranking[1].team_id == team_b.id
        assert ranking[0].rank == 1
        assert ranking[1].rank == 2

    @pytest.mark.asyncio
    async def test_disqualified_round_counts_as_zero(self, db, season, event, team):
        from modules.scoring.models import Match
        from modules.scoring.service import _recompute_ranking, get_ranking, update_match

        match = Match(
            season_id=season.id,
            event_id=event.id,
            team_id=team.id,
            total_score=100,
            raw_scores={},
        )
        db.add(match)
        await db.flush()
        await _recompute_ranking(db, event.id, team.id, None)
        assert len(await get_ranking(db, season.id)) == 1

        # A disqualified round is a round with 0 points, not a dropped round.
        await update_match(db, match.id, is_disqualified=True)
        ranking = await get_ranking(db, season.id)
        assert len(ranking) == 1
        assert ranking[0].seed_score == 0.0
        assert ranking[0].rounds_played == 1
