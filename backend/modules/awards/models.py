"""Award categories, nominations and results of an event.

* AwardCategory – one award of an event (ECER: "Botball Overall", "Spirit of
  ECER", …). ``kind`` is ``computed`` (filled from a ranking, ``source``) or
  ``judged`` (nominations and a jury decision).
* AwardNomination – a team proposed for a judged award.
* AwardResult – the placed teams (1st, 2nd, … – ties share a place; per
  course for GCER's tiered awards).
* EventAwards – per event: the template it started from and whether the
  results are published on the public event page.
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


class EventAwards(Base):
    __tablename__ = "event_awards"

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    template: Mapped[str | None] = mapped_column(String(20), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AwardCategory(Base):
    __tablename__ = "award_categories"
    __table_args__ = (UniqueConstraint("event_id", "key", name="uq_award_category_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # computed | judged
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="judged")
    # computed: overall | seeding | de | doc | adapted_doc | paper | aerial | jbc;
    # judged: paper_on_stage seeds the nominations from the on-stage papers.
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Team category the award is for (None: every category the source has).
    team_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    places: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # GCER: placed per DE bracket ("course"), e.g. Overall 1–4 per course.
    per_course: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AwardNomination(Base):
    __tablename__ = "award_nominations"
    __table_args__ = (UniqueConstraint("award_id", "team_id", name="uq_award_nomination"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    award_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("award_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    nominated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AwardResult(Base):
    __tablename__ = "award_results"
    __table_args__ = (UniqueConstraint("award_id", "team_id", name="uq_award_result_team"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    award_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("award_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    place: Mapped[int] = mapped_column(Integer, nullable=False)
    course: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # The value the place was computed from (overall score, …), if any.
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
