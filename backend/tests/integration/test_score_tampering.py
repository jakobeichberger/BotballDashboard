"""Scores that feed the ranking must not be settable through the wrong door.

Both fields below are review/derived outcomes that flow into the overall
ranking, and both were reachable from a permission that ordinary participants
hold (papers:write is granted to the mentor role; scoring:write to any juror).
The boundary is the request schema, so that is what these assert.
"""

import pytest

from modules.paper_review.schemas import PaperScoreUpdate, PaperUpdate
from modules.scoring.schemas import MatchUpdate


class TestPaperScoreIsAdminOnly:
    def test_papers_write_schema_cannot_carry_the_review_outcome(self):
        assert "final_score" not in PaperUpdate.model_fields
        assert "paper_rank" not in PaperUpdate.model_fields

    def test_admin_schema_carries_it(self):
        assert set(PaperScoreUpdate.model_fields) == {"final_score", "paper_rank"}

    def test_extra_keys_are_rejected_not_silently_kept(self):
        parsed = PaperUpdate(title="T", final_score=1.0)
        assert not hasattr(parsed, "final_score")

    @pytest.mark.asyncio
    async def test_score_route_requires_papers_admin(self, client, db, season, event):
        """Unauthenticated must not get through; the guard is papers:admin."""
        from modules.paper_review.models import Paper
        from modules.teams.models import Team

        team = Team(name="Tamper Team", country="AT")
        db.add(team)
        await db.flush()
        paper = Paper(season_id=season.id, event_id=event.id, team_id=team.id, title="P")
        db.add(paper)
        await db.flush()

        resp = await client.put(f"/api/papers/{paper.id}/score", json={"final_score": 1.0})
        assert resp.status_code == 401


class TestMatchTotalIsDerived:
    def test_total_score_is_not_settable_on_update(self):
        """create_match strips a client total and recomputes; update used to
        assign it straight through, bypassing validate_raw_scores."""
        assert "total_score" not in MatchUpdate.model_fields

    def test_a_submitted_total_is_dropped_rather_than_applied(self):
        parsed = MatchUpdate(raw_scores={"a": 1}, total_score=9999.0)
        assert not hasattr(parsed, "total_score")
        assert parsed.model_dump(exclude_none=True) == {"raw_scores": {"a": 1}}
