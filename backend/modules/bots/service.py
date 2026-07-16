from pathlib import Path

import aiofiles
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.exceptions import NotFoundError
from core.files import ensure_within, safe_filename, validate_image
from modules.bots.models import Bot

settings = get_settings()


async def list_bots(
    db: AsyncSession,
    season_id: str | None = None,
    team_id: str | None = None,
    external: bool | None = None,
) -> list[Bot]:
    q = select(Bot).order_by(Bot.name)
    if season_id:
        q = q.where(Bot.season_id == season_id)
    if team_id:
        q = q.where(Bot.team_id == team_id)
    if external is True:
        q = q.where(Bot.team_id.is_(None))
    elif external is False:
        q = q.where(Bot.team_id.isnot(None))
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_bot(db: AsyncSession, bot_id: str) -> Bot:
    result = await db.execute(select(Bot).where(Bot.id == bot_id))
    bot = result.scalar_one_or_none()
    if not bot:
        raise NotFoundError("Bot not found")
    return bot


async def create_bot(db: AsyncSession, data: dict, created_by: str | None) -> Bot:
    bot = Bot(**data, created_by=created_by)
    db.add(bot)
    await db.flush()
    return bot


async def update_bot(db: AsyncSession, bot_id: str, **kwargs) -> Bot:
    bot = await get_bot(db, bot_id)
    for key, value in kwargs.items():
        if value is not None:
            setattr(bot, key, value)
    return bot


async def delete_bot(db: AsyncSession, bot_id: str) -> None:
    bot = await get_bot(db, bot_id)
    await db.delete(bot)


async def save_image(db: AsyncSession, bot_id: str, file: UploadFile) -> Bot:
    """Store a bot image (magic-byte validated) and record its name."""
    bot = await get_bot(db, bot_id)

    content = await file.read()
    validate_image(content)  # size + magic-byte check

    upload_dir = Path(settings.upload_dir) / "bots" / bot_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = safe_filename(file.filename, "bot.png")
    file_path = ensure_within(upload_dir, upload_dir / safe_name)

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    bot.image_name = safe_name
    return bot


def image_path(bot: Bot) -> Path:
    upload_dir = Path(settings.upload_dir) / "bots" / bot.id
    safe_name = safe_filename(bot.image_name, "bot.png")
    return ensure_within(upload_dir, upload_dir / safe_name)
