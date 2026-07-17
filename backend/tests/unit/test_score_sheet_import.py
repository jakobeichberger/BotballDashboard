"""Regression tests for score-sheet schema application and secure PDF storage."""

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from starlette.datastructures import Headers

from modules.paper_review import service as paper_service
from modules.scoring.models import ScoringSchema
from modules.scoring.score_sheets.models import ScoreSheetTemplate
from modules.scoring.score_sheets.schemas import ScoringField
from modules.scoring.score_sheets.service import confirm_fields


@pytest.mark.asyncio
async def test_confirmed_sheet_applies_to_competition_level_schema(db, season, admin_user):
    template = ScoreSheetTemplate(
        season_id=season.id,
        competition_level_id=None,
        label="Official sheet",
        year=season.year,
        is_active=False,
        file_url="/tmp/official.pdf",
        file_name="official.pdf",
        ocr_status="done",
        uploaded_by=admin_user.id,
    )
    db.add(template)
    await db.flush()

    fields = [ScoringField(key="objects", label="Objects", multiplier=2.0)]
    await confirm_fields(db, template.id, fields, admin_user.id, apply_to_schema=True)

    result = await db.execute(
        select(ScoringSchema).where(
            ScoringSchema.season_id == season.id,
            ScoringSchema.competition_level_id.is_(None),
        )
    )
    schema = result.scalar_one()
    assert schema.fields[0]["key"] == "objects"
    assert schema.fields[0]["multiplier"] == 2.0


@pytest.mark.asyncio
async def test_paper_upload_sanitizes_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(paper_service.settings, "upload_dir", str(tmp_path))
    upload = UploadFile(
        filename="../unsafe paper.pdf",
        file=BytesIO(b"%PDF-1.4\nfixture"),
        headers=Headers({"content-type": "application/pdf"}),
    )

    stored_path, stored_name, size = await paper_service.save_file(upload, "paper-id")

    path = Path(stored_path)
    assert path.parent == tmp_path / "papers" / "paper-id"
    assert stored_name == "unsafe_paper.pdf"
    assert path.read_bytes().startswith(b"%PDF-")
    assert size == len(b"%PDF-1.4\nfixture")


@pytest.mark.asyncio
async def test_paper_upload_rejects_fake_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(paper_service.settings, "upload_dir", str(tmp_path))
    upload = UploadFile(
        filename="fake.pdf",
        file=BytesIO(b"not a pdf"),
        headers=Headers({"content-type": "application/pdf"}),
    )

    with pytest.raises(HTTPException, match="not a PDF"):
        await paper_service.save_file(upload, "paper-id")

    assert not list((tmp_path / "papers" / "paper-id").glob("*.upload"))
