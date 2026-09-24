"""Mentors may only score their own team on the event platform routes.

Migration 0014 grants mentors scoring:write for self-service. The season-scoped
scoring routes check team membership (assert_team_access), but the event-scoped
routes and the OCR scan routes were written when only jurors held scoring:write
and did not — so after the two lines of work met, a mentor could enter a score
for any team, or accept a scanned sheet as a rival's official result.
"""

import pytest

from modules.scoring.score_sheets.models import ScoreSheetScan, ScoreSheetTemplate
from modules.teams.models import Team

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
