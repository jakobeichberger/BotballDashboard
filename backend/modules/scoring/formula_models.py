"""Per-season, per-category scoring formulas and bracket weights.

Formulas are stored rather than hard-coded because the game documents change
every year, and because the ECER amendments regularly override the official
formula for one season (e.g. dropping the onsite documentation in 2025).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ScoringFormula(Base):
    """One named formula, e.g. key="seed_score", expression="3/4 * (...) + ...".

    Formulas within a (season, category) may reference each other by key; the
    engine resolves the evaluation order, so `sort_order` only controls the
    order they are listed in the editor.
    """

    __tablename__ = "scoring_formulas"
    __table_args__ = (
        UniqueConstraint("season_id", "category", "key", name="uq_scoring_formula_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # botball | open | aerial | jbc
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="botball")

    key: Mapped[str] = mapped_column(String(50), nullable=False)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ScoringBracketWeight(Base):
    """Weight applied to a double-elimination bracket's score.

    The game review states the weighting of brackets is announced per
    tournament ("Note #2"), so it cannot be derived — ECER 2025 used 1.0 for
    bracket A and 0.5683760683760684 for bracket B.
    """

    __tablename__ = "scoring_bracket_weights"
    __table_args__ = (
        UniqueConstraint("season_id", "category", "bracket", name="uq_scoring_bracket_weight"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="botball")
    bracket: Mapped[str] = mapped_column(String(4), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
