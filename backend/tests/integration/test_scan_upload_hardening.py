"""Score-sheet scan uploads (security review 2026-09, #11).

Uploads were written to disk before the template, team, file type or season
were checked, and the OCR task was queued before the scan row was committed.
"""

import io
import os
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from core.auth import create_access_token
from modules.auth.models import Permission, Role, RolePermission, User, UserRole
from modules.auth.service import hash_password
from modules.events.models import EventRegistration
from modules.teams.models import TeamMember

MENTOR = ["teams:read", "scoring:read", "scoring:write", "events:read"]


async def _mentor(db, email, team):
    role = Role(name=f"role-{email}", description="test")
    db.add(role)
    await db.flush()
    for name in MENTOR:
        perm = (
            await db.execute(select(Permission).where(Permission.name == name))
        ).scalar_one_or_none()
        if perm is None:
            perm = Permission(name=name, description=name)
            db.add(perm)
            await db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    user = User(
        email=email,
        display_name=email,
        hashed_password=hash_password("password123"),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add(TeamMember(team_id=team.id, user_id=user.id, name="M", email=email, role="mentor"))
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _png(size=(40, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
async def template(db, season, event, team, admin_user, tmp_path):
    from modules.scoring.score_sheets.models import ScoreSheetTemplate

    db.add(EventRegistration(event_id=event.id, team_id=team.id))
    template = ScoreSheetTemplate(
        season_id=season.id,
        label="Sheet",
        year=2026,
        file_url=str(tmp_path / "t.pdf"),
        file_name="t.pdf",
        uploaded_by=admin_user.id,
    )
    db.add(template)
    await db.commit()
    return template


@pytest.fixture
def queued(monkeypatch):
    from modules.scoring.score_sheets import tasks

    calls: list[str] = []
    monkeypatch.setattr(tasks.process_scan, "delay", lambda scan_id: calls.append(scan_id))
    return calls


def _stored(event_id: str) -> list[Path]:
    root = Path(os.environ["UPLOAD_DIR"]) / "score_sheet_scans" / event_id
    return sorted(p for p in root.iterdir() if p.is_file()) if root.exists() else []


async def _upload(client, headers, event, team, template_id, content, name="s.png"):
    return await client.post(
        f"/api/v1/events/{event.id}/score-sheet-scans",
        headers=headers,
        data={"template_id": template_id, "team_id": team.id},
        files={"file": (name, content, "image/png")},
    )


@pytest.mark.asyncio
async def test_rejected_uploads_leave_no_file_behind(client, db, event, team, template, queued):
    mentor = await _mentor(db, "m-scan@test.com", team)
    unknown = "00000000-0000-0000-0000-000000000000"
    assert (await _upload(client, mentor, event, team, unknown, _png())).status_code == 422
    # PNG signature, but no decodable image behind it.
    not_an_image = b"\x89PNG\r\n\x1a\n" + b"0" * 1000
    resp = await _upload(client, mentor, event, team, template.id, not_an_image)
    assert resp.status_code == 415, resp.text
    # A GIF is an image, but not one the OCR accepts.
    resp = await _upload(client, mentor, event, team, template.id, b"GIF89a" + b"0" * 64)
    assert resp.status_code == 415, resp.text
    assert _stored(event.id) == []
    assert queued == []


@pytest.mark.asyncio
async def test_scan_for_a_foreign_head_to_head_match_is_refused(
    client, db, event, team, template, queued
):
    """A scan of team A attached to a match between B and C (security review #2)."""
    from modules.events.models import EventPhase, MatchParticipant, ScheduledMatch
    from modules.teams.models import Team

    phase = EventPhase(event_id=event.id, name="DS", phase_type="double_seeding", sort_order=1)
    others = [Team(name="B", country="AT"), Team(name="C", country="DE")]
    db.add_all([phase, *others])
    await db.flush()
    scheduled = ScheduledMatch(
        event_id=event.id, phase_id=phase.id, code="DS-1", round_number=1, sequence_number=1
    )
    db.add(scheduled)
    await db.flush()
    for position, other in enumerate(others, start=1):
        db.add(
            MatchParticipant(scheduled_match_id=scheduled.id, team_id=other.id, position=position)
        )
    await db.commit()
    mentor = await _mentor(db, "m-scan-h2h@test.com", team)
    resp = await client.post(
        f"/api/v1/events/{event.id}/score-sheet-scans",
        headers=mentor,
        data={"template_id": template.id, "team_id": team.id, "scheduled_match_id": scheduled.id},
        files={"file": ("s.png", _png(), "image/png")},
    )
    assert resp.status_code == 422, resp.text
    assert "does not play" in resp.json()["message"]
    assert _stored(event.id) == []


@pytest.mark.asyncio
async def test_oversized_image_is_refused_at_upload(client, db, event, team, template, queued):
    mentor = await _mentor(db, "m-scan-big@test.com", team)
    big = io.BytesIO()
    Image.new("1", (7000, 7000)).save(big, "PNG")  # 49 MP, a few KB
    resp = await _upload(client, mentor, event, team, template.id, big.getvalue())
    assert resp.status_code == 422, resp.text
    assert _stored(event.id) == []


@pytest.mark.asyncio
async def test_archived_season_refuses_upload_and_retry(
    client, db, auth_headers, admin_user, season, event, team, template, queued
):
    from modules.scoring.score_sheets.models import ScoreSheetScan

    scan = ScoreSheetScan(
        event_id=event.id,
        template_id=template.id,
        team_id=team.id,
        file_url="/tmp/none.png",
        file_name="none.png",
        status="failed",
        created_by=admin_user.id,
    )
    db.add(scan)
    season.status = "archived"
    await db.commit()
    resp = await _upload(client, auth_headers, event, team, template.id, _png())
    assert resp.status_code == 409, resp.text
    assert _stored(event.id) == []
    retry = await client.post(
        f"/api/v1/events/{event.id}/score-sheet-scans/{scan.id}/retry", headers=auth_headers
    )
    assert retry.status_code == 409, retry.text
    assert queued == []


@pytest.mark.asyncio
async def test_valid_upload_is_stored_and_queued_after_commit(
    client, db, event, team, template, queued
):
    from core.task_queue import drain_pending_tasks

    mentor = await _mentor(db, "m-scan2@test.com", team)
    resp = await _upload(client, mentor, event, team, template.id, _png(), "a.pdf")
    assert resp.status_code == 202, resp.text
    stored = _stored(event.id)
    assert len(stored) == 1
    # Named after the detected type, not after the client's file name.
    assert stored[0].suffix == ".png"
    # The worker must not see the scan before its row is committed.
    assert queued == []
    await db.commit()
    await drain_pending_tasks()
    assert queued == [resp.json()["id"]]


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "suffix"), [("JPEG", ".jpg"), ("WEBP", ".webp"), ("PDF", ".pdf")])
async def test_every_accepted_type_is_stored_under_its_own_suffix(
    client, db, event, team, template, queued, kind, suffix
):
    mentor = await _mentor(db, f"m-scan-{kind.lower()}@test.com", team)
    if kind == "PDF":
        content = b"%PDF-1.4\n%%EOF\n"
    else:
        buf = io.BytesIO()
        Image.new("RGB", (40, 30), "white").save(buf, kind)
        content = buf.getvalue()
    resp = await _upload(client, mentor, event, team, template.id, content, "upload.bin")
    assert resp.status_code == 202, resp.text
    assert [path.suffix for path in _stored(event.id)] == [suffix]


@pytest.mark.asyncio
async def test_rolled_back_upload_is_neither_kept_nor_queued(
    client, db, event, team, template, queued
):
    from core.task_queue import drain_pending_tasks

    mentor = await _mentor(db, "m-scan3@test.com", team)
    event_id = event.id  # the rollback expires the loaded fixtures
    resp = await _upload(client, mentor, event, team, template.id, _png())
    assert resp.status_code == 202, resp.text
    assert len(_stored(event_id)) == 1
    await db.rollback()
    await db.commit()
    await drain_pending_tasks()
    assert queued == []
    assert _stored(event_id) == []
