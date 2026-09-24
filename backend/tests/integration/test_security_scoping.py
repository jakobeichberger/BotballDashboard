"""Security regressions from the September 2026 audit.

papers:read, printing:read and teams:read are held by every mentor (and
teams:read by guests), so read endpoints must scope to the caller's own team
the way the write endpoints already did. Also covers the push-recipient rule,
token revocation on password change and the removed public global stream.
"""

from types import SimpleNamespace

import pytest

from core.auth import create_access_token
from modules.auth.models import Permission, Role, RolePermission, User, UserRole
from modules.auth.service import hash_password
from modules.bots.models import Bot
from modules.dashboard.tasks import push_targets
from modules.paper_review.models import Paper
from modules.printing.models import PrintJob
from modules.teams.models import Team, TeamMember


async def _mentor(db, team, permissions, email="mentor@test.com"):
    role = Role(name=f"mentor-{email}", description="Team mentor")
    db.add(role)
    await db.flush()
    for name in permissions:
        perm = Permission(name=name, description=name)
        db.add(perm)
        await db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    user = User(
        email=email,
        display_name="Mentor",
        hashed_password=hash_password("password123"),
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add(TeamMember(team_id=team.id, user_id=user.id, name="Mentor", email=email, role="mentor"))
    await db.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
async def rival(db):
    team = Team(name="Rival Team", country="AT")
    db.add(team)
    await db.flush()
    db.add(TeamMember(team_id=team.id, name="Student", email="student@rival.test"))
    await db.flush()
    return team


class TestPaperReadScoping:
    @pytest.fixture
    async def papers(self, db, season, team, rival):
        own = Paper(season_id=season.id, team_id=team.id, title="Own paper")
        other = Paper(season_id=season.id, team_id=rival.id, title="Rival paper")
        db.add_all([own, other])
        await db.flush()
        return own, other

    @pytest.mark.asyncio
    async def test_mentor_lists_only_own_papers(self, client, db, team, papers):
        _, headers = await _mentor(db, team, ["papers:read"])
        resp = await client.get("/api/papers", headers=headers)
        assert resp.status_code == 200, resp.text
        assert [p["title"] for p in resp.json()] == ["Own paper"]

    @pytest.mark.asyncio
    async def test_mentor_cannot_open_a_rival_paper(self, client, db, team, papers):
        _, headers = await _mentor(db, team, ["papers:read"])
        own, other = papers
        assert (await client.get(f"/api/papers/{own.id}", headers=headers)).status_code == 200
        for path in ("", "/download", "/history"):
            resp = await client.get(f"/api/papers/{other.id}{path}", headers=headers)
            assert resp.status_code == 403, (path, resp.text)

    @pytest.mark.asyncio
    async def test_admin_still_sees_every_paper(self, client, auth_headers, papers):
        resp = await client.get("/api/papers", headers=auth_headers)
        assert {p["title"] for p in resp.json()} == {"Own paper", "Rival paper"}


class TestTeamMemberPrivacy:
    @pytest.mark.asyncio
    async def test_other_teams_member_emails_are_hidden(self, client, db, team, rival):
        _, headers = await _mentor(db, team, ["teams:read"])
        resp = await client.get(f"/api/teams/{rival.id}", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["members"][0]["name"] == "Student"
        assert resp.json()["members"][0]["email"] is None

    @pytest.mark.asyncio
    async def test_own_team_keeps_member_emails(self, client, db, team):
        _, headers = await _mentor(db, team, ["teams:read"])
        resp = await client.get(f"/api/teams/{team.id}", headers=headers)
        assert resp.json()["members"][0]["email"] == "mentor@test.com"

    @pytest.mark.asyncio
    async def test_admin_sees_member_emails(self, client, auth_headers, rival):
        resp = await client.get(f"/api/teams/{rival.id}", headers=auth_headers)
        assert resp.json()["members"][0]["email"] == "student@rival.test"


class TestPrintJobScoping:
    @pytest.mark.asyncio
    async def test_mentor_sees_only_own_jobs_and_quota(self, client, db, season, team, rival):
        db.add_all(
            [
                PrintJob(team_id=team.id, season_id=season.id, file_name="own.stl"),
                PrintJob(team_id=rival.id, season_id=season.id, file_name="rival.stl"),
            ]
        )
        await db.flush()
        _, headers = await _mentor(db, team, ["printing:read"])

        jobs = await client.get("/api/printing/jobs", headers=headers)
        assert [j["file_name"] for j in jobs.json()] == ["own.stl"]

        quota = await client.get(
            "/api/printing/quotas",
            headers=headers,
            params={"team_id": rival.id, "season_id": season.id},
        )
        assert quota.status_code == 403, quota.text


class TestUnpublishedBots:
    @pytest.mark.asyncio
    async def test_drafts_are_hidden_from_other_teams(self, client, db, team, rival):
        draft = Bot(name="Secret", team_id=rival.id, is_published=False)
        public = Bot(name="Shown", team_id=rival.id, is_published=True)
        own_draft = Bot(name="Mine", team_id=team.id, is_published=False)
        db.add_all([draft, public, own_draft])
        await db.flush()
        _, headers = await _mentor(db, team, ["teams:read"])

        names = {b["name"] for b in (await client.get("/api/bots", headers=headers)).json()}
        assert names == {"Shown", "Mine"}
        resp = await client.get(f"/api/bots/{draft.id}", headers=headers)
        assert resp.status_code == 404


class TestPushRecipients:
    subs = [SimpleNamespace(user_id="u1"), SimpleNamespace(user_id="u2")]

    def test_untargeted_events_reach_nobody(self):
        assert push_targets({"message": "Paper status: accepted"}, self.subs) == []

    def test_targeted_events_reach_only_their_users(self):
        assert push_targets({"userIds": ["u2"]}, self.subs) == [self.subs[1]]
        assert push_targets({"userId": "u1"}, self.subs) == [self.subs[0]]

    def test_broadcast_reaches_everyone(self):
        assert push_targets({"broadcast": True}, self.subs) == self.subs


class TestPasswordChangeEndsSessions:
    @pytest.mark.asyncio
    async def test_old_refresh_token_stops_working(self, client, db, admin_user):
        login = await client.post(
            "/api/auth/login", json={"email": admin_user.email, "password": "testpassword"}
        )
        assert login.status_code == 200, login.text
        old_refresh = login.cookies.get("refresh_token")
        access = login.json()["access_token"]
        # The test client shares one session and never commits (get_db does per
        # request), so persist each request's writes as production would.
        await db.commit()

        changed = await client.post(
            "/api/auth/me/password",
            headers={"Authorization": f"Bearer {access}"},
            json={"current_password": "testpassword", "new_password": "a-new-password-1"},
        )
        assert changed.status_code == 204, changed.text
        new_refresh = changed.cookies.get("refresh_token")
        assert new_refresh and new_refresh != old_refresh
        await db.commit()

        client.cookies.clear()
        stale = await client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
        assert stale.status_code == 401, stale.text
        fresh = await client.post("/api/auth/refresh", json={"refresh_token": new_refresh})
        assert fresh.status_code == 200, fresh.text


class TestPublicSurface:
    @pytest.mark.asyncio
    async def test_metrics_are_not_served_through_the_proxy(self, client):
        assert (await client.get("/api/system/metrics")).status_code == 200
        proxied = await client.get(
            "/api/system/metrics", headers={"X-Forwarded-For": "203.0.113.9"}
        )
        assert proxied.status_code == 404

    def test_global_unauthenticated_stream_is_gone(self):
        from main import app

        assert "/api/scoring/scoreboard/ws" not in {getattr(r, "path", "") for r in app.routes}
