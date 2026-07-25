"""Safety invariants for local OCR review and template geometry."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from core.exceptions import ConflictError
from modules.scoring.score_sheets.models import ScoreSheetScan
from modules.scoring.score_sheets.scan_service import accept_scan
from modules.scoring.score_sheets.schemas import OcrFieldRegion


def test_normalized_regions_must_fit_on_the_page():
    with pytest.raises(PydanticValidationError):
        OcrFieldRegion(key="objects", x=0.9, y=0.1, width=0.2, height=0.2)


@pytest.mark.asyncio
async def test_unreviewed_scan_can_never_create_an_official_score(db, event, team, admin_user):
    scan = ScoreSheetScan(
        event_id=event.id,
        template_id="template-id",
        team_id=team.id,
        file_url="/tmp/anonymized-score-sheet.png",
        file_name="anonymized-score-sheet.png",
        status="queued",
        created_by=admin_user.id,
        extracted_values=[
            {
                "key": "objects",
                "value": 4,
                "confidence": 0.4,
                "requiresReview": True,
            }
        ],
    )
    with pytest.raises(ConflictError, match="not ready for review"):
        await accept_scan(db, scan, {"objects": 4}, admin_user.id, None)
