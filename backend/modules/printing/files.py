"""Upload handling for print job files (STL, 3MF, OBJ, G-code, binary G-code).

Files are streamed to a temporary file under upload_dir/printing/<job_id>/,
validated by extension *and* content, and only then moved into place. The
stored name goes through core.files.safe_filename and every path is checked
with ensure_within, so a client-chosen name can never leave the job folder.
"""

import os
import struct
from pathlib import Path

import aiofiles
from fastapi import UploadFile

from core.config import get_settings
from core.exceptions import ValidationError
from core.files import ensure_within, safe_filename

# Slicer projects and meshes are larger than papers or photos, so this limit is
# separate from max_upload_size_mb. Keep it in sync with the reverse proxy.
MAX_PRINT_FILE_MB = 100

ALLOWED_EXTENSIONS = (".stl", ".3mf", ".obj", ".gcode", ".bgcode")

_ZIP_MAGIC = b"PK\x03\x04"  # 3MF is a ZIP container
_BGCODE_MAGIC = b"GCDE"  # Prusa binary G-code
_OBJ_KEYWORDS = (
    b"v",
    b"vt",
    b"vn",
    b"vp",
    b"f",
    b"l",
    b"o",
    b"g",
    b"s",
    b"mtllib",
    b"usemtl",
)
_HEAD_BYTES = 8192


def job_dir(job_id: str) -> Path:
    return Path(get_settings().upload_dir) / "printing" / job_id


def stored_path(job_id: str, file_name: str) -> Path:
    """Absolute, containment-checked path of a job's stored file."""
    base = job_dir(job_id)
    return ensure_within(base, base / safe_filename(file_name, "model.stl"))


def extension_of(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def _is_text(head: bytes) -> bool:
    if b"\x00" in head:
        return False
    try:
        # A multi-byte character may be cut at the end of the sampled head.
        head.decode("utf-8")
    except UnicodeDecodeError as exc:
        if exc.start < len(head) - 4:
            return False
    return True


def _looks_like_obj(head: bytes) -> bool:
    for raw in head.splitlines():
        line = raw.strip()
        if not line or line.startswith(b"#"):
            continue
        keyword = line.split(maxsplit=1)[0]
        return keyword in _OBJ_KEYWORDS
    return False


def validate_print_file(ext: str, head: bytes, size: int) -> None:
    """Check that the content matches the (already whitelisted) extension."""
    if size == 0:
        raise ValidationError("Empty file")
    if ext == ".3mf":
        if not head.startswith(_ZIP_MAGIC):
            raise ValidationError("File is not a valid 3MF archive")
    elif ext == ".bgcode":
        if not head.startswith(_BGCODE_MAGIC):
            raise ValidationError("File is not valid binary G-code")
    elif ext == ".stl":
        # Binary STL: 80-byte header, uint32 triangle count, 50 bytes each.
        # Many exporters also write "solid" into a binary header, so the size
        # check decides first and ASCII is the fallback.
        if len(head) >= 84:
            (triangles,) = struct.unpack_from("<I", head, 80)
            if size == 84 + 50 * triangles:
                return
        if not (head.lstrip().lower().startswith(b"solid") and _is_text(head)):
            raise ValidationError("File is not a valid STL")
    elif ext == ".obj":
        if not (_is_text(head) and _looks_like_obj(head)):
            raise ValidationError("File is not a valid OBJ mesh")
    elif ext == ".gcode":
        if not _is_text(head):
            raise ValidationError("File is not valid G-code")
    else:
        raise ValidationError(f"Unsupported file type (allowed: {', '.join(ALLOWED_EXTENSIONS)})")


async def save_print_file(file: UploadFile, job_id: str) -> tuple[str, str, int]:
    """Store an upload for `job_id`; returns (relative path, stored name, size)."""
    safe_name = safe_filename(file.filename, "")
    ext = extension_of(safe_name)
    if not safe_name or ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"Unsupported file type (allowed: {', '.join(ALLOWED_EXTENSIONS)})")

    max_bytes = MAX_PRINT_FILE_MB * 1024 * 1024
    declared = getattr(file, "size", None)
    if declared is not None and declared > max_bytes:
        raise ValidationError(f"File too large (max {MAX_PRINT_FILE_MB} MB)")

    base = job_dir(job_id)
    base.mkdir(parents=True, exist_ok=True)
    target = ensure_within(base, base / safe_name)
    temp = ensure_within(base, base / f".{safe_name}.upload")
    size = 0
    head = b""
    try:
        async with aiofiles.open(temp, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                if len(head) < _HEAD_BYTES:
                    head += chunk[: _HEAD_BYTES - len(head)]
                size += len(chunk)
                if size > max_bytes:
                    raise ValidationError(f"File too large (max {MAX_PRINT_FILE_MB} MB)")
                await out.write(chunk)
        validate_print_file(ext, head, size)
        temp.replace(target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise

    # One file per job: a replacement with another name drops the old one.
    for other in base.iterdir():
        if other.is_file() and other.name != safe_name and not other.name.startswith("."):
            other.unlink(missing_ok=True)

    relative = f"printing/{job_id}/{safe_name}"
    return relative, safe_name, size
