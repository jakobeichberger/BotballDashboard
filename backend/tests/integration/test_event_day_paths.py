"""Event-day paths without tests before (review 2026-09, #5).

- rescheduling a match (PATCH /events/{id}/schedule/{match_id}): table and
  team conflict checks, table count, optimistic version;
- check-in and level/category changes of a registration;
- creating, updating and deleting phases.

The shared test client neither commits nor rolls back per request (see
tests/conftest.py). Conflicts leave changed rows behind in the session there,
so these tests use a client that ends every request like core.database.get_db:
commit on success, rollback on an error (SAVEPOINTs inside the test's
transaction).

SQLite returns naive datetimes. The conflict checks compare the new slot
with the stored ones, so these tests send naive UTC times; on PostgreSQL
(aware values) a naive slot is a separate problem, see
tests/postgres/test_reschedule_timezones.py.
"""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from core.database import get_db
from main import app
from modules.teams.models import Team

# Naive UTC, like the values SQLite hands back (see the module docstring).
START = datetime(2026, 7, 18, 8, 0)


async def _teams(db, count: int) -> list[Team]:
    teams = [Team(name=f"Day Team {i}", team_number=f"DAY-{i:02d}") for i in range(count)]
    db.add_all(teams)
    await db.commit()
    return teams


async def _seeding_schedule(client, headers, db, event, teams: int = 2, rounds: int = 2):
    """Registered teams, a seeding phase and its generated schedule.

    Seeding = one solo run per team and round; two teams on two tables run in
    parallel, so round 1 is slot 08:00 (tables 1, 2), round 2 slot 08:10.
    """
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    event.table_count = 2
    await db.commit()
    team_rows = await _teams(db, teams)
    for number, team in enumerate(team_rows, start=1):
        response = await client.post(
            f"/api/v1/events/{event_id}/registrations",
            headers=headers,
            json={"team_id": team.id, "seed_number": number},
        )
        assert response.status_code == 201, response.text
    phase = await client.post(
        f"/api/v1/events/{event_id}/phases",
        headers=headers,
        json={"name": "Seeding", "phase_type": "seeding", "sort_order": 0, "rounds": rounds},
    )
    assert phase.status_code == 201, phase.text
    schedule = await client.post(
        f"/api/v1/events/{event_id}/schedule/generate",
        headers=headers,
        json={
            "phase_id": phase.json()["id"],
            "starts_at": START.isoformat(),
            "slot_minutes": 10,
        },
    )
    assert schedule.status_code == 201, schedule.text
    return team_rows, schedule.json()


@pytest_asyncio.fixture
async def client(db):
    """Like conftest's client, but each request commits or rolls back."""

    async def per_request_db():
        try:
            yield db
        except Exception:
            await db.rollback()
            raise
        else:
            await db.commit()

    app.dependency_overrides[get_db] = per_request_db
    app.state.testing = True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    app.state.testing = False


def _team_of(match: dict) -> str:
    return match["participants"][0]["team_id"]


def _naive(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _at(match: dict) -> datetime:
    value = datetime.fromisoformat(match["scheduled_at"].replace("Z", "+00:00"))
    return value.replace(tzinfo=None)


# ── Rescheduling ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reschedule_moves_a_match_and_bumps_its_version(client, auth_headers, db, event):
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    _, matches = await _seeding_schedule(client, auth_headers, db, event)
    match = matches[0]
    later = START + timedelta(hours=2)
    response = await client.patch(
        f"/api/v1/events/{event_id}/schedule/{match['id']}",
        headers=auth_headers,
        json={
            "scheduled_at": later.isoformat(),
            "table_number": 1,
            "notes": "moved after the lunch break",
            "expected_version": match["version"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert _at(body) == later
    assert body["version"] == match["version"] + 1
    assert body["notes"] == "moved after the lunch break"

    schedule = await client.get(f"/api/v1/events/{event_id}/schedule", headers=auth_headers)
    stored = next(m for m in schedule.json() if m["id"] == match["id"])
    assert _at(stored) == later and stored["version"] == body["version"]


@pytest.mark.asyncio
async def test_reschedule_rejects_a_stale_version(client, auth_headers, db, event):
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    _, matches = await _seeding_schedule(client, auth_headers, db, event)
    match = matches[0]
    url = f"/api/v1/events/{event_id}/schedule/{match['id']}"
    first = await client.patch(
        url, headers=auth_headers, json={"notes": "first", "expected_version": match["version"]}
    )
    assert first.status_code == 200
    # A second juror still holds the old version.
    stale = await client.patch(
        url, headers=auth_headers, json={"notes": "second", "expected_version": match["version"]}
    )
    assert stale.status_code == 409
    assert f"current version: {match['version'] + 1}" in stale.text


@pytest.mark.asyncio
async def test_reschedule_rejects_a_table_that_is_taken(client, auth_headers, db, event):
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    _, matches = await _seeding_schedule(client, auth_headers, db, event)
    round_one = [m for m in matches if m["round_number"] == 1]
    round_two = [m for m in matches if m["round_number"] == 2]
    occupied = round_one[0]
    # A round-2 run of the OTHER team into the slot and table of `occupied`.
    mover = next(m for m in round_two if _team_of(m) != _team_of(occupied))
    response = await client.patch(
        f"/api/v1/events/{event_id}/schedule/{mover['id']}",
        headers=auth_headers,
        json={
            "scheduled_at": occupied["scheduled_at"],
            "table_number": occupied["table_number"],
            "expected_version": mover["version"],
        },
    )
    assert response.status_code == 409
    assert "table and time slot" in response.text


@pytest.mark.asyncio
async def test_reschedule_rejects_a_team_playing_twice_at_once(client, auth_headers, db, event):
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    _, matches = await _seeding_schedule(client, auth_headers, db, event)
    first_run = next(m for m in matches if m["round_number"] == 1)
    second_run = next(
        m for m in matches if m["round_number"] == 2 and _team_of(m) == _team_of(first_run)
    )
    other_table = 2 if first_run["table_number"] == 1 else 1
    # Free table, but the same team is already on the other table then; the
    # overlap also counts when the new slot only starts inside the other one.
    response = await client.patch(
        f"/api/v1/events/{event_id}/schedule/{second_run['id']}",
        headers=auth_headers,
        json={
            "scheduled_at": (_at(first_run) + timedelta(minutes=5)).isoformat(),
            "table_number": other_table,
            "expected_version": second_run["version"],
        },
    )
    assert response.status_code == 409
    assert "team is already scheduled" in response.text


@pytest.mark.asyncio
async def test_reschedule_allows_the_slot_right_after_another(client, auth_headers, db, event):
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    _, matches = await _seeding_schedule(client, auth_headers, db, event)
    last_slot = max(_at(m) for m in matches)
    busy = next(m for m in matches if _at(m) == last_slot)
    mover = next(m for m in matches if m["round_number"] == 1 and _team_of(m) != _team_of(busy))
    # busy ends at last_slot + 10 min; starting exactly then is no overlap.
    response = await client.patch(
        f"/api/v1/events/{event_id}/schedule/{mover['id']}",
        headers=auth_headers,
        json={
            "scheduled_at": (last_slot + timedelta(minutes=10)).isoformat(),
            "table_number": busy["table_number"],
            "expected_version": mover["version"],
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_reschedule_ignores_cancelled_matches(client, auth_headers, db, event):
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    _, matches = await _seeding_schedule(client, auth_headers, db, event)
    first = next(m for m in matches if m["round_number"] == 1)
    second = next(m for m in matches if m["round_number"] == 2 and _team_of(m) == _team_of(first))
    url = f"/api/v1/events/{event_id}/schedule/"
    # Same team, same table, same slot: blocked while the first run stands ...
    blocked = await client.patch(
        url + second["id"],
        headers=auth_headers,
        json={
            "scheduled_at": first["scheduled_at"],
            "table_number": first["table_number"],
            "expected_version": second["version"],
        },
    )
    assert blocked.status_code == 409
    # ... and free once it is cancelled (neither table nor team conflict).
    cancelled = await client.patch(
        url + first["id"],
        headers=auth_headers,
        json={"status": "cancelled", "expected_version": first["version"]},
    )
    assert cancelled.status_code == 200, cancelled.text
    moved = await client.patch(
        url + second["id"],
        headers=auth_headers,
        json={
            "scheduled_at": first["scheduled_at"],
            "table_number": first["table_number"],
            "expected_version": second["version"],
        },
    )
    assert moved.status_code == 200, moved.text


@pytest.mark.asyncio
async def test_reschedule_checks_the_table_count_and_the_match(client, auth_headers, db, event):
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    _, matches = await _seeding_schedule(client, auth_headers, db, event)
    match = matches[0]
    beyond = await client.patch(
        f"/api/v1/events/{event_id}/schedule/{match['id']}",
        headers=auth_headers,
        json={"table_number": 3, "expected_version": match["version"]},
    )
    assert beyond.status_code == 422
    assert "table count" in beyond.text
    missing = await client.patch(
        f"/api/v1/events/{event_id}/schedule/does-not-exist",
        headers=auth_headers,
        json={"notes": "x", "expected_version": 1},
    )
    assert missing.status_code == 404
    no_version = await client.patch(
        f"/api/v1/events/{event_id}/schedule/{match['id']}",
        headers=auth_headers,
        json={"notes": "x"},
    )
    assert no_version.status_code == 422


@pytest.mark.asyncio
async def test_reschedule_needs_events_write(client, db, event):
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    from core.auth import create_access_token
    from modules.auth.models import User

    viewer = User(email="viewer@test.com", display_name="Viewer", hashed_password="x")
    db.add(viewer)
    await db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(viewer.id)}"}
    response = await client.patch(
        f"/api/v1/events/{event_id}/schedule/any",
        headers=headers,
        json={"notes": "x", "expected_version": 1},
    )
    assert response.status_code == 403


# ── Check-in and registration changes ────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_in_and_undo(client, auth_headers, db, event, team):
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    registration = await client.post(
        f"/api/v1/events/{event_id}/registrations",
        headers=auth_headers,
        json={"team_id": team.id},
    )
    assert registration.status_code == 201
    assert registration.json()["checked_in_at"] is None
    url = f"/api/v1/events/{event_id}/registrations/{registration.json()['id']}"

    checked_in = await client.patch(url, headers=auth_headers, json={"checked_in": True})
    assert checked_in.status_code == 200, checked_in.text
    stamp = datetime.fromisoformat(checked_in.json()["checked_in_at"].replace("Z", "+00:00"))
    assert abs((datetime.now(UTC) - stamp).total_seconds()) < 60

    # Other fields leave the check-in alone.
    noted = await client.patch(url, headers=auth_headers, json={"notes": "late bus"})
    assert _naive(noted.json()["checked_in_at"]) == _naive(checked_in.json()["checked_in_at"])
    assert noted.json()["notes"] == "late bus"

    undone = await client.patch(url, headers=auth_headers, json={"checked_in": False})
    assert undone.status_code == 200
    assert undone.json()["checked_in_at"] is None

    listed = await client.get(f"/api/v1/events/{event_id}/registrations", headers=auth_headers)
    assert [r["checked_in_at"] for r in listed.json()] == [None]


@pytest.mark.asyncio
async def test_registration_changes_are_validated(client, auth_headers, db, event, team):
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    registration = await client.post(
        f"/api/v1/events/{event_id}/registrations",
        headers=auth_headers,
        json={"team_id": team.id},
    )
    url = f"/api/v1/events/{event_id}/registrations/{registration.json()['id']}"
    level = await client.patch(
        url, headers=auth_headers, json={"competition_level_id": "no-such-level"}
    )
    assert level.status_code == 404
    seed = await client.patch(url, headers=auth_headers, json={"seed_number": 0})
    assert seed.status_code == 422
    other_event = await client.patch(
        f"/api/v1/events/other-event/registrations/{registration.json()['id']}",
        headers=auth_headers,
        json={"checked_in": True},
    )
    assert other_event.status_code == 404

    removed = await client.delete(url, headers=auth_headers)
    assert removed.status_code == 204
    again = await client.patch(url, headers=auth_headers, json={"checked_in": True})
    assert again.status_code == 404


# ── Phases ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_phase_create_update_and_delete(client, auth_headers, db, event):
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    base = f"/api/v1/events/{event_id}/phases"
    created = await client.post(
        base,
        headers=auth_headers,
        json={"name": "Seeding", "phase_type": "seeding", "sort_order": 0, "rounds": 3},
    )
    assert created.status_code == 201, created.text
    phase_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    duplicate = await client.post(
        base,
        headers=auth_headers,
        json={"name": "Seeding 2", "phase_type": "seeding", "sort_order": 0},
    )
    assert duplicate.status_code == 409

    starts = START
    updated = await client.patch(
        f"{base}/{phase_id}",
        headers=auth_headers,
        json={
            "name": "Seeding rounds",
            "rounds": 4,
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=3)).isoformat(),
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Seeding rounds"
    assert updated.json()["rounds"] == 4

    backwards = await client.patch(
        f"{base}/{phase_id}",
        headers=auth_headers,
        json={"ends_at": (starts - timedelta(minutes=1)).isoformat()},
    )
    assert backwards.status_code == 422
    assert "ends_at" in backwards.text

    listed = await client.get(base, headers=auth_headers)
    assert [p["name"] for p in listed.json()] == ["Seeding rounds"]

    deleted = await client.delete(f"{base}/{phase_id}", headers=auth_headers)
    assert deleted.status_code == 204
    assert (await client.get(base, headers=auth_headers)).json() == []
    assert (await client.delete(f"{base}/{phase_id}", headers=auth_headers)).status_code == 404


@pytest.mark.asyncio
async def test_live_or_completed_phases_cannot_be_deleted(client, auth_headers, event):
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    base = f"/api/v1/events/{event_id}/phases"
    for order, status in enumerate(("live", "completed")):
        phase = await client.post(
            base,
            headers=auth_headers,
            json={
                "name": f"Phase {status}",
                "phase_type": "seeding",
                "sort_order": order,
                "status": status,
            },
        )
        assert phase.status_code == 201
        response = await client.delete(f"{base}/{phase.json()['id']}", headers=auth_headers)
        assert response.status_code == 409
    assert len((await client.get(base, headers=auth_headers)).json()) == 2


@pytest.mark.asyncio
async def test_phases_of_disabled_modules_are_refused(client, auth_headers, db, event):
    # Read once: a rolled-back request expires the loaded objects.
    event_id = event.id
    event.active_modules = ["seeding"]
    await db.commit()
    base = f"/api/v1/events/{event_id}/phases"
    refused = await client.post(
        base,
        headers=auth_headers,
        json={"name": "DE", "phase_type": "double_elimination", "sort_order": 1},
    )
    assert refused.status_code == 409
    seeding = await client.post(
        base,
        headers=auth_headers,
        json={"name": "Seeding", "phase_type": "seeding", "sort_order": 0},
    )
    switched = await client.patch(
        f"{base}/{seeding.json()['id']}",
        headers=auth_headers,
        json={"phase_type": "double_elimination"},
    )
    assert switched.status_code == 409
