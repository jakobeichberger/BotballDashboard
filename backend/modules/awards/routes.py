"""Awards API.

Reading needs scoring:read; only the jury (awards:admin or scoring:admin)
sees unpublished placings, nominations and jury notes, everyone else gets
the published view (see service.restricted_view). The exports are the
jury's. Nominating, templates, award categories,
computing, the jury decision and publishing need awards:admin or
scoring:admin (the jury; mentors hold scoring:write for their own team and
must not nominate). The public event page reads published awards without
login.
"""

import io

from fastapi import APIRouter, Depends, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import has_elevated_access, require_any_permission, require_permission
from core.database import get_db
from core.files import safe_filename
from core.live import publish_after_commit
from modules.awards import service
from modules.awards.schemas import (
    AwardCategoryCreate,
    AwardCategoryUpdate,
    AwardDecision,
    AwardResponse,
    EventAwardsResponse,
    NominationCreate,
    PublicAward,
    PublishRequest,
    TemplateInfo,
)
from modules.events import service as event_service

router = APIRouter(prefix="/awards", tags=["awards"])
public_router = APIRouter(prefix="/v1/public/events", tags=["public-events"])

_ADMIN_PERMISSIONS = ("awards:admin", "scoring:admin")
_ADMIN = require_any_permission(*_ADMIN_PERMISSIONS)
_NOMINATE = _ADMIN


def _changed(db: AsyncSession, event_id: str) -> None:
    publish_after_commit(db, event_id, "awards_updated")


async def _award(db: AsyncSession, award_id: str) -> dict:
    award = await service.get_award(db, award_id)
    data = await service.event_awards(db, award.event_id)
    return next(a for a in data["awards"] if a["id"] == award_id)


@router.get("/templates", response_model=list[TemplateInfo])
async def list_templates(_=Depends(require_permission("scoring:read"))):
    """Award line-ups of ECER and GCER."""
    return service.list_templates()


@router.get("/events/{event_id}", response_model=EventAwardsResponse)
async def get_event_awards(
    event_id: str,
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    data = await service.event_awards(db, event_id)
    if await has_elevated_access(db, current_user, _ADMIN_PERMISSIONS):
        return data
    return service.restricted_view(data)


@router.post("/events/{event_id}/templates/{template_id}", response_model=EventAwardsResponse)
async def apply_template(
    event_id: str,
    template_id: str,
    _=Depends(_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    """Add the template's awards the event does not have yet."""
    return await service.apply_template(db, event_id, template_id)


@router.post("/events/{event_id}/awards", response_model=AwardResponse, status_code=201)
async def create_award(
    event_id: str,
    body: AwardCategoryCreate,
    _=Depends(_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    award = await service.create_award(db, event_id, body.model_dump())
    return await _award(db, award.id)


@router.put("/{award_id}", response_model=AwardResponse)
async def update_award(
    award_id: str,
    body: AwardCategoryUpdate,
    _=Depends(_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    await service.update_award(db, award_id, body.model_dump())
    return await _award(db, award_id)


@router.delete("/{award_id}", status_code=204)
async def delete_award(
    award_id: str,
    _=Depends(_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_award(db, award_id)
    return Response(status_code=204)


@router.post("/events/{event_id}/compute", response_model=EventAwardsResponse)
async def compute_awards(
    event_id: str,
    award_id: str | None = None,
    current_user=Depends(_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    """Fill the computed awards from the current rankings (and seed the
    Best Paper Presentation nominations from the papers presented on stage)."""
    data = await service.compute(db, event_id, current_user.id, award_id)
    _changed(db, event_id)
    return data


@router.post("/{award_id}/nominations", response_model=AwardResponse, status_code=201)
async def nominate(
    award_id: str,
    body: NominationCreate,
    current_user=Depends(_NOMINATE),
    db: AsyncSession = Depends(get_db),
):
    await service.nominate(db, award_id, body.team_id, body.note, current_user.id)
    return await _award(db, award_id)


@router.delete("/{award_id}/nominations/{team_id}", status_code=204)
async def withdraw_nomination(
    award_id: str,
    team_id: str,
    _=Depends(_NOMINATE),
    db: AsyncSession = Depends(get_db),
):
    await service.withdraw_nomination(db, award_id, team_id)
    return Response(status_code=204)


@router.put("/{award_id}/results", response_model=AwardResponse)
async def decide_award(
    award_id: str,
    body: AwardDecision,
    current_user=Depends(_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    """The jury's placing; replaces the award's results.

    Changing or clearing an existing decision needs ``replace: true``."""
    await service.decide(
        db,
        award_id,
        [p.model_dump() for p in body.placements],
        current_user.id,
        replace=body.replace,
    )
    award = await service.get_award(db, award_id)
    _changed(db, award.event_id)
    return await _award(db, award_id)


@router.put("/events/{event_id}/publish", response_model=EventAwardsResponse)
async def publish_awards(
    event_id: str,
    body: PublishRequest,
    _=Depends(_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    """Show (or hide) the placed awards on the public event page."""
    data = await service.set_published(db, event_id, body.published)
    _changed(db, event_id)
    return data


@router.get("/events/{event_id}/export.csv")
async def export_awards_csv(
    event_id: str,
    _=Depends(_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    from modules.exports.routes import _SafeWriter

    event = await event_service.get_event(db, event_id)
    data = await service.event_awards(db, event_id)
    buf = io.StringIO()
    writer = _SafeWriter(buf)
    writer.writerow(["Award", "Course", "Place", "Team ID", "Team", "Score"])
    writer.writerows(service.export_rows(data))
    name = safe_filename(f"awards-{event.slug}.csv", "awards.csv")
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/events/{event_id}/export.pdf")
async def export_awards_pdf(
    event_id: str,
    _=Depends(_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    from modules.exports import pdf_builder
    from modules.seasons.service import get_season

    event = await event_service.get_event(db, event_id)
    season = await get_season(db, event.season_id)
    data = await service.event_awards(db, event_id)
    content = await run_in_threadpool(
        pdf_builder.build_awards_pdf, event.name, season.name, data["awards"]
    )
    name = safe_filename(f"awards-{event.slug}.pdf", "awards.pdf")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@public_router.get("/{slug}/awards", response_model=list[PublicAward])
async def get_public_awards(slug: str, db: AsyncSession = Depends(get_db)):
    """Published awards of a public event (404 until the organisers publish)."""
    event = await event_service.get_public_event(db, slug)
    return await service.public_awards(db, event)
