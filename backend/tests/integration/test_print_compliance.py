"""3D-print compliance checklist: configuration, mentor ticks, organizer
verification and the warning on print job submission."""

import pytest

from modules.teams.compliance import DEFAULT_ITEMS
from modules.teams.models import Team, TeamMember
from tests.paper_helpers import headers_for, make_user

MENTOR_PERMS = ("teams:read", "teams:write", "printing:read", "printing:write")


async def _mentor(db, team, email="mentor@test.com"):
    user = await make_user(db, email, MENTOR_PERMS)
    db.add(TeamMember(team_id=team.id, user_id=user.id, name="Mentor", role="mentor"))
    await db.commit()
    return user


async def _seed(client, headers, season):
    resp = await client.post(
        "/api/teams/print-compliance/items/defaults",
        headers=headers,
        params={"season_id": season.id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _url(team, season, suffix=""):
    return f"/api/teams/{team.id}/seasons/{season.id}/print-compliance{suffix}"


async def _tick_all(client, headers, team, season, items, checked=True):
    status = None
    for item in items:
        resp = await client.put(
            _url(team, season, f"/{item['id']}"), headers=headers, json={"checked": checked}
        )
        assert resp.status_code == 200, resp.text
        status = resp.json()
    return status


class TestChecklistConfiguration:
    @pytest.mark.asyncio
    async def test_seed_defaults_once(self, client, auth_headers, season):
        items = await _seed(client, auth_headers, season)
        assert len(items) == len(DEFAULT_ITEMS)
        again = await client.post(
            "/api/teams/print-compliance/items/defaults",
            headers=auth_headers,
            params={"season_id": season.id},
        )
        assert again.status_code == 409

    @pytest.mark.asyncio
    async def test_crud_and_permissions(self, client, db, auth_headers, season, team):
        mentor = await _mentor(db, team)
        body = {"season_id": season.id, "label": "Max. 6 Teile (2026)", "sort_order": 5}
        denied = await client.post(
            "/api/teams/print-compliance/items", headers=headers_for(mentor), json=body
        )
        assert denied.status_code == 403
        created = await client.post(
            "/api/teams/print-compliance/items", headers=auth_headers, json=body
        )
        assert created.status_code == 201
        item_id = created.json()["id"]

        printing_admin = await make_user(db, "print@test.com", ("printing:admin",))
        patched = await client.patch(
            f"/api/teams/print-compliance/items/{item_id}",
            headers=headers_for(printing_admin),
            json={"label": "Max. 6 Teile zwischen beiden Robotern"},
        )
        assert patched.status_code == 200
        listed = await client.get(
            "/api/teams/print-compliance/items",
            headers=headers_for(mentor),
            params={"season_id": season.id},
        )
        assert [i["label"] for i in listed.json()] == ["Max. 6 Teile zwischen beiden Robotern"]

        deleted = await client.delete(
            f"/api/teams/print-compliance/items/{item_id}", headers=auth_headers
        )
        assert deleted.status_code == 204

    @pytest.mark.asyncio
    async def test_answered_item_can_only_be_deactivated(self, client, auth_headers, season, team):
        items = await _seed(client, auth_headers, season)
        await _tick_all(client, auth_headers, team, season, items[:1])
        resp = await client.delete(
            f"/api/teams/print-compliance/items/{items[0]['id']}", headers=auth_headers
        )
        assert resp.status_code == 409
        await client.patch(
            f"/api/teams/print-compliance/items/{items[0]['id']}",
            headers=auth_headers,
            json={"is_active": False},
        )
        status = (await client.get(_url(team, season), headers=auth_headers)).json()
        assert status["total"] == len(items) - 1


class TestTeamChecklist:
    @pytest.mark.asyncio
    async def test_mentor_ticks_organizer_verifies(self, client, db, auth_headers, season, team):
        items = await _seed(client, auth_headers, season)
        mentor = await _mentor(db, team)
        headers = headers_for(mentor)

        status = (await client.get(_url(team, season), headers=headers)).json()
        assert status["total"] == len(items)
        assert status["checked"] == 0
        assert status["complete"] is False

        early = await client.put(_url(team, season, "/verify"), headers=auth_headers, json={})
        assert early.status_code == 409

        status = await _tick_all(client, headers, team, season, items)
        assert status["complete"] is True
        assert status["is_verified"] is False
        assert status["items"][0]["checked_by"] == mentor.id

        mentor_verify = await client.put(_url(team, season, "/verify"), headers=headers, json={})
        assert mentor_verify.status_code == 403
        verified = await client.put(_url(team, season, "/verify"), headers=auth_headers, json={})
        assert verified.status_code == 200
        assert verified.json()["is_verified"] is True
        assert verified.json()["verified"] == len(items)

        # Unticking an item withdraws its verification.
        changed = await client.put(
            _url(team, season, f"/{items[0]['id']}"), headers=headers, json={"checked": False}
        )
        assert changed.json()["is_verified"] is False
        assert changed.json()["items"][0]["verified_at"] is None

    @pytest.mark.asyncio
    async def test_other_teams_cannot_see_or_tick(self, client, db, auth_headers, season, team):
        items = await _seed(client, auth_headers, season)
        rival = Team(name="Rival", country="AT")
        db.add(rival)
        await db.commit()
        mentor = await _mentor(db, rival, "rival@test.com")
        headers = headers_for(mentor)
        assert (await client.get(_url(team, season), headers=headers)).status_code == 404
        tick = await client.put(
            _url(team, season, f"/{items[0]['id']}"), headers=headers, json={"checked": True}
        )
        assert tick.status_code == 404

    @pytest.mark.asyncio
    async def test_item_of_other_season_rejected(self, client, db, auth_headers, season, team):
        from modules.seasons.models import Season

        other = Season(name="Other", year=2025)
        db.add(other)
        await db.commit()
        items = await _seed(client, auth_headers, other)
        resp = await client.put(
            _url(team, season, f"/{items[0]['id']}"), headers=auth_headers, json={"checked": True}
        )
        assert resp.status_code == 404


class TestPrintJobWarning:
    async def _job(self, client, headers, team, season):
        resp = await client.post(
            "/api/printing/jobs",
            headers=headers,
            json={"team_id": team.id, "season_id": season.id, "file_name": "part.stl"},
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    @pytest.mark.asyncio
    async def test_warns_until_checklist_complete(self, client, db, auth_headers, season, team):
        items = await _seed(client, auth_headers, season)
        mentor = await _mentor(db, team)
        headers = headers_for(mentor)

        job = await self._job(client, headers, team, season)
        assert "checklist incomplete" in job["compliance_warning"]
        assert f"{len(items)} of {len(items)}" in job["compliance_warning"]

        await _tick_all(client, headers, team, season, items)
        job = await self._job(client, headers, team, season)
        assert job["compliance_warning"] is None

    @pytest.mark.asyncio
    async def test_no_checklist_no_warning(self, client, auth_headers, season, team):
        job = await self._job(client, auth_headers, team, season)
        assert job["compliance_warning"] is None
