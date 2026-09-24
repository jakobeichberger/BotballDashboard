"""3D-print compliance checklist per team and season (module 04).

Organizers configure the season's checklist items (the competition rules for
printed robot parts: material, number and size of parts, spare copy for the
judges, STL hand-in, …). A team's mentor ticks the items; an organizer then
verifies the ticked items. Changing a tick clears that item's verification.

The print module asks ``compliance_warning`` when a team submits a print job
and shows the answer as a warning (it does not block the job).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ConflictError, NotFoundError, ValidationError
from modules.seasons.lifecycle import ensure_writable
from modules.teams.models import PrintComplianceCheck, PrintComplianceItem

# Starting point for a season's checklist: the general rules of module 04
# (valid for 2025 and 2026). Season-specific limits (material, number of
# parts) are added or edited by the organizers.
DEFAULT_ITEMS: tuple[tuple[str, str | None], ...] = (
    (
        "Material und Farbe entsprechen den Saisonregeln",
        "z. B. 2025: PLA graustufig; 2026: PLA oder PETG graustufig",
    ),
    (
        "Anzahl gedruckter Teile innerhalb des Limits",
        "Jedes bewegliche Teil zählt einzeln (Kette mit 10 Gliedern = 10 Teile). "
        "Jigs/Positionierhilfen zählen nicht, solange sie nicht am Roboter sind.",
    ),
    ("Jedes Teil passt in den Bauraum 220 × 220 × 250 mm (Ender 3 V3 SE)", None),
    ("Von jedem Teil liegt eine zweite, identische Kopie für die Judges bereit", None),
    ("STL-Dateien aller Teile werden mit Periode 3 eingereicht", None),
    ("Keine Teile werden beim Turnier gedruckt", None),
)


async def list_items(
    db: AsyncSession, season_id: str, include_inactive: bool = False
) -> list[PrintComplianceItem]:
    query = (
        select(PrintComplianceItem)
        .where(PrintComplianceItem.season_id == season_id)
        .order_by(PrintComplianceItem.sort_order, PrintComplianceItem.created_at)
    )
    if not include_inactive:
        query = query.where(PrintComplianceItem.is_active == True)
    return list((await db.execute(query)).scalars().all())


async def get_item(db: AsyncSession, item_id: str) -> PrintComplianceItem:
    item = await db.get(PrintComplianceItem, item_id)
    if not item:
        raise NotFoundError("Checklist item not found")
    return item


async def create_item(db: AsyncSession, data: dict) -> PrintComplianceItem:
    from modules.seasons.models import Season

    if not await db.get(Season, data["season_id"]):
        raise ValidationError("Season not found")
    await ensure_writable(db, season_id=data["season_id"])
    item = PrintComplianceItem(**data)
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


async def update_item(db: AsyncSession, item_id: str, changes: dict) -> PrintComplianceItem:
    item = await get_item(db, item_id)
    await ensure_writable(db, season_id=item.season_id)
    for key in ("label", "sort_order", "is_active"):
        if key in changes and changes[key] is None:
            raise ValidationError(f"{key} must not be empty")
    for key, value in changes.items():
        setattr(item, key, value)
    await db.flush()
    await db.refresh(item)
    return item


async def delete_item(db: AsyncSession, item_id: str) -> None:
    """Delete an item nobody has ticked yet; otherwise deactivate it instead."""
    item = await get_item(db, item_id)
    await ensure_writable(db, season_id=item.season_id)
    ticked = await db.execute(
        select(PrintComplianceCheck.id).where(PrintComplianceCheck.item_id == item.id).limit(1)
    )
    if ticked.scalar_one_or_none():
        raise ConflictError("Teams have answered this item; deactivate it instead")
    await db.delete(item)


async def seed_default_items(db: AsyncSession, season_id: str) -> list[PrintComplianceItem]:
    """Add the module-04 default rules to a season that has no items yet."""
    if await list_items(db, season_id, include_inactive=True):
        raise ConflictError("This season already has a checklist")
    for index, (label, description) in enumerate(DEFAULT_ITEMS):
        await create_item(
            db,
            {
                "season_id": season_id,
                "label": label,
                "description": description,
                "sort_order": index * 10,
            },
        )
    return await list_items(db, season_id)


async def _checks(
    db: AsyncSession, team_id: str, item_ids: list[str]
) -> dict[str, PrintComplianceCheck]:
    if not item_ids:
        return {}
    result = await db.execute(
        select(PrintComplianceCheck).where(
            PrintComplianceCheck.team_id == team_id,
            PrintComplianceCheck.item_id.in_(item_ids),
        )
    )
    return {check.item_id: check for check in result.scalars()}


async def team_status(db: AsyncSession, team_id: str, season_id: str) -> dict:
    """The team's checklist for the season with progress counters."""
    items = await list_items(db, season_id)
    checks = await _checks(db, team_id, [item.id for item in items])
    entries = []
    for item in items:
        check = checks.get(item.id)
        entries.append(
            {
                "item": item,
                "checked": bool(check and check.checked),
                "note": check.note if check else None,
                "checked_by": check.checked_by if check else None,
                "checked_at": check.checked_at if check else None,
                "verified_by": check.verified_by if check else None,
                "verified_at": check.verified_at if check else None,
            }
        )
    checked = sum(1 for e in entries if e["checked"])
    verified = sum(1 for e in entries if e["checked"] and e["verified_at"] is not None)
    return {
        "team_id": team_id,
        "season_id": season_id,
        "items": entries,
        "total": len(entries),
        "checked": checked,
        "verified": verified,
        "complete": checked == len(entries),
        "is_verified": bool(entries) and verified == len(entries),
    }


async def set_check(
    db: AsyncSession,
    team_id: str,
    season_id: str,
    item_id: str,
    *,
    checked: bool,
    note: str | None,
    user_id: str,
) -> dict:
    item = await get_item(db, item_id)
    if item.season_id != season_id or not item.is_active:
        raise NotFoundError("Checklist item not found")
    await ensure_writable(db, season_id=season_id)
    check = (await _checks(db, team_id, [item_id])).get(item_id)
    if check is None:
        check = PrintComplianceCheck(team_id=team_id, item_id=item_id)
        db.add(check)
    if check.checked != checked:
        # What the organizer verified no longer holds.
        check.verified_by = None
        check.verified_at = None
    check.checked = checked
    check.note = (note or "").strip() or None
    check.checked_by = user_id
    check.checked_at = datetime.now(UTC)
    await db.flush()
    return await team_status(db, team_id, season_id)


async def verify(
    db: AsyncSession, team_id: str, season_id: str, *, verified: bool, user_id: str
) -> dict:
    """Verify every ticked item (or withdraw the verification).

    Verification needs a complete checklist: an organizer confirms the whole
    list, not a half-filled one.
    """
    await ensure_writable(db, season_id=season_id)
    status = await team_status(db, team_id, season_id)
    if verified and not (status["total"] and status["complete"]):
        raise ConflictError("The checklist is not complete yet")
    checks = await _checks(db, team_id, [e["item"].id for e in status["items"]])
    now = datetime.now(UTC)
    for check in checks.values():
        if verified and check.checked:
            check.verified_by = user_id
            check.verified_at = now
        elif not verified:
            check.verified_by = None
            check.verified_at = None
    await db.flush()
    return await team_status(db, team_id, season_id)


async def compliance_warning(db: AsyncSession, team_id: str, season_id: str) -> str | None:
    """Warning for a print job submitted without a complete checklist.

    None when the season has no checklist or the team ticked every item.
    """
    status = await team_status(db, team_id, season_id)
    if not status["total"] or status["complete"]:
        return None
    open_items = status["total"] - status["checked"]
    return (
        f"3D-print compliance checklist incomplete: {open_items} of {status['total']} "
        "item(s) not confirmed yet."
    )
