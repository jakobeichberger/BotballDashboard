"""Second round of review findings — all were reachable from the API.

  1. MatchUpdate accepted total_score, so anyone allowed to edit a match (incl.
     a mentor on their own) could write an arbitrary score into the public
     ranking. compute_match_total also scored unknown keys with multiplier 1.
  2. The de/aerial/doc result routes were only gated on scoring:write, which
     migration 0010 newly granted to mentors -> a mentor could overwrite any
     team's bracket/aerial/documentation scores.
  3. GET /papers/{id} embedded every review, bypassing the papers:admin gate on
     GET /papers/{id}/reviews.
  4. Bot images were served with a media type guessed from the filename.
  5. CSV exports did not neutralise spreadsheet formulas.
"""
import pytest

from core.auth import create_access_token
from modules.auth.models import Permission, Role, RolePermission, User, UserRole
from modules.auth.service import hash_password
from modules.scoring.models import ScoringSchema
from modules.teams.models import Team, TeamMember

GIF = b"GIF87a" + b"\x00" * 32


async def _mentor(db, team, email="m2@test.com"):
    role = Role(name=f"mentor-{email}", description="Team mentor")
    db.add(role)
    await db.flush()
    for name in ("scoring:write", "papers:read", "teams:read"):
        p = Permission(name=f"{name}-{email}" if False else name, description=name)
        db.add(p)
        await db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    user = User(email=email, display_name="Mentor", hashed_password=hash_password("password123"),
                is_active=True, is_superuser=False)
    db.add(user)
    await db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add(TeamMember(team_id=team.id, user_id=user.id, name="Mentor", role="mentor"))
    await db.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
async def schema(db, season):
    db.add(ScoringSchema(
        season_id=season.id, is_active=True,
        fields=[{"key": "cubes", "label": "Cubes", "multiplier": 5, "max_value": 12, "type": "count"}],
    ))
    await db.commit()


class TestScoreCannotBeForged:
    @pytest.mark.asyncio
    async def test_total_score_cannot_be_injected(self, client, db, season, team, schema):
        _, headers = await _mentor(db, team)
        created = await client.post(f"/api/scoring/seasons/{season.id}/matches", headers=headers,
                                    json={"team_id": team.id, "round_number": 1, "raw_scores": {"cubes": 1}})
        assert created.status_code == 201
        assert created.json()["total_score"] == 5
        await db.commit()

        patched = await client.patch(f"/api/scoring/matches/{created.json()['id']}", headers=headers,
                                     json={"total_score": 999999})
        assert patched.status_code == 200
        assert patched.json()["total_score"] == 5, "client-supplied total_score must be ignored"

    @pytest.mark.asyncio
    async def test_unknown_fields_score_nothing(self, client, db, season, team, schema, auth_headers):
        created = await client.post(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers,
                                    json={"team_id": team.id, "round_number": 1,
                                          "raw_scores": {"totally_made_up": 50000}})
        assert created.status_code == 201
        assert created.json()["total_score"] == 0

    @pytest.mark.asyncio
    async def test_values_above_max_are_rejected(self, client, db, season, team, schema, auth_headers):
        # Ignoring unknown keys alone isn't enough — a legit key with an absurd
        # value would still forge a score, so the schema's max_value is enforced.
        created = await client.post(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers,
                                    json={"team_id": team.id, "round_number": 1,
                                          "raw_scores": {"cubes": 99999}})
        assert created.status_code == 422

        ok = await client.post(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers,
                               json={"team_id": team.id, "round_number": 2, "raw_scores": {"cubes": 12}})
        assert ok.status_code == 201
        assert ok.json()["total_score"] == 60  # 12 * 5


class TestOrganizerOnlyResultRoutes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,payload", [
        ("de-results/{team}", {"de_rank": 1, "bracket_score": 0}),
        ("aerial-results/{team}", {"run1": 0}),
        ("doc-scores/{team}", {"part1": 0}),
    ])
    async def test_mentor_cannot_write_result_routes(self, client, db, season, team, path, payload):
        _, headers = await _mentor(db, team)
        url = f"/api/scoring/seasons/{season.id}/" + path.format(team=team.id)
        resp = await client.put(url, headers=headers, json=payload)
        # Even for their OWN team: these are organizer-entered results.
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_organizer_can_still_write(self, client, season, team, auth_headers):
        resp = await client.put(f"/api/scoring/seasons/{season.id}/doc-scores/{team.id}",
                                headers=auth_headers, json={"part1": 50})
        assert resp.status_code == 200


class TestReviewsAreNotLeakedByGetPaper:
    @pytest.mark.asyncio
    async def test_reviews_are_filtered_for_non_admins(self, client, db, season, team, auth_headers):
        paper = await client.post("/api/papers", headers=auth_headers,
                                  json={"season_id": season.id, "team_id": team.id, "title": "P"})
        pid = paper.json()["id"]
        reviewer = User(email="rev2@test.com", display_name="Rev",
                        hashed_password=hash_password("password123"), is_active=True, is_superuser=True)
        db.add(reviewer)
        await db.commit()
        await db.refresh(reviewer)
        await client.post(f"/api/papers/{pid}/assignments", headers=auth_headers,
                          json={"reviewer_id": reviewer.id})
        await db.commit()
        rev_headers = {"Authorization": f"Bearer {create_access_token(reviewer.id)}"}
        await client.put(f"/api/papers/{pid}/reviews", headers=rev_headers,
                         json={"score_content": 3, "comments": "CONFIDENTIAL"})
        await db.commit()

        # An outsider with papers:read must not see the review…
        outsider_team = Team(name="Outsider", country="DE")
        db.add(outsider_team)
        await db.commit()
        await db.refresh(outsider_team)
        _, mentor_headers = await _mentor(db, outsider_team, email="outsider@test.com")
        seen = await client.get(f"/api/papers/{pid}", headers=mentor_headers)
        assert seen.status_code == 200
        assert seen.json()["reviews"] == [], "reviews must not leak via GET /papers/{id}"

        # …the reviewer still gets their own back (the edit form needs it)…
        own = await client.get(f"/api/papers/{pid}", headers=rev_headers)
        assert len(own.json()["reviews"]) == 1

        # …and an organizer sees everything.
        all_reviews = await client.get(f"/api/papers/{pid}", headers=auth_headers)
        assert len(all_reviews.json()["reviews"]) == 1


class TestBotImageIsServedSafely:
    @pytest.mark.asyncio
    async def test_html_named_image_is_not_served_as_html(self, client, db, team, auth_headers):
        bot = await client.post("/api/bots", headers=auth_headers,
                                json={"name": "XSS", "team_id": team.id})
        bid = bot.json()["id"]
        await db.commit()

        up = await client.post(f"/api/bots/{bid}/image", headers=auth_headers,
                               files={"file": ("evil.html", GIF, "image/gif")})
        assert up.status_code == 200
        await db.commit()

        img = await client.get(f"/api/bots/{bid}/image", headers=auth_headers)
        assert img.status_code == 200
        # Served as the validated type, never text/html.
        assert img.headers["content-type"].startswith("image/gif")


class TestCsvFormulaInjection:
    def test_dangerous_prefixes_are_escaped(self):
        from modules.exports.routes import _csv_safe

        for payload in ("=cmd|' /C calc'!A1", "+1+1", "-1+1", "@SUM(A1)"):
            assert _csv_safe(payload).startswith("'")
        assert _csv_safe("RoboLions") == "RoboLions"
        assert _csv_safe(42) == 42
