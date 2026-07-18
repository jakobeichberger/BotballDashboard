"""
Unit tests for the score-sheet template service (non-OCR parts).

Covers:
  - create_template (initial state: ocr_status=pending, is_active=False)
  - list_templates (ordering, level filtering)
  - get_template (found / not found)
  - set_active_template (deactivates siblings, activates chosen)
  - delete_template (removes row + file)
  - confirm_fields (writes confirmed_fields, confirmed_by/at; apply_to_schema upsert)
  - run_ocr_pipeline status transitions (text extraction stubbed; no poppler needed)
  - field-detection helpers that need no external binaries
"""

import uuid
from pathlib import Path

import pytest

from modules.scoring.score_sheets import service as svc
from modules.scoring.score_sheets.schemas import ScoringField

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_template(
    db, season, admin_user, tmp_path, label="Sheet", active=False, level_id=None
):
    pdf = tmp_path / f"{uuid.uuid4()}.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")
    tpl = await svc.create_template(
        db=db,
        season_id=season.id,
        competition_level_id=level_id,
        label=label,
        year=2026,
        game_theme="Test Theme",
        file_path=pdf,
        file_size=pdf.stat().st_size,
        uploaded_by=admin_user.id,
    )
    if active:
        tpl.is_active = True
        await db.commit()
        await db.refresh(tpl)
    return tpl


# ── Field-detection helpers (no poppler required) ─────────────────────────────


class TestFieldHelpers:
    def test_to_snake_case(self):
        assert svc._to_snake_case("Sorted Poms") == "sorted_poms"
        assert svc._to_snake_case("Solar Panel  Flipped!") == "solar_panel_flipped"

    def test_extract_multiplier_x_notation(self):
        assert svc._extract_multiplier("Botguy ×15") == 15.0
        assert svc._extract_multiplier("Cubes x10") == 10.0

    def test_extract_multiplier_pts_notation(self):
        assert svc._extract_multiplier("Solar Panel Flipped 50 pts") == 50.0
        assert svc._extract_multiplier("Bonus 10 points") == 10.0

    def test_extract_multiplier_none(self):
        assert svc._extract_multiplier("Just a label") is None

    def test_detect_fields_from_text(self):
        # "Area 1" is a section header; the two ×-lines are scoring fields.
        # (Lines beginning with a section keyword like "solar"/"habitat" are
        # themselves treated as section headers, so we avoid those here.)
        raw = "Area 1\n" "Sorted Poms ×5\n" "Botguy ×15\n" "page 1\n"
        candidates = svc.detect_fields(raw)
        keys = {c.suggested_key for c in candidates}
        assert "sorted_poms" in keys
        assert "botguy" in keys
        # The "page 1" ignore line is filtered out
        assert "page_1" not in keys
        sorted_poms = next(c for c in candidates if c.suggested_key == "sorted_poms")
        assert sorted_poms.suggested_multiplier == 5.0
        # multiplier + section → confidence 0.4+0.4+0.2 = 1.0 → auto-accepted
        assert sorted_poms.confidence == 1.0
        assert sorted_poms.accepted is True

    def test_section_keyword_line_is_treated_as_header(self):
        # A line that starts with a section keyword is consumed as a section
        # header, not emitted as a scoring field even if it has a multiplier.
        raw = "Solar Panel Flipped 50 pts\nSorted Poms ×5\n"
        candidates = svc.detect_fields(raw)
        keys = {c.suggested_key for c in candidates}
        assert "solar_panel_flipped" not in keys
        assert "sorted_poms" in keys
        # The poms field inherits the "Solar Panel Flipped" section → conf 1.0
        poms = next(c for c in candidates if c.suggested_key == "sorted_poms")
        assert poms.confidence == 1.0

    def test_detect_fields_dedupes_keys(self):
        raw = "Area 1\nSorted Poms ×5\nSorted Poms ×9\n"
        candidates = svc.detect_fields(raw)
        keys = [c.suggested_key for c in candidates]
        assert keys.count("sorted_poms") == 1

    def test_detect_fields_empty(self):
        assert svc.detect_fields("") == []


# ── create_template ───────────────────────────────────────────────────────────


class TestCreateTemplate:
    @pytest.mark.asyncio
    async def test_initial_state(self, db, season, admin_user, tmp_path):
        tpl = await _make_template(db, season, admin_user, tmp_path, label="ECER 2026")
        assert tpl.id is not None
        assert tpl.label == "ECER 2026"
        assert tpl.year == 2026
        assert tpl.is_active is False
        assert tpl.ocr_status == "pending"
        assert tpl.confirmed_fields is None
        assert tpl.uploaded_by == admin_user.id
        assert tpl.file_name.endswith(".pdf")


# ── list_templates ────────────────────────────────────────────────────────────


class TestListTemplates:
    @pytest.mark.asyncio
    async def test_lists_for_season(self, db, season, admin_user, tmp_path):
        await _make_template(db, season, admin_user, tmp_path, label="A")
        await _make_template(db, season, admin_user, tmp_path, label="B")
        templates = await svc.list_templates(db, season.id)
        assert len(templates) == 2

    @pytest.mark.asyncio
    async def test_other_season_excluded(self, db, season, admin_user, tmp_path):
        await _make_template(db, season, admin_user, tmp_path)
        assert await svc.list_templates(db, "other-season-id") == []

    @pytest.mark.asyncio
    async def test_level_filter(self, db, season, admin_user, tmp_path):
        from modules.seasons.models import CompetitionLevel

        level = CompetitionLevel(name="ECER", code="ECER")
        db.add(level)
        await db.flush()

        await _make_template(db, season, admin_user, tmp_path, label="NoLevel")
        await _make_template(db, season, admin_user, tmp_path, label="Leveled", level_id=level.id)

        leveled = await svc.list_templates(db, season.id, competition_level_id=level.id)
        assert len(leveled) == 1
        assert leveled[0].label == "Leveled"


# ── get_template ──────────────────────────────────────────────────────────────


class TestGetTemplate:
    @pytest.mark.asyncio
    async def test_found(self, db, season, admin_user, tmp_path):
        tpl = await _make_template(db, season, admin_user, tmp_path)
        fetched = await svc.get_template(db, tpl.id)
        assert fetched is not None
        assert fetched.id == tpl.id

    @pytest.mark.asyncio
    async def test_not_found(self, db):
        assert await svc.get_template(db, str(uuid.uuid4())) is None


# ── set_active_template ───────────────────────────────────────────────────────


class TestSetActive:
    @pytest.mark.asyncio
    async def test_activates_one_deactivates_others(self, db, season, admin_user, tmp_path):
        a = await _make_template(db, season, admin_user, tmp_path, label="A", active=True)
        b = await _make_template(db, season, admin_user, tmp_path, label="B")

        await svc.set_active_template(db, season.id, None, b.id)

        await db.refresh(a)
        await db.refresh(b)
        assert a.is_active is False
        assert b.is_active is True

    @pytest.mark.asyncio
    async def test_only_affects_same_season_level(self, db, season, admin_user, tmp_path):
        from modules.seasons.models import CompetitionLevel

        level = CompetitionLevel(name="GCER", code="GCER")
        db.add(level)
        await db.flush()

        no_level = await _make_template(
            db, season, admin_user, tmp_path, label="NoLevel", active=True
        )
        leveled = await _make_template(
            db, season, admin_user, tmp_path, label="Leveled", level_id=level.id
        )

        # Activate the leveled one; the NULL-level template must stay active
        await svc.set_active_template(db, season.id, level.id, leveled.id)

        await db.refresh(no_level)
        await db.refresh(leveled)
        assert leveled.is_active is True
        assert no_level.is_active is True


# ── delete_template ───────────────────────────────────────────────────────────


class TestDeleteTemplate:
    @pytest.mark.asyncio
    async def test_deletes_row_and_file(self, db, season, admin_user, tmp_path):
        tpl = await _make_template(db, season, admin_user, tmp_path)
        file_path = Path(tpl.file_url)
        assert file_path.exists()

        await svc.delete_template(db, tpl.id)

        assert await svc.get_template(db, tpl.id) is None
        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_missing_is_noop(self, db):
        # Should not raise even if the template does not exist
        await svc.delete_template(db, str(uuid.uuid4()))


# ── confirm_fields ────────────────────────────────────────────────────────────


class TestConfirmFields:
    @pytest.mark.asyncio
    async def test_confirms_without_schema(self, db, season, admin_user, tmp_path):
        tpl = await _make_template(db, season, admin_user, tmp_path)
        fields = [
            ScoringField(key="sorted_poms", label="Sorted Poms", multiplier=5.0),
            ScoringField(key="botguy", label="Botguy", multiplier=15.0),
        ]
        result = await svc.confirm_fields(
            db, tpl.id, fields, confirmed_by=admin_user.id, apply_to_schema=False
        )
        assert result.confirmed_by == admin_user.id
        assert result.confirmed_at is not None
        assert len(result.confirmed_fields) == 2
        assert result.confirmed_fields[0]["key"] == "sorted_poms"

    @pytest.mark.asyncio
    async def test_apply_to_schema_creates_scoring_schema(self, db, season, admin_user, tmp_path):
        """confirm_fields(apply_to_schema=True) writes the confirmed fields to a
        ScoringSchema row for the template's season + level.
        """
        from sqlalchemy import select

        from modules.scoring.models import ScoringSchema

        tpl = await _make_template(db, season, admin_user, tmp_path)
        fields = [ScoringField(key="cubes", label="Cubes", multiplier=2.0)]

        result = await svc.confirm_fields(
            db, tpl.id, fields, confirmed_by=admin_user.id, apply_to_schema=True
        )
        assert result.confirmed_by == admin_user.id

        # A ScoringSchema row was created from the confirmed fields.
        res = await db.execute(select(ScoringSchema).where(ScoringSchema.season_id == season.id))
        schemas = res.scalars().all()
        assert len(schemas) == 1
        assert schemas[0].fields[0]["key"] == "cubes"


# ── run_ocr_pipeline (status transitions, text extraction stubbed) ────────────


class TestOcrPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_marks_done(self, db, season, admin_user, tmp_path, monkeypatch):
        tpl = await _make_template(db, season, admin_user, tmp_path)

        # Stub the poppler-dependent text extraction
        monkeypatch.setattr(
            svc,
            "extract_text_from_pdf",
            lambda path: "Area 1\nSorted Poms ×5\n",
        )

        await svc.run_ocr_pipeline(db, tpl.id)

        await db.refresh(tpl)
        assert tpl.ocr_status == "done"
        assert tpl.raw_text == "Area 1\nSorted Poms ×5\n"
        assert tpl.extracted_fields is not None
        keys = {f["suggested_key"] for f in tpl.extracted_fields}
        assert "sorted_poms" in keys

    @pytest.mark.asyncio
    async def test_pipeline_marks_failed_on_error(
        self, db, season, admin_user, tmp_path, monkeypatch
    ):
        tpl = await _make_template(db, season, admin_user, tmp_path)

        def boom(path):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(svc, "extract_text_from_pdf", boom)

        await svc.run_ocr_pipeline(db, tpl.id)

        await db.refresh(tpl)
        assert tpl.ocr_status == "failed"
        assert "kaboom" in (tpl.ocr_error or "")

    @pytest.mark.asyncio
    async def test_pipeline_missing_template_is_noop(self, db):
        # Unknown id → returns without raising
        await svc.run_ocr_pipeline(db, str(uuid.uuid4()))
