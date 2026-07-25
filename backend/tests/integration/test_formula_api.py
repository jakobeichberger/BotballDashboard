"""End-to-end tests for the configurable scoring formulas."""

import pytest


@pytest.fixture
async def scored_season(db, season, event, admin_user):
    """An event with two Botball teams, seeding runs, DE results and documentation."""
    from modules.paper_review.models import Paper
    from modules.scoring.competition_models import DEResult, DocumentationScore
    from modules.scoring.models import Match
    from modules.teams.models import Team, TeamSeasonRegistration

    teams = [Team(name="Alpha", country="AT"), Team(name="Beta", country="AT")]
    db.add_all(teams)
    await db.flush()

    for t in teams:
        db.add(TeamSeasonRegistration(team_id=t.id, season_id=season.id, category="botball"))

    # Alpha clearly ahead on seeding: best two are 300 and 200.
    runs = {teams[0].id: [100.0, 300.0, 200.0], teams[1].id: [50.0, 40.0, 30.0]}
    for team_id, scores in runs.items():
        for i, score in enumerate(scores, start=1):
            db.add(
                Match(
                    season_id=season.id,
                    event_id=event.id,
                    team_id=team_id,
                    round_number=i,
                    raw_scores={},
                    total_score=score,
                )
            )

    db.add_all(
        [
            DEResult(
                season_id=season.id,
                event_id=event.id,
                team_id=teams[0].id,
                bracket="A",
                de_rank=1,
            ),
            DEResult(
                season_id=season.id,
                event_id=event.id,
                team_id=teams[1].id,
                bracket="A",
                de_rank=2,
            ),
            DocumentationScore(
                season_id=season.id,
                event_id=event.id,
                team_id=teams[0].id,
                part1=100.0,
                part2=100.0,
                part3=100.0,
            ),
            DocumentationScore(
                season_id=season.id,
                event_id=event.id,
                team_id=teams[1].id,
                part1=50.0,
                part2=50.0,
                part3=50.0,
            ),
            Paper(
                season_id=season.id,
                event_id=event.id,
                team_id=teams[0].id,
                title="Alpha paper",
                final_score=80.0,
            ),
        ]
    )
    await db.flush()
    return {"season": season, "event": event, "teams": teams}


class TestFormulaDrivenRanking:
    @pytest.mark.asyncio
    async def test_ranking_uses_the_documented_formulas(self, db, scored_season):
        from modules.scoring.formula_service import compute_category_ranking

        ranked, run = await compute_category_ranking(db, scored_season["event"].id, "botball")
        assert run.ok, run.issues
        assert [r["team_name"] for r in ranked] == ["Alpha", "Beta"]
        assert [r["rank"] for r in ranked] == [1, 2]

        alpha = ranked[0]
        # seed_total = avg of best two = (300 + 200) / 2
        assert alpha["seed_total"] == 250.0
        # 3/4 * ((2 - 1 + 1)/2) + 1/4 * (250 / 300)
        assert alpha["seed_score"] == pytest.approx(0.75 * 1.0 + 0.25 * (250 / 300))
        # bracket of two teams, rank 1, default weight 1.0
        assert alpha["de_score"] == pytest.approx(1.0)
        assert alpha["doc_score"] == pytest.approx(1.0)
        assert alpha["paper_score"] == pytest.approx(0.8)
        assert alpha["adapted_doc_score"] == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_seeding_score_is_normalized_not_the_raw_total(self, db, scored_season):
        """The old ranking added the raw seeding total, which swamped the 0..1 parts."""
        from modules.scoring.formula_service import compute_category_ranking

        ranked, _ = await compute_category_ranking(db, scored_season["event"].id, "botball")
        assert all(0.0 <= r["seed_score"] <= 1.0 for r in ranked)
        assert all(0.0 <= r["overall"] <= 3.0 for r in ranked)

    @pytest.mark.asyncio
    async def test_bracket_weight_scales_the_de_score(self, db, scored_season):
        from modules.scoring.formula_service import (
            compute_category_ranking,
            set_bracket_weights,
        )

        season_id = scored_season["season"].id
        await set_bracket_weights(db, season_id, "botball", {"A": 0.5})
        ranked, _ = await compute_category_ranking(db, scored_season["event"].id, "botball")
        assert ranked[0]["de_score"] == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_overall_endpoint_returns_formula_values(
        self, client, auth_headers, db, scored_season
    ):
        season = scored_season["season"]
        season.active_categories = ["botball"]
        await db.flush()

        resp = await client.get(
            f"/api/scoring/seasons/{season.id}/ranking/overall", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert [r["team_name"] for r in rows] == ["Alpha", "Beta"]
        assert rows[0]["seeding_score"] is not None
        assert "adapted_doc_score" in rows[0]["values"]


class TestFormulaEditing:
    @pytest.mark.asyncio
    async def test_effective_set_falls_back_to_the_documented_defaults(
        self, client, auth_headers, season
    ):
        resp = await client.get(
            f"/api/scoring/formulas/seasons/{season.id}/botball/effective", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        keys = [f["key"] for f in resp.json()]
        assert "seed_score" in keys and "overall" in keys

    @pytest.mark.asyncio
    async def test_saving_a_custom_set_changes_the_ranking(
        self, client, auth_headers, db, scored_season
    ):
        from modules.scoring.formula_service import compute_category_ranking

        season_id = scored_season["season"].id
        resp = await client.put(
            f"/api/scoring/formulas/seasons/{season_id}/botball",
            headers=auth_headers,
            json={
                "formulas": [
                    {"key": "seed_total", "expression": "avg_best(seed_runs, 2)"},
                    {"key": "overall", "expression": "seed_total / 1000"},
                ]
            },
        )
        assert resp.status_code == 200, resp.text

        ranked, run = await compute_category_ranking(db, scored_season["event"].id, "botball")
        assert run.ok, run.issues
        assert ranked[0]["overall"] == pytest.approx(0.25)

    @pytest.mark.asyncio
    async def test_invalid_formula_is_rejected_before_anything_is_saved(
        self, client, auth_headers, season
    ):
        resp = await client.put(
            f"/api/scoring/formulas/seasons/{season.id}/botball",
            headers=auth_headers,
            json={"formulas": [{"key": "overall", "expression": "__import__('os')"}]},
        )
        assert resp.status_code == 400
        assert "__import__" in resp.json()["message"]

        # nothing was written
        listed = await client.get(
            f"/api/scoring/formulas/seasons/{season.id}", headers=auth_headers
        )
        assert listed.json() == []

    @pytest.mark.asyncio
    async def test_cycle_is_rejected(self, client, auth_headers, season):
        resp = await client.put(
            f"/api/scoring/formulas/seasons/{season.id}/botball",
            headers=auth_headers,
            json={
                "formulas": [
                    {"key": "a", "expression": "b + 1"},
                    {"key": "b", "expression": "a + 1"},
                ]
            },
        )
        assert resp.status_code == 400
        assert "cycle" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_preview_runs_against_real_data_without_saving(
        self, client, auth_headers, scored_season
    ):
        event_id = scored_season["event"].id
        resp = await client.post(
            f"/api/scoring/formulas/events/{event_id}/botball/preview",
            headers=auth_headers,
            json={
                "formulas": [
                    {"key": "seed_total", "expression": "avg_best(seed_runs, 2)"},
                    {"key": "overall", "expression": "seed_total"},
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["order"] == ["seed_total", "overall"]
        assert body["rows"][0]["values"]["overall"] == 250.0

        # preview must not persist anything
        listed = await client.get(
            f"/api/scoring/formulas/seasons/{scored_season['season'].id}", headers=auth_headers
        )
        assert listed.json() == []

    @pytest.mark.asyncio
    async def test_preview_reports_errors_instead_of_failing(
        self, client, auth_headers, scored_season
    ):
        resp = await client.post(
            f"/api/scoring/formulas/events/{scored_season['event'].id}/botball/preview",
            headers=auth_headers,
            json={"formulas": [{"key": "overall", "expression": "1 +"}]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is False
        assert "Syntax error" in body["issues"][0]["message"]

    @pytest.mark.asyncio
    async def test_reset_restores_the_documented_defaults(self, client, auth_headers, season):
        await client.put(
            f"/api/scoring/formulas/seasons/{season.id}/botball",
            headers=auth_headers,
            json={"formulas": [{"key": "overall", "expression": "1"}]},
        )
        resp = await client.post(
            f"/api/scoring/formulas/seasons/{season.id}/botball/reset", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert [f["key"] for f in resp.json()][0] == "seed_total"

    @pytest.mark.asyncio
    async def test_reference_lists_functions_and_defaults(self, client, auth_headers):
        resp = await client.get("/api/scoring/formulas/reference", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "seed_runs" in body["inputs"]
        assert any(f["name"] == "avg_best" for f in body["row_functions"])
        assert any(f["name"] == "rank" for f in body["scope_functions"])
        assert "botball" in body["defaults"]
