"""Integration coverage for event setup, scheduling, and event scoring."""

from datetime import UTC, datetime

import pytest


@pytest.mark.asyncio
async def test_event_crud_and_public_flags(client, auth_headers, season):
    response = await client.post(
        "/api/v1/events",
        headers=auth_headers,
        json={
            "season_id": season.id,
            "name": "Vienna Regional",
            "slug": "vienna-regional",
            "timezone": "Europe/Vienna",
            "status": "published",
            "public_scoreboard": True,
            "public_schedule": True,
        },
    )
    assert response.status_code == 201
    event_id = response.json()["id"]

    response = await client.patch(
        f"/api/v1/events/{event_id}",
        headers=auth_headers,
        json={"venue": "TU Wien", "table_count": 3},
    )
    assert response.status_code == 200
    assert response.json()["venue"] == "TU Wien"

    response = await client.get("/api/v1/public/events/vienna-regional")
    assert response.status_code == 200
    assert response.json()["name"] == "Vienna Regional"


@pytest.mark.asyncio
async def test_registration_phase_and_schedule_generation(
    client, auth_headers, event, team
):
    registration = await client.post(
        f"/api/v1/events/{event.id}/registrations",
        headers=auth_headers,
        json={"team_id": team.id, "seed_number": 1},
    )
    assert registration.status_code == 201

    phase = await client.post(
        f"/api/v1/events/{event.id}/phases",
        headers=auth_headers,
        json={
            "name": "Double Seeding",
            "phase_type": "double_seeding",
            "sort_order": 0,
            "rounds": 2,
        },
    )
    assert phase.status_code == 201

    schedule = await client.post(
        f"/api/v1/events/{event.id}/schedule/generate",
        headers=auth_headers,
        json={
            "phase_id": phase.json()["id"],
            "starts_at": datetime(2026, 7, 18, 8, 0, tzinfo=UTC).isoformat(),
            "slot_minutes": 8,
        },
    )
    assert schedule.status_code == 201
    assert len(schedule.json()) == 2
    assert schedule.json()[0]["participants"][0]["team_id"] == team.id

    public_schedule = await client.get(f"/api/v1/public/events/{event.slug}/schedule")
    assert public_schedule.status_code == 200
    assert len(public_schedule.json()) == 2


@pytest.mark.asyncio
async def test_score_is_idempotent_versioned_and_audited(
    client, auth_headers, event, team
):
    payload = {
        "team_id": team.id,
        "raw_scores": {"objects": 4},
        "idempotency_key": "score-entry-0001",
    }
    first = await client.post(
        f"/api/v1/events/{event.id}/matches", headers=auth_headers, json=payload
    )
    duplicate = await client.post(
        f"/api/v1/events/{event.id}/matches", headers=auth_headers, json=payload
    )
    assert first.status_code == 201
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == first.json()["id"]

    match_id = first.json()["id"]
    changed = await client.patch(
        f"/api/scoring/matches/{match_id}",
        headers=auth_headers,
        json={
            "raw_scores": {"objects": 5},
            "expected_version": 1,
            "correction_reason": "Sheet recount",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["version"] == 2

    stale = await client.patch(
        f"/api/scoring/matches/{match_id}",
        headers=auth_headers,
        json={"notes": "stale", "expected_version": 1},
    )
    assert stale.status_code == 409

    revisions = await client.get(
        f"/api/scoring/matches/{match_id}/revisions", headers=auth_headers
    )
    assert revisions.status_code == 200
    assert [item["revision"] for item in revisions.json()] == [1, 2]
    assert revisions.json()[1]["reason"] == "Sheet recount"
