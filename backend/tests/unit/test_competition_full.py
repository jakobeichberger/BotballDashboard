"""
Unit tests for competition scoring service logic.

Covers:
  - helper functions: aerial_score, documentation_score, bracket_score
  - DE upsert (insert then update same team), bracket scores (n − rank + 1)/n
  - Aerial upsert (mean of all runs), aerial ranking with shared ties
  - Documentation upsert (0.2/0.2/0.2/0.4 weighting, missing parts = 0)
  - get_de_results / get_aerial_results / get_doc_scores filtering by event
  - get_aerial_ranking ordering and team enrichment
  - ResultRevision audit entries for every change
"""

import pytest
from sqlalchemy import select

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


async def _other_event(db, season):
    from modules.events.models import Event

    other = Event(season_id=season.id, name="Other", slug=f"other-{season.id}")
    db.add(other)
    await db.flush()
    return other


# ── Helper functions ──────────────────────────────────────────────────────────


class TestHelpers:
    def test_aerial_score_is_mean_of_all_runs(self):
        assert svc.aerial_score([4.0, 10.0, 6.0, 8.0]) == 7.0

    def test_aerial_score_ignores_missing_runs(self):
        assert svc.aerial_score([10.0, None, 6.0, None]) == 8.0

    def test_aerial_score_none_without_runs(self):
        assert svc.aerial_score([None, None]) is None

    def test_documentation_score_weights(self):
        assert svc.documentation_score(100, 100, 100, 100) == pytest.approx(1.0)
        assert svc.documentation_score(0, 0, 0, 100) == pytest.approx(0.4)
        assert svc.documentation_score(90, 60, 30, None) == pytest.approx(0.36)

    def test_documentation_score_none_without_parts(self):
        assert svc.documentation_score(None, None, None, None) is None

    def test_bracket_score(self):
        assert svc.bracket_score(4, 1) == 1.0
        assert svc.bracket_score(4, 4) == 0.25
        assert svc.bracket_score(0, 1) == 0.0


# ── Double Elimination ────────────────────────────────────────────────────────


class TestDEUpsert:
    @pytest.mark.asyncio
    async def test_insert_then_update_same_team(self, db, season, event, team):
        row = await svc.upsert_de_result(
            db, event, {"team_id": team.id, "bracket": "A", "de_rank": 1, "de_score": 1.0}
        )
        assert row.id is not None
        assert row.bracket == "A"
        assert row.de_rank == 1

        # Upsert again for same team → updates, not inserts a second row
        updated = await svc.upsert_de_result(
            db, event, {"team_id": team.id, "bracket": "B", "de_rank": 3, "de_score": 0.5}
        )
        assert updated.id == row.id
        assert updated.bracket == "B"
        assert updated.de_rank == 3

        results = await svc.get_de_results(db, event)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_de_results_filters_by_event(self, db, season, event, team):
        await svc.upsert_de_result(db, event, {"team_id": team.id, "bracket": "A", "de_rank": 1})
        other = await _other_event(db, season)
        assert await svc.get_de_results(db, other) == []
        assert len(await svc.get_de_results(db, event)) == 1


class TestBulkDEResults:
    @pytest.mark.asyncio
    async def test_bracket_score_computed_per_bracket(self, db, season, event):
        t1 = await _register_team(db, season.id, "T1")
        t2 = await _register_team(db, season.id, "T2")
        t3 = await _register_team(db, season.id, "T3")

        entries = [
            {"team_id": t1.id, "bracket": "A", "de_rank": 1},
            {"team_id": t2.id, "bracket": "A", "de_rank": 2},
            {"team_id": t3.id, "bracket": "A", "de_rank": 3},
        ]
        rows = await svc.bulk_upsert_de_results(db, event, entries)
        by_team = {r.team_id: r for r in rows}
        # (n − rank + 1) / n with n = 3
        assert by_team[t1.id].bracket_score == pytest.approx(1.0)
        assert by_team[t2.id].bracket_score == pytest.approx(2 / 3)
        assert by_team[t3.id].bracket_score == pytest.approx(1 / 3)

    @pytest.mark.asyncio
    async def test_single_team_in_bracket_gets_full_score(self, db, season, event):
        t1 = await _register_team(db, season.id, "Solo")
        rows = await svc.bulk_upsert_de_results(
            db, event, [{"team_id": t1.id, "bracket": "B", "de_rank": 1}]
        )
        assert rows[0].bracket_score == 1.0

    @pytest.mark.asyncio
    async def test_two_brackets_scored_independently(self, db, season, event):
        a1 = await _register_team(db, season.id, "A1")
        a2 = await _register_team(db, season.id, "A2")
        b1 = await _register_team(db, season.id, "B1")
        entries = [
            {"team_id": a1.id, "bracket": "A", "de_rank": 1},
            {"team_id": a2.id, "bracket": "A", "de_rank": 2},
            {"team_id": b1.id, "bracket": "B", "de_rank": 1},
        ]
        rows = await svc.bulk_upsert_de_results(db, event, entries)
        by_team = {r.team_id: r for r in rows}
        assert by_team[a1.id].bracket_score == 1.0
        assert by_team[a2.id].bracket_score == 0.5
        # Single team in bracket B → 1.0
        assert by_team[b1.id].bracket_score == 1.0

    @pytest.mark.asyncio
    async def test_single_upserts_rescore_the_whole_bracket(self, db, season, event):
        t1 = await _register_team(db, season.id, "T1")
        t2 = await _register_team(db, season.id, "T2")
        first = await svc.upsert_de_result(
            db, event, {"team_id": t1.id, "bracket": "A", "de_rank": 1}
        )
        await svc.upsert_de_result(db, event, {"team_id": t2.id, "bracket": "A", "de_rank": 2})
        await db.refresh(first)
        assert first.bracket_score == 1.0
        rows = {r.team_id: r for r in await svc.get_de_results(db, event)}
        assert rows[t2.id].bracket_score == 0.5


# ── Aerial ────────────────────────────────────────────────────────────────────


class TestAerialUpsert:
    @pytest.mark.asyncio
    async def test_score_is_mean_of_all_runs(self, db, season, event, team):
        row = await svc.upsert_aerial_result(
            db,
            event,
            {"team_id": team.id, "run1": 10.0, "run2": 4.0, "run3": 8.0, "run4": 2.0},
        )
        # (10 + 4 + 8 + 2) / 4 — ECER 2025 ranked aerial on all runs.
        assert row.score == 6.0

    @pytest.mark.asyncio
    async def test_partial_runs(self, db, season, event, team):
        row = await svc.upsert_aerial_result(db, event, {"team_id": team.id, "run1": 6.0})
        assert row.score == 6.0

    @pytest.mark.asyncio
    async def test_no_runs_no_score(self, db, season, event, team):
        row = await svc.upsert_aerial_result(db, event, {"team_id": team.id})
        assert row.score is None
        assert row.rank is None

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_and_recomputes(self, db, season, event, team):
        first = await svc.upsert_aerial_result(
            db, event, {"team_id": team.id, "run1": 10.0, "run2": 10.0}
        )
        assert first.score == 10.0
        second = await svc.upsert_aerial_result(
            db, event, {"team_id": team.id, "run1": 2.0, "run2": 2.0}
        )
        assert second.id == first.id
        assert second.score == 2.0
        assert len(await svc.get_aerial_results(db, event)) == 1


class TestBulkAerialResults:
    @pytest.mark.asyncio
    async def test_ranked_by_score_descending(self, db, season, event):
        t1 = await _register_team(db, season.id, "Low")
        t2 = await _register_team(db, season.id, "High")
        entries = [
            {"team_id": t1.id, "run1": 2.0, "run2": 2.0},  # score 2.0
            {"team_id": t2.id, "run1": 10.0, "run2": 8.0},  # score 9.0
        ]
        rows = await svc.bulk_upsert_aerial_results(db, event, entries)
        by_team = {r.team_id: r for r in rows}
        assert by_team[t2.id].rank == 1
        assert by_team[t1.id].rank == 2


# ── Documentation ─────────────────────────────────────────────────────────────


class TestDocUpsert:
    @pytest.mark.asyncio
    async def test_doc_score_is_weighted(self, db, season, event, team):
        row = await svc.upsert_doc_score(
            db,
            event,
            {"team_id": team.id, "part1": 90.0, "part2": 60.0, "part3": 30.0, "onsite": 50.0},
        )
        # 0.2·0.9 + 0.2·0.6 + 0.2·0.3 + 0.4·0.5
        assert row.doc_score == pytest.approx(0.56)

    @pytest.mark.asyncio
    async def test_missing_parts_count_zero(self, db, season, event, team):
        row = await svc.upsert_doc_score(db, event, {"team_id": team.id, "part1": 80.0})
        assert row.doc_score == pytest.approx(0.16)

    @pytest.mark.asyncio
    async def test_onsite_only_score(self, db, season, event, team):
        row = await svc.upsert_doc_score(db, event, {"team_id": team.id, "onsite": 50.0})
        assert row.doc_score == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, db, season, event, team):
        first = await svc.upsert_doc_score(db, event, {"team_id": team.id, "part1": 100.0})
        second = await svc.upsert_doc_score(db, event, {"team_id": team.id, "part1": 50.0})
        assert second.id == first.id
        assert second.doc_score == pytest.approx(0.1)
        assert len(await svc.get_doc_scores(db, event)) == 1


class TestBulkDocScores:
    @pytest.mark.asyncio
    async def test_ranked_by_doc_score_descending(self, db, season, event):
        t1 = await _register_team(db, season.id, "Worse")
        t2 = await _register_team(db, season.id, "Better")
        entries = [
            {"team_id": t1.id, "part1": 40.0},
            {"team_id": t2.id, "part1": 90.0},
        ]
        rows = await svc.bulk_upsert_doc_scores(db, event, entries)
        by_team = {r.team_id: r for r in rows}
        assert by_team[t2.id].doc_rank == 1
        assert by_team[t1.id].doc_rank == 2


class TestAerialRanking:
    @pytest.mark.asyncio
    async def test_orders_and_enriches_with_team_name(self, db, season, event):
        t1 = await _register_team(db, season.id, "Falcon")
        t2 = await _register_team(db, season.id, "Eagle")
        await svc.upsert_aerial_result(db, event, {"team_id": t1.id, "run1": 4.0, "run2": 4.0})
        await svc.upsert_aerial_result(db, event, {"team_id": t2.id, "run1": 10.0, "run2": 10.0})

        ranking = await svc.get_aerial_ranking(db, event)
        assert ranking[0]["team_id"] == t2.id
        assert ranking[0]["team_name"] == "Eagle"
        assert ranking[0]["rank"] == 1
        assert ranking[0]["score"] == 10.0
        assert ranking[1]["team_id"] == t1.id
        assert ranking[1]["rank"] == 2

    @pytest.mark.asyncio
    async def test_ties_share_a_rank(self, db, season, event):
        t1 = await _register_team(db, season.id, "A")
        t2 = await _register_team(db, season.id, "B")
        t3 = await _register_team(db, season.id, "C")
        for t, run in ((t1, 5.0), (t2, 5.0), (t3, 1.0)):
            await svc.upsert_aerial_result(db, event, {"team_id": t.id, "run1": run})
        ranks = {r["team_id"]: r["rank"] for r in await svc.get_aerial_ranking(db, event)}
        assert ranks == {t1.id: 1, t2.id: 1, t3.id: 3}

    @pytest.mark.asyncio
    async def test_empty_ranking(self, db, season, event):
        assert await svc.get_aerial_ranking(db, event) == []


# ── Audit trail ───────────────────────────────────────────────────────────────


class TestResultRevisions:
    @pytest.mark.asyncio
    async def test_every_change_is_recorded(self, db, season, event, team, admin_user):
        from modules.scoring.competition_models import ResultRevision

        await svc.upsert_aerial_result(db, event, {"team_id": team.id, "run1": 4.0}, admin_user.id)
        await svc.upsert_aerial_result(db, event, {"team_id": team.id, "run1": 6.0}, admin_user.id)
        await svc.upsert_aerial_result(db, event, {"team_id": team.id, "run1": 6.0}, admin_user.id)

        rows = (await db.execute(select(ResultRevision))).scalars().all()
        assert len(rows) == 2  # the unchanged third write is not an entry
        created = next(r for r in rows if r.previous_value is None)
        changed = next(r for r in rows if r.previous_value is not None)
        assert created.new_value["run1"] == 4.0
        assert changed.previous_value["run1"] == 4.0
        assert changed.new_value["run1"] == 6.0
        assert changed.changed_by == admin_user.id
        assert changed.kind == "aerial"

        listed = await svc.list_result_revisions(db, event, kind="aerial", team_id=team.id)
        assert len(listed) == 2
