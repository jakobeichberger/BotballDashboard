"""Season lifecycle: creation, status, archive read-only guard, delete rules,
draft visibility, registration window, clone and JSON export."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from core.auth import create_access_token
from modules.auth.models import Permission, Role, RolePermission, User, UserRole
from modules.auth.service import hash_password
from modules.events.models import Event, EventPhase, EventRegistration
from modules.paper_review.models import Paper
from modules.printing.models import PrintJob
from modules.scoring.formula_models import ScoringBracketWeight, ScoringFormula
from modules.scoring.models import Match, ScoringSchema
from modules.seasons.models import Season, SeasonEvent, SeasonPhase
from modules.teams.models import TeamMember, TeamSeasonRegistration


async def _user(db, permissions, email="mentor@test.com", team=None):
    role = Role(name=f"role-{email}")
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
        display_name="Someone",
        hashed_password=hash_password("password123"),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    if team is not None:
        db.add(TeamMember(team_id=team.id, user_id=user.id, name="Mentor", role="mentor"))
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def _archive(client, auth_headers, season_id):
    resp = await client.patch(
        f"/api/seasons/{season_id}", json={"status": "archived"}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "archived"
    assert resp.json()["is_active"] is False


class TestCreateSeason:
    async def test_is_active_on_create_activates_and_deactivates_others(
        self, client, auth_headers, season
    ):
        resp = await client.post(
            "/api/seasons",
            json={"name": "Wizard", "year": 2027, "is_active": True},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["is_active"] is True
        assert resp.json()["status"] == "active"
        active = (await client.get("/api/seasons/active", headers=auth_headers)).json()
        assert active["id"] == resp.json()["id"]
        old = (await client.get(f"/api/seasons/{season.id}", headers=auth_headers)).json()
        assert old["is_active"] is False
        assert old["status"] == "finished"

    async def test_default_is_draft_with_main_event(self, client, auth_headers, db):
        resp = await client.post(
            "/api/seasons", json={"name": "Plain", "year": 2027}, headers=auth_headers
        )
        assert resp.json()["status"] == "draft"
        events = (
            (await db.execute(select(Event).where(Event.season_id == resp.json()["id"])))
            .scalars()
            .all()
        )
        assert len(events) == 1

    async def test_wizard_can_skip_the_default_event(self, client, auth_headers, db):
        resp = await client.post(
            "/api/seasons",
            json={"name": "Wizard", "year": 2027, "is_active": True, "create_default_event": False},
            headers=auth_headers,
        )
        season_id = resp.json()["id"]
        created = await client.post(
            "/api/v1/events",
            json={"season_id": season_id, "name": "Regional", "slug": "regional-2027"},
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text
        events = (
            (await db.execute(select(Event).where(Event.season_id == season_id))).scalars().all()
        )
        assert [e.name for e in events] == ["Regional"]


class TestArchivedIsReadOnly:
    async def test_writes_are_refused(self, client, auth_headers, db, season, event, team):
        db.add(EventRegistration(event_id=event.id, team_id=team.id))
        paper = Paper(season_id=season.id, event_id=event.id, team_id=team.id, title="P")
        job = PrintJob(season_id=season.id, event_id=event.id, team_id=team.id, file_name="a")
        db.add_all([paper, job])
        # Documentation results need their module; the archive guard must win
        # over an otherwise allowed write.
        season.use_documentation_scoring = True
        event.active_modules = [*event.active_modules, "documentation"]
        await db.commit()
        match = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            json={"team_id": team.id, "event_id": event.id},
            headers=auth_headers,
        )
        assert match.status_code == 201, match.text
        match_id = match.json()["id"]

        await _archive(client, auth_headers, season.id)

        attempts = [
            ("post", f"/api/scoring/seasons/{season.id}/matches", {"team_id": team.id}),
            ("patch", f"/api/scoring/matches/{match_id}", {"notes": "x"}),
            ("delete", f"/api/scoring/matches/{match_id}", None),
            ("put", f"/api/scoring/seasons/{season.id}/doc-scores/{team.id}", {"part1": 50}),
            (
                "put",
                f"/api/scoring/formulas/seasons/{season.id}/botball/bracket-weights",
                {"weights": {"A": 1.0}},
            ),
            ("patch", f"/api/v1/events/{event.id}", {"name": "Renamed"}),
            (
                "post",
                f"/api/v1/events/{event.id}/phases",
                {"name": "Seeding", "phase_type": "seeding", "sort_order": 5},
            ),
            (
                "post",
                "/api/v1/events",
                {"season_id": season.id, "name": "New", "slug": "new-event"},
            ),
            ("patch", f"/api/papers/{paper.id}", {"title": "Changed"}),
            ("put", f"/api/papers/{paper.id}/submit", None),
            (
                "post",
                "/api/papers",
                {"season_id": season.id, "team_id": team.id, "title": "Another"},
            ),
            (
                "post",
                "/api/printing/jobs",
                {"season_id": season.id, "team_id": team.id, "file_name": "b.stl"},
            ),
            ("put", f"/api/printing/jobs/{job.id}/approve", None),
            ("post", "/api/teams/registrations", {"season_id": season.id, "team_id": team.id}),
            (
                "post",
                f"/api/seasons/{season.id}/events",
                {"title": "Kickoff", "event_date": "2026-01-01"},
            ),
        ]
        for method, url, body in attempts:
            kwargs = {"headers": auth_headers}
            if body is not None:
                kwargs["json"] = body
            resp = await getattr(client, method)(url, **kwargs)
            assert resp.status_code == 409, (method, url, resp.status_code, resp.text)
            assert "archived" in resp.text

    async def test_season_fields_locked_until_unarchived(self, client, auth_headers, season):
        await _archive(client, auth_headers, season.id)
        resp = await client.patch(
            f"/api/seasons/{season.id}", json={"name": "Renamed"}, headers=auth_headers
        )
        assert resp.status_code == 409
        resp = await client.patch(
            f"/api/seasons/{season.id}", json={"status": "finished"}, headers=auth_headers
        )
        assert resp.status_code == 200
        resp = await client.patch(
            f"/api/seasons/{season.id}", json={"name": "Renamed"}, headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

    async def test_reads_still_work(self, client, auth_headers, season, event):
        await _archive(client, auth_headers, season.id)
        assert (await client.get(f"/api/v1/events/{event.id}", headers=auth_headers)).is_success
        assert (
            await client.get(f"/api/scoring/seasons/{season.id}/matches", headers=auth_headers)
        ).is_success

    async def test_archived_event_is_read_only_and_not_deletable(self, client, auth_headers, event):
        resp = await client.patch(
            f"/api/v1/events/{event.id}", json={"status": "archived"}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        resp = await client.patch(
            f"/api/v1/events/{event.id}", json={"name": "Renamed"}, headers=auth_headers
        )
        assert resp.status_code == 409
        resp = await client.delete(f"/api/v1/events/{event.id}", headers=auth_headers)
        assert resp.status_code == 409
        # Taking it out of the archive is allowed.
        resp = await client.patch(
            f"/api/v1/events/{event.id}", json={"status": "completed"}, headers=auth_headers
        )
        assert resp.status_code == 200


class TestDeleteSeason:
    async def test_empty_season_can_be_deleted(self, client, auth_headers):
        created = await client.post(
            "/api/seasons", json={"name": "Empty", "year": 2030}, headers=auth_headers
        )
        season_id = created.json()["id"]
        resp = await client.delete(f"/api/seasons/{season_id}", headers=auth_headers)
        assert resp.status_code == 204
        assert (
            await client.get(f"/api/seasons/{season_id}", headers=auth_headers)
        ).status_code == 404

    async def test_season_with_data_is_refused(self, client, auth_headers, db, season, team):
        season.is_active = False
        season.status = "finished"
        db.add(TeamSeasonRegistration(season_id=season.id, team_id=team.id))
        await db.commit()
        resp = await client.delete(f"/api/seasons/{season.id}", headers=auth_headers)
        assert resp.status_code == 409
        assert "archive" in resp.text


class TestDraftVisibility:
    async def test_drafts_hidden_from_readers(self, client, auth_headers, db, season, event):
        draft = Season(name="Next year", year=2027)
        db.add(draft)
        await db.flush()
        draft_event = Event(season_id=draft.id, name="Hidden", slug="hidden", status="draft")
        own_draft_event = Event(season_id=season.id, name="Draft", slug="draft-ev")
        db.add_all([draft_event, own_draft_event])
        await db.commit()
        assert draft.status == "draft"

        guest = await _user(db, ["seasons:read", "events:read"], email="guest@test.com")
        seasons = (await client.get("/api/seasons", headers=guest)).json()
        assert {s["id"] for s in seasons} == {season.id}
        assert (await client.get(f"/api/seasons/{draft.id}", headers=guest)).status_code == 404
        events = (await client.get("/api/v1/events", headers=guest)).json()
        assert {e["id"] for e in events} == {event.id}
        for hidden in (draft_event, own_draft_event):
            resp = await client.get(f"/api/v1/events/{hidden.id}", headers=guest)
            assert resp.status_code == 404

        admin_seasons = (await client.get("/api/seasons", headers=auth_headers)).json()
        assert draft.id in {s["id"] for s in admin_seasons}
        admin_events = (await client.get("/api/v1/events", headers=auth_headers)).json()
        assert draft_event.id in {e["id"] for e in admin_events}


class TestRegistrationWindow:
    async def _season(self, db, opens, closes):
        season = Season(
            name="Window",
            year=2026,
            status="active",
            registration_open=opens,
            registration_close=closes,
        )
        db.add(season)
        await db.commit()
        return season

    async def test_mentor_outside_window_rejected(self, client, db, team):
        today = date.today()
        season = await self._season(db, today - timedelta(days=30), today - timedelta(days=1))
        mentor = await _user(db, ["teams:write"], team=team)
        resp = await client.post(
            "/api/teams/registrations",
            json={"season_id": season.id, "team_id": team.id},
            headers=mentor,
        )
        assert resp.status_code == 409
        assert "closed" in resp.text

    async def test_mentor_inside_window_accepted(self, client, db, team):
        today = date.today()
        season = await self._season(db, today - timedelta(days=1), today + timedelta(days=1))
        mentor = await _user(db, ["teams:write"], team=team)
        resp = await client.post(
            "/api/teams/registrations",
            json={"season_id": season.id, "team_id": team.id},
            headers=mentor,
        )
        assert resp.status_code == 201, resp.text

    async def test_admin_may_register_late(self, client, auth_headers, db, team):
        today = date.today()
        season = await self._season(db, None, today - timedelta(days=1))
        resp = await client.post(
            "/api/teams/registrations",
            json={"season_id": season.id, "team_id": team.id},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text


class TestClone:
    async def test_clone_copies_configuration_not_results(
        self, client, auth_headers, db, season, event, team
    ):
        season.year = 2024
        season.paper_submission_deadline = date(2024, 2, 29)
        season.use_aerial = True
        season.active_categories = ["botball", "aerial"]
        event.slug = "ecer-2024"
        event.name = "ECER 2024"
        event.starts_at = datetime(2024, 7, 1, 9, tzinfo=UTC)
        db.add_all(
            [
                SeasonPhase(season_id=season.id, name="Seeding", phase_type="seeding"),
                SeasonEvent(season_id=season.id, title="Kickoff", event_date=date(2024, 1, 10)),
                EventPhase(event_id=event.id, name="Seeding", phase_type="seeding", rounds=3),
                ScoringSchema(season_id=season.id, fields=[{"key": "a"}], version=2),
                ScoringSchema(
                    season_id=season.id, fields=[{"key": "old"}], version=1, is_active=False
                ),
                ScoringFormula(season_id=season.id, key="seed_score", expression="1"),
                ScoringBracketWeight(season_id=season.id, bracket="B", weight=0.5),
                EventRegistration(event_id=event.id, team_id=team.id),
                Match(season_id=season.id, event_id=event.id, team_id=team.id, total_score=5),
            ]
        )
        await db.commit()

        resp = await client.post(
            f"/api/seasons/{season.id}/clone",
            json={"name": "Botball 2025", "year": 2025},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        clone = resp.json()
        assert clone["status"] == "draft" and clone["is_active"] is False
        assert clone["use_aerial"] is True
        assert clone["active_categories"] == ["botball", "aerial"]
        assert clone["paper_submission_deadline"] == "2025-02-28"
        assert [p["name"] for p in clone["phases"]] == ["Seeding"]

        cid = clone["id"]
        events = (await db.execute(select(Event).where(Event.season_id == cid))).scalars().all()
        assert len(events) == 1
        assert events[0].slug == "ecer-2025" and events[0].name == "ECER 2025"
        assert events[0].status == "draft"
        assert events[0].starts_at.year == 2025
        phases = (
            (await db.execute(select(EventPhase).where(EventPhase.event_id == events[0].id)))
            .scalars()
            .all()
        )
        assert [p.name for p in phases] == ["Seeding"]
        deadlines = (
            (await db.execute(select(SeasonEvent).where(SeasonEvent.season_id == cid)))
            .scalars()
            .all()
        )
        assert [d.event_date for d in deadlines] == [date(2025, 1, 10)]
        schemas = (
            (await db.execute(select(ScoringSchema).where(ScoringSchema.season_id == cid)))
            .scalars()
            .all()
        )
        assert [s.fields for s in schemas] == [[{"key": "a"}]]
        formulas = (
            (await db.execute(select(ScoringFormula).where(ScoringFormula.season_id == cid)))
            .scalars()
            .all()
        )
        assert [f.key for f in formulas] == ["seed_score"]
        weights = (
            (
                await db.execute(
                    select(ScoringBracketWeight).where(ScoringBracketWeight.season_id == cid)
                )
            )
            .scalars()
            .all()
        )
        assert [(w.bracket, w.weight) for w in weights] == [("B", 0.5)]
        # No results or registrations were copied.
        assert (await db.execute(select(Match).where(Match.season_id == cid))).first() is None
        regs = await db.execute(
            select(EventRegistration).where(EventRegistration.event_id == events[0].id)
        )
        assert regs.first() is None


class TestExport:
    async def test_export_contains_season_data(self, client, auth_headers, db, season, event, team):
        db.add_all(
            [
                EventRegistration(event_id=event.id, team_id=team.id),
                Match(season_id=season.id, event_id=event.id, team_id=team.id, total_score=7),
                Paper(season_id=season.id, team_id=team.id, title="P", file_url="/secret"),
                PrintJob(season_id=season.id, team_id=team.id, file_name="a.stl"),
                TeamMember(team_id=team.id, name="Kid", email="kid@test.com"),
            ]
        )
        await db.commit()
        resp = await client.get(f"/api/seasons/{season.id}/export.json", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert "attachment" in resp.headers["content-disposition"]
        data = resp.json()
        assert data["season"]["id"] == season.id
        assert [e["id"] for e in data["events"]] == [event.id]
        assert len(data["event_registrations"]) == 1
        assert data["matches"][0]["total_score"] == 7
        assert data["papers"][0]["title"] == "P" and "file_url" not in data["papers"][0]
        assert data["print_jobs"][0]["file_name"] == "a.stl"
        assert [t["name"] for t in data["teams"]] == [team.name]
        assert "kid@test.com" not in resp.text

    async def test_export_requires_season_write(self, client, db, season):
        guest = await _user(db, ["seasons:read"], email="guest2@test.com")
        resp = await client.get(f"/api/seasons/{season.id}/export.json", headers=guest)
        assert resp.status_code == 403
