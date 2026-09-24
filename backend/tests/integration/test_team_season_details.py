"""Teams module leftovers: search & filters, season registration details
(PUT /teams/{id}/seasons/{season_id}) and the season-scoped roster."""

import pytest

from modules.seasons.models import Season
from modules.teams.models import Team, TeamMember, TeamSeasonRegistration
from tests.paper_helpers import headers_for, make_user

MENTOR_PERMS = ("teams:read", "teams:write")


async def _mentor(db, team, email="mentor@test.com"):
    user = await make_user(db, email, MENTOR_PERMS)
    db.add(TeamMember(team_id=team.id, user_id=user.id, name="Mentor", role="mentor"))
    await db.commit()
    return user


async def _register(db, team, season, **extra):
    reg = TeamSeasonRegistration(team_id=team.id, season_id=season.id, **extra)
    db.add(reg)
    await db.commit()
    return reg


@pytest.fixture
async def teams(db, season):
    rows = [
        Team(name="Robo Lions", team_number="0815", school="HTL Wien", country="AT"),
        Team(name="Bit Bears", team_number="4711", school="Gymnasium Graz", country="AT"),
        Team(name="Circuit Cats", team_number="1234", school="Schule Berlin", country="DE"),
        Team(name="Old Owls", team_number="9999", school="HTL Wien", country="AT", is_active=False),
    ]
    db.add_all(rows)
    await db.flush()
    db.add(TeamSeasonRegistration(team_id=rows[0].id, season_id=season.id, category="botball"))
    db.add(TeamSeasonRegistration(team_id=rows[1].id, season_id=season.id, category="open"))
    await db.commit()
    return rows


async def _names(client, headers, **params):
    resp = await client.get("/api/teams", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return sorted(t["name"] for t in resp.json())


class TestSearchAndFilters:
    @pytest.mark.asyncio
    async def test_search_matches_name_number_and_school(self, client, auth_headers, teams):
        assert await _names(client, auth_headers, q="lions") == ["Robo Lions"]
        assert await _names(client, auth_headers, q="4711") == ["Bit Bears"]
        assert await _names(client, auth_headers, q="htl wien") == ["Old Owls", "Robo Lions"]
        assert await _names(client, auth_headers, q="nothing like this") == []

    @pytest.mark.asyncio
    async def test_like_wildcards_are_literal(self, client, auth_headers, teams):
        assert await _names(client, auth_headers, q="%") == []
        assert await _names(client, auth_headers, q="_") == []

    @pytest.mark.asyncio
    async def test_country_status_and_category(self, client, auth_headers, teams, season):
        assert await _names(client, auth_headers, country="de") == ["Circuit Cats"]
        assert await _names(client, auth_headers, status="archived") == ["Old Owls"]
        assert "Old Owls" not in await _names(client, auth_headers, status="active")
        assert await _names(client, auth_headers, season_id=season.id) == [
            "Bit Bears",
            "Robo Lions",
        ]
        assert await _names(client, auth_headers, season_id=season.id, category="open") == [
            "Bit Bears"
        ]
        assert await _names(client, auth_headers, country="AT", status="active", q="htl") == [
            "Robo Lions"
        ]

    @pytest.mark.asyncio
    async def test_invalid_status_rejected(self, client, auth_headers, teams):
        resp = await client.get("/api/teams", headers=auth_headers, params={"status": "gone"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_countries(self, client, auth_headers, teams):
        resp = await client.get("/api/teams/countries", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == ["AT", "DE"]


class TestSeasonDetails:
    @pytest.mark.asyncio
    async def test_organizer_edits_everything(self, client, db, auth_headers, team, season):
        await _register(db, team, season)
        resp = await client.put(
            f"/api/teams/{team.id}/seasons/{season.id}",
            headers=auth_headers,
            json={
                "category": "botball",
                "fee_status": "paid",
                "kit_status": "sent",
                "confirmed": True,
                "contact_name": "Frau Direktor",
                "contact_email": "office@schule-wien.at",
                "contact_phone": "+43 1 234",
                "address": "Schulgasse 1\n1010 Wien",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["fee_status"] == "paid"
        assert data["kit_status"] == "sent"
        assert data["confirmed"] is True
        assert data["contact_email"] == "office@schule-wien.at"
        assert data["paper_required"] is True

        listing = await client.get(f"/api/teams/{team.id}/seasons", headers=auth_headers)
        assert listing.json()[0]["address"] == "Schulgasse 1\n1010 Wien"

    @pytest.mark.asyncio
    async def test_switching_to_open_clears_kit(self, client, db, auth_headers, team, season):
        await _register(db, team, season, kit_status="sent")
        resp = await client.put(
            f"/api/teams/{team.id}/seasons/{season.id}",
            headers=auth_headers,
            json={"category": "open"},
        )
        assert resp.json()["category"] == "open"
        assert resp.json()["kit_status"] == "not_sent"

    @pytest.mark.asyncio
    async def test_invalid_values_rejected(self, client, db, auth_headers, team, season):
        await _register(db, team, season)
        url = f"/api/teams/{team.id}/seasons/{season.id}"
        for body in (
            {"fee_status": "maybe"},
            {"kit_status": None},
            {"category": "soccer"},
            {"contact_email": "not-an-email"},
        ):
            resp = await client.put(url, headers=auth_headers, json=body)
            assert resp.status_code == 422, body

    @pytest.mark.asyncio
    async def test_mentor_limited_to_contact_fields(self, client, db, team, season):
        await _register(db, team, season)
        mentor = await _mentor(db, team)
        url = f"/api/teams/{team.id}/seasons/{season.id}"
        ok = await client.put(
            url,
            headers=headers_for(mentor),
            json={"contact_name": "Herr Lehrer", "address": "Weg 2"},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["contact_name"] == "Herr Lehrer"

        for body in ({"fee_status": "paid"}, {"category": "open"}, {"confirmed": True}):
            denied = await client.put(url, headers=headers_for(mentor), json=body)
            assert denied.status_code == 403, body
        reg = await db.get(TeamSeasonRegistration, ok.json()["id"])
        await db.refresh(reg)
        assert reg.fee_status == "pending"

    @pytest.mark.asyncio
    async def test_other_team_mentor_denied(self, client, db, team, season):
        await _register(db, team, season)
        rival = Team(name="Rival", country="AT")
        db.add(rival)
        await db.commit()
        mentor = await _mentor(db, rival)
        resp = await client.put(
            f"/api/teams/{team.id}/seasons/{season.id}",
            headers=headers_for(mentor),
            json={"contact_name": "Hijack"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unregistered_season_is_404(self, client, auth_headers, team, season):
        resp = await client.put(
            f"/api/teams/{team.id}/seasons/{season.id}",
            headers=auth_headers,
            json={"fee_status": "paid"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_contacts_hidden_from_outsiders(self, client, db, team, season):
        await _register(db, team, season, contact_name="Secret", contact_email="s@x.test")
        guest = await make_user(db, "guest@test.com", ("teams:read",))
        for url in (
            f"/api/teams/{team.id}/seasons",
            "/api/teams/registrations",
        ):
            data = (await client.get(url, headers=headers_for(guest))).json()
            assert data[0]["contact_name"] is None
            assert data[0]["contact_email"] is None
            assert data[0]["fee_status"] == "pending"
        mentor = await _mentor(db, team)
        own = (
            await client.get(f"/api/teams/{team.id}/seasons", headers=headers_for(mentor))
        ).json()
        assert own[0]["contact_name"] == "Secret"

    @pytest.mark.asyncio
    async def test_archived_season_read_only(self, client, db, auth_headers, team, season):
        await _register(db, team, season)
        season_row = await db.get(Season, season.id)
        season_row.status = "archived"
        await db.commit()
        resp = await client.put(
            f"/api/teams/{team.id}/seasons/{season.id}",
            headers=auth_headers,
            json={"fee_status": "paid"},
        )
        assert resp.status_code == 409


class TestSeasonRoster:
    @pytest.fixture
    async def members(self, db, team):
        rows = [
            TeamMember(team_id=team.id, name="Anna", role="member"),
            TeamMember(team_id=team.id, name="Ben", role="member"),
        ]
        db.add_all(rows)
        await db.commit()
        return rows

    @pytest.mark.asyncio
    async def test_set_and_replace_roster(self, client, db, team, season, members):
        await _register(db, team, season)
        mentor = await _mentor(db, team)
        url = f"/api/teams/{team.id}/seasons/{season.id}/members"
        resp = await client.put(
            url,
            headers=headers_for(mentor),
            json={
                "members": [
                    {"member_id": members[0].id, "role": "Programmiererin"},
                    {"member_id": members[1].id, "role": "Konstrukteur"},
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        assert {(m["name"], m["role"]) for m in resp.json()} == {
            ("Anna", "Programmiererin"),
            ("Ben", "Konstrukteur"),
        }

        resp = await client.put(
            url,
            headers=headers_for(mentor),
            json={"members": [{"member_id": members[1].id, "role": "Teamleitung"}]},
        )
        assert [(m["name"], m["role"]) for m in resp.json()] == [("Ben", "Teamleitung")]
        read = await client.get(url, headers=headers_for(mentor))
        assert [m["member_id"] for m in read.json()] == [members[1].id]

    @pytest.mark.asyncio
    async def test_roster_is_per_season(self, client, db, auth_headers, team, season, members):
        other = Season(name="Other", year=2025)
        db.add(other)
        await db.flush()
        await _register(db, team, season)
        await _register(db, team, other)
        await client.put(
            f"/api/teams/{team.id}/seasons/{season.id}/members",
            headers=auth_headers,
            json={"members": [{"member_id": members[0].id}]},
        )
        other_roster = await client.get(
            f"/api/teams/{team.id}/seasons/{other.id}/members", headers=auth_headers
        )
        assert other_roster.json() == []

    @pytest.mark.asyncio
    async def test_roster_validation(self, client, db, auth_headers, team, season, members):
        await _register(db, team, season)
        stranger_team = Team(name="Stranger", country="DE")
        db.add(stranger_team)
        await db.flush()
        stranger = TeamMember(team_id=stranger_team.id, name="Stranger")
        db.add(stranger)
        await db.commit()
        url = f"/api/teams/{team.id}/seasons/{season.id}/members"
        foreign = await client.put(
            url, headers=auth_headers, json={"members": [{"member_id": stranger.id}]}
        )
        assert foreign.status_code == 422
        twice = await client.put(
            url,
            headers=auth_headers,
            json={"members": [{"member_id": members[0].id}, {"member_id": members[0].id}]},
        )
        assert twice.status_code == 422

    @pytest.mark.asyncio
    async def test_other_mentor_cannot_set_roster(self, client, db, team, season, members):
        await _register(db, team, season)
        rival = Team(name="Rival", country="AT")
        db.add(rival)
        await db.commit()
        mentor = await _mentor(db, rival)
        resp = await client.put(
            f"/api/teams/{team.id}/seasons/{season.id}/members",
            headers=headers_for(mentor),
            json={"members": []},
        )
        assert resp.status_code == 403
