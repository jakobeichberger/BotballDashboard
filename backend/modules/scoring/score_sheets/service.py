"""
Score Sheet Import – Business Logic

Pipeline:
  1. Admin uploads PDF  →  stored to disk / object storage
  2. Background task: pdftotext extracts raw text
  3. Field parser tries to detect scoring fields (label + multiplier)
  4. Results stored as `extracted_fields` (candidates)
  5. Admin reviews candidates, edits if needed, confirms
  6. Confirmed fields optionally applied to ScoringSchema for the season/level
"""

from __future__ import annotations

import re
import subprocess
import unicodedata
import uuid
from datetime import UTC
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.logging import get_logger

from .models import ScoreSheetTemplate
from .schemas import ExtractedFieldCandidate, ScoringField

logger = get_logger("scoring.score_sheets")

# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


async def save_upload(file: UploadFile, season_id: uuid.UUID) -> tuple[Path, int]:
    """Save the uploaded PDF to disk and return (path, size_bytes)."""
    dest_dir = Path(get_settings().upload_dir) / "score_sheets" / str(season_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    original_name = Path(file.filename or "score-sheet.pdf").name
    original_name = re.sub(r"[^A-Za-z0-9._-]", "_", original_name)
    safe_name = f"{uuid.uuid4()}_{original_name}"
    dest = dest_dir / safe_name

    content = await file.read()
    dest.write_bytes(content)

    logger.info(
        "score_sheet_uploaded",
        extra={"season_id": str(season_id), "file": safe_name, "size": len(content)},
    )
    return dest, len(content)


# ---------------------------------------------------------------------------
# OCR / text extraction
# ---------------------------------------------------------------------------


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Use pdftotext (poppler-utils) to extract text from the PDF.
    Falls back to an empty string on error.
    """
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(
                "pdftotext_failed",
                extra={"file": str(pdf_path), "stderr": result.stderr[:500]},
            )
            return ""
        return result.stdout
    except FileNotFoundError:
        logger.error("pdftotext_not_found", extra={"hint": "install poppler-utils"})
        return ""
    except subprocess.TimeoutExpired:
        logger.error("pdftotext_timeout", extra={"file": str(pdf_path)})
        return ""


# ---------------------------------------------------------------------------
# Field detection
# ---------------------------------------------------------------------------

# Patterns that typically appear next to scoring fields in Botball sheets:
#   "Sorted Poms   ×5"   |   "Solar Panel Flipped   50 pts"   |   "Botguy   ×15"
_MULTIPLIER_PATTERNS = [
    re.compile(r"[×x\*]\s*(\d+(?:\.\d+)?)"),  # ×5, x10, *3
    re.compile(r"(\d+(?:\.\d+)?)\s*pts?"),  # 50 pts
    re.compile(r"(\d+(?:\.\d+)?)\s*points?"),  # 10 points
    re.compile(r"(\d+(?:\.\d+)?)\s*pt\.?"),  # 5 pt
]

_SECTION_KEYWORDS = re.compile(
    r"^(area\s*\d|rover\s*bay|loading\s*dock|warehouse|packaging|drum|serving|"
    r"beverage|fry|condiment|kitchen|habitat|astronaut|solar|lava|starting\s*box)",
    re.IGNORECASE,
)

_IGNORE_LINES = re.compile(
    r"^\s*(page\s*\d|scoring\s*rules?|tie\s*breaker|version|botball|gcer|ecer|©|\d{4})\b",
    re.IGNORECASE,
)


def _to_snake_case(text: str) -> str:
    """Convert a label like 'Sorted Poms' → 'sorted_poms'."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s]", "", text).strip().lower()
    return re.sub(r"\s+", "_", text)


def _extract_multiplier(line: str) -> float | None:
    for pat in _MULTIPLIER_PATTERNS:
        m = pat.search(line)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return None


def detect_fields(raw_text: str) -> list[ExtractedFieldCandidate]:
    """
    Parse the raw pdftotext output and return a list of candidate scoring fields.
    This is best-effort: the admin will review and correct the results.
    """
    candidates: list[ExtractedFieldCandidate] = []
    current_section: str | None = None
    seen_keys: set[str] = set()

    for page_num, page_text in enumerate(raw_text.split("\x0c"), start=1):
        for line in page_text.splitlines():
            line_stripped = line.strip()

            # Skip empty lines and lines that are clearly not field labels
            if not line_stripped or _IGNORE_LINES.match(line_stripped):
                continue

            # Detect section headers
            if _SECTION_KEYWORDS.match(line_stripped) and len(line_stripped) < 60:
                current_section = line_stripped.title()
                continue

            multiplier = _extract_multiplier(line_stripped)

            # Remove the multiplier part to get the clean label
            clean_label = line_stripped
            for pat in _MULTIPLIER_PATTERNS:
                clean_label = pat.sub("", clean_label).strip()
            clean_label = re.sub(r"\s{2,}", " ", clean_label).strip(" /-–")

            if not clean_label or len(clean_label) < 3 or len(clean_label) > 120:
                continue

            key = _to_snake_case(clean_label)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)

            # Confidence: higher if we found a multiplier AND have a section
            confidence = 0.4
            if multiplier is not None:
                confidence += 0.4
            if current_section:
                confidence += 0.2

            # Only include lines that look like they could be scoring fields
            if confidence < 0.5 and multiplier is None:
                continue

            candidates.append(
                ExtractedFieldCandidate(
                    raw_text=line_stripped,
                    suggested_key=key,
                    suggested_label=clean_label,
                    suggested_multiplier=multiplier,
                    suggested_max_value=None,
                    confidence=round(min(confidence, 1.0), 2),
                    page=page_num,
                    accepted=confidence >= 0.8,  # auto-accept high-confidence candidates
                )
            )

    logger.info(
        "fields_detected",
        extra={"total": len(candidates), "auto_accepted": sum(1 for c in candidates if c.accepted)},
    )
    return candidates


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------


async def create_template(
    db: AsyncSession,
    season_id: str,
    competition_level_id: str | None,
    label: str,
    year: int,
    game_theme: str | None,
    file_path: Path,
    file_size: int,
    uploaded_by: str,
) -> ScoreSheetTemplate:
    template = ScoreSheetTemplate(
        season_id=season_id,
        competition_level_id=competition_level_id,
        label=label,
        year=year,
        game_theme=game_theme,
        is_active=False,
        file_url=str(file_path),
        file_name=file_path.name,
        file_size_bytes=file_size,
        ocr_status="pending",
        uploaded_by=uploaded_by,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def run_ocr_pipeline(db: AsyncSession, template_id: str) -> None:
    """
    Called as a background task after upload.
    Extracts text and detects fields, then saves results to the DB.
    """
    result = await db.execute(
        select(ScoreSheetTemplate).where(ScoreSheetTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        logger.error("template_not_found", extra={"id": str(template_id)})
        return

    await db.execute(
        update(ScoreSheetTemplate)
        .where(ScoreSheetTemplate.id == template_id)
        .values(ocr_status="processing")
    )
    await db.commit()

    try:
        raw_text = extract_text_from_pdf(Path(template.file_url))
        candidates = detect_fields(raw_text)

        await db.execute(
            update(ScoreSheetTemplate)
            .where(ScoreSheetTemplate.id == template_id)
            .values(
                raw_text=raw_text,
                extracted_fields=[c.model_dump() for c in candidates],
                ocr_status="done",
            )
        )
    except Exception as exc:
        logger.error(
            "ocr_pipeline_failed",
            extra={"id": str(template_id), "error": str(exc)},
        )
        await db.execute(
            update(ScoreSheetTemplate)
            .where(ScoreSheetTemplate.id == template_id)
            .values(ocr_status="failed", ocr_error=str(exc))
        )
    finally:
        await db.commit()


async def confirm_fields(
    db: AsyncSession,
    template_id: str,
    fields: list[ScoringField],
    confirmed_by: str,
    apply_to_schema: bool,
) -> ScoreSheetTemplate:
    """
    Admin confirms the field list. Optionally writes it to ScoringSchema.
    """
    from datetime import datetime

    await db.execute(
        update(ScoreSheetTemplate)
        .where(ScoreSheetTemplate.id == template_id)
        .values(
            confirmed_fields=[f.model_dump() for f in fields],
            confirmed_by=confirmed_by,
            confirmed_at=datetime.now(UTC),
        )
    )
    await db.commit()

    if apply_to_schema:
        result = await db.execute(
            select(ScoreSheetTemplate).where(ScoreSheetTemplate.id == template_id)
        )
        template = result.scalar_one()
        await _apply_to_scoring_schema(db, template, fields)

    result = await db.execute(
        select(ScoreSheetTemplate).where(ScoreSheetTemplate.id == template_id)
    )
    return result.scalar_one()


async def _apply_to_scoring_schema(
    db: AsyncSession,
    template: ScoreSheetTemplate,
    fields: list[ScoringField],
) -> None:
    """
    Upsert the ScoringSchema for this season + level with the confirmed fields.
    """
    from sqlalchemy import select as sa_select

    # Import here to avoid circular imports at module level
    from modules.scoring.models import ScoringSchema  # type: ignore[import]

    result = await db.execute(
        sa_select(ScoringSchema).where(
            ScoringSchema.season_id == template.season_id,
            ScoringSchema.competition_level_id == template.competition_level_id,
        )
    )
    schema = result.scalar_one_or_none()

    field_dicts = [f.model_dump() for f in fields]
    if schema:
        schema.fields = field_dicts
    else:
        schema = ScoringSchema(
            season_id=template.season_id,
            competition_level_id=template.competition_level_id,
            fields=field_dicts,
        )
        db.add(schema)

    await db.commit()
    logger.info(
        "scoring_schema_updated_from_sheet",
        extra={
            "season_id": str(template.season_id),
            "level_id": str(template.competition_level_id),
            "field_count": len(fields),
        },
    )


async def set_active_template(
    db: AsyncSession,
    season_id: str,
    competition_level_id: str | None,
    template_id: str,
) -> None:
    """Deactivate all templates for this season/level, then activate the chosen one."""
    await db.execute(
        update(ScoreSheetTemplate)
        .where(
            ScoreSheetTemplate.season_id == season_id,
            ScoreSheetTemplate.competition_level_id == competition_level_id,
        )
        .values(is_active=False)
    )
    await db.execute(
        update(ScoreSheetTemplate)
        .where(ScoreSheetTemplate.id == template_id)
        .values(is_active=True)
    )
    await db.commit()


async def list_templates(
    db: AsyncSession,
    season_id: str,
    competition_level_id: str | None = None,
) -> list[ScoreSheetTemplate]:
    stmt = select(ScoreSheetTemplate).where(ScoreSheetTemplate.season_id == season_id)
    if competition_level_id:
        stmt = stmt.where(ScoreSheetTemplate.competition_level_id == competition_level_id)
    stmt = stmt.order_by(ScoreSheetTemplate.uploaded_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_template(db: AsyncSession, template_id: str) -> ScoreSheetTemplate | None:
    result = await db.execute(
        select(ScoreSheetTemplate).where(ScoreSheetTemplate.id == template_id)
    )
    return result.scalar_one_or_none()


async def delete_template(db: AsyncSession, template_id: str) -> None:
    result = await db.execute(
        select(ScoreSheetTemplate).where(ScoreSheetTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if template:
        pdf_path = Path(template.file_url)
        if pdf_path.exists():
            pdf_path.unlink()
        await db.delete(template)
        await db.commit()


async def update_template_layout(
    db: AsyncSession, template_id: str, data: dict
) -> ScoreSheetTemplate:
    template = await get_template(db, template_id)
    if not template:
        raise ValueError("Score sheet not found")
    keys = {field.get("key") for field in (template.confirmed_fields or [])}
    region_keys = [region.get("key") for region in data["field_regions"]]
    if any(not key or key not in keys for key in region_keys):
        raise ValueError("Every OCR region must reference a confirmed scoring field")
    if len(set(region_keys)) != len(region_keys):
        raise ValueError("OCR field regions must use unique keys")
    for region in data["field_regions"]:
        values = (region["x"], region["y"], region["width"], region["height"])
        if max(values) <= 1:
            continue
        if (
            region["x"] + region["width"] > data["page_width"]
            or region["y"] + region["height"] > data["page_height"]
        ):
            raise ValueError("Pixel OCR regions must fit within the configured page")
    for key, value in data.items():
        setattr(template, key, value)
    await db.flush()
    return template
