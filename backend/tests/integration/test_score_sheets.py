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


class TestScoreSheetLayout:
    FIELDS = [
        {"key": "cubes", "label": "Cubes", "multiplier": 1, "type": "count"},
        {"key": "rings", "label": "Rings", "multiplier": 1, "type": "count"},
    ]

    def _layout(self, **overrides):
        body = {
            "page_width": 1000,
            "page_height": 1400,
            "anchors": [
                {"name": "top_left", "x": 0.02, "y": 0.02, "width": 0.03, "height": 0.02},
                {"name": "bottom_right", "x": 950, "y": 1360, "width": 30, "height": 30},
            ],
            "field_regions": [{"key": "cubes", "x": 0.1, "y": 0.2, "width": 0.1, "height": 0.05}],
            "validation_rules": {
                "min_confidence": 0.7,
                "fields": [{"key": "cubes", "max_value": 12, "integer": True}],
                "sums": [{"label": "Objects", "keys": ["cubes", "rings"], "max_value": 20}],
            },
        }
        body.update(overrides)
        return body

    @pytest.mark.asyncio
    async def test_anchors_and_rules_are_stored(self, client, auth_headers, db, template):
        template.confirmed_fields = self.FIELDS
        await db.flush()
        resp = await client.patch(
            f"/api/scoring/score-sheets/{template.id}/layout",
            json=self._layout(),
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert [a["name"] for a in data["anchors"]] == ["top_left", "bottom_right"]
        assert data["validation_rules"]["min_confidence"] == 0.7
        assert data["validation_rules"]["fields"][0] == {
            "key": "cubes",
            "min_value": None,
            "max_value": 12,
            "integer": True,
            "min_confidence": None,
        }
        assert data["validation_rules"]["sums"][0]["keys"] == ["cubes", "rings"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "overrides",
        [
            # Rules for a field the template does not have.
            {"validation_rules": {"fields": [{"key": "ghost", "max_value": 1}]}},
            {
                "validation_rules": {
                    "sums": [{"label": "S", "keys": ["cubes", "ghost"], "max_value": 1}]
                }
            },
            # Anchors outside the page (pixels and normalized), duplicate names.
            {"anchors": [{"name": "a", "x": 990, "y": 10, "width": 30, "height": 30}]},
            {"anchors": [{"name": "a", "x": 0.99, "y": 0.1, "width": 0.05, "height": 0.05}]},
            {
                "anchors": [
                    {"name": "a", "x": 0.1, "y": 0.1, "width": 0.05, "height": 0.05},
                    {"name": "a", "x": 0.8, "y": 0.1, "width": 0.05, "height": 0.05},
                ]
            },
        ],
    )
    async def test_inconsistent_layouts_are_rejected(
        self, client, auth_headers, db, template, overrides
    ):
        template.confirmed_fields = self.FIELDS
        await db.flush()
        resp = await client.patch(
            f"/api/scoring/score-sheets/{template.id}/layout",
            json=self._layout(**overrides),
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
