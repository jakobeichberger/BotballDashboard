"""Integration tests for features added in the detail-pages / review-workflow branch:
season events/deadlines, competition-level CRUD, print-quota editing, custom
roles, paper finalization, and practice-match exclusion from the ranking.

The admin fixture is a superuser and bypasses every permission check.
"""
import pytest

from core.auth import create_access_token


class TestSeasonEvents:
    @pytest.mark.asyncio
    async def test_create_list_delete(self, client, auth_headers, season, db):
        r1 = await client.post(f"/api/seasons/{season.id}/events", headers=auth_headers,
                               json={"title": "Paper deadline", "event_type": "deadline", "event_date": "2026-04-15"})
        assert r1.status_code == 201
        r2 = await client.post(f"/api/seasons/{season.id}/events", headers=auth_headers,
                               json={"title": "Competition day", "event_type": "event", "event_date": "2026-05-08"})
        assert r2.status_code == 201
        await db.commit()

        lst = await client.get(f"/api/seasons/{season.id}/events", headers=auth_headers)
        assert lst.status_code == 200
        events = lst.json()
        assert len(events) == 2
        assert events[0]["event_date"] == "2026-04-15"  # sorted by date
        assert events[0]["event_type"] == "deadline"

        eid = events[0]["id"]
        d = await client.delete(f"/api/seasons/{season.id}/events/{eid}", headers=auth_headers)
        assert d.status_code == 204
        await db.commit()

        lst2 = await client.get(f"/api/seasons/{season.id}/events", headers=auth_headers)
        assert len(lst2.json()) == 1

    @pytest.mark.asyncio
    async def test_delete_missing_event_404(self, client, auth_headers, season):
        d = await client.delete(f"/api/seasons/{season.id}/events/does-not-exist", headers=auth_headers)
        assert d.status_code == 404


class TestCompetitionLevelCrud:
    @pytest.mark.asyncio
    async def test_create_patch_delete(self, client, auth_headers, db):
        c = await client.post("/api/seasons/competition-levels", headers=auth_headers,
                              json={"name": "Senior", "code": "SR"})
        assert c.status_code == 201
        lid = c.json()["id"]
        await db.commit()

        p = await client.patch(f"/api/seasons/competition-levels/{lid}", headers=auth_headers,
                               json={"is_active": False})
        assert p.status_code == 200
        assert p.json()["is_active"] is False
        await db.commit()

        all_lvls = await client.get("/api/seasons/competition-levels/all?include_inactive=true", headers=auth_headers)
        assert any(l["code"] == "SR" for l in all_lvls.json())
        active = await client.get("/api/seasons/competition-levels/all", headers=auth_headers)
        assert not any(l["code"] == "SR" for l in active.json())

        d = await client.delete(f"/api/seasons/competition-levels/{lid}", headers=auth_headers)
        assert d.status_code == 204

    @pytest.mark.asyncio
    async def test_duplicate_code_conflict(self, client, auth_headers, db):
        await client.post("/api/seasons/competition-levels", headers=auth_headers, json={"name": "A", "code": "DUP"})
        await db.commit()
        r = await client.post("/api/seasons/competition-levels", headers=auth_headers, json={"name": "B", "code": "DUP"})
        assert r.status_code == 409


class TestQuotaEditing:
    @pytest.mark.asyncio
    async def test_set_quota(self, client, auth_headers, season, team):
        r = await client.put("/api/printing/quotas", headers=auth_headers,
                             json={"team_id": team.id, "season_id": season.id, "max_parts": 8, "max_grams": 800})
        assert r.status_code == 200
        body = r.json()
        assert body["max_parts"] == 8
        assert body["max_grams"] == 800


class TestRoles:
    @pytest.mark.asyncio
    async def test_permissions_and_create_role(self, client, auth_headers, db):
        from modules.auth.models import Permission
        db.add(Permission(name="scoring:read", description="x"))
        db.add(Permission(name="scoring:write", description="y"))
        await db.commit()

        perms = await client.get("/api/auth/permissions", headers=auth_headers)
        assert perms.status_code == 200
        assert "scoring:read" in [p["name"] for p in perms.json()]

        r = await client.post("/api/auth/roles", headers=auth_headers,
                              json={"name": "head-juror", "description": "chief", "permission_names": ["scoring:read", "scoring:write"]})
        assert r.status_code == 201
        assert len(r.json()["permissions"]) == 2


class TestPracticeMatches:
    @pytest.mark.asyncio
    async def test_practice_excluded_from_ranking(self, client, auth_headers, season, team, db):
        from modules.scoring.models import ScoringSchema
        db.add(ScoringSchema(season_id=season.id, fields=[{"key": "pts", "multiplier": 1}], is_active=True))
        await db.commit()

        r1 = await client.post(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers,
                               json={"team_id": team.id, "round_number": 1, "raw_scores": {"pts": 10}})
        assert r1.status_code == 201
        r2 = await client.post(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers,
                               json={"team_id": team.id, "round_number": 1, "is_practice": True, "raw_scores": {"pts": 100}})
        assert r2.status_code == 201
        await db.commit()

        ranking = await client.get(f"/api/scoring/seasons/{season.id}/ranking", headers=auth_headers)
        rows = ranking.json()
        team_row = next(x for x in rows if x["team_id"] == team.id)
        assert team_row["best_score"] == 10  # practice 100 excluded

        practice = await client.get(f"/api/scoring/seasons/{season.id}/matches?is_practice=true", headers=auth_headers)
        assert len(practice.json()) == 1
        assert practice.json()[0]["total_score"] == 100


class TestPaperFinalize:
    @pytest.mark.asyncio
    async def test_finalize_aggregates_and_ranks(self, client, auth_headers, season, team, db):
        from modules.auth.models import User
        from modules.auth.service import hash_password

        reviewer = User(email="rev@test.com", display_name="Rev", hashed_password=hash_password("password123"),
                        is_active=True, is_superuser=True)  # superuser to bypass papers:review gate
        db.add(reviewer)
        await db.commit()
        await db.refresh(reviewer)

        p = await client.post("/api/papers", headers=auth_headers,
                              json={"season_id": season.id, "team_id": team.id, "title": "P1"})
        assert p.status_code == 201
        pid = p.json()["id"]
        await db.commit()

        a = await client.post(f"/api/papers/{pid}/assignments", headers=auth_headers,
                              json={"reviewer_id": reviewer.id})
        assert a.status_code == 201
        await db.commit()

        rev_headers = {"Authorization": f"Bearer {create_access_token(reviewer.id)}"}
        rv = await client.put(f"/api/papers/{pid}/reviews?submit=true", headers=rev_headers,
                             json={"score_content": 8, "score_methodology": 8, "score_presentation": 8,
                                   "score_originality": 8, "recommendation": "accept"})
        assert rv.status_code == 200
        await db.commit()

        f = await client.post(f"/api/papers/{pid}/finalize", headers=auth_headers)
        assert f.status_code == 200
        body = f.json()
        assert body["final_score"] == 0.8   # mean review score 8 / 10
        assert body["paper_rank"] == 1
