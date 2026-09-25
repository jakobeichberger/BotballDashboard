"""Local score-sheet image alignment, field OCR, review, and acceptance."""

from __future__ import annotations

import io
import os
import re
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.exceptions import ConflictError, NotFoundError, ValidationError
from core.files import remove_on_rollback
from modules.events.models import Event, EventRegistration, ScheduledMatch
from modules.scoring import service as scoring_service
from modules.scoring.score_sheets.models import ScoreSheetScan, ScoreSheetTemplate
from modules.scoring.score_sheets.schemas import OcrValidationRules
from modules.seasons.lifecycle import ensure_writable
from modules.teams.models import Team

# ── Input limits ──────────────────────────────────────────────────────────────
#
# A score sheet is one A4 page; at 300 dpi that is about 8.7 MP. A PNG of a few
# KB can declare billions of pixels, and decoding it would take gigabytes (a
# decompression bomb), so images are measured from their header first.
MAX_SCAN_PIXELS = 40_000_000
# OpenCV's own decoder cap, read when cv2 decodes its first image.
os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(MAX_SCAN_PIXELS))
# PDFs are rasterized at 150 dpi, the longer side capped at 3000 px, whatever
# page size the PDF declares.
PDF_RASTER_DPI = 150
PDF_RASTER_MAX_SIDE = 3000

_PDF_MAGIC = b"%PDF-"
# Detected image format -> stored extension. GIF and anything else is refused.
# Pillow reports many phone-camera JPEGs as "MPO" (JPEG with a preview image).
SCAN_TYPES = {"PNG": ".png", "JPEG": ".jpg", "MPO": ".jpg", "WEBP": ".webp"}


class ScanImageTooLarge(ValueError):
    pass


def assert_scan_dimensions(source: Path | bytes) -> None:
    """Refuse images with more than MAX_SCAN_PIXELS pixels without decoding them.

    Raises ValueError for data that is not a readable image and
    ScanImageTooLarge for an image that is too large.
    """
    try:
        with Image.open(io.BytesIO(source) if isinstance(source, bytes) else source) as image:
            width, height = image.size
    except Image.DecompressionBombError as exc:
        raise ScanImageTooLarge("Score sheet image is too large") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Uploaded score sheet is not a readable image") from exc
    if width * height > MAX_SCAN_PIXELS:
        raise ScanImageTooLarge(
            f"Score sheet image is too large ({width}x{height} px, "
            f"at most {MAX_SCAN_PIXELS // 1_000_000} MP)"
        )


def scan_extension(content: bytes) -> str:
    """Stored extension of an accepted scan (by content, not by name); 415 otherwise."""
    if content.startswith(_PDF_MAGIC):
        return ".pdf"
    try:
        with Image.open(io.BytesIO(content)) as image:
            kind = image.format
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        kind = None
    if kind not in SCAN_TYPES:
        raise HTTPException(status_code=415, detail="PDF, JPEG, PNG or WebP required")
    return SCAN_TYPES[kind]


def _scan_directory(event_id: str) -> Path:
    return Path(get_settings().upload_dir) / "score_sheet_scans" / event_id


async def create_scan(
    db: AsyncSession,
    *,
    event_id: str,
    template_id: str,
    team_id: str,
    scheduled_match_id: str | None,
    content: bytes,
    created_by: str,
) -> ScoreSheetScan:
    """Validate an uploaded score sheet, then store it and create the scan row.

    Everything is checked before the file touches the disk; the file is named
    by its detected type and removed again if the transaction rolls back.
    """
    event = await db.get(Event, event_id)
    template = await db.get(ScoreSheetTemplate, template_id)
    if not event:
        raise NotFoundError("Event not found")
    if not template or template.season_id != event.season_id:
        raise ValidationError("Score-sheet template does not belong to this event's season")
    if not await db.get(Team, team_id):
        raise NotFoundError("Team not found")
    registration = await db.execute(
        select(EventRegistration.id).where(
            EventRegistration.event_id == event_id,
            EventRegistration.team_id == team_id,
        )
    )
    if not registration.scalar_one_or_none():
        raise ValidationError("Team is not registered for this event")
    if scheduled_match_id:
        scheduled = await db.get(ScheduledMatch, scheduled_match_id)
        if not scheduled or scheduled.event_id != event_id:
            raise ValidationError("Scheduled match does not belong to this event")
        await scoring_service.assert_match_participant(db, scheduled_match_id, team_id)
    await ensure_writable(db, event_id=event_id)
    extension = scan_extension(content)
    if extension != ".pdf":
        try:
            assert_scan_dimensions(content)
        except ScanImageTooLarge as exc:
            raise ValidationError(str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc

    directory = _scan_directory(event_id)
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / f"{uuid.uuid4()}{extension}"
    file_path.write_bytes(content)
    remove_on_rollback(db, file_path)
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
    try:
        await db.flush()
    except Exception:
        file_path.unlink(missing_ok=True)
        raise
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
    db: AsyncSession,
    event_id: str,
    status: str | None = None,
    team_ids: set[str] | None = None,
) -> list[ScoreSheetScan]:
    """Scans of an event; ``team_ids`` (when given) restricts them to those teams."""
    query = select(ScoreSheetScan).where(ScoreSheetScan.event_id == event_id)
    if team_ids is not None:
        query = query.where(ScoreSheetScan.team_id.in_(team_ids))
    if status:
        query = query.where(ScoreSheetScan.status == status)
    result = await db.execute(query.order_by(ScoreSheetScan.created_at.desc()))
    return list(result.scalars().all())


def _rasterize(path: Path, output_directory: Path) -> Path:
    if path.suffix.lower() != ".pdf":
        return path
    target = output_directory / "page"
    result = subprocess.run(
        [
            "pdftoppm",
            "-f",
            "1",
            "-l",
            "1",
            "-singlefile",
            "-r",
            str(PDF_RASTER_DPI),
            "-scale-to",
            str(PDF_RASTER_MAX_SIDE),
            "-png",
            str(path),
            str(target),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not rasterize PDF: {result.stderr[:300]}")
    return target.with_suffix(".png")


# Anchors are searched this far (fraction of the page) around their expected box.
ANCHOR_SEARCH_MARGIN = 0.1
# A found anchor mark may be this much smaller or larger (area) than configured.
ANCHOR_AREA_TOLERANCE = 4.0
# Anchor alignment is rejected when a mark ends up further than this (fraction
# of the page diagonal) from its configured position.
ANCHOR_MAX_RESIDUAL = 0.02
# Search-and-correct rounds; each one starts from the previous correction.
ANCHOR_PASSES = 2


def _page_box(box: dict, width: int, height: int) -> tuple[float, float, float, float]:
    """A stored box in page pixels; normalized boxes (all values ≤ 1) are scaled."""
    x, y = float(box.get("x", 0)), float(box.get("y", 0))
    box_width, box_height = float(box.get("width", 0)), float(box.get("height", 0))
    if max(x, y, box_width, box_height) <= 1:
        return x * width, y * height, box_width * width, box_height * height
    return x, y, box_width, box_height


def _contour_transform(image, width: int, height: int):
    """Homography mapping the largest quadrilateral (the sheet edge) onto the page."""
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
        return cv2.getPerspectiveTransform(source, destination)
    return None


def _locate_anchor(gray, box: tuple[float, float, float, float]) -> tuple[float, float] | None:
    """Centre of the solid dark mark near ``box`` in a roughly aligned page, if any."""
    import cv2
    import numpy as np

    page_height, page_width = gray.shape[:2]
    x, y, box_width, box_height = box
    margin_x = max(box_width, ANCHOR_SEARCH_MARGIN * page_width)
    margin_y = max(box_height, ANCHOR_SEARCH_MARGIN * page_height)
    x1, y1 = max(0, int(x - margin_x)), max(0, int(y - margin_y))
    x2 = min(page_width, int(x + box_width + margin_x))
    y2 = min(page_height, int(y + box_height + margin_y))
    window = gray[y1:y2, x1:x2]
    if window.size == 0:
        return None
    otsu, _ = cv2.threshold(window, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Capped, so an empty (all white) window does not turn paper grain into marks.
    mask = np.where(window < min(otsu, 160), 255, 0).astype("uint8")
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    expected = box_width * box_height
    best: tuple[float, tuple[float, float]] | None = None
    for contour in contours:
        area = cv2.contourArea(contour)
        if not expected / ANCHOR_AREA_TOLERANCE <= area <= expected * ANCHOR_AREA_TOLERANCE:
            continue
        left, top, bound_width, bound_height = cv2.boundingRect(contour)
        # Anchors are filled marks; text and ruled lines fill little of their box.
        if area / max(1, bound_width * bound_height) < 0.6:
            continue
        # A mark cut off by the search window would give a skewed centre; the
        # next pass (after the first correction) finds it whole.
        cut_x = (left == 0 and x1 > 0) or (
            left + bound_width >= window.shape[1] and x2 < page_width
        )
        cut_y = (top == 0 and y1 > 0) or (
            top + bound_height >= window.shape[0] and y2 < page_height
        )
        if cut_x or cut_y:
            continue
        moments = cv2.moments(contour)
        if not moments["m00"]:
            continue
        centre = (x1 + moments["m10"] / moments["m00"], y1 + moments["m01"] / moments["m00"])
        score = abs(float(np.log(area / expected)))
        if best is None or score < best[0]:
            best = (score, centre)
    return best[1] if best else None


def _anchor_transform(page, anchors: list[dict], width: int, height: int):
    """Correction that moves the anchor marks found in ``page`` onto their boxes.

    Four or more marks give a perspective correction, three an affine one and
    two a similarity (shift, rotation, scale). Returns None when fewer than two
    marks are found or the found marks do not fit together.
    """
    import cv2
    import numpy as np

    gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
    found: list[tuple[float, float]] = []
    expected: list[tuple[float, float]] = []
    for anchor in anchors:
        box = _page_box(anchor, width, height)
        centre = _locate_anchor(gray, box)
        if centre is not None:
            found.append(centre)
            expected.append((box[0] + box[2] / 2, box[1] + box[3] / 2))
    if len(found) < 2:
        return None
    source = np.array(found, dtype="float32")
    target = np.array(expected, dtype="float32")
    if len(found) >= 4:
        matrix, _ = cv2.findHomography(source, target, 0)
    else:
        if len(found) == 3:
            affine = cv2.getAffineTransform(source, target)
        else:
            affine, _ = cv2.estimateAffinePartial2D(source, target)
        matrix = None if affine is None else np.vstack([affine, [0, 0, 1]])
    if matrix is None or abs(np.linalg.det(matrix)) < 1e-6:
        return None
    projected = cv2.perspectiveTransform(source.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    residual = float(np.linalg.norm(projected - target, axis=1).max())
    if residual > ANCHOR_MAX_RESIDUAL * float(np.hypot(width, height)):
        return None
    return matrix


def _align_page(image, width: int, height: int, anchors: list[dict] | None = None):
    """Warp a scan onto the template page; returns ``(page, method)``.

    With anchors, the scan is first roughly aligned (sheet edge, else a plain
    resize) and then corrected so the printed marks land on their configured
    boxes. Without anchors, or when too few marks are found, the sheet edge
    (largest quadrilateral) is used. ``method`` is "anchors", "contour" or
    "resize".
    """
    import cv2
    import numpy as np

    image_height, image_width = image.shape[:2]
    contour = _contour_transform(image, width, height)
    resize = np.array(
        [[width / image_width, 0, 0], [0, height / image_height, 0], [0, 0, 1]],
        dtype="float64",
    )

    def warp(matrix):
        # Areas outside the scan become white paper, not dark blobs that could
        # pass for marks or ink.
        return cv2.warpPerspective(image, matrix, (width, height), borderValue=(255, 255, 255))

    if anchors:
        for rough in (contour, resize):
            if rough is None:
                continue
            matrix, corrected = rough, False
            # The second pass searches around the corrected positions, so marks
            # that were too far off (or cut off) at first are found as well.
            for _ in range(ANCHOR_PASSES):
                correction = _anchor_transform(warp(matrix), anchors, width, height)
                if correction is None:
                    break
                matrix, corrected = correction @ matrix, True
            if corrected:
                return warp(matrix), "anchors"
    if contour is not None:
        return cv2.warpPerspective(image, contour, (width, height)), "contour"
    return cv2.resize(image, (width, height)), "resize"


def _validation_rules(template: ScoreSheetTemplate) -> OcrValidationRules:
    try:
        return OcrValidationRules.model_validate(template.validation_rules or {})
    except PydanticValidationError:
        # Rules stored before the editor existed may not validate; the defaults
        # still flag empty, unreadable and out-of-range values.
        return OcrValidationRules()


def apply_validation_rules(
    values: list[dict],
    fields: dict[str, dict],
    rules: OcrValidationRules,
    *,
    anchors_missing: bool = False,
) -> list[dict]:
    """Set ``reasons`` and ``requiresReview`` on OCR candidates (in place).

    Reasons: empty, low_confidence, below_minimum, above_maximum, not_integer,
    sum_out_of_range and anchors_not_found (anchors are configured but the scan
    could not be aligned by them, so every box may be off). Field and rule
    limits combine: the stricter one wins.
    """
    field_rules = {rule.key: rule for rule in rules.fields}
    for item in values:
        field = fields.get(item["key"], {})
        rule = field_rules.get(item["key"])
        value = item.get("value")
        reasons: list[str] = []
        if value is None:
            reasons.append("empty")
        threshold = rules.min_confidence
        if rule and rule.min_confidence is not None:
            threshold = rule.min_confidence
        if item.get("confidence", 0.0) < threshold:
            reasons.append("low_confidence")
        if value is not None and field.get("type") != "boolean":
            minimums = [field.get("min_value"), rule.min_value if rule else None]
            maximums = [field.get("max_value"), rule.max_value if rule else None]
            minimum = max((float(v) for v in minimums if v is not None), default=None)
            maximum = min((float(v) for v in maximums if v is not None), default=None)
            if minimum is not None and float(value) < minimum:
                reasons.append("below_minimum")
            if maximum is not None and float(value) > maximum:
                reasons.append("above_maximum")
            if rule and rule.integer and not float(value).is_integer():
                reasons.append("not_integer")
        if anchors_missing:
            reasons.append("anchors_not_found")
        item["reasons"] = reasons
    by_key = {item["key"]: item for item in values}
    for sum_rule in rules.sums:
        members = [by_key[key] for key in sum_rule.keys if key in by_key]
        total = sum(float(item["value"]) for item in members if item.get("value") is not None)
        too_low = sum_rule.min_value is not None and total < sum_rule.min_value
        too_high = sum_rule.max_value is not None and total > sum_rule.max_value
        if too_low or too_high:
            for item in members:
                if "sum_out_of_range" not in item["reasons"]:
                    item["reasons"].append("sum_out_of_range")
    for item in values:
        item["requiresReview"] = bool(item["reasons"])
    return values


def _read_number(crop) -> tuple[float | None, str, float]:
    """Tesseract single-line digit read: ``(value, raw text, confidence 0–1)``."""
    import pytesseract
    from pytesseract import Output

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
    return value, raw_text, confidence


def run_local_ocr(scan: ScoreSheetScan, template: ScoreSheetTemplate) -> list[dict]:
    """CPU-only OpenCV/Tesseract provider. No image data leaves the installation."""
    import cv2

    crop_directory = Path(scan.file_url).parent / scan.id / "crops"
    crop_directory.mkdir(parents=True, exist_ok=True)
    image_path = _rasterize(Path(scan.file_url), crop_directory.parent)
    # Measured from the header before anything is decoded (decompression bombs).
    try:
        assert_scan_dimensions(image_path)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError("Uploaded score sheet is not a readable image")
    width = template.page_width or image.shape[1]
    height = template.page_height or image.shape[0]
    anchors = template.anchors or []
    aligned, method = _align_page(image, width, height, anchors)
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
        x, y, region_width, region_height = _page_box(region, width, height)
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
            value, raw_text, confidence = _read_number(crop)
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
            }
        )
    return apply_validation_rules(
        values,
        fields,
        _validation_rules(template),
        anchors_missing=bool(anchors) and method != "anchors",
    )


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
