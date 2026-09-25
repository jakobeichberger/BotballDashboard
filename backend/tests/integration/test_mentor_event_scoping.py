"""Mentors may only score their own team on the event platform routes.

Migration 0014 grants mentors scoring:write for self-service. The season-scoped
scoring routes check team membership (assert_team_access), but the event-scoped
routes and the OCR scan routes were written when only jurors held scoring:write
and did not — so after the two lines of work met, a mentor could enter a score
for any team, or accept a scanned sheet as a rival's official result.
"""

import pytest
from sqlalchemy import select

from core.auth import create_access_token
from modules.auth.models import Permission, Role, RolePermission, User, UserRole
from modules.auth.service import hash_password
from modules.scoring.score_sheets.models import ScoreSheetScan, ScoreSheetTemplate
from modules.teams.models import Team, TeamMember

from .test_security_regressions_2 import _mentor


@pytest.fixture
async def rival(db):
    team = Team(name="Rival Team", country="AT")
    db.add(team)
    await db.flush()
    return team


class TestEventScoreEntry:
    @pytest.mark.asyncio
    async def test_mentor_cannot_score_a_rival_team(self, client, db, event, team, rival):
        _, headers = await _mentor(db, team)
        resp = await client.post(
            f"/api/v1/events/{event.id}/matches",
            headers=headers,
            json={"team_id": rival.id, "raw_scores": {}, "idempotency_key": "mentor-rival-1"},
        )
        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_mentor_is_not_blocked_for_their_own_team(self, client, db, event, team):
        _, headers = await _mentor(db, team)
        resp = await client.post(
            f"/api/v1/events/{event.id}/matches",
            headers=headers,
            json={"team_id": team.id, "raw_scores": {}, "idempotency_key": "mentor-own-1"},
        )
        # Whatever the event's registration rules say, it must not be the
        # team-scoping 403.
        assert resp.status_code != 403, resp.text


class TestScoreSheetScans:
    @pytest.mark.asyncio
    async def test_mentor_cannot_upload_a_scan_for_a_rival(self, client, db, event, team, rival):
        _, headers = await _mentor(db, team)
        resp = await client.post(
            f"/api/v1/events/{event.id}/score-sheet-scans",
            headers=headers,
            data={"template_id": "00000000-0000-0000-0000-000000000000", "team_id": rival.id},
            files={"file": ("sheet.pdf", b"%PDF-1.4\n", "application/pdf")},
        )
        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_mentor_cannot_accept_a_rivals_scan(
        self, client, db, season, event, team, rival, admin_user
    ):
        template = ScoreSheetTemplate(
            season_id=season.id,
            label="Sheet",
            year=2026,
            file_url="/tmp/sheet.pdf",
            file_name="sheet.pdf",
            uploaded_by=admin_user.id,
            ocr_status="done",
        )
        db.add(template)
        await db.flush()
        scan = ScoreSheetScan(
            event_id=event.id,
            template_id=template.id,
            team_id=rival.id,
            file_url="/tmp/scan.pdf",
            file_name="scan.pdf",
            status="needs_review",
            created_by=admin_user.id,
        )
        db.add(scan)
        await db.flush()
        _, headers = await _mentor(db, team)

        accept = await client.post(
            f"/api/v1/events/{event.id}/score-sheet-scans/{scan.id}/accept",
            headers=headers,
            json={"values": {}},
        )
        assert accept.status_code == 403, accept.text

        retry = await client.post(
            f"/api/v1/events/{event.id}/score-sheet-scans/{scan.id}/retry", headers=headers
        )
        assert retry.status_code == 403, retry.text


async def _user_with(db, email, permissions, team=None):
    role = Role(name=f"role-{email}")
    db.add(role)
    await db.flush()
    for name in permissions:
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
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    if team is not None:
        db.add(TeamMember(team_id=team.id, user_id=user.id, name=email, role="mentor"))
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


class TestScanVisibility:
    """Guests (scoring:read) and mentors only see their own teams' scans."""

    @pytest.fixture
    async def scans(self, db, season, event, team, rival, admin_user, tmp_path):
        template = ScoreSheetTemplate(
            season_id=season.id,
            label="Sheet",
            year=2026,
            file_url=str(tmp_path / "sheet.pdf"),
            file_name="sheet.pdf",
            uploaded_by=admin_user.id,
            ocr_status="done",
        )
        db.add(template)
        await db.flush()
        result = {}
        for owner in (team, rival):
            scan = ScoreSheetScan(
                event_id=event.id,
                template_id=template.id,
                team_id=owner.id,
                file_url=str(tmp_path / f"{owner.id}.pdf"),
                file_name="scan.pdf",
                status="needs_review",
                created_by=admin_user.id,
            )
            db.add(scan)
            await db.flush()
            crops = tmp_path / scan.id / "crops"
            crops.mkdir(parents=True)
            (crops / "field.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            result[owner.id] = scan
        await db.commit()
        return result

    @pytest.mark.asyncio
    async def test_guest_sees_no_foreign_scans(self, client, db, event, team, rival, scans):
        headers = await _user_with(db, "guest@test.com", ["scoring:read"])
        base = f"/api/v1/events/{event.id}/score-sheet-scans"
        resp = await client.get(base, headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []
        rival_scan = scans[rival.id]
        assert (await client.get(f"{base}/{rival_scan.id}", headers=headers)).status_code == 403
        crop = await client.get(f"{base}/{rival_scan.id}/crops/field.png", headers=headers)
        assert crop.status_code == 403

    @pytest.mark.asyncio
    async def test_mentor_sees_only_own_team(self, client, db, event, team, rival, scans):
        headers = await _user_with(
            db, "mentor-scan@test.com", ["scoring:read", "scoring:write"], team=team
        )
        base = f"/api/v1/events/{event.id}/score-sheet-scans"
        listed = (await client.get(base, headers=headers)).json()
        assert [s["team_id"] for s in listed] == [team.id]
        own = scans[team.id]
        assert (await client.get(f"{base}/{own.id}", headers=headers)).status_code == 200
        crop = await client.get(f"{base}/{own.id}/crops/field.png", headers=headers)
        assert crop.status_code == 200
        rival_scan = scans[rival.id]
        assert (await client.get(f"{base}/{rival_scan.id}", headers=headers)).status_code == 403

    @pytest.mark.asyncio
    async def test_juror_sees_all_scans(self, client, db, event, team, rival, scans):
        headers = await _user_with(db, "juror@test.com", ["scoring:read", "scoring:admin"])
        base = f"/api/v1/events/{event.id}/score-sheet-scans"
        listed = (await client.get(base, headers=headers)).json()
        assert {s["team_id"] for s in listed} == {team.id, rival.id}
        rival_scan = scans[rival.id]
        assert (await client.get(f"{base}/{rival_scan.id}", headers=headers)).status_code == 200
        crop = await client.get(f"{base}/{rival_scan.id}/crops/field.png", headers=headers)
        assert crop.status_code == 200
