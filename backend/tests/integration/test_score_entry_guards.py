"""Score entry guards: matchless categories, duplicate seeding rounds, round numbers.

* Aerial and JBC teams play no matches: a score for one is rejected (422
  ``category_has_no_matches``) and a stray run never shows up in the seeding
  ranking (public scoreboard included).
* A second official run for the same seeding round is rejected (409
  ``duplicate_round``) instead of counting as an extra run; corrections go
  through PATCH. Practice runs and head-to-head replays are not affected.
* A run that names no round gets the scheduled match's round, or the team's
  next free round.
"""

import uuid

import pytest
from sqlalchemy import select

from modules.events.models import EventPhase, EventRegistration, MatchParticipant, ScheduledMatch
from modules.scoring.models import Match, Ranking
from modules.teams.models import Team


async def _team(db, event, name: str, category: str | None = "botball") -> Team:
    team = Team(name=name, country="AT")
    db.add(team)
    await db.flush()
    if category:
        db.add(EventRegistration(event_id=event.id, team_id=team.id, category=category))
    await db.commit()
    return team


async def _event_score(client, headers, event, team, **body):
    return await client.post(
        f"/api/v1/events/{event.id}/matches",
        headers=headers,
        json={"team_id": team.id, "raw_scores": {}, "idempotency_key": str(uuid.uuid4())} | body,
    )


async def _season_score(client, headers, event, team, **body):
    return await client.post(
        f"/api/scoring/seasons/{event.season_id}/matches",
        headers=headers,
        json={"team_id": team.id, "event_id": event.id, "raw_scores": {}} | body,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["aerial_junior", "aerial", "jbc"])
async def test_matchless_category_cannot_get_a_match_score(
    client, auth_headers, db, event, category
):
    team = await _team(db, event, "Drone Masters", category)
    for post in (_event_score, _season_score):
        response = await post(client, auth_headers, event, team, round_number=1)
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "category_has_no_matches"
    assert (await db.execute(select(Match).where(Match.team_id == team.id))).first() is None


@pytest.mark.asyncio
async def test_botball_open_and_unregistered_teams_still_score(client, auth_headers, db, event):
    for name, category in (("Lions", "botball"), ("Owls", "open"), ("Walk-in", None)):
        team = await _team(db, event, name, category)
        response = await _event_score(client, auth_headers, event, team, round_number=1)
        assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_seeding_ranking_leaves_out_matchless_categories(client, auth_headers, db, event):
    lions = await _team(db, event, "RoboLions", "botball")
    drones = await _team(db, event, "Drone Masters", "aerial_junior")
    assert (
        await _event_score(client, auth_headers, event, lions, raw_scores={})
    ).status_code == 201
    # A run stored before the entry guard existed.
    db.add(
        Ranking(
            season_id=event.season_id,
            event_id=event.id,
            team_id=drones.id,
            category="aerial_junior",
            rank=1,
            seed_score=30.0,
            best_score=30.0,
            average_score=30.0,
            rounds_played=1,
        )
    )
    await db.commit()

    public = await client.get(f"/api/v1/public/events/{event.slug}/ranking")
    assert public.status_code == 200, public.text
    assert [row["team_name"] for row in public.json()] == ["RoboLions"]
    internal = await client.get(f"/api/v1/events/{event.id}/ranking", headers=auth_headers)
    assert [row["team_id"] for row in internal.json()] == [lions.id]


@pytest.mark.asyncio
async def test_duplicate_seeding_round_is_rejected(client, auth_headers, db, event):
    team = await _team(db, event, "RoboLions")
    first = await _season_score(client, auth_headers, event, team, round_number=1)
    assert first.status_code == 201, first.text
    again = await _season_score(client, auth_headers, event, team, round_number=1)
    assert again.status_code == 409, again.text
    assert again.json()["code"] == "duplicate_round"
    again = await _event_score(client, auth_headers, event, team, round_number=1)
    assert again.status_code == 409
    # Only the first run counts.
    ranking = (await db.execute(select(Ranking).where(Ranking.team_id == team.id))).scalar_one()
    await db.refresh(ranking)
    assert ranking.rounds_played == 1
    # The next round is fine, and practice runs may repeat a number.
    assert (
        await _season_score(client, auth_headers, event, team, round_number=2)
    ).status_code == 201
    for _ in range(2):
        practice = await _season_score(
            client, auth_headers, event, team, round_number=1, is_practice=True
        )
        assert practice.status_code == 201, practice.text


@pytest.mark.asyncio
async def test_run_without_round_gets_the_next_free_round(client, auth_headers, db, event):
    team = await _team(db, event, "RoboLions")
    rounds = []
    for _ in range(3):
        response = await _event_score(client, auth_headers, event, team)
        assert response.status_code == 201, response.text
        rounds.append(response.json()["round_number"])
    assert rounds == [1, 2, 3]


@pytest.mark.asyncio
async def test_scheduled_seeding_match_sets_the_round_and_cannot_be_scored_twice(
    client, auth_headers, db, event
):
    team = await _team(db, event, "RoboLions")
    phase = EventPhase(event_id=event.id, name="Seeding", phase_type="seeding", sort_order=0)
    db.add(phase)
    await db.flush()
    scheduled = ScheduledMatch(
        event_id=event.id,
        phase_id=phase.id,
        code="S-3",
        sequence_number=3,
        round_number=3,
        table_number=2,
        status="scheduled",
    )
    db.add(scheduled)
    await db.flush()
    db.add(MatchParticipant(scheduled_match_id=scheduled.id, team_id=team.id, position=1))
    await db.commit()

    response = await _event_score(
        client, auth_headers, event, team, scheduled_match_id=scheduled.id
    )
    assert response.status_code == 201, response.text
    assert response.json()["round_number"] == 3
    assert response.json()["table_number"] == 2
    again = await _event_score(client, auth_headers, event, team, scheduled_match_id=scheduled.id)
    assert again.status_code == 409
    assert again.json()["code"] == "duplicate_round"
