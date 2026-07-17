"""Local score-sheet image alignment, field OCR, review, and acceptance."""

from __future__ import annotations

import re
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.exceptions import ConflictError, NotFoundError, ValidationError
from modules.events.models import Event, ScheduledMatch
from modules.scoring import service as scoring_service
from modules.scoring.score_sheets.models import ScoreSheetScan, ScoreSheetTemplate
from modules.teams.models import Team


async def save_scan_upload(file: UploadFile, event_id: str) -> tuple[Path, int]:
    directory = Path(get_settings().upload_dir) / "score_sheet_scans" / event_id
    directory.mkdir(parents=True, exist_ok=True)
    original = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file.filename or "scan.jpg").name)
    destination = directory / f"{uuid.uuid4()}_{original}"
    content = await file.read()
    destination.write_bytes(content)
    return destination, len(content)


async def create_scan(
    db: AsyncSession,
    *,
    event_id: str,
    template_id: str,
    team_id: str,
    scheduled_match_id: str | None,
    file_path: Path,
    created_by: str,
) -> ScoreSheetScan:
    event = await db.get(Event, event_id)
    template = await db.get(ScoreSheetTemplate, template_id)
    if not event:
        raise NotFoundError("Event not found")
    if not template or template.season_id != event.season_id:
        raise ValidationError("Score-sheet template does not belong to this event's season")
    if not await db.get(Team, team_id):
        raise NotFoundError("Team not found")
    if scheduled_match_id:
        scheduled = await db.get(ScheduledMatch, scheduled_match_id)
        if not scheduled or scheduled.event_id != event_id:
            raise ValidationError("Scheduled match does not belong to this event")
    scan = ScoreSheetScan(
        event_id=event_id,
        template_id=template_id,
        team_id=team_id,
        scheduled_match_id=scheduled_match_id,
        file_url=str(file_path),
        file_name=file_path.name,
        status="queued",
        created_by=created_by,
    )
    db.add(scan)
    await db.flush()
    return scan


async def get_scan(db: AsyncSession, event_id: str, scan_id: str) -> ScoreSheetScan:
    result = await db.execute(
        select(ScoreSheetScan).where(
            ScoreSheetScan.id == scan_id, ScoreSheetScan.event_id == event_id
        )
    )
    scan = result.scalar_one_or_none()
    if not scan:
        raise NotFoundError("Score-sheet scan not found")
    return scan


async def list_scans(
    db: AsyncSession, event_id: str, status: str | None = None
) -> list[ScoreSheetScan]:
    query = select(ScoreSheetScan).where(ScoreSheetScan.event_id == event_id)
    if status:
        query = query.where(ScoreSheetScan.status == status)
    result = await db.execute(query.order_by(ScoreSheetScan.created_at.desc()))
    return list(result.scalars().all())


def _rasterize(path: Path, output_directory: Path) -> Path:
    if path.suffix.lower() != ".pdf":
        return path
    target = output_directory / "page"
    result = subprocess.run(
        ["pdftoppm", "-f", "1", "-singlefile", "-png", str(path), str(target)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not rasterize PDF: {result.stderr[:300]}")
    return target.with_suffix(".png")


def _align_page(image, width: int, height: int):
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) != 4:
            continue
        points = polygon.reshape(4, 2).astype("float32")
        sums = points.sum(axis=1)
        diffs = np.diff(points, axis=1).reshape(-1)
        source = np.array(
            [
                points[sums.argmin()],
                points[diffs.argmin()],
                points[sums.argmax()],
                points[diffs.argmax()],
            ],
            dtype="float32",
        )
        destination = np.array(
            [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
            dtype="float32",
        )
        matrix = cv2.getPerspectiveTransform(source, destination)
        return cv2.warpPerspective(image, matrix, (width, height))
    return cv2.resize(image, (width, height))


def run_local_ocr(scan: ScoreSheetScan, template: ScoreSheetTemplate) -> list[dict]:
    """CPU-only OpenCV/Tesseract provider. No image data leaves the installation."""
    import cv2
    import pytesseract
    from pytesseract import Output

    crop_directory = Path(scan.file_url).parent / scan.id / "crops"
    crop_directory.mkdir(parents=True, exist_ok=True)
    image_path = _rasterize(Path(scan.file_url), crop_directory.parent)
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError("Uploaded score sheet is not a readable image")
    width = template.page_width or image.shape[1]
    height = template.page_height or image.shape[0]
    aligned = _align_page(image, width, height)
    regions = template.field_regions or [
        {"key": field.get("key"), **(field.get("region") or {})}
        for field in (template.confirmed_fields or [])
        if field.get("region")
    ]
    if not regions:
        raise RuntimeError("Template has no configured OCR field regions")
    fields = {field["key"]: field for field in (template.confirmed_fields or [])}
    values: list[dict] = []
    for region in regions:
        key = region.get("key")
        if not key:
            continue
        x, y = region.get("x", 0), region.get("y", 0)
        region_width, region_height = region.get("width", 0), region.get("height", 0)
        if max(x, y, region_width, region_height) <= 1:
            x, region_width = x * width, region_width * width
            y, region_height = y * height, region_height * height
        x1, y1 = max(0, int(x)), max(0, int(y))
        x2, y2 = min(width, int(x + region_width)), min(height, int(y + region_height))
        crop = aligned[y1:y2, x1:x2]
        if crop.size == 0:
            raise RuntimeError(f"Invalid crop region for {key}")
        crop_path = crop_directory / f"{re.sub(r'[^A-Za-z0-9_-]', '_', key)}.png"
        cv2.imwrite(str(crop_path), crop)
        field = fields.get(key, {})
        value: bool | float | None
        if field.get("type") == "boolean":
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            value = bool((gray < 128).mean() > 0.12)
            confidence = 0.8
            raw_text = "marked" if value else "unmarked"
        else:
            data = pytesseract.image_to_data(
                crop,
                config="--psm 7 -c tessedit_char_whitelist=0123456789.,-",
                output_type=Output.DICT,
            )
            tokens = [text.strip() for text in data["text"] if text.strip()]
            confidences = [float(c) for c in data["conf"] if float(c) >= 0]
            raw_text = "".join(tokens).replace(",", ".")
            match = re.search(r"-?\d+(?:\.\d+)?", raw_text)
            value = float(match.group()) if match else None
            confidence = (max(confidences) / 100.0) if confidences else 0.0
        reasons = []
        if value is None:
            reasons.append("empty")
        if confidence < 0.85:
            reasons.append("low_confidence")
        minimum = field.get("min_value")
        maximum = field.get("max_value")
        if value is not None and minimum is not None and float(value) < float(minimum):
            reasons.append("below_minimum")
        if value is not None and maximum is not None and float(value) > float(maximum):
            reasons.append("above_maximum")
        values.append(
            {
                "key": key,
                "value": value,
                "rawText": raw_text,
                "confidence": round(confidence, 3),
                "cropUrl": (
                    f"/api/v1/events/{scan.event_id}/score-sheet-scans/"
                    f"{scan.id}/crops/{crop_path.name}"
                ),
                "requiresReview": bool(reasons),
                "reasons": reasons,
            }
        )
    return values


async def accept_scan(
    db: AsyncSession,
    scan: ScoreSheetScan,
    values: dict,
    reviewed_by: str,
    correction_reason: str | None,
):
    if scan.status == "accepted":
        if scan.accepted_match_id:
            return await scoring_service.get_match(db, scan.accepted_match_id)
        raise ConflictError("Scan is already accepted")
    if scan.status != "review":
        raise ConflictError("Scan is not ready for review")
    template = await db.get(ScoreSheetTemplate, scan.template_id)
    event = await db.get(Event, scan.event_id)
    if not template or not event:
        raise NotFoundError("Scan template or event no longer exists")
    fields = template.confirmed_fields or []
    scoring_service.validate_raw_scores(values, fields)
    match = await scoring_service.create_match(
        db,
        {
            "season_id": event.season_id,
            "event_id": event.id,
            "scheduled_match_id": scan.scheduled_match_id,
            "team_id": scan.team_id,
            "competition_level_id": template.competition_level_id,
            "raw_scores": values,
            "notes": correction_reason,
            "idempotency_key": f"ocr:{scan.id}",
        },
        reviewed_by,
    )
    scan.reviewed_values = values
    scan.reviewed_by = reviewed_by
    scan.reviewed_at = datetime.now(UTC)
    scan.accepted_match_id = match.id
    scan.status = "accepted"
    await db.flush()
    return match
