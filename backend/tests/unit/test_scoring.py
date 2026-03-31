"""Unit tests for scoring calculations."""
import pytest
from modules.scoring.service import compute_seed_score, compute_match_total


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

    def test_unknown_field_uses_multiplier_1(self):
        # Field not in schema → default multiplier 1
        schema = [{"key": "known", "multiplier": 3}]
        scores = {"known": 10, "unknown": 5}
        # 10*3 + 5*1 = 35
        assert compute_match_total(scores, schema) == 35.0

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
            "total_score": 0.0,
        }
        # Manually set total to test ranking
        match = await create_match(db, {**data, "raw_scores": {}, "total_score": 100.0}, team.id)
        # Override total for test
        match.total_score = 100.0
        await db.commit()

        ranking = await get_ranking(db, season.id)
        assert len(ranking) == 1
        assert ranking[0].team_id == team.id
        assert ranking[0].rank == 1

    @pytest.mark.asyncio
    async def test_multiple_teams_ranked_by_seed_score(self, db, season):
        from modules.teams.models import Team
        from modules.scoring.models import Match, Ranking
        from modules.scoring.service import _recompute_ranking, _refresh_ranks, get_ranking

        # Create two teams
        team_a = Team(name="Team A", country="DE")
        team_b = Team(name="Team B", country="DE")
        db.add_all([team_a, team_b])
        await db.flush()

        # Team A: scores 90, 80, 70 → seed = avg(90,80) = 85
        # Team B: scores 100, 50, 30 → seed = avg(100,50) = 75
        for score in [90.0, 80.0, 70.0]:
            m = Match(season_id=season.id, team_id=team_a.id, round_number=1,
                      raw_scores={}, total_score=score, is_disqualified=False,
                      yellow_card=False, red_card=False)
            db.add(m)
        for score in [100.0, 50.0, 30.0]:
            m = Match(season_id=season.id, team_id=team_b.id, round_number=1,
                      raw_scores={}, total_score=score, is_disqualified=False,
                      yellow_card=False, red_card=False)
            db.add(m)
        await db.flush()

        await _recompute_ranking(db, season.id, team_a.id, None)
        await _recompute_ranking(db, season.id, team_b.id, None)
        await db.commit()

        ranking = await get_ranking(db, season.id)
        assert ranking[0].team_id == team_a.id  # Team A: seed=85 > Team B: seed=75
        assert ranking[1].team_id == team_b.id
        assert ranking[0].rank == 1
        assert ranking[1].rank == 2
