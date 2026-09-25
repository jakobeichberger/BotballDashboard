"""Scouting of external teams (scoped per team) and GCER qualification."""

import uuid

import pytest

from core.auth import create_access_token
from modules.auth.models import Permission, Role, RolePermission, User, UserRole
from modules.auth.service import hash_password
from modules.events.models import EventRegistration
from modules.seasons.models import CompetitionLevel
from modules.teams.models import Team, TeamMember


async def _user(db, permissions, team=None, email=None):
    email = email or f"{uuid.uuid4().hex[:8]}@test.com"
    role = Role(name=f"role-{email}", description="test role")
    db.add(role)
    await db.flush()
    for name in permissions:
        existing = await db.execute(Permission.__table__.select().where(Permission.name == name))
        row = existing.first()
        if row:
            perm_id = row.id
        else:
            perm = Permission(name=name, description=name)
            db.add(perm)
            await db.flush()
            perm_id = perm.id
        db.add(RolePermission(role_id=role.id, permission_id=perm_id))
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
        db.add(TeamMember(team_id=team.id, user_id=user.id, name="Mentor", email=email))
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


MENTOR = ["scoring:read", "scoring:write"]


@pytest.fixture
async def rival(db):
    team = Team(name="Own Second Team", country="AT")
    db.add(team)
    await db.commit()
    return team


@pytest.fixture
async def external(client, auth_headers, season):
    resp = await client.post(
        "/api/scoring/external-teams",
        headers=auth_headers,
        json={"season_id": season.id, "name": "Robo Masters", "number": "25-0538", "country": "KW"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Scouting ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mentor_notes_are_owned_by_their_team(
    client, db, auth_headers, event, team, rival, external
):
    mentor_a = await _user(db, MENTOR, team)
    mentor_b = await _user(db, MENTOR, rival)

    resp = await client.post(
        f"/api/scoring/events/{event.id}/scouting/notes",
        headers=mentor_a,
        json={"external_team_id": external["id"], "body": "Fast drive base", "threat_level": 4},
    )
    assert resp.status_code == 201, resp.text
    note = resp.json()
    assert note["owner_team_id"] == team.id  # defaulted to the mentor's only team

    # A mentor may not write in another team's name.
    resp = await client.post(
        f"/api/scoring/events/{event.id}/scouting/notes",
        headers=mentor_b,
        json={"external_team_id": external["id"], "owner_team_id": team.id, "body": "x"},
    )
    assert resp.status_code == 403

    own_b = await client.post(
        f"/api/scoring/events/{event.id}/scouting/notes",
        headers=mentor_b,
        json={"external_team_id": external["id"], "body": "Weak at the fry station"},
    )
    assert own_b.status_code == 201

    listing_a = await client.get(f"/api/scoring/events/{event.id}/scouting/notes", headers=mentor_a)
    assert [n["body"] for n in listing_a.json()] == ["Fast drive base"]
    listing_all = await client.get(
        f"/api/scoring/events/{event.id}/scouting/notes", headers=auth_headers
    )
    assert len(listing_all.json()) == 2  # organizers see everything

    # Other teams' notes can be neither edited nor deleted (and are not disclosed).
    resp = await client.patch(
        f"/api/scoring/scouting/notes/{note['id']}", headers=mentor_b, json={"body": "hacked"}
    )
    assert resp.status_code == 404
    resp = await client.delete(f"/api/scoring/scouting/notes/{note['id']}", headers=mentor_b)
    assert resp.status_code == 404
    resp = await client.patch(
        f"/api/scoring/scouting/notes/{note['id']}", headers=mentor_a, json={"body": "Very fast"}
    )
    assert resp.status_code == 200 and resp.json()["body"] == "Very fast"


@pytest.mark.asyncio
async def test_read_only_users_cannot_write_scouting(client, db, event, team, external):
    guest = await _user(db, ["scoring:read"], team)
    resp = await client.post(
        f"/api/scoring/events/{event.id}/scouting/notes",
        headers=guest,
        json={"external_team_id": external["id"], "body": "x"},
    )
    assert resp.status_code == 403
    resp = await client.post(
        "/api/scoring/external-teams",
        headers=guest,
        json={"season_id": event.season_id, "name": "Nope"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_opponent_ranking_mixes_own_and_external_teams(
    client, db, auth_headers, event, team, rival, external
):
    for points in (100, 300, 200):
        resp = await client.post(
            f"/api/v1/events/{event.id}/matches",
            headers=auth_headers,
            json={
                "team_id": team.id,
                "raw_scores": {"points": points},
                "idempotency_key": uuid.uuid4().hex,
            },
        )
        assert resp.status_code == 201
    mentor = await _user(db, MENTOR, team)
    for score in (400, 380, 10):
        resp = await client.post(
            f"/api/scoring/events/{event.id}/scouting/observations",
            headers=mentor,
            json={"external_team_id": external["id"], "score": score, "round_number": 1},
        )
        assert resp.status_code == 201, resp.text
    # Another team's observation is not used for this mentor's view …
    other = await _user(db, MENTOR, rival)
    await client.post(
        f"/api/scoring/events/{event.id}/scouting/observations",
        headers=other,
        json={"external_team_id": external["id"], "score": 999},
    )

    resp = await client.get(f"/api/scoring/events/{event.id}/opponent-ranking", headers=mentor)
    assert resp.status_code == 200, resp.text
    rows = [(r["kind"], r["team_name"], r["seed_score"], r["rank"]) for r in resp.json()]
    assert rows == [
        ("external", "Robo Masters", 390.0, 1),
        ("internal", team.name, 250.0, 2),
    ]
    # … but organizers see all observations.
    resp = await client.get(
        f"/api/scoring/events/{event.id}/opponent-ranking", headers=auth_headers
    )
    assert resp.json()[0]["seed_score"] == (999 + 400) / 2

    pdf = await client.get(f"/api/scoring/events/{event.id}/scouting/report.pdf", headers=mentor)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_external_team_edit_rights(client, db, auth_headers, team, external):
    mentor = await _user(db, MENTOR, team)
    resp = await client.patch(
        f"/api/scoring/external-teams/{external['id']}", headers=mentor, json={"notes": "x"}
    )
    assert resp.status_code == 403  # created by the organizer
    resp = await client.patch(
        f"/api/scoring/external-teams/{external['id']}",
        headers=auth_headers,
        json={"school": "Al-Ru'ya Bilingual School"},
    )
    assert resp.status_code == 200 and resp.json()["school"] == "Al-Ru'ya Bilingual School"
    resp = await client.delete(f"/api/scoring/external-teams/{external['id']}", headers=mentor)
    assert resp.status_code == 403
    listing = await client.get(
        f"/api/scoring/seasons/{external['season_id']}/external-teams", headers=mentor
    )
    assert [t["name"] for t in listing.json()] == ["Robo Masters"]


# ── Qualification ─────────────────────────────────────────────────────────────


@pytest.fixture
async def levels(client, auth_headers):
    ecer = await client.post(
        "/api/seasons/competition-levels",
        headers=auth_headers,
        json={"name": "ECER", "code": "ECER", "order": 1},
    )
    assert ecer.status_code == 201, ecer.text
    gcer = await client.post(
        "/api/seasons/competition-levels",
        headers=auth_headers,
        json={
            "name": "GCER",
            "code": "GCER",
            "order": 2,
            "qualifies_from_level_id": ecer.json()["id"],
        },
    )
    assert gcer.status_code == 201, gcer.text
    return ecer.json(), gcer.json()


@pytest.mark.asyncio
async def test_levels_have_order_and_qualification_source(client, auth_headers, levels):
    ecer, gcer = levels
    assert gcer["qualifies_from_level_id"] == ecer["id"] and gcer["order"] == 2
    listing = await client.get("/api/seasons/competition-levels/all", headers=auth_headers)
    assert [level["code"] for level in listing.json()] == ["ECER", "GCER"]

    # No cycles: ECER cannot qualify from GCER.
    resp = await client.patch(
        f"/api/seasons/competition-levels/{ecer['id']}",
        headers=auth_headers,
        json={"qualifies_from_level_id": gcer["id"]},
    )
    assert resp.status_code == 422
    # An explicit null clears the source.
    resp = await client.patch(
        f"/api/seasons/competition-levels/{gcer['id']}",
        headers=auth_headers,
        json={"qualifies_from_level_id": None},
    )
    assert resp.status_code == 200 and resp.json()["qualifies_from_level_id"] is None


@pytest.mark.asyncio
async def test_qualification_gates_gcer_registration(
    client, db, auth_headers, season, event, team, rival, levels
):
    ecer, gcer = levels
    db.add_all(
        [
            EventRegistration(event_id=event.id, team_id=team.id, competition_level_id=ecer["id"]),
            EventRegistration(event_id=event.id, team_id=rival.id, competition_level_id=ecer["id"]),
        ]
    )
    await db.commit()
    gcer_event = await client.post(
        "/api/v1/events",
        headers=auth_headers,
        json={"season_id": season.id, "name": "GCER", "slug": "gcer-event"},
    )
    gcer_event_id = gcer_event.json()["id"]

    # Not qualified yet → registration for the GCER level is refused.
    resp = await client.post(
        f"/api/v1/events/{gcer_event_id}/registrations",
        headers=auth_headers,
        json={"team_id": team.id, "competition_level_id": gcer["id"]},
    )
    assert resp.status_code == 422
    assert "not qualified" in resp.text

    status = await client.get(
        f"/api/scoring/seasons/{season.id}/qualification-status",
        headers=auth_headers,
        params={"level_id": gcer["id"]},
    )
    assert {r["team_id"] for r in status.json()} == {team.id, rival.id}
    assert not any(r["qualified"] for r in status.json())

    resp = await client.post(
        f"/api/scoring/levels/{gcer['id']}/qualify",
        headers=auth_headers,
        json={
            "season_id": season.id,
            "team_ids": [team.id],
            "note": "ECER winner",
            "source_event_id": event.id,
        },
    )
    assert resp.status_code == 201, resp.text
    qualification = resp.json()[0]
    assert qualification["from_level_id"] == ecer["id"]
    assert qualification["note"] == "ECER winner"
    assert qualification["team_name"] == team.name

    listing = await client.get(
        f"/api/scoring/seasons/{season.id}/qualifications",
        headers=auth_headers,
        params={"level_id": gcer["id"]},
    )
    assert [q["team_id"] for q in listing.json()] == [team.id]

    resp = await client.post(
        f"/api/scoring/events/{gcer_event_id}/register-qualified",
        headers=auth_headers,
        json={"level_id": gcer["id"]},
    )
    assert resp.status_code == 201, resp.text
    assert [r["team_id"] for r in resp.json()] == [team.id]
    assert resp.json()[0]["competition_level_id"] == gcer["id"]

    # The rival still cannot be registered at GCER level.
    resp = await client.post(
        f"/api/v1/events/{gcer_event_id}/registrations",
        headers=auth_headers,
        json={"team_id": rival.id, "competition_level_id": gcer["id"]},
    )
    assert resp.status_code == 422

    # A qualification in use cannot be revoked silently.
    resp = await client.delete(
        f"/api/scoring/qualifications/{qualification['id']}", headers=auth_headers
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_only_admins_qualify_teams(client, db, season, team, levels):
    _, gcer = levels
    juror = await _user(db, ["scoring:read", "scoring:write", "scoring:admin"])
    resp = await client.post(
        f"/api/scoring/levels/{gcer['id']}/qualify",
        headers=juror,
        json={"season_id": season.id, "team_ids": [team.id]},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revoke_unused_qualification(client, auth_headers, season, team, levels):
    _, gcer = levels
    resp = await client.post(
        f"/api/scoring/levels/{gcer['id']}/qualify",
        headers=auth_headers,
        json={"season_id": season.id, "team_ids": [team.id, team.id]},
    )
    assert len(resp.json()) == 1
    resp = await client.delete(
        f"/api/scoring/qualifications/{resp.json()[0]['id']}", headers=auth_headers
    )
    assert resp.status_code == 204
    listing = await client.get(
        f"/api/scoring/seasons/{season.id}/qualifications", headers=auth_headers
    )
    assert listing.json() == []


@pytest.mark.asyncio
async def test_levels_without_source_do_not_require_qualification(
    client, db, auth_headers, event, team
):
    level = CompetitionLevel(name="Regional", code="REG")
    db.add(level)
    await db.commit()
    resp = await client.post(
        f"/api/v1/events/{event.id}/registrations",
        headers=auth_headers,
        json={"team_id": team.id, "competition_level_id": level.id},
    )
    assert resp.status_code == 201
