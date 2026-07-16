"""Regression tests for bugs found in the branch review.

Each test pins a hole that was reachable from the API:
  1. bulk match create bypassed the own-team check of the single-create route
  2. PATCH /scoring/matches/{id} had no own-team check at all
  3. PATCH /papers/{id} had no own-team check
  4. ?include_unpublished=true leaked draft announcements to any logged-in user
  5. disqualifying a match left it counted in the ranking (missing flush)
  6. review criteria were unbounded, pushing final_score outside 0-1
"""
import pytest

from core.auth import create_access_token
from modules.auth.models import Permission, Role, RolePermission, User, UserRole
from modules.auth.service import hash_password
from modules.scoring.models import ScoringSchema
from modules.teams.models import Team, TeamMember


async def _mentor(db, team):
    """A non-superuser mentor who belongs to `team`, with the mentor perms that
    migrations 0010/0012 grant."""
    perms = {}
    for name in ("scoring:write", "papers:write", "teams:write"):
        p = Permission(name=name, description=name)
        db.add(p)
        perms[name] = p
    role = Role(name="mentor", description="Team mentor")
    db.add(role)
    await db.flush()
    for p in perms.values():
        db.add(RolePermission(role_id=role.id, permission_id=p.id))

    user = User(email="mentor-reg@test.com", display_name="Mentor",
                hashed_password=hash_password("password123"), is_active=True, is_superuser=False)
    db.add(user)
    await db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add(TeamMember(team_id=team.id, user_id=user.id, name="Mentor", role="mentor"))
    await db.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
async def rival(db):
    t = Team(name="Rival Team", country="DE")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


class TestMentorCannotTouchOtherTeams:
    @pytest.mark.asyncio
    async def test_bulk_create_is_scoped_like_single_create(self, client, db, season, team, rival):
        _, headers = await _mentor(db, team)
        payload = {"entries": [{"team_id": rival.id, "round_number": 1, "raw_scores": {"pts": 10}}]}
        resp = await client.post(f"/api/scoring/seasons/{season.id}/matches/bulk",
                                 headers=headers, json=payload)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_bulk_create_still_works_for_own_team(self, client, db, season, team):
        _, headers = await _mentor(db, team)
        payload = {"entries": [{"team_id": team.id, "round_number": 1, "raw_scores": {"pts": 10}}]}
        resp = await client.post(f"/api/scoring/seasons/{season.id}/matches/bulk",
                                 headers=headers, json=payload)
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_cannot_patch_another_teams_match(self, client, db, season, team, rival, auth_headers):
        created = await client.post(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers,
                                    json={"team_id": rival.id, "round_number": 1, "raw_scores": {"pts": 10}})
        match_id = created.json()["id"]
        await db.commit()

        _, headers = await _mentor(db, team)
        resp = await client.patch(f"/api/scoring/matches/{match_id}", headers=headers,
                                  json={"is_disqualified": True})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_patch_another_teams_paper(self, client, db, season, team, rival, auth_headers):
        created = await client.post("/api/papers", headers=auth_headers,
                                    json={"season_id": season.id, "team_id": rival.id, "title": "Theirs"})
        paper_id = created.json()["id"]
        await db.commit()

        _, headers = await _mentor(db, team)
        resp = await client.patch(f"/api/papers/{paper_id}", headers=headers, json={"title": "Hijacked"})
        assert resp.status_code == 403


class TestDraftAnnouncementsArePrivate:
    @pytest.mark.asyncio
    async def test_plain_user_cannot_list_unpublished(self, client, db):
        user = User(email="nosy@test.com", display_name="Nosy",
                    hashed_password=hash_password("password123"), is_active=True)
        db.add(user)
        await db.commit()
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

        resp = await client.get("/api/dashboard/announcements?include_unpublished=true", headers=headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_list_unpublished(self, client, auth_headers):
        resp = await client.get("/api/dashboard/announcements?include_unpublished=true", headers=auth_headers)
        assert resp.status_code == 200


class TestDisqualificationUpdatesRanking:
    @pytest.mark.asyncio
    async def test_disqualified_match_leaves_the_ranking(self, client, db, season, team, auth_headers):
        db.add(ScoringSchema(season_id=season.id, fields=[{"key": "pts", "multiplier": 1}], is_active=True))
        await db.commit()

        big = await client.post(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers,
                                json={"team_id": team.id, "round_number": 1, "raw_scores": {"pts": 100}})
        await client.post(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers,
                          json={"team_id": team.id, "round_number": 2, "raw_scores": {"pts": 10}})
        await db.commit()

        before = (await client.get(f"/api/scoring/seasons/{season.id}/ranking", headers=auth_headers)).json()[0]
        assert before["best_score"] == 100 and before["rounds_played"] == 2

        await client.patch(f"/api/scoring/matches/{big.json()['id']}", headers=auth_headers,
                           json={"is_disqualified": True})
        await db.commit()

        after = (await client.get(f"/api/scoring/seasons/{season.id}/ranking", headers=auth_headers)).json()[0]
        assert after["rounds_played"] == 1, "disqualified match still counted"
        assert after["best_score"] == 10, "disqualified score still counted"


class TestReviewScoreBounds:
    @pytest.mark.asyncio
    async def test_criteria_above_ten_are_rejected(self, client, db, season, team, auth_headers):
        paper = await client.post("/api/papers", headers=auth_headers,
                                  json={"season_id": season.id, "team_id": team.id, "title": "P"})
        pid = paper.json()["id"]
        reviewer = User(email="rev-bounds@test.com", display_name="Rev",
                        hashed_password=hash_password("password123"), is_active=True, is_superuser=True)
        db.add(reviewer)
        await db.commit()
        await db.refresh(reviewer)
        await client.post(f"/api/papers/{pid}/assignments", headers=auth_headers,
                          json={"reviewer_id": reviewer.id})
        await db.commit()

        headers = {"Authorization": f"Bearer {create_access_token(reviewer.id)}"}
        too_high = await client.put(f"/api/papers/{pid}/reviews?submit=true", headers=headers,
                                    json={"score_content": 100})
        assert too_high.status_code == 422

        negative = await client.put(f"/api/papers/{pid}/reviews?submit=true", headers=headers,
                                    json={"score_content": -5})
        assert negative.status_code == 422

        ok = await client.put(f"/api/papers/{pid}/reviews?submit=true", headers=headers,
                              json={"score_content": 8, "score_methodology": 8,
                                    "score_presentation": 8, "score_originality": 8})
        assert ok.status_code == 200
        await db.commit()

        final = await client.post(f"/api/papers/{pid}/finalize", headers=auth_headers)
        assert 0.0 <= final.json()["final_score"] <= 1.0
