"""Versioned team documents (project plans, presentations, code documentation).

Every upload becomes a new TeamDocumentVersion with its own file under
upload_dir/team-documents/<team_id>/<document_id>/v<n>-<random>/, so older
versions stay downloadable. Accepted are PDFs and images (PNG, JPEG, GIF,
WebP), checked by their content, not their name.

Access is decided by the routes: the team's own members/mentors and
organizers (teams:admin); nobody else learns that a document exists.
"""

import shutil
import uuid
from pathlib import Path

import aiofiles
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import get_settings
from core.exceptions import NotFoundError, ValidationError
from core.files import assert_upload_size, ensure_within, safe_filename, validate_image
from modules.seasons.lifecycle import ensure_writable
from modules.teams.models import DOCUMENT_CATEGORIES, TeamDocument, TeamDocumentVersion

_PDF_MAGIC = b"%PDF-"


def _documents_root() -> Path:
    return Path(get_settings().upload_dir) / "team-documents"


def detect_media_type(content: bytes) -> str:
    """media type of an accepted upload, or ValidationError."""
    if not content:
        raise ValidationError("Empty file")
    if content.startswith(_PDF_MAGIC):
        return "application/pdf"
    try:
        return validate_image(content)
    except ValidationError:
        raise ValidationError(
            "Only PDF files and images (PNG, JPEG, GIF, WebP) are accepted"
        ) from None


async def _store(file: UploadFile, team_id: str, document_id: str, number: int):
    """Validate and write one upload; returns (relative path, name, type, size)."""
    assert_upload_size(file)
    content = await file.read()
    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise ValidationError(f"File too large (max {get_settings().max_upload_size_mb} MB)")
    media_type = detect_media_type(content)

    root = _documents_root()
    directory = ensure_within(
        root, root / team_id / document_id / f"v{number}-{uuid.uuid4().hex[:8]}"
    )
    directory.mkdir(parents=True, exist_ok=True)
    name = safe_filename(file.filename, "document.pdf" if media_type.endswith("pdf") else "image")
    path = ensure_within(directory, directory / name)
    async with aiofiles.open(path, "wb") as out:
        await out.write(content)
    relative = path.relative_to(Path(get_settings().upload_dir).resolve()).as_posix()
    return relative, name, media_type, len(content)


def _validate_category(category: str) -> str:
    if category not in DOCUMENT_CATEGORIES:
        raise ValidationError(f"Unknown category (allowed: {', '.join(DOCUMENT_CATEGORIES)})")
    return category


async def list_documents(
    db: AsyncSession, team_id: str, season_id: str | None = None
) -> list[TeamDocument]:
    query = (
        select(TeamDocument)
        .where(TeamDocument.team_id == team_id)
        .options(selectinload(TeamDocument.versions))
        .order_by(TeamDocument.updated_at.desc(), TeamDocument.title)
    )
    if season_id:
        query = query.where(TeamDocument.season_id == season_id)
    return list((await db.execute(query)).scalars().all())


async def get_document(db: AsyncSession, team_id: str, document_id: str) -> TeamDocument:
    # Versions are separate rows; reload them so a new upload is included.
    await db.flush()
    result = await db.execute(
        select(TeamDocument)
        .where(TeamDocument.id == document_id, TeamDocument.team_id == team_id)
        .options(selectinload(TeamDocument.versions))
        .execution_options(populate_existing=True)
    )
    document = result.scalar_one_or_none()
    if not document:
        raise NotFoundError("Document not found")
    return document


async def create_document(
    db: AsyncSession,
    team_id: str,
    *,
    title: str,
    category: str,
    season_id: str | None,
    description: str | None,
    file: UploadFile,
    uploaded_by: str | None,
) -> TeamDocument:
    from modules.seasons.models import Season

    title = title.strip()
    if not title:
        raise ValidationError("Title must not be empty")
    _validate_category(category)
    if season_id:
        if not await db.get(Season, season_id):
            raise ValidationError("Season not found")
        await ensure_writable(db, season_id=season_id)
    document = TeamDocument(
        team_id=team_id,
        season_id=season_id,
        title=title,
        category=category,
        description=(description or "").strip() or None,
        created_by=uploaded_by,
    )
    db.add(document)
    await db.flush()
    await add_version(db, team_id, document.id, file, uploaded_by)
    return await get_document(db, team_id, document.id)


async def add_version(
    db: AsyncSession,
    team_id: str,
    document_id: str,
    file: UploadFile,
    uploaded_by: str | None,
    comment: str | None = None,
) -> TeamDocument:
    document = await get_document(db, team_id, document_id)
    if document.season_id:
        await ensure_writable(db, season_id=document.season_id)
    number = document.current_version + 1
    relative, name, media_type, size = await _store(file, team_id, document.id, number)
    db.add(
        TeamDocumentVersion(
            document_id=document.id,
            version_number=number,
            file_name=name,
            storage_path=relative,
            media_type=media_type,
            file_size_bytes=size,
            comment=(comment or "").strip() or None,
            uploaded_by=uploaded_by,
        )
    )
    document.current_version = number
    await db.flush()
    return await get_document(db, team_id, document.id)


async def update_document(
    db: AsyncSession, team_id: str, document_id: str, changes: dict
) -> TeamDocument:
    from modules.seasons.models import Season

    document = await get_document(db, team_id, document_id)
    if "category" in changes and changes["category"] is not None:
        _validate_category(changes["category"])
    if changes.get("season_id") and not await db.get(Season, changes["season_id"]):
        raise ValidationError("Season not found")
    for key in ("title", "category"):
        if key in changes and changes[key] is None:
            raise ValidationError(f"{key} must not be empty")
    for key, value in changes.items():
        setattr(document, key, value.strip() if isinstance(value, str) else value)
    await db.flush()
    return await get_document(db, team_id, document_id)


async def delete_document(db: AsyncSession, team_id: str, document_id: str) -> None:
    document = await get_document(db, team_id, document_id)
    if document.season_id:
        await ensure_writable(db, season_id=document.season_id)
    await db.delete(document)
    await db.flush()
    root = _documents_root()
    shutil.rmtree(ensure_within(root, root / team_id / document_id), ignore_errors=True)


def version_file(document: TeamDocument, version_number: int | None) -> tuple[Path, str, str]:
    """(absolute path, file name, media type) of one version (default: latest)."""
    wanted = version_number if version_number is not None else document.current_version
    version = next((v for v in document.versions if v.version_number == wanted), None)
    if version is None:
        raise NotFoundError(f"Version {wanted} not found")
    base = Path(get_settings().upload_dir)
    path = ensure_within(base, base / version.storage_path)
    if not path.is_file():
        raise NotFoundError("File missing on the server")
    return path, safe_filename(version.file_name, "document"), version.media_type
