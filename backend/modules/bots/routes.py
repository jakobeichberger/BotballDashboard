from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import assert_team_access, has_elevated_access, own_team_ids, require_permission
from core.database import get_db
from core.exceptions import ForbiddenError, NotFoundError
from modules.bots import service
from modules.bots.schemas import BotCreate, BotResponse, BotUpdate

router = APIRouter(prefix="/bots", tags=["bots"])


async def _assert_bot_access(db: AsyncSession, user, team_id: str | None) -> None:
    """Mentors may manage their own team's bots; external bots (no team) are
    organizer-only."""
    if team_id:
        await assert_team_access(db, user, team_id, "teams:admin")
        return
    if not await has_elevated_access(db, user, "teams:admin"):
        raise ForbiddenError("Only organizers may manage bots of external teams")


async def _visible_filter(db: AsyncSession, user):
    """Predicate for which bots `user` may see.

    Published bots form the shared gallery. Unpublished ones are drafts: only
    organizers and the owning team see them (teams:read also reaches guests).
    """
    if await has_elevated_access(db, user, "teams:admin"):
        return lambda bot: True
    mine = await own_team_ids(db, user)
    return lambda bot: bot.is_published or (bot.team_id is not None and bot.team_id in mine)


async def _get_visible_bot(db: AsyncSession, user, bot_id: str):
    bot = await service.get_bot(db, bot_id)
    if not (await _visible_filter(db, user))(bot):
        raise NotFoundError("Bot not found")
    return bot


@router.get("", response_model=list[BotResponse])
async def list_bots(
    season_id: str | None = Query(None),
    team_id: str | None = Query(None),
    external: bool | None = Query(None),
    current_user=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    visible = await _visible_filter(db, current_user)
    return [b for b in await service.list_bots(db, season_id, team_id, external) if visible(b)]


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(
    bot_id: str,
    current_user=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    return await _get_visible_bot(db, current_user, bot_id)


@router.post("", response_model=BotResponse, status_code=201)
async def create_bot(
    body: BotCreate,
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    await _assert_bot_access(db, current_user, body.team_id)
    return await service.create_bot(db, body.model_dump(), current_user.id)


@router.patch("/{bot_id}", response_model=BotResponse)
async def update_bot(
    bot_id: str,
    body: BotUpdate,
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    bot = await service.get_bot(db, bot_id)
    await _assert_bot_access(db, current_user, bot.team_id)
    return await service.update_bot(db, bot_id, **body.model_dump(exclude_none=True))


@router.delete("/{bot_id}", status_code=204)
async def delete_bot(
    bot_id: str,
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    bot = await service.get_bot(db, bot_id)
    await _assert_bot_access(db, current_user, bot.team_id)
    await service.delete_bot(db, bot_id)


@router.post("/{bot_id}/image", response_model=BotResponse)
async def upload_bot_image(
    bot_id: str,
    file: UploadFile = File(...),
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    bot = await service.get_bot(db, bot_id)
    await _assert_bot_access(db, current_user, bot.team_id)
    return await service.save_image(db, bot_id, file)


@router.get("/{bot_id}/image")
async def get_bot_image(
    bot_id: str,
    current_user=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    bot = await _get_visible_bot(db, current_user, bot_id)
    if not bot.image_name:
        raise NotFoundError("No image uploaded")
    # Serve with the media type we validated from the magic bytes, never one
    # guessed from the (client-chosen) extension: "evil.html" with a GIF header
    # would otherwise come back as text/html and render inline.
    return FileResponse(
        str(service.image_path(bot)),
        media_type=bot.image_media_type or "application/octet-stream",
        content_disposition_type="inline",
    )
