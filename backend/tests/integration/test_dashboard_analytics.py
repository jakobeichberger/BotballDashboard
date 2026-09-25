"""Analytics, role summary, deadline calendar and the new exports.

Covers the scoping rules: per-team performance, team reports and practice
figures are for the team itself and organizers only; event statistics are for
jurors (scoring:admin).
"""

from datetime import UTC, date, datetime, timedelta

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
from modules.paper_review.models import Paper
from modules.scoring import service as scoring_service
from modules.scoring.models import Match, ScoringSchema
from modules.seasons.models import SeasonEvent
from modules.teams.models import Team, TeamMember, TeamSeasonRegistration

MENTOR_PERMS = ["scoring:read", "scoring:write", "teams:read", "dashboard:read", "seasons:read"]
JUROR_PERMS = [
    "scoring:read",
    "scoring:write",
    "scoring:admin",
    "teams:read",
    "dashboard:read",
    "seasons:read",
]
GUEST_PERMS = ["scoring:read", "teams:read", "dashboard:read", "seasons:read"]

FIELDS = [
    {
        "key": "cubes",
        "label": "Würfel",
        "type": "count",
        "multiplier": 10,
        "min_value": 0,
        "max_value": 20,
        "required": False,
    },
    {
        "key": "park",
        "label": "Parken",
        "type": "boolean",
        "multiplier": 25,
        "min_value": None,
        "max_value": None,
        "required": False,
    },
]


async def _user(db, email, permissions, team=None):
    role = Role(name=f"role-{email}", description=email)
    db.add(role)
    await db.flush()
    for name in permissions:
        perm = (
            await db.execute(select(Permission).where(Permission.name == name))
        ).scalar_one_or_none()
        if perm is None:
            perm = Permission(name=name, description=name)
            db.add(perm)
            await db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    user = User(
        email=email,
        display_name=email.split("@")[0],
        hashed_password=hash_password("password123"),
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    if team is not None:
        db.add(TeamMember(team_id=team.id, user_id=user.id, name=email, role="mentor"))
    await db.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
async def rival(db):
    team = Team(name="Rival Robots", team_number="RR-9", country="AT")
    db.add(team)
    await db.commit()
    return team


@pytest.fixture
async def scored(db, season, event, team, rival, admin_user):
    """Two registered teams with official and practice runs."""
    db.add(ScoringSchema(season_id=season.id, fields=FIELDS, version=1, is_active=True))
    db.add(EventRegistration(event_id=event.id, team_id=team.id, category="botball"))
    db.add(EventRegistration(event_id=event.id, team_id=rival.id, category="botball"))
    # The formula engine's field of teams (season registration today; the
    # event registration is registered as well so either source works).
    db.add(TeamSeasonRegistration(team_id=team.id, season_id=season.id, category="botball"))
    db.add(TeamSeasonRegistration(team_id=rival.id, season_id=season.id, category="botball"))
    await db.flush()

    async def run(team_id, round_number, cubes, park=False, practice=False, entered_by=None):
        return await scoring_service.create_match(
            db,
            {
                "season_id": season.id,
                "event_id": event.id,
                "team_id": team_id,
                "round_number": round_number,
                "raw_scores": {"cubes": cubes, "park": park},
                "is_practice": practice,
            },
            entered_by or admin_user.id,
        )

    for i, cubes in enumerate([5, 6, 7], start=1):
        await run(team.id, i, cubes, park=True)
    for i, cubes in enumerate([10, 11, 12], start=1):
        await run(rival.id, i, cubes)
    await run(team.id, 1, 3, practice=True)
    await run(team.id, 2, 4, practice=True)
    await db.commit()
    return run


# ── Performance ───────────────────────────────────────────────────────────────


class TestPerformance:
    @pytest.mark.asyncio
    async def test_mentor_sees_own_team_performance(self, client, db, event, team, scored):
        _, headers = await _user(db, "mentor@test.com", MENTOR_PERMS, team)
        resp = await client.get(
            f"/api/dashboard/events/{event.id}/teams/{team.id}/performance", headers=headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["summary"]["official_runs"] == 3
        assert data["summary"]["practice_runs"] == 2
        assert sum(1 for r in data["runs"] if r["is_practice"]) == 2
        assert {r["phase"] for r in data["runs"]} == {"practice", "seeding"}
        assert {p["phase"] for p in data["phases"]} == {"practice", "seeding"}

        fields = {f["key"]: f for f in data["fields"]}
        # Parking: the team always parks (25), the rival never → strength.
        assert fields["park"]["team_avg"] > fields["park"]["field_avg"]
        assert "park" in data["strengths"]
        assert "cubes" in data["weaknesses"]

        preview = data["ranking_preview"]
        # Seeding avg of best two: team (95+85... ) = (25+70 + 25+60)/2 = 90,
        # rival (120+110)/2 = 115 → second of two.
        assert preview["seeding_rank"] == 2
        assert preview["seeding_teams"] == 2
        assert preview["points_to_next_rank"] == pytest.approx(25.0)
        assert preview["overall_rank"] is not None

    @pytest.mark.asyncio
    async def test_practice_can_be_excluded(self, client, db, event, team, scored):
        _, headers = await _user(db, "mentor@test.com", MENTOR_PERMS, team)
        resp = await client.get(
            f"/api/dashboard/events/{event.id}/teams/{team.id}/performance",
            params={"include_practice": False},
            headers=headers,
        )
        assert resp.status_code == 200
        fields = {f["key"]: f for f in resp.json()["fields"]}
        assert fields["cubes"]["team_avg"] == pytest.approx(60.0)

    @pytest.mark.asyncio
    async def test_mentor_cannot_read_rival_performance(
        self, client, db, event, team, rival, scored
    ):
        _, headers = await _user(db, "mentor@test.com", MENTOR_PERMS, team)
        resp = await client.get(
            f"/api/dashboard/events/{event.id}/teams/{rival.id}/performance", headers=headers
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_guest_cannot_read_any_team_performance(self, client, db, event, team, scored):
        _, headers = await _user(db, "guest@test.com", GUEST_PERMS)
        resp = await client.get(
            f"/api/dashboard/events/{event.id}/teams/{team.id}/performance", headers=headers
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_juror_reads_any_team(self, client, db, event, rival, scored):
        _, headers = await _user(db, "juror@test.com", JUROR_PERMS)
        resp = await client.get(
            f"/api/dashboard/events/{event.id}/teams/{rival.id}/performance", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["ranking_preview"]["seeding_rank"] == 1

    @pytest.mark.asyncio
    async def test_overview_is_scoped(self, client, db, event, team, rival, scored):
        _, mentor = await _user(db, "mentor@test.com", MENTOR_PERMS, team)
        _, juror = await _user(db, "juror@test.com", JUROR_PERMS)
        own = await client.get(f"/api/dashboard/events/{event.id}/performance", headers=mentor)
        assert own.status_code == 200
        assert [r["team_id"] for r in own.json()] == [team.id]
        everyone = await client.get(f"/api/dashboard/events/{event.id}/performance", headers=juror)
        # Sorted by official average: rival first.
        assert [r["team_id"] for r in everyone.json()] == [rival.id, team.id]


# ── Statistics & anomalies ────────────────────────────────────────────────────


class TestStatistics:
    @pytest.mark.asyncio
    async def test_requires_scoring_admin(self, client, db, event, team, scored):
        _, headers = await _user(db, "mentor@test.com", MENTOR_PERMS, team)
        resp = await client.get(f"/api/dashboard/events/{event.id}/statistics", headers=headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_distribution_heatmap_and_anomalies(
        self, client, db, season, event, rival, scored
    ):
        # A run with an impossible value, as if typed in past the validation.
        bad = Match(
            season_id=season.id,
            event_id=event.id,
            team_id=rival.id,
            round_number=4,
            raw_scores={"cubes": 50, "park": False},
            total_score=500,
        )
        db.add(bad)
        await db.commit()
        _, headers = await _user(db, "juror@test.com", JUROR_PERMS)
        resp = await client.get(f"/api/dashboard/events/{event.id}/statistics", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["overview"]["runs"] == 7  # practice excluded by default
        assert [r["round_number"] for r in data["rounds"]] == [1, 2, 3, 4]
        round1 = data["rounds"][0]
        assert round1["min"] == 75 and round1["max"] == 100
        assert {f["key"] for f in data["fields"]} == {"cubes", "park"}
        assert len(data["heatmap"]["teams"]) == 2
        assert len(data["trend"]["teams"]) == 2

        flagged = {a["match_id"]: a for a in data["anomalies"]}
        assert bad.id in flagged
        assert flagged[bad.id]["severity"] == "error"
        assert any(r["kind"] == "out_of_range" for r in flagged[bad.id]["reasons"])

    @pytest.mark.asyncio
    async def test_practice_included_on_request(self, client, db, event, scored):
        _, headers = await _user(db, "juror@test.com", JUROR_PERMS)
        resp = await client.get(
            f"/api/dashboard/events/{event.id}/statistics",
            params={"include_practice": True},
            headers=headers,
        )
        assert resp.json()["overview"]["runs"] == 8


# ── History ───────────────────────────────────────────────────────────────────


class TestHistory:
    @pytest.mark.asyncio
    async def test_history_rows_with_ranks(self, client, db, event, team, scored):
        _, headers = await _user(db, "mentor@test.com", MENTOR_PERMS, team)
        resp = await client.get(f"/api/dashboard/teams/{team.id}/history", headers=headers)
        assert resp.status_code == 200
        [row] = resp.json()
        assert row["event_id"] == event.id
        assert row["season_year"] == 2026
        assert row["seeding_rank"] == 2
        assert row["seeding_score"] == pytest.approx(90.0)
        assert row["official_runs"] == 3
        assert row["overall_rank"] is not None
        assert row["practice_runs"] == 2

    @pytest.mark.asyncio
    async def test_other_teams_do_not_see_practice(self, client, db, team, rival, scored):
        _, headers = await _user(db, "mentor@test.com", MENTOR_PERMS, rival)
        resp = await client.get(f"/api/dashboard/teams/{team.id}/history", headers=headers)
        assert resp.status_code == 200
        assert resp.json()[0]["practice_runs"] is None


# ── Role summary ──────────────────────────────────────────────────────────────


class TestSummary:
    @pytest.mark.asyncio
    async def test_juror_queue_marks_mentor_entries(self, client, db, event, team, scored):
        mentor, _ = await _user(db, "mentor@test.com", MENTOR_PERMS, team)
        await scored(team.id, 4, 8, entered_by=mentor.id)
        phase = EventPhase(event_id=event.id, name="Seeding", phase_type="seeding", sort_order=0)
        db.add(phase)
        await db.flush()
        sm = ScheduledMatch(
            event_id=event.id,
            phase_id=phase.id,
            code="S-1",
            round_number=1,
            sequence_number=1,
            scheduled_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(sm)
        await db.flush()
        db.add(MatchParticipant(scheduled_match_id=sm.id, team_id=team.id, position=1))
        await db.commit()

        _, headers = await _user(db, "juror@test.com", JUROR_PERMS)
        resp = await client.get(
            "/api/dashboard/summary", params={"event_id": event.id}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mentor"] is None and data["admin"] is None
        juror = data["juror"]
        assert juror["unconfirmed_count"] == 7
        assert juror["unconfirmed"][0]["entered_by_team_member"] is True
        assert [m["code"] for m in juror["upcoming_matches"]] == ["S-1"]
        assert juror["upcoming_matches"][0]["teams"][0]["team_name"] == team.name

    @pytest.mark.asyncio
    async def test_mentor_section_only_own_team(self, client, db, season, event, team, scored):
        db.add(Paper(season_id=season.id, team_id=team.id, title="Our paper", status="submitted"))
        await db.commit()
        _, headers = await _user(db, "mentor@test.com", MENTOR_PERMS, team)
        resp = await client.get(
            "/api/dashboard/summary", params={"event_id": event.id}, headers=headers
        )
        data = resp.json()
        assert data["juror"] is None and data["admin"] is None
        [own] = data["mentor"]["teams"]
        assert own["team_id"] == team.id
        assert own["paper"]["status"] == "submitted"
        assert own["seeding_rank"] == 2
        assert len(own["latest_scores"]) == 5
        assert any(s["is_practice"] for s in own["latest_scores"])

    @pytest.mark.asyncio
    async def test_admin_status_counts(self, client, event, auth_headers, scored):
        resp = await client.get(
            "/api/dashboard/summary", params={"event_id": event.id}, headers=auth_headers
        )
        admin = resp.json()["admin"]
        assert admin["teams_registered"] == 2
        assert admin["teams_scored"] == 2
        assert admin["practice_runs"] == 2
        assert admin["official_runs"] == 6
        assert admin["teams_with_paper"] == 0


# ── Deadlines & iCal ──────────────────────────────────────────────────────────


@pytest.fixture
async def deadlines(db, season, event):
    season.paper_submission_deadline = date.today() + timedelta(days=10)
    season.registration_close = date.today() + timedelta(days=3)
    event.starts_at = datetime.now(UTC) + timedelta(days=20)
    db.add(
        SeasonEvent(
            season_id=season.id,
            title="Kickoff",
            event_type="event",
            event_date=date.today() + timedelta(days=1),
        )
    )
    db.add(
        Event(
            season_id=season.id,
            name="Geheimes Draft-Event",
            slug=f"draft-{season.id}",
            status="draft",
            starts_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    await db.commit()


class TestDeadlines:
    @pytest.mark.asyncio
    async def test_mentor_sees_season_deadlines_without_drafts(
        self, client, db, season, team, deadlines
    ):
        _, headers = await _user(db, "mentor@test.com", MENTOR_PERMS, team)
        resp = await client.get("/api/dashboard/deadlines", headers=headers)
        assert resp.status_code == 200
        titles = [d["title"] for d in resp.json()]
        assert "Paper-Einreichung" in titles
        assert "Kickoff" in titles
        assert "Test Event" in titles
        assert "Geheimes Draft-Event" not in titles
        paper = next(d for d in resp.json() if d["kind"] == "paper")
        assert paper["color"] == "red" and paper["done"] is False
        # Sorted chronologically.
        starts = [d["start"][:10] for d in resp.json()]
        assert starts == sorted(starts)

    @pytest.mark.asyncio
    async def test_organizer_sees_drafts(self, client, auth_headers, deadlines):
        resp = await client.get("/api/dashboard/deadlines", headers=auth_headers)
        assert "Geheimes Draft-Event" in [d["title"] for d in resp.json()]

    @pytest.mark.asyncio
    async def test_timeline(self, client, auth_headers, season, deadlines):
        resp = await client.get(
            f"/api/dashboard/seasons/{season.id}/timeline", headers=auth_headers
        )
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert [e["name"] for e in events] == ["Test Event", "Geheimes Draft-Event"]
        assert events[0]["status"] == "planned"

    @pytest.mark.asyncio
    async def test_ical_feed_token_lifecycle(self, client, db, team, deadlines):
        _, headers = await _user(db, "mentor@test.com", MENTOR_PERMS, team)
        assert (await client.get("/api/dashboard/calendar-feed", headers=headers)).json() == {
            "active": False,
            "created_at": None,
            "last_used_at": None,
        }
        created = await client.post("/api/dashboard/calendar-feed", headers=headers)
        assert created.status_code == 201
        token = created.json()["token"]
        assert created.json()["path"].endswith(token)

        feed = await client.get("/api/dashboard/deadlines.ics", params={"token": token})
        assert feed.status_code == 200
        assert feed.headers["content-type"].startswith("text/calendar")
        assert "SUMMARY:Paper-Einreichung" in feed.text
        assert "Geheimes Draft-Event" not in feed.text

        assert (await client.get("/api/dashboard/calendar-feed", headers=headers)).json()["active"]

        # Rotating invalidates the old URL.
        rotated = (await client.post("/api/dashboard/calendar-feed", headers=headers)).json()
        old = await client.get("/api/dashboard/deadlines.ics", params={"token": token})
        assert old.status_code == 401
        new = await client.get("/api/dashboard/deadlines.ics", params={"token": rotated["token"]})
        assert new.status_code == 200

        # Revoking ends it.
        assert (
            await client.delete("/api/dashboard/calendar-feed", headers=headers)
        ).status_code == 204
        gone = await client.get("/api/dashboard/deadlines.ics", params={"token": rotated["token"]})
        assert gone.status_code == 401

    @pytest.mark.asyncio
    async def test_ical_feed_needs_credentials(self, client, auth_headers, deadlines):
        assert (await client.get("/api/dashboard/deadlines.ics")).status_code == 401
        bad = await client.get("/api/dashboard/deadlines.ics", params={"token": "nope"})
        assert bad.status_code == 401
        ok = await client.get("/api/dashboard/deadlines.ics", headers=auth_headers)
        assert ok.status_code == 200
        assert "BEGIN:VCALENDAR" in ok.text


# ── Exports ───────────────────────────────────────────────────────────────────


class TestExports:
    @pytest.mark.asyncio
    async def test_overall_ranking_csv_and_pdf(
        self, client, event, team, rival, auth_headers, scored
    ):
        csv_resp = await client.get(
            f"/api/exports/events/{event.id}/overall-ranking.csv", headers=auth_headers
        )
        assert csv_resp.status_code == 200
        text = csv_resp.content.decode("utf-8-sig")
        header, first, second = text.strip().splitlines()[:3]
        assert header.startswith("Rank,Team,Category")
        assert "overall" in header
        assert first.startswith("1,Rival Robots")
        assert team.name in second

        pdf = await client.get(
            f"/api/exports/events/{event.id}/overall-ranking.pdf", headers=auth_headers
        )
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_team_report_is_scoped(self, client, db, team, rival, scored):
        _, headers = await _user(db, "mentor@test.com", MENTOR_PERMS, team)
        own = await client.get(f"/api/exports/teams/{team.id}/report.pdf", headers=headers)
        assert own.status_code == 200
        assert own.content.startswith(b"%PDF")
        other = await client.get(f"/api/exports/teams/{rival.id}/report.pdf", headers=headers)
        assert other.status_code == 403
        csv_other = await client.get(f"/api/exports/teams/{rival.id}/history.csv", headers=headers)
        assert csv_other.status_code == 403
        csv_own = await client.get(f"/api/exports/teams/{team.id}/history.csv", headers=headers)
        assert csv_own.status_code == 200
        assert "Übungsläufe" in csv_own.content.decode("utf-8-sig")

    @pytest.mark.asyncio
    async def test_multi_year_export_for_organizers(
        self, client, db, team, rival, auth_headers, scored
    ):
        _, mentor = await _user(db, "mentor@test.com", MENTOR_PERMS, team)
        assert (await client.get("/api/exports/history.csv", headers=mentor)).status_code == 403
        resp = await client.get("/api/exports/history.csv", headers=auth_headers)
        assert resp.status_code == 200
        lines = resp.content.decode("utf-8-sig").strip().splitlines()
        assert len(lines) == 3  # header + two teams
        assert "Übungsläufe" not in lines[0]
