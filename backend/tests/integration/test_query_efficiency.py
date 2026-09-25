"""Query counts that must not grow with the data: batching, pagination, list payloads."""

import pytest
from sqlalchemy import event as sa_event

from modules.events.models import EventPhase, EventRegistration, MatchParticipant, ScheduledMatch
from modules.scoring import formula_service
from modules.scoring import service as scoring_service
from modules.teams.models import Team, TeamSeasonRegistration
from tests.conftest import test_engine

from .test_security_regressions_2 import _mentor

_TRANSACTION_CONTROL = ("SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO SAVEPOINT", "BEGIN")


@pytest.fixture
def statements():
    """Number of SQL statements executed while the test runs (reset at will).

    Transaction control is not counted: the test session runs inside SAVEPOINTs
    (tests/conftest.py), which the application never issues.
    """
    counter = {"n": 0}

    def count(_conn, _cursor, statement: str, *_args):
        if not statement.lstrip().upper().startswith(_TRANSACTION_CONTROL):
            counter["n"] += 1

    sa_event.listen(test_engine.sync_engine, "before_cursor_execute", count)
    yield counter
    sa_event.remove(test_engine.sync_engine, "before_cursor_execute", count)


async def _teams(db, season, event, count: int, prefix: str = "T") -> list[Team]:
    teams = [Team(name=f"{prefix}{i:02d}", team_number=f"{prefix}{i}") for i in range(count)]
    db.add_all(teams)
    await db.flush()
    for i, team in enumerate(teams):
        category = "botball" if i % 2 == 0 else "open"
        db.add(EventRegistration(event_id=event.id, team_id=team.id, category=category))
        db.add(TeamSeasonRegistration(team_id=team.id, season_id=season.id, category=category))
    await db.commit()
    return teams


# ── Bulk score entry ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_entry_reranks_each_table_once(
    client, db, season, event, auth_headers, monkeypatch
):
    teams = await _teams(db, season, event, 6)
    refreshed: list[tuple[str, str | None]] = []
    original = scoring_service._refresh_ranks

    async def counting(db_, event_id, level_id, *args):
        refreshed.append((event_id, level_id))
        return await original(db_, event_id, level_id, *args)

    monkeypatch.setattr(scoring_service, "_refresh_ranks", counting)
    response = await client.post(
        f"/api/scoring/seasons/{season.id}/matches/bulk",
        headers=auth_headers,
        json={
            "entries": [
                {"team_id": t.id, "event_id": event.id, "raw_scores": {"p": 10 * (i + 1)}}
                for i, t in enumerate(teams)
            ]
        },
    )
    assert response.status_code == 201, response.text
    assert refreshed == [(event.id, None)]
    ranking = await scoring_service.get_ranking(db, event_id=event.id, category="open")
    assert [r.seed_score for r in ranking] == [60, 40, 20]
    assert [r.rank for r in ranking] == [1, 2, 3]


@pytest.mark.asyncio
async def test_bulk_entry_checks_every_team_before_writing(client, db, season, event, team):
    rival = Team(name="Rival", team_number="R1")
    db.add(rival)
    await db.commit()
    _, headers = await _mentor(db, team, email="bulk-mentor@test.com")
    response = await client.post(
        f"/api/scoring/seasons/{season.id}/matches/bulk",
        headers=headers,
        json={
            "entries": [
                {"team_id": team.id, "event_id": event.id, "raw_scores": {"p": 1}},
                {"team_id": rival.id, "event_id": event.id, "raw_scores": {"p": 1}},
            ]
        },
    )
    assert response.status_code == 403
    assert await scoring_service.list_matches(db, event_id=event.id) == []


@pytest.mark.asyncio
async def test_head_to_head_score_reranks_once(db, season, event, admin_user, monkeypatch):
    home, away = await _teams(db, season, event, 2)
    phase = EventPhase(event_id=event.id, name="Seeding", phase_type="seeding", sort_order=0)
    db.add(phase)
    await db.flush()
    scheduled = ScheduledMatch(
        event_id=event.id, phase_id=phase.id, code="S-1", round_number=1, sequence_number=1
    )
    db.add(scheduled)
    await db.flush()
    db.add_all(
        [
            MatchParticipant(scheduled_match_id=scheduled.id, team_id=home.id, position=1),
            MatchParticipant(scheduled_match_id=scheduled.id, team_id=away.id, position=2),
        ]
    )
    await db.commit()
    base = {"season_id": season.id, "event_id": event.id, "scheduled_match_id": scheduled.id}
    await scoring_service.create_match(
        db, {**base, "team_id": home.id, "raw_scores": {"p": 5}}, admin_user.id
    )
    calls: list[str] = []
    original = scoring_service._refresh_ranks

    async def counting(*args, **kwargs):
        calls.append("x")
        return await original(*args, **kwargs)

    monkeypatch.setattr(scoring_service, "_refresh_ranks", counting)
    # The second row of the match also rebuilds the opponent's row.
    await scoring_service.create_match(
        db, {**base, "team_id": away.id, "raw_scores": {"p": 7}}, admin_user.id
    )
    assert calls == ["x"]


# ── Formula inputs ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_overall_ranking_loads_inputs_once_for_all_categories(db, season, event, statements):
    await _teams(db, season, event, 8)
    statements["n"] = 0
    await formula_service.compute_overall_ranking(db, event.id, ["botball"])
    one = statements["n"]
    statements["n"] = 0
    result = await formula_service.compute_overall_ranking(
        db, event.id, ["botball", "open", "aerial", "jbc"]
    )
    assert statements["n"] == one
    assert {r["category"] for r in result} == {"botball", "open"}


# ── Dashboard summary and history ─────────────────────────────────────────────


async def _summary_statements(client, headers, event, statements) -> int:
    statements["n"] = 0
    response = await client.get(f"/api/dashboard/summary?event_id={event.id}", headers=headers)
    assert response.status_code == 200, response.text
    return statements["n"]


@pytest.mark.asyncio
async def test_mentor_summary_queries_do_not_grow_with_teams(client, db, season, event, statements):
    from modules.auth.models import Permission, RolePermission, UserRole
    from modules.teams.models import TeamMember

    teams = await _teams(db, season, event, 4, prefix="M")
    user, headers = await _mentor(db, teams[0], email="summary-mentor@test.com")
    # dashboard:read for the summary route.
    role_id = (
        (await db.execute(UserRole.__table__.select().where(UserRole.user_id == user.id)))
        .first()
        .role_id
    )
    permission = Permission(name="dashboard:read", description="dashboard:read")
    db.add(permission)
    await db.flush()
    db.add(RolePermission(role_id=role_id, permission_id=permission.id))
    await db.commit()
    single = await _summary_statements(client, headers, event, statements)
    for team in teams[1:]:
        db.add(TeamMember(team_id=team.id, user_id=user.id, name="Mentor", role="mentor"))
    await db.commit()
    several = await _summary_statements(client, headers, event, statements)
    body = (await client.get(f"/api/dashboard/summary?event_id={event.id}", headers=headers)).json()
    assert len(body["mentor"]["teams"]) == 4
    assert several == single


@pytest.mark.asyncio
async def test_history_loads_seeding_and_formulas_once_per_event(
    client, db, season, event, auth_headers, statements, monkeypatch
):
    await _teams(db, season, event, 6)
    calls: list[str] = []
    original = formula_service.load_event_inputs

    async def counting(db_, event_id):
        calls.append(event_id)
        return await original(db_, event_id)

    monkeypatch.setattr(formula_service, "load_event_inputs", counting)
    response = await client.get("/api/exports/history.csv", headers=auth_headers)
    assert response.status_code == 200, response.text
    # Six teams in two categories at one event: one load, not one per team.
    assert calls == [event.id]


# ── Pagination and list payloads ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_match_lists_page_and_leave_out_the_snapshot(client, db, season, event, auth_headers):
    teams = await _teams(db, season, event, 5)
    for round_number in (1, 2):
        for team in teams:
            await scoring_service.create_match(
                db,
                {
                    "season_id": season.id,
                    "event_id": event.id,
                    "team_id": team.id,
                    "round_number": round_number,
                    "raw_scores": {"p": 1},
                },
                "admin",
            )
    await db.commit()
    url = f"/api/scoring/seasons/{season.id}/matches?event_id={event.id}"
    everything = (await client.get(url, headers=auth_headers)).json()
    assert len(everything) == 10
    assert "schema_snapshot" not in everything[0]
    pages = [
        (await client.get(f"{url}&limit=4&offset={offset}", headers=auth_headers)).json()
        for offset in (0, 4, 8)
    ]
    assert [len(page) for page in pages] == [4, 4, 2]
    assert [m["id"] for page in pages for m in page] == [m["id"] for m in everything]

    event_list = (
        await client.get(f"/api/v1/events/{event.id}/matches?limit=3", headers=auth_headers)
    ).json()
    assert len(event_list) == 3 and "schema_snapshot" not in event_list[0]
    detail = await client.get(f"/api/scoring/matches/{everything[0]['id']}", headers=auth_headers)
    assert "schema_snapshot" in detail.json()


@pytest.mark.asyncio
async def test_public_results_and_schedule_page(client, db, season, event, auth_headers):
    event.status = "live"
    event.public_results = True
    teams = await _teams(db, season, event, 3)
    for round_number in (1, 2):
        for team in teams:
            await scoring_service.create_match(
                db,
                {
                    "season_id": season.id,
                    "event_id": event.id,
                    "team_id": team.id,
                    "round_number": round_number,
                    "raw_scores": {"p": round_number},
                },
                "admin",
            )
    phase = EventPhase(event_id=event.id, name="Seeding", phase_type="seeding", sort_order=0)
    db.add(phase)
    await db.flush()
    for sequence, status in enumerate(("completed", "scheduled", "cancelled", "scheduled")):
        db.add(
            ScheduledMatch(
                event_id=event.id,
                phase_id=phase.id,
                code=f"P-{sequence}",
                sequence_number=sequence,
                status=status,
            )
        )
    await db.commit()

    base = f"/api/v1/public/events/{event.slug}"
    all_results = (await client.get(f"{base}/results")).json()
    latest = (await client.get(f"{base}/results?limit=2&order=desc")).json()
    assert len(all_results) == 6
    assert [r["id"] for r in latest] == [r["id"] for r in reversed(all_results[-2:])]
    assert (await client.get(f"{base}/results?limit=0")).status_code == 422

    schedule = (await client.get(f"{base}/schedule")).json()
    upcoming = (await client.get(f"{base}/schedule?upcoming=true&limit=1")).json()
    assert len(schedule) == 4
    assert [m["code"] for m in upcoming] == ["P-1"]
