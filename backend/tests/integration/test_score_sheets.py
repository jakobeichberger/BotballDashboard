"""Regression tests for the score sheet template routes.

The route/query params were typed as `uuid.UUID` while the columns are
`String(36)`. SQLAlchemy then bound the 32-char undashed hex against the
36-char dashed ids actually stored, so every lookup silently matched nothing:
list endpoints returned [] and detail endpoints 404'd even though the row
existed.
"""

import pytest


@pytest.fixture
async def template(db, season, admin_user):
    from modules.scoring.score_sheets.models import ScoreSheetTemplate

    t = ScoreSheetTemplate(
        season_id=season.id,
        label="Botball 2026 Score Sheet",
        year=2026,
        file_url="/tmp/sheet.pdf",
        file_name="sheet.pdf",
        uploaded_by=admin_user.id,
        ocr_status="done",
    )
    db.add(t)
    await db.flush()
    return t


class TestScoreSheetLookup:
    @pytest.mark.asyncio
    async def test_list_finds_existing_template(self, client, auth_headers, season, template):
        resp = await client.get(
            f"/api/scoring/seasons/{season.id}/score-sheets", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 1, "template exists but the season_id lookup did not match it"
        assert rows[0]["label"] == "Botball 2026 Score Sheet"

    @pytest.mark.asyncio
    async def test_get_detail_finds_existing_template(self, client, auth_headers, template):
        resp = await client.get(f"/api/scoring/score-sheets/{template.id}", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["label"] == "Botball 2026 Score Sheet"
