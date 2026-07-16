"""Secure file-handling helpers — filename sanitisation, path-containment and
upload validation. Used by every endpoint that writes or serves user files.
"""
import os
import re
from pathlib import Path

from core.config import get_settings
from core.exceptions import ValidationError

# Conservative whitelist for the *stored* base name.
_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_PDF_MAGIC = b"%PDF-"

# Magic-byte prefixes for the image types accepted by the bot gallery.
_IMAGE_MAGIC: dict[bytes, str] = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
}


def safe_filename(name: str | None, default: str = "upload.bin") -> str:
    """Return a safe base filename: strips any directory components and
    path-traversal sequences, keeps only a conservative character set.

    ``safe_filename('../../etc/passwd')`` -> ``'passwd'``
    ``safe_filename('a/b/../c.pdf')``     -> ``'c.pdf'``
    """
    if not name:
        return default
    # Take only the final path component (handles both / and \ separators).
    base = os.path.basename(name.replace("\\", "/")).strip()
    # Drop any residual traversal / leading dots.
    base = base.lstrip(".") or default
    base = _SAFE_CHARS.sub("_", base)
    # Bound the length to avoid filesystem limits / abuse.
    if len(base) > 200:
        root, ext = os.path.splitext(base)
        base = root[:200 - len(ext)] + ext
    return base or default


def ensure_within(base_dir: Path, target: Path) -> Path:
    """Resolve ``target`` and assert it stays inside ``base_dir``.

    Defence-in-depth against path traversal even if a name slips through.
    Raises ValidationError if the resolved path escapes ``base_dir``.
    """
    base_resolved = base_dir.resolve()
    target_resolved = target.resolve()
    if base_resolved != target_resolved and base_resolved not in target_resolved.parents:
        raise ValidationError("Invalid file path")
    return target_resolved


def assert_upload_size(file, *, max_mb: int | None = None) -> None:
    """Reject an oversized upload *before* it is read into memory.

    Starlette populates UploadFile.size, so we can fail fast instead of
    buffering a multi-gigabyte body just to reject it afterwards.
    """
    if max_mb is None:
        max_mb = getattr(get_settings(), "max_upload_size_mb", 20)
    size = getattr(file, "size", None)
    if size is not None and size > max_mb * 1024 * 1024:
        raise ValidationError(f"File too large (max {max_mb} MB)")


def validate_pdf(content: bytes, *, max_mb: int | None = None) -> None:
    """Validate an uploaded PDF: enforce a size cap and verify the magic bytes.

    Raises ValidationError on violation.
    """
    if max_mb is None:
        max_mb = getattr(get_settings(), "max_upload_size_mb", 20)
    if len(content) == 0:
        raise ValidationError("Empty file")
    if len(content) > max_mb * 1024 * 1024:
        raise ValidationError(f"File too large (max {max_mb} MB)")
    if not content.startswith(_PDF_MAGIC):
        raise ValidationError("File is not a valid PDF")


def validate_image(content: bytes, *, max_mb: int | None = None) -> str:
    """Validate an uploaded image by magic bytes and size.

    Returns the detected media type. Raises ValidationError on violation.
    """
    if max_mb is None:
        max_mb = getattr(get_settings(), "max_upload_size_mb", 20)
    if len(content) == 0:
        raise ValidationError("Empty file")
    if len(content) > max_mb * 1024 * 1024:
        raise ValidationError(f"File too large (max {max_mb} MB)")
    for magic, media_type in _IMAGE_MAGIC.items():
        if content.startswith(magic):
            return media_type
    # WebP: "RIFF" .... "WEBP"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    raise ValidationError("File is not a valid image (PNG, JPEG, GIF or WebP)")
