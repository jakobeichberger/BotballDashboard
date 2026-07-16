import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Bot(Base):
    """A robot in the gallery — either from one of our own teams (``team_id``)
    or from an external team (``external_team_name``), with a description of
    how it works."""

    __tablename__ = "bots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Exactly one of these identifies the owner: an internal team or a free-text
    # external team name.
    team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True
    )
    external_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    season_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True, index=True
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    functionality: Mapped[str | None] = mapped_column(Text, nullable=True)
    drive_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sensors: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    image_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Detected from the magic bytes on upload — never trust the extension.
    image_media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
