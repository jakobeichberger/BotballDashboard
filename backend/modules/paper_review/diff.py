"""Text diff between two uploaded versions of a paper.

The text of both PDFs is extracted with pypdf and compared line by line
(unified diff). When no text can be extracted – pypdf not installed, a
scanned PDF without a text layer, a damaged file – the response says so and
compares only the metadata (file name, size, upload time, page count).
"""

import difflib
import re
from pathlib import Path

from core.exceptions import NotFoundError, ValidationError
from core.logging import get_logger
from modules.paper_review.models import Paper, PaperVersion

logger = get_logger(__name__)

# Papers are limited to 5 pages; the caps only guard against abuse.
MAX_PAGES = 40
MAX_DIFF_LINES = 2000
_SPACES = re.compile(r"[ \t ]+")


def extract_text(path: Path) -> tuple[list[str] | None, int | None, str | None]:
    """(normalised text lines, page count, error) of one PDF."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, None, "PDF text extraction is not available (pypdf is not installed)"
    try:
        reader = PdfReader(str(path))
        pages = len(reader.pages)
        lines: list[str] = []
        for page in reader.pages[:MAX_PAGES]:
            for raw in (page.extract_text() or "").splitlines():
                line = _SPACES.sub(" ", raw).strip()
                if line:
                    lines.append(line)
    except Exception as exc:  # pypdf raises many types for broken files
        logger.warning("paper_text_extraction_failed", file=str(path), error=str(exc))
        return None, None, f"The PDF text could not be read: {exc}"[:300]
    if not lines:
        return None, pages, "The PDF contains no extractable text (scanned document?)"
    return lines, pages, None


def _version(paper: Paper, number: int) -> PaperVersion:
    version = next((v for v in paper.versions if v.version_number == number), None)
    if version is None:
        raise NotFoundError(f"Version {number} not found")
    return version


def _meta(version: PaperVersion, pages: int | None) -> dict:
    return {
        "version_number": version.version_number,
        "file_name": version.file_name,
        "file_size_bytes": version.file_size_bytes,
        "uploaded_at": version.uploaded_at,
        "pages": pages,
    }


def version_diff(paper: Paper, from_number: int | None, to_number: int | None) -> dict:
    """Diff two versions; defaults to the previous and the latest one."""
    from modules.paper_review.service import resolve_version_file

    if not paper.versions:
        raise NotFoundError("No file uploaded")
    to_number = to_number or paper.current_version or paper.versions[-1].version_number
    if from_number is None:
        from_number = to_number - 1
    if from_number == to_number:
        raise ValidationError("Choose two different versions")
    old, new = _version(paper, from_number), _version(paper, to_number)
    old_path, _ = resolve_version_file(paper, old.version_number)
    new_path, _ = resolve_version_file(paper, new.version_number)

    old_lines, old_pages, old_error = extract_text(old_path)
    new_lines, new_pages, new_error = extract_text(new_path)
    result = {
        "from_version": _meta(old, old_pages),
        "to_version": _meta(new, new_pages),
        "text_available": False,
        "reason": None,
        "diff": [],
        "added": 0,
        "removed": 0,
        "truncated": False,
    }
    if old_lines is None or new_lines is None:
        result["reason"] = old_error or new_error
        return result

    lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"v{old.version_number}",
            tofile=f"v{new.version_number}",
            n=2,
            lineterm="",
        )
    )
    body = [line for line in lines if not line.startswith(("---", "+++"))]
    result.update(
        text_available=True,
        added=sum(1 for line in body if line.startswith("+")),
        removed=sum(1 for line in body if line.startswith("-")),
        diff=lines[:MAX_DIFF_LINES],
        truncated=len(lines) > MAX_DIFF_LINES,
    )
    return result
