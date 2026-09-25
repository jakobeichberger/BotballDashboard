"""Versioned team documents: upload, versions, download, access control."""

from pathlib import Path

import pytest

from core.config import get_settings
from modules.teams.models import Team, TeamMember
from tests.paper_helpers import headers_for, make_user

PDF_V1 = b"%PDF-1.4 project plan v1"
PDF_V2 = b"%PDF-1.4 project plan v2 with more detail"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

MENTOR_PERMS = ("teams:read", "teams:write")


async def _mentor(db, team, email="mentor@test.com"):
    user = await make_user(db, email, MENTOR_PERMS)
    db.add(TeamMember(team_id=team.id, user_id=user.id, name="Mentor", role="mentor"))
    await db.commit()
    return user


async def _upload(client, headers, team_id, content=PDF_V1, name="plan.pdf", **form):
    data = {"title": "Projektplan", "category": "project_plan", **form}
    return await client.post(
        f"/api/teams/{team_id}/documents",
        headers=headers,
        data=data,
        files={"file": (name, content, "application/octet-stream")},
    )


class TestTeamDocuments:
    @pytest.mark.asyncio
    async def test_upload_versions_and_download(self, client, db, team, season):
        mentor = await _mentor(db, team)
        headers = headers_for(mentor)
        created = await _upload(client, headers, team.id, season_id=season.id)
        assert created.status_code == 201, created.text
        doc = created.json()
        assert doc["current_version"] == 1
        assert doc["season_id"] == season.id
        assert doc["versions"][0]["media_type"] == "application/pdf"

        v2 = await client.post(
            f"/api/teams/{team.id}/documents/{doc['id']}/versions",
            headers=headers,
            data={"comment": "Zeitplan ergänzt"},
            files={"file": ("plan-v2.pdf", PDF_V2, "application/pdf")},
        )
        assert v2.status_code == 201, v2.text
        assert v2.json()["current_version"] == 2
        assert [v["version_number"] for v in v2.json()["versions"]] == [1, 2]
        assert v2.json()["versions"][1]["comment"] == "Zeitplan ergänzt"

        base = f"/api/teams/{team.id}/documents/{doc['id']}/download"
        latest = await client.get(base, headers=headers)
        assert latest.status_code == 200
        assert latest.content == PDF_V2
        assert latest.headers["content-disposition"].startswith("attachment")
        first = await client.get(base, headers=headers, params={"version": 1})
        assert first.content == PDF_V1
        missing = await client.get(base, headers=headers, params={"version": 9})
        assert missing.status_code == 404

        listing = await client.get(
            f"/api/teams/{team.id}/documents", headers=headers, params={"season_id": season.id}
        )
        assert [d["id"] for d in listing.json()] == [doc["id"]]

    @pytest.mark.asyncio
    async def test_images_accepted_other_types_rejected(self, client, auth_headers, team):
        image = await _upload(client, auth_headers, team.id, content=PNG, name="slide.png")
        assert image.status_code == 201, image.text
        assert image.json()["versions"][0]["media_type"] == "image/png"
        for name, content in (("notes.txt", b"hello"), ("evil.pdf", b"MZ\x90\x00"), ("e", b"")):
            resp = await _upload(client, auth_headers, team.id, content=content, name=name)
            assert resp.status_code == 422, name

    @pytest.mark.asyncio
    async def test_invalid_category_rejected(self, client, auth_headers, team):
        resp = await _upload(client, auth_headers, team.id, category="secret")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_other_teams_and_guests_see_nothing(self, client, db, auth_headers, team):
        doc = (await _upload(client, auth_headers, team.id)).json()
        rival = Team(name="Rival", country="AT")
        db.add(rival)
        await db.commit()
        rival_mentor = await _mentor(db, rival, "rival@test.com")
        guest = await make_user(db, "guest@test.com", ("teams:read",))
        for user in (rival_mentor, guest):
            headers = headers_for(user)
            assert (
                await client.get(f"/api/teams/{team.id}/documents", headers=headers)
            ).status_code == 404
            assert (
                await client.get(
                    f"/api/teams/{team.id}/documents/{doc['id']}/download", headers=headers
                )
            ).status_code == 404
        upload = await _upload(client, headers_for(rival_mentor), team.id)
        assert upload.status_code == 404

    @pytest.mark.asyncio
    async def test_document_of_other_team_not_reachable_via_own_team(
        self, client, db, auth_headers, team
    ):
        doc = (await _upload(client, auth_headers, team.id)).json()
        rival = Team(name="Rival", country="AT")
        db.add(rival)
        await db.commit()
        mentor = await _mentor(db, rival, "rival@test.com")
        resp = await client.get(
            f"/api/teams/{rival.id}/documents/{doc['id']}/download", headers=headers_for(mentor)
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_and_delete(self, client, db, team):
        mentor = await _mentor(db, team)
        headers = headers_for(mentor)
        doc = (await _upload(client, headers, team.id)).json()
        patched = await client.patch(
            f"/api/teams/{team.id}/documents/{doc['id']}",
            headers=headers,
            json={"title": "Präsentation", "category": "presentation"},
        )
        assert patched.status_code == 200
        assert patched.json()["title"] == "Präsentation"

        stored = Path(get_settings().upload_dir) / "team-documents" / team.id / doc["id"]
        assert stored.is_dir()
        deleted = await client.delete(
            f"/api/teams/{team.id}/documents/{doc['id']}", headers=headers
        )
        assert deleted.status_code == 204
        assert not stored.exists()
        assert (await client.get(f"/api/teams/{team.id}/documents", headers=headers)).json() == []

    @pytest.mark.asyncio
    async def test_traversal_name_is_sanitised(self, client, auth_headers, team):
        resp = await _upload(client, auth_headers, team.id, name="../../../etc/plan.pdf")
        assert resp.status_code == 201
        assert resp.json()["versions"][0]["file_name"] == "plan.pdf"
