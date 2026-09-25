"""Access-control gaps of the 2026-09 security review, reproduced over the API.

2.  A score could be attached to a head-to-head match the team does not play in.
5.  Audience-restricted announcements were listed for everyone.
6.  Practice runs and notes of other teams leaked through the match lists,
    the audit trail and the CSV exports.
8.  Mentors could set organizer fields of their team (notes, is_active, …).
10. Draft events were readable through their sub-routes and /scoring/schemas.
12. Team documents could be moved out of (or into) an archived season.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from core.auth import create_access_token
from modules.auth.models import Permission, Role, RolePermission, User, UserRole
from modules.auth.service import hash_password
from modules.events.models import (
    Event,
    EventPhase,
    EventRegistration,
    MatchParticipant,
    ScheduledMatch,
)
from modules.teams.models import Team, TeamMember

MENTOR = [
    "teams:read",
    "teams:write",
    "scoring:read",
    "scoring:write",
    "papers:read",
    "dashboard:read",
    "seasons:read",
    "events:read",
]
GUEST = ["scoring:read", "dashboard:read", "seasons:read", "teams:read", "events:read"]
JUROR = ["scoring:read", "scoring:write", "scoring:admin", "dashboard:read", "events:read"]
REVIEWER = ["papers:read", "papers:review", "dashboard:read", "events:read"]


async def _permission(db, name):
    perm = (
        await db.execute(select(Permission).where(Permission.name == name))
    ).scalar_one_or_none()
    if perm is None:
        perm = Permission(name=name, description=name)
        db.add(perm)
        await db.flush()
    return perm


async def _user(db, email, permissions, team=None):
    role = Role(name=f"role-{email}", description="test")
    db.add(role)
    await db.flush()
    for name in permissions:
        db.add(RolePermission(role_id=role.id, permission_id=(await _permission(db, name)).id))
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
        db.add(TeamMember(team_id=team.id, user_id=user.id, name="M", email=email, role="mentor"))
    await db.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
async def rival(db):
    team = Team(name="Rival", country="AT")
    db.add(team)
    await db.commit()
    return team


# ── 2. Head-to-head scores only for participants ──────────────────────────────


@pytest.fixture
async def h2h(db, event, team, rival):
    third = Team(name="Third", country="DE")
    db.add(third)
    await db.flush()
    for item in (team, rival, third):
        db.add(EventRegistration(event_id=event.id, team_id=item.id))
    phase = EventPhase(event_id=event.id, name="DS", phase_type="double_seeding", sort_order=1)
    db.add(phase)
    await db.flush()
    scheduled = ScheduledMatch(
        event_id=event.id, phase_id=phase.id, code="DS-1", round_number=1, sequence_number=1
    )
    db.add(scheduled)
    await db.flush()
    db.add_all(
        [
            MatchParticipant(scheduled_match_id=scheduled.id, team_id=rival.id, position=1),
            MatchParticipant(scheduled_match_id=scheduled.id, team_id=third.id, position=2),
        ]
    )
    await db.commit()
    return scheduled


class TestHeadToHeadParticipants:
    @pytest.mark.asyncio
    async def test_mentor_cannot_join_a_foreign_match(
        self, client, db, auth_headers, season, event, team, rival, h2h
    ):
        official = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": rival.id, "event_id": event.id, "scheduled_match_id": h2h.id},
        )
        assert official.status_code == 201, official.text
        _, mentor = await _user(db, "m-h2h@test.com", MENTOR, team)
        for number, url in enumerate(
            (f"/api/scoring/seasons/{season.id}/matches", f"/api/v1/events/{event.id}/matches")
        ):
            resp = await client.post(
                url,
                headers=mentor,
                json={
                    "team_id": team.id,
                    "event_id": event.id,
                    "scheduled_match_id": h2h.id,
                    "idempotency_key": f"foreign-h2h-{number}",
                },
            )
            assert resp.status_code == 422, (url, resp.text)
            assert "does not play" in resp.json()["message"], url
        parts = (
            (
                await db.execute(
                    select(MatchParticipant).where(MatchParticipant.scheduled_match_id == h2h.id)
                )
            )
            .scalars()
            .all()
        )
        for part in parts:
            await db.refresh(part)
        # The rival's match stays undecided: its opponent has not played yet.
        assert all(part.result is None for part in parts)

    @pytest.mark.asyncio
    async def test_organizers_cannot_either(self, client, auth_headers, season, event, team, h2h):
        resp = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={"team_id": team.id, "event_id": event.id, "scheduled_match_id": h2h.id},
        )
        assert resp.status_code == 422, resp.text


# ── 5. Announcement audiences ─────────────────────────────────────────────────


class TestAnnouncementAudience:
    @pytest.fixture
    async def announcements(self, client, auth_headers):
        ids = {}
        for audience in ("all", "teams", "reviewers", "jurors", "internal"):
            resp = await client.post(
                "/api/dashboard/announcements",
                headers=auth_headers,
                json={"title": f"for {audience}", "body": "text", "audience": audience},
            )
            assert resp.status_code == 201, resp.text
            ids[audience] = resp.json()["id"]
        expired = await client.post(
            "/api/dashboard/announcements",
            headers=auth_headers,
            json={
                "title": "expired",
                "body": "old",
                "audience": "all",
                "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            },
        )
        ids["expired"] = expired.json()["id"]
        for ann_id in ids.values():
            publish = await client.put(
                f"/api/dashboard/announcements/{ann_id}/publish", headers=auth_headers
            )
            assert publish.status_code == 200
        return ids

    @staticmethod
    async def _titles(client, headers, **params):
        resp = await client.get("/api/dashboard/announcements", headers=headers, params=params)
        assert resp.status_code == 200, resp.text
        return {item["title"] for item in resp.json()}

    @pytest.mark.asyncio
    async def test_each_role_sees_only_its_audience(self, client, db, team, announcements):
        _, guest = await _user(db, "guest-ann@test.com", GUEST)
        _, mentor = await _user(db, "mentor-ann@test.com", MENTOR, team)
        _, juror = await _user(db, "juror-ann@test.com", JUROR)
        _, reviewer = await _user(db, "reviewer-ann@test.com", REVIEWER)
        assert await self._titles(client, guest) == {"for all"}
        assert await self._titles(client, mentor) == {"for all", "for teams"}
        assert await self._titles(client, juror) == {"for all", "for jurors"}
        assert await self._titles(client, reviewer) == {"for all", "for reviewers"}

    @pytest.mark.asyncio
    async def test_organizers_see_every_audience(self, client, auth_headers, announcements):
        visible = await self._titles(client, auth_headers)
        assert visible == {"for all", "for teams", "for reviewers", "for jurors", "for internal"}
        managed = await self._titles(client, auth_headers, include_unpublished=True)
        assert "expired" in managed

    @pytest.mark.asyncio
    async def test_unknown_audience_is_rejected(self, client, auth_headers):
        resp = await client.post(
            "/api/dashboard/announcements",
            headers=auth_headers,
            json={"title": "x", "body": "y", "audience": "everyone"},
        )
        assert resp.status_code == 422


# ── 6. Practice runs and notes of other teams ────────────────────────────────


class TestPracticeRunsStayWithTheTeam:
    @pytest.fixture
    async def runs(self, client, db, auth_headers, season, event, team, rival):
        db.add_all(
            [
                EventRegistration(event_id=event.id, team_id=rival.id),
                EventRegistration(event_id=event.id, team_id=team.id),
            ]
        )
        await db.commit()
        created = {}
        for key, owner, practice, notes in (
            ("rival_practice", rival, True, "strategy B: skip ramp"),
            ("rival_official", rival, False, "juror: robot touched the wall"),
            ("own_practice", team, True, "own practice note"),
        ):
            resp = await client.post(
                f"/api/scoring/seasons/{season.id}/matches",
                headers=auth_headers,
                json={
                    "team_id": owner.id,
                    "event_id": event.id,
                    "is_practice": practice,
                    "raw_scores": {},
                    "notes": notes,
                },
            )
            assert resp.status_code == 201, resp.text
            created[key] = resp.json()["id"]
        return created

    @pytest.mark.asyncio
    async def test_match_lists_hide_foreign_practice_and_notes(
        self, client, db, season, event, team, runs
    ):
        _, mentor = await _user(db, "m-practice@test.com", MENTOR, team)
        for url in (
            f"/api/scoring/seasons/{season.id}/matches",
            f"/api/scoring/seasons/{season.id}/matches?is_practice=true",
            f"/api/v1/events/{event.id}/matches",
        ):
            resp = await client.get(url, headers=mentor)
            assert resp.status_code == 200, resp.text
            rows = {row["id"]: row for row in resp.json()}
            assert runs["rival_practice"] not in rows, url
            assert runs["own_practice"] in rows, url
            assert rows[runs["own_practice"]]["notes"] == "own practice note"
            if runs["rival_official"] in rows:
                assert rows[runs["rival_official"]]["notes"] is None, url

    @pytest.mark.asyncio
    async def test_single_match_and_history_of_foreign_practice_are_hidden(
        self, client, db, team, runs
    ):
        _, mentor = await _user(db, "m-practice2@test.com", MENTOR, team)
        rival_practice = runs["rival_practice"]
        match = await client.get(f"/api/scoring/matches/{rival_practice}", headers=mentor)
        assert match.status_code == 404
        history = await client.get(
            f"/api/scoring/matches/{rival_practice}/revisions", headers=mentor
        )
        assert history.status_code == 404
        own = await client.get(f"/api/scoring/matches/{runs['own_practice']}", headers=mentor)
        assert own.status_code == 200
        official = await client.get(
            f"/api/scoring/matches/{runs['rival_official']}", headers=mentor
        )
        assert official.status_code == 200 and official.json()["notes"] is None

    @pytest.mark.asyncio
    async def test_audit_trail_hides_foreign_practice(
        self, client, db, auth_headers, event, team, runs
    ):
        _, mentor = await _user(db, "m-practice3@test.com", MENTOR, team)
        # Deleting the practice run leaves only its revisions behind.
        deleted = await client.delete(
            f"/api/scoring/matches/{runs['rival_practice']}", headers=auth_headers
        )
        assert deleted.status_code == 204
        resp = await client.get(f"/api/scoring/events/{event.id}/revisions", headers=mentor)
        assert resp.status_code == 200
        refs = {row["match_ref"] for row in resp.json()}
        assert runs["rival_practice"] not in refs
        assert {runs["own_practice"], runs["rival_official"]} <= refs
        for row in resp.json():
            if row["match_ref"] == runs["rival_official"]:
                assert "notes" not in (row["new_value"] or {})
        organizer = await client.get(
            f"/api/scoring/events/{event.id}/revisions", headers=auth_headers
        )
        assert runs["rival_practice"] in {row["match_ref"] for row in organizer.json()}

    @pytest.mark.asyncio
    async def test_csv_exports_hide_foreign_practice(self, client, db, season, event, team, runs):
        _, mentor = await _user(db, "m-practice4@test.com", MENTOR, team)
        for url in (
            f"/api/exports/events/{event.id}/matches.csv",
            f"/api/exports/seasons/{season.id}/matches.csv",
        ):
            resp = await client.get(url, headers=mentor)
            assert resp.status_code == 200, resp.text
            assert runs["rival_practice"] not in resp.text, url
            assert runs["rival_official"] in resp.text, url
            assert "skip ramp" not in resp.text and "touched the wall" not in resp.text

    @pytest.mark.asyncio
    async def test_organizers_still_see_everything(self, client, auth_headers, season, runs):
        resp = await client.get(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers)
        rows = {row["id"]: row for row in resp.json()}
        assert set(runs.values()) <= set(rows)
        assert rows[runs["rival_practice"]]["notes"] == "strategy B: skip ramp"


# ── 8. Organizer-only team fields ─────────────────────────────────────────────


class TestMentorTeamFields:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "change",
        [
            {"notes": "organizer note overwritten"},
            {"is_active": False},
            {"team_number": "999"},
            {"competition_level_id": "00000000-0000-0000-0000-000000000000"},
        ],
    )
    async def test_mentor_cannot_change_organizer_fields(self, client, db, team, change):
        _, mentor = await _user(db, f"m-team-{next(iter(change))}@test.com", MENTOR, team)
        resp = await client.patch(f"/api/teams/{team.id}", headers=mentor, json=change)
        assert resp.status_code == 403, resp.text
        await db.refresh(team)
        assert team.is_active is True and team.notes is None and team.team_number == "TTA-01"

    @pytest.mark.asyncio
    async def test_mentor_keeps_the_team_profile_up_to_date(self, client, db, team):
        _, mentor = await _user(db, "m-team-ok@test.com", MENTOR, team)
        # Older clients send the unchanged organizer fields back as they were.
        resp = await client.patch(
            f"/api/teams/{team.id}",
            headers=mentor,
            json={
                "name": "Renamed",
                "school": "HTL",
                "city": "Wien",
                "country": "AT",
                "team_number": "TTA-01",
                "notes": None,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Renamed" and resp.json()["city"] == "Wien"

    @pytest.mark.asyncio
    async def test_organizers_change_everything(self, client, auth_headers, team):
        resp = await client.patch(
            f"/api/teams/{team.id}",
            headers=auth_headers,
            json={"notes": "checked", "is_active": False, "team_number": "42"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["notes"] == "checked" and resp.json()["is_active"] is False


# ── 10. Draft events ──────────────────────────────────────────────────────────


class TestDraftEventsStayHidden:
    @pytest.fixture
    async def draft(self, db, season, team):
        from modules.scoring.models import ScoringSchema

        event = Event(
            season_id=season.id, name="Secret Draft Cup", slug="secret-draft", status="draft"
        )
        db.add(event)
        await db.flush()
        db.add(
            ScoringSchema(
                season_id=season.id, event_id=event.id, fields=[], version=1, is_active=True
            )
        )
        db.add(EventRegistration(event_id=event.id, team_id=team.id))
        await db.commit()
        return event

    @pytest.mark.asyncio
    async def test_guest_cannot_read_draft_sub_routes(self, client, db, season, draft):
        _, guest = await _user(db, "guest-draft@test.com", GUEST)
        for url in (
            f"/api/v1/events/{draft.id}",
            f"/api/v1/events/{draft.id}/registrations",
            f"/api/v1/events/{draft.id}/phases",
            f"/api/v1/events/{draft.id}/schedule",
            f"/api/v1/events/{draft.id}/modules",
            f"/api/scoring/events/{draft.id}/revisions",
            f"/api/scoring/seasons/{season.id}/matches?event_id={draft.id}",
        ):
            resp = await client.get(url, headers=guest)
            assert resp.status_code == 404, (url, resp.status_code)
        listing = await client.get("/api/scoring/schemas", headers=guest)
        assert listing.status_code == 200
        assert "Secret Draft Cup" not in {row["event_name"] for row in listing.json()}

    @pytest.mark.asyncio
    async def test_event_of_a_draft_season_is_hidden_too(self, client, db, season, event):
        season.status = "draft"
        await db.commit()
        _, guest = await _user(db, "guest-draft2@test.com", GUEST)
        resp = await client.get(f"/api/v1/events/{event.id}/registrations", headers=guest)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_anonymous_requests_still_get_401(self, client, draft):
        resp = await client.get(f"/api/v1/events/{draft.id}/registrations")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_organizers_still_work_on_drafts(self, client, db, draft):
        _, juror = await _user(
            db, "juror-draft@test.com", ["events:read", "events:write", "scoring:read"]
        )
        resp = await client.get(f"/api/v1/events/{draft.id}/registrations", headers=juror)
        assert resp.status_code == 200 and len(resp.json()) == 1
        listing = await client.get("/api/scoring/schemas", headers=juror)
        assert "Secret Draft Cup" in {row["event_name"] for row in listing.json()}


# ── 12. Team documents and archived seasons ───────────────────────────────────


@pytest.mark.asyncio
async def test_document_cannot_leave_or_enter_an_archived_season(client, db, team):
    from modules.seasons.models import Season

    old = Season(name="Old", year=2020, status="active")
    current = Season(name="Current", year=2027, status="active")
    db.add_all([old, current])
    await db.commit()
    _, mentor = await _user(db, "m-doc@test.com", MENTOR, team)
    pdf = b"%PDF-1.4\n%%EOF\n"
    docs = {}
    for season in (old, current):
        resp = await client.post(
            f"/api/teams/{team.id}/documents",
            headers=mentor,
            data={"title": "Plan", "season_id": season.id},
            files={"file": ("a.pdf", pdf, "application/pdf")},
        )
        assert resp.status_code == 201, resp.text
        docs[season.id] = resp.json()["id"]
    old.status = "archived"
    await db.commit()
    moved_out = await client.patch(
        f"/api/teams/{team.id}/documents/{docs[old.id]}",
        headers=mentor,
        json={"season_id": None, "title": "renamed"},
    )
    assert moved_out.status_code == 409, moved_out.text
    moved_in = await client.patch(
        f"/api/teams/{team.id}/documents/{docs[current.id]}",
        headers=mentor,
        json={"season_id": old.id},
    )
    assert moved_in.status_code == 409, moved_in.text
    renamed = await client.patch(
        f"/api/teams/{team.id}/documents/{docs[current.id]}",
        headers=mentor,
        json={"title": "Still editable"},
    )
    assert renamed.status_code == 200, renamed.text
