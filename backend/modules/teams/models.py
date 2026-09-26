import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    team_number: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    school: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="DE", nullable=False)
    competition_level_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competition_levels.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    members: Mapped[list[TeamMember]] = relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan"
    )
    season_registrations: Mapped[list[TeamSeasonRegistration]] = relationship(
        "TeamSeasonRegistration", back_populates="team", cascade="all, delete-orphan"
    )


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Indexed: "which teams is this user in" runs on almost every request
    # of a mentor (own_team_ids).
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(
        String(50), default="member", nullable=False
    )  # mentor | member

    team: Mapped[Team] = relationship(Team, back_populates="members")


class TeamSeasonRegistration(Base):
    __tablename__ = "team_season_registrations"
    __table_args__ = (
        UniqueConstraint("team_id", "season_id", name="uq_team_registration_team_season"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_level_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competition_levels.id"), nullable=True
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Competition category (the team type of this season): botball | open |
    # aerial | jbc. A team may play botball one year and open the next.
    category: Mapped[str] = mapped_column(String(20), default="botball", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Participation fee: pending | paid | waived.
    fee_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # KIPR kit shipping (botball teams only): not_sent | sent | received.
    kit_status: Mapped[str] = mapped_column(String(20), default="not_sent", nullable=False)
    # Both team types have to hand in a paper with us (module 06).
    paper_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # The school's contact person and postal address for this season (kit
    # shipping, invoices). Mentors keep these up to date themselves.
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    team: Mapped[Team] = relationship(Team, back_populates="season_registrations")
    roster: Mapped[list[TeamSeasonMember]] = relationship(
        "TeamSeasonMember", back_populates="registration", cascade="all, delete-orphan"
    )


class TeamSeasonMember(Base):
    """A team member taking part in one season, with that season's role.

    TeamMember is the team's lasting list of people (and the user links that
    grant mentors access); the roster says who was on the team in which
    season, e.g. "programmer" in 2025 and "team lead" in 2026.
    """

    __tablename__ = "team_season_members"
    __table_args__ = (
        UniqueConstraint("registration_id", "member_id", name="uq_team_season_member"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    registration_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("team_season_registrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    member_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("team_members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Free text role within the season's team, e.g. "Programmierer".
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)

    registration: Mapped[TeamSeasonRegistration] = relationship(
        TeamSeasonRegistration, back_populates="roster"
    )
    member: Mapped[TeamMember] = relationship(TeamMember)


# ── Team documents ────────────────────────────────────────────────────────────

DOCUMENT_CATEGORIES = ("project_plan", "presentation", "code_documentation", "other")


class TeamDocument(Base):
    """A team document (project plan, presentation, code documentation, …).

    The file itself lives in TeamDocumentVersion rows: every upload is a new
    version, nothing is overwritten, so the archive of older versions stays.
    """

    __tablename__ = "team_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="other")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    versions: Mapped[list[TeamDocumentVersion]] = relationship(
        "TeamDocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="TeamDocumentVersion.version_number",
    )


class TeamDocumentVersion(Base):
    __tablename__ = "team_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_team_document_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("team_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Relative to settings.upload_dir.
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[TeamDocument] = relationship(TeamDocument, back_populates="versions")


# ── 3D-print compliance checklist ─────────────────────────────────────────────


class PrintComplianceItem(Base):
    """One rule of a season's 3D-print checklist (competition rules for printed
    robot parts, module 04), configured by the organizers."""

    __tablename__ = "print_compliance_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Inactive items are kept (earlier ticks refer to them) but no longer count.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PrintComplianceCheck(Base):
    """A team's answer to one checklist item: ticked by the mentor, verified
    by an organizer. Changing the tick clears the verification."""

    __tablename__ = "print_compliance_checks"
    __table_args__ = (UniqueConstraint("team_id", "item_id", name="uq_print_compliance_check"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("print_compliance_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
