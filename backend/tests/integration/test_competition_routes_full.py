"""
Integration tests for competition-scoring + score-sheet routes.

Competition routes (under /api/scoring):
  - PUT  /seasons/{sid}/de-results/{team_id}   upsert single (team_id from path)
  - PUT  /seasons/{sid}/de-results             bulk upsert
  - GET  /seasons/{sid}/de-results             list
  - PUT  /seasons/{sid}/aerial-results/{team_id}, bulk, GET, aerial-ranking
  - PUT  /seasons/{sid}/doc-scores/{team_id}, bulk, GET
  - GET  /seasons/{sid}/ranking/overall        combined ranking
  - validation (bad bracket → 422), auth (401)

Score-sheet routes:
  - GET  list / get / 404
  - PUT  active / 404 / 409 (active)
  - POST confirm / 404 / 400 empty
  - DELETE / 404
"""

import io

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────


@pytest.fixture
async def comp_season(db):
    """Season with all competition modules enabled."""
    from modules.seasons.models import Season

    s = Season(
        name="Comp Season",
        year=2026,
        is_active=True,
        use_seeding=False,
        use_double_elimination=True,
        use_paper_scoring=False,
        use_documentation_scoring=True,
        use_aerial=True,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def _register(db, season_id, name):
    from modules.teams.models import Team, TeamSeasonRegistration

    t = Team(name=name, country="DE")
    db.add(t)
    await db.flush()
    db.add(TeamSeasonRegistration(team_id=t.id, season_id=season_id, category="botball"))
    await db.commit()
    await db.refresh(t)
    return t


def _minimal_pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n" b"trailer<</Root 1 0 R>>\n%%EOF\n"


# ── Double Elimination routes ─────────────────────────────────────────────────


class TestDERoutes:
    @pytest.mark.asyncio
    async def test_upsert_single_team_id_from_path(self, client, auth_headers, comp_season, team):
        resp = await client.put(
            f"/api/scoring/seasons/{comp_season.id}/de-results/{team.id}",
            headers=auth_headers,
            json={"bracket": "a", "de_rank": 1, "de_score": 1.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["team_id"] == team.id  # taken from path, not body
        assert data["bracket"] == "A"  # normalized to upper
        assert data["de_rank"] == 1

    @pytest.mark.asyncio
    async def test_upsert_then_update_idempotent_in_db(
        self, client, auth_headers, comp_season, team, db
    ):
        """Re-submitting the same team updates in place (no duplicate row).

        Both the insert and the update path serialize correctly (the service
        flushes and refreshes the row so ``updated_at`` is populated).
        """
        from modules.scoring import competition_service as comp_svc

        url = f"/api/scoring/seasons/{comp_season.id}/de-results/{team.id}"
        first = await client.put(url, headers=auth_headers, json={"bracket": "A", "de_rank": 1})
        assert first.status_code == 200
        assert first.json()["bracket"] == "A"

        second = await client.put(url, headers=auth_headers, json={"bracket": "B", "de_rank": 5})
        assert second.status_code == 200
        assert second.json()["bracket"] == "B"
        assert second.json()["de_rank"] == 5

        rows = await comp_svc.get_de_results(db, comp_season.id)
        assert len(rows) == 1  # updated in place, not duplicated
        assert rows[0].bracket == "B"
        assert rows[0].de_rank == 5

    @pytest.mark.asyncio
    async def test_invalid_bracket_422(self, client, auth_headers, comp_season, team):
        resp = await client.put(
            f"/api/scoring/seasons/{comp_season.id}/de-results/{team.id}",
            headers=auth_headers,
            json={"bracket": "Z"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_bulk_upsert_computes_bracket_scores(self, client, auth_headers, comp_season, db):
        t1 = await _register(db, comp_season.id, "T1")
        t2 = await _register(db, comp_season.id, "T2")
        t3 = await _register(db, comp_season.id, "T3")
        resp = await client.put(
            f"/api/scoring/seasons/{comp_season.id}/de-results",
            headers=auth_headers,
            json=[
                {"team_id": t1.id, "bracket": "A", "de_rank": 1},
                {"team_id": t2.id, "bracket": "A", "de_rank": 2},
                {"team_id": t3.id, "bracket": "A", "de_rank": 3},
            ],
        )
        assert resp.status_code == 200
        by_team = {r["team_id"]: r for r in resp.json()}
        assert by_team[t1.id]["bracket_score"] == 1.0
        assert by_team[t2.id]["bracket_score"] == 0.5
        assert by_team[t3.id]["bracket_score"] == 0.0

    @pytest.mark.asyncio
    async def test_requires_auth(self, client, comp_season, team):
        resp = await client.put(
            f"/api/scoring/seasons/{comp_season.id}/de-results/{team.id}",
            json={"bracket": "A"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_empty(self, client, auth_headers, comp_season):
        resp = await client.get(
            f"/api/scoring/seasons/{comp_season.id}/de-results", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ── Aerial routes ─────────────────────────────────────────────────────────────


class TestAerialRoutes:
    @pytest.mark.asyncio
    async def test_upsert_best_two_score(self, client, auth_headers, comp_season, team):
        resp = await client.put(
            f"/api/scoring/seasons/{comp_season.id}/aerial-results/{team.id}",
            headers=auth_headers,
            json={"run1": 10.0, "run2": 4.0, "run3": 8.0, "run4": 2.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["team_id"] == team.id
        assert data["score"] == 9.0  # (10 + 8) / 2

    @pytest.mark.asyncio
    async def test_bulk_and_ranking(self, client, auth_headers, comp_season, db):
        t1 = await _register(db, comp_season.id, "Low")
        t2 = await _register(db, comp_season.id, "High")
        await client.put(
            f"/api/scoring/seasons/{comp_season.id}/aerial-results",
            headers=auth_headers,
            json=[
                {"team_id": t1.id, "run1": 2.0, "run2": 2.0},
                {"team_id": t2.id, "run1": 10.0, "run2": 8.0},
            ],
        )
        ranking = await client.get(f"/api/scoring/seasons/{comp_season.id}/aerial-ranking")
        assert ranking.status_code == 200
        rows = ranking.json()
        assert rows[0]["team_id"] == t2.id
        assert rows[0]["rank"] == 1
        assert rows[0]["team_name"] == "High"

    @pytest.mark.asyncio
    async def test_list_aerial_results(self, client, auth_headers, comp_season, team):
        await client.put(
            f"/api/scoring/seasons/{comp_season.id}/aerial-results/{team.id}",
            headers=auth_headers,
            json={"run1": 5.0},
        )
        resp = await client.get(
            f"/api/scoring/seasons/{comp_season.id}/aerial-results", headers=auth_headers
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ── Documentation routes ──────────────────────────────────────────────────────


class TestDocRoutes:
    @pytest.mark.asyncio
    async def test_upsert_doc_score(self, client, auth_headers, comp_season, team):
        resp = await client.put(
            f"/api/scoring/seasons/{comp_season.id}/doc-scores/{team.id}",
            headers=auth_headers,
            json={"part1": 90.0, "part2": 60.0, "part3": 30.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["team_id"] == team.id
        assert data["doc_score"] == pytest.approx(0.6)

    @pytest.mark.asyncio
    async def test_bulk_doc_ranking(self, client, auth_headers, comp_season, db):
        t1 = await _register(db, comp_season.id, "Worse")
        t2 = await _register(db, comp_season.id, "Better")
        resp = await client.put(
            f"/api/scoring/seasons/{comp_season.id}/doc-scores",
            headers=auth_headers,
            json=[
                {"team_id": t1.id, "part1": 40.0},
                {"team_id": t2.id, "part1": 90.0},
            ],
        )
        assert resp.status_code == 200
        by_team = {r["team_id"]: r for r in resp.json()}
        assert by_team[t2.id]["doc_rank"] == 1
        assert by_team[t1.id]["doc_rank"] == 2

    @pytest.mark.asyncio
    async def test_list_doc_scores(self, client, auth_headers, comp_season, team):
        await client.put(
            f"/api/scoring/seasons/{comp_season.id}/doc-scores/{team.id}",
            headers=auth_headers,
            json={"part1": 80.0},
        )
        resp = await client.get(
            f"/api/scoring/seasons/{comp_season.id}/doc-scores", headers=auth_headers
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ── Overall ranking route ─────────────────────────────────────────────────────


class TestOverallRankingRoute:
    @pytest.mark.asyncio
    async def test_overall_combines_modules(self, client, auth_headers, comp_season, db):
        t1 = await _register(db, comp_season.id, "T1")
        t2 = await _register(db, comp_season.id, "T2")
        await client.put(
            f"/api/scoring/seasons/{comp_season.id}/de-results/{t1.id}",
            headers=auth_headers,
            json={"bracket": "A", "de_rank": 2},
        )
        await client.put(
            f"/api/scoring/seasons/{comp_season.id}/de-results/{t2.id}",
            headers=auth_headers,
            json={"bracket": "A", "de_rank": 1},
        )
        await client.put(
            f"/api/scoring/seasons/{comp_season.id}/doc-scores/{t1.id}",
            headers=auth_headers,
            json={"part1": 100.0},
        )
        await client.put(
            f"/api/scoring/seasons/{comp_season.id}/doc-scores/{t2.id}",
            headers=auth_headers,
            json={"part1": 10.0},
        )
        resp = await client.get(f"/api/scoring/seasons/{comp_season.id}/ranking/overall")
        assert resp.status_code == 200
        entries = resp.json()
        by_team = {e["team_id"]: e for e in entries}
        # Ranking now follows the game document rather than summing whatever
        # was stored: DE comes from the bracket rank, documentation from the
        # period scores, and both teams tie on (empty) seeding.
        #   seeding 0.75 (tie, no runs)
        #   t1: DE (2-2+1)/2 = 0.5,  doc 100/300 -> adapted 0.5*1/3
        #   t2: DE (2-1+1)/2 = 1.0,  doc  10/300 -> adapted 0.5*1/30
        assert by_team[t1.id]["overall_score"] == pytest.approx(0.75 + 0.5 + (100 / 300) / 2)
        assert by_team[t2.id]["overall_score"] == pytest.approx(0.75 + 1.0 + (10 / 300) / 2)
        assert by_team[t2.id]["rank"] == 1
        assert by_team[t1.id]["rank"] == 2

    @pytest.mark.asyncio
    async def test_overall_category_filter(self, client, auth_headers, comp_season, db):
        await _register(db, comp_season.id, "T1")
        resp = await client.get(
            f"/api/scoring/seasons/{comp_season.id}/ranking/overall",
            params={"category": "open"},  # no team registered as 'open'
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ── Score-sheet routes ────────────────────────────────────────────────────────


@pytest.fixture
async def score_sheet(db, season, admin_user, tmp_path):
    """Create a score-sheet template directly via the service for route tests."""
    from modules.scoring.score_sheets import service as ss_svc

    pdf = tmp_path / "sheet.pdf"
    pdf.write_bytes(_minimal_pdf())
    tpl = await ss_svc.create_template(
        db=db,
        season_id=season.id,
        competition_level_id=None,
        label="ECER 2026",
        year=2026,
        game_theme="Theme",
        file_path=pdf,
        file_size=pdf.stat().st_size,
        uploaded_by=admin_user.id,
    )
    return tpl


class TestScoreSheetRoutes:
    @pytest.mark.asyncio
    async def test_list(self, client, auth_headers, season, score_sheet):
        resp = await client.get(
            f"/api/scoring/seasons/{season.id}/score-sheets", headers=auth_headers
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["label"] == "ECER 2026"
        assert rows[0]["ocr_status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_one(self, client, auth_headers, score_sheet):
        resp = await client.get(f"/api/scoring/score-sheets/{score_sheet.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == str(score_sheet.id)

    @pytest.mark.asyncio
    async def test_get_404(self, client, auth_headers):
        resp = await client.get(
            "/api/scoring/score-sheets/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_set_active(self, client, auth_headers, db, score_sheet):
        resp = await client.put(
            f"/api/scoring/score-sheets/{score_sheet.id}/active", headers=auth_headers
        )
        assert resp.status_code == 204
        await db.refresh(score_sheet)
        assert score_sheet.is_active is True

    @pytest.mark.asyncio
    async def test_set_active_404(self, client, auth_headers):
        resp = await client.put(
            "/api/scoring/score-sheets/00000000-0000-0000-0000-000000000000/active",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_confirm_fields(self, client, auth_headers, score_sheet):
        resp = await client.post(
            f"/api/scoring/score-sheets/{score_sheet.id}/confirm",
            headers=auth_headers,
            json={
                "fields": [
                    {"key": "cubes", "label": "Cubes", "multiplier": 2.0},
                ],
                "apply_to_schema": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["confirmed_fields"][0]["key"] == "cubes"
        assert data["confirmed_by"] is not None

    @pytest.mark.asyncio
    async def test_confirm_empty_fields_400(self, client, auth_headers, score_sheet):
        resp = await client.post(
            f"/api/scoring/score-sheets/{score_sheet.id}/confirm",
            headers=auth_headers,
            json={"fields": [], "apply_to_schema": False},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_404(self, client, auth_headers):
        resp = await client.post(
            "/api/scoring/score-sheets/00000000-0000-0000-0000-000000000000/confirm",
            headers=auth_headers,
            json={"fields": [{"key": "k", "label": "L"}], "apply_to_schema": False},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete(self, client, auth_headers, score_sheet):
        resp = await client.delete(
            f"/api/scoring/score-sheets/{score_sheet.id}", headers=auth_headers
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_active_409(self, client, auth_headers, db, score_sheet):
        score_sheet.is_active = True
        await db.commit()
        resp = await client.delete(
            f"/api/scoring/score-sheets/{score_sheet.id}", headers=auth_headers
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_404(self, client, auth_headers):
        resp = await client.delete(
            "/api/scoring/score-sheets/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_non_pdf_400(self, client, auth_headers, season):
        resp = await client.post(
            f"/api/scoring/seasons/{season.id}/score-sheets",
            headers=auth_headers,
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
            data={"label": "Bad", "year": "2026"},
        )
        assert resp.status_code == 400
