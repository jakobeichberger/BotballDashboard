"""Bracket generation, seeding, result advancement and bracket views over the API."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from modules.events.models import EventPhase, EventRegistration, ScheduledMatch
from modules.scoring.competition_models import DEResult
from modules.scoring.models import Match, Ranking
from modules.teams.models import Team

START = datetime(2026, 7, 18, 8, 0, tzinfo=UTC).isoformat()


@pytest.fixture(autouse=True)
async def _double_elimination_enabled(db, season, event):
    """DE phases need the module on the season and the event
    (modules.events.module_access); these tests exercise the brackets."""
    season.use_double_elimination = True
    event.active_modules = [*event.active_modules, "double_elimination"]
    await db.commit()


async def _register(db, event, count: int, category: str = "botball") -> list[Team]:
    teams = [Team(name=f"Team {i:02d}", team_number=f"T{i:02d}") for i in range(1, count + 1)]
    db.add_all(teams)
    await db.flush()
    for seed, team in enumerate(teams, start=1):
        db.add(
            EventRegistration(
                event_id=event.id, team_id=team.id, category=category, seed_number=seed
            )
        )
    await db.commit()
    return teams


async def _phase(client, headers, event, phase_type: str, sort_order: int, **extra) -> dict:
    response = await client.post(
        f"/api/v1/events/{event.id}/phases",
        headers=headers,
        json={"name": phase_type.title(), "phase_type": phase_type, "sort_order": sort_order}
        | extra,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _generate(client, headers, event, phase_id: str, **extra) -> list[dict]:
    response = await client.post(
        f"/api/v1/events/{event.id}/schedule/generate",
        headers=headers,
        json={"phase_id": phase_id, "starts_at": START, "slot_minutes": 10} | extra,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _schedule(client, headers, event, phase_id: str) -> dict[str, dict]:
    response = await client.get(
        f"/api/v1/events/{event.id}/schedule", headers=headers, params={"phase_id": phase_id}
    )
    return {match["code"]: match for match in response.json()}


async def _play(client, headers, event, match: dict, winner_id: str):
    return await client.post(
        f"/api/v1/events/{event.id}/schedule/{match['id']}/result",
        headers=headers,
        json={"winner_team_id": winner_id},
    )


def _favourite(match: dict, seed_of: dict[str, int]) -> str:
    teams = [p["team_id"] for p in match["participants"]]
    return min(teams, key=lambda team_id: seed_of[team_id])


@pytest.mark.asyncio
async def test_seeds_from_seeding_ranking_per_category(client, auth_headers, event, db):
    teams = await _register(db, event, 4)
    open_team = Team(name="Open One", team_number="O1")
    db.add(open_team)
    await db.flush()
    db.add(EventRegistration(event_id=event.id, team_id=open_team.id, category="open"))
    seeding = EventPhase(event_id=event.id, name="Seeding", phase_type="seeding", sort_order=0)
    db.add(seeding)
    await db.flush()
    # Seeding scores: team 3 best, then 1, then 4; team 2 has not played.
    for team, score in ((teams[2], 300.0), (teams[0], 200.0), (teams[3], 100.0)):
        db.add(
            Ranking(
                season_id=event.season_id,
                event_id=event.id,
                event_phase_id=seeding.id,
                team_id=team.id,
                rank=0,
                seed_score=score,
                best_score=score,
                average_score=score,
                rounds_played=3,
            )
        )
    await db.commit()

    response = await client.post(
        f"/api/v1/events/{event.id}/registrations/seeds-from-seeding",
        headers=auth_headers,
        json={},
    )
    assert response.status_code == 200, response.text
    seeds = {item["team_id"]: (item["category"], item["seed_number"]) for item in response.json()}
    assert seeds[teams[2].id] == ("botball", 1)
    assert seeds[teams[0].id] == ("botball", 2)
    assert seeds[teams[3].id] == ("botball", 3)
    assert seeds[teams[1].id] == ("botball", 4)
    # Categories are seeded independently.
    assert seeds[open_team.id] == ("open", 1)


@pytest.mark.asyncio
async def test_double_elimination_runs_to_a_champion_and_writes_de_ranks(
    client, auth_headers, event, db
):
    teams = await _register(db, event, 5)
    seed_of = {team.id: seed for seed, team in enumerate(teams, start=1)}
    phase = await _phase(
        client, auth_headers, event, "double_elimination", 1, settings={"bracket_label": "C"}
    )
    schedule = await _generate(client, auth_headers, event, phase["id"])
    assert len(schedule) == 2 * 5 - 1
    by_code = {match["code"]: match for match in schedule}
    # Seeds 1-3 have byes: the only opening match is seed 4 v seed 5.
    opener = by_code["2-W1-2"]
    assert {p["team_id"] for p in opener["participants"]} == {teams[3].id, teams[4].id}
    assert by_code["2-L2-1"]["round_kind"] == "major"
    assert by_code["2-GF"]["bracket"] == "final"
    # Dependent matches never share a time slot with what they depend on.
    assert by_code["2-W2-1"]["scheduled_at"] > opener["scheduled_at"]

    # The loser-bracket team wins the grand final: a reset final is needed.
    played = 0
    while True:
        current = await _schedule(client, auth_headers, event, phase["id"])
        ready = [
            match
            for match in current.values()
            if match["status"] == "scheduled" and len(match["participants"]) == 2
        ]
        if not ready:
            break
        match = min(ready, key=lambda item: item["sequence_number"])
        winner = _favourite(match, seed_of)
        if match["code"] == "2-GF":
            winner = next(p["team_id"] for p in match["participants"] if p["position"] == 2)
        response = await _play(client, auth_headers, event, match, winner)
        assert response.status_code == 200, response.text
        played += 1
    assert played == 2 * 5 - 1

    await db.commit()
    rows = {
        row.team_id: row
        for row in (await db.execute(select(DEResult).where(DEResult.event_id == event.id)))
        .scalars()
        .all()
    }
    assert {row.bracket for row in rows.values()} == {"C"}
    ranks = {seed_of[team_id]: row.de_rank for team_id, row in rows.items()}
    assert ranks[1] == 1 and ranks[2] == 2 and ranks[3] == 3
    assert sorted(ranks.values()) == [1, 2, 3, 4, 5]
    assert rows[teams[0].id].bracket_score == 1.0
    phase_row = await db.get(EventPhase, phase["id"])
    await db.refresh(phase_row)
    assert phase_row.status == "completed"

    bracket = await client.get(f"/api/v1/events/{event.id}/bracket", headers=auth_headers)
    assert bracket.status_code == 200
    [view] = bracket.json()
    assert view["bracket_label"] == "C"
    assert view["placements"][0]["team_id"] == teams[0].id
    assert len(view["matches"]) == 9

    public = await client.get(f"/api/v1/public/events/{event.slug}/bracket")
    assert public.status_code == 200
    assert public.json()[0]["placements"] == view["placements"]


@pytest.mark.asyncio
async def test_grand_final_won_by_winner_bracket_side_cancels_the_reset(
    client, auth_headers, event, db
):
    teams = await _register(db, event, 2)
    phase = await _phase(client, auth_headers, event, "double_elimination", 1)
    schedule = await _generate(client, auth_headers, event, phase["id"])
    by_code = {match["code"]: match for match in schedule}
    assert set(by_code) == {"2-W1-1", "2-GF", "2-GF2"}
    response = await _play(client, auth_headers, event, by_code["2-W1-1"], teams[0].id)
    assert response.status_code == 200
    current = await _schedule(client, auth_headers, event, phase["id"])
    # The loser of the only winner-bracket match gets a second chance.
    assert {p["team_id"] for p in current["2-GF"]["participants"]} == {teams[0].id, teams[1].id}
    response = await _play(client, auth_headers, event, current["2-GF"], teams[0].id)
    assert response.status_code == 200
    current = await _schedule(client, auth_headers, event, phase["id"])
    assert current["2-GF2"]["status"] == "cancelled"
    await db.commit()
    ranks = {
        row.team_id: row.de_rank for row in (await db.execute(select(DEResult))).scalars().all()
    }
    assert ranks == {teams[0].id: 1, teams[1].id: 2}


@pytest.mark.asyncio
async def test_result_correction_moves_teams_until_the_next_match_is_played(
    client, auth_headers, event, db
):
    teams = await _register(db, event, 4)
    phase = await _phase(client, auth_headers, event, "double_elimination", 1)
    await _generate(client, auth_headers, event, phase["id"])
    current = await _schedule(client, auth_headers, event, phase["id"])
    opener = current["2-W1-1"]  # seed 1 v seed 4
    assert (await _play(client, auth_headers, event, opener, teams[0].id)).status_code == 200
    current = await _schedule(client, auth_headers, event, phase["id"])
    assert teams[0].id in {p["team_id"] for p in current["2-W2-1"]["participants"]}
    assert teams[3].id in {p["team_id"] for p in current["2-L1-1"]["participants"]}

    # Correct the winner: seed 4 moves on, seed 1 drops into the loser bracket.
    response = await _play(client, auth_headers, event, current["2-W1-1"], teams[3].id)
    assert response.status_code == 200, response.text
    current = await _schedule(client, auth_headers, event, phase["id"])
    assert {p["team_id"] for p in current["2-W2-1"]["participants"]} == {teams[3].id}
    assert {p["team_id"] for p in current["2-L1-1"]["participants"]} == {teams[0].id}

    # Once the following match is played the result is locked.
    other = current["2-W1-2"]
    assert (await _play(client, auth_headers, event, other, teams[1].id)).status_code == 200
    current = await _schedule(client, auth_headers, event, phase["id"])
    assert (
        await _play(client, auth_headers, event, current["2-W2-1"], teams[1].id)
    ).status_code == 200
    response = await _play(client, auth_headers, event, current["2-W1-1"], teams[0].id)
    assert response.status_code == 409

    # A result needs a winner from the match.
    response = await _play(client, auth_headers, event, current["2-L1-1"], teams[3].id)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_bracket_label_must_fit_de_results(client, auth_headers, event, db):
    await _register(db, event, 4)
    phase = await _phase(
        client, auth_headers, event, "double_elimination", 1, settings={"bracket_label": "AB"}
    )
    response = await client.post(
        f"/api/v1/events/{event.id}/schedule/generate",
        headers=auth_headers,
        json={"phase_id": phase["id"], "starts_at": START},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_double_seeding_pairs_two_teams_per_match(client, auth_headers, event, db):
    teams = await _register(db, event, 4)
    phase = await _phase(client, auth_headers, event, "double_seeding", 0, rounds=3)
    schedule = await _generate(client, auth_headers, event, phase["id"], table_count=2)
    assert len(schedule) == 6
    assert all(len(match["participants"]) == 2 for match in schedule)
    pairs = [frozenset(p["team_id"] for p in match["participants"]) for match in schedule]
    # Opponents rotate: no pairing repeats within three rounds of four teams.
    assert len(set(pairs)) == 6
    runs = {team.id: 0 for team in teams}
    for match in schedule:
        for participant in match["participants"]:
            runs[participant["team_id"]] += 1
    assert set(runs.values()) == {3}
    # Two tables: each round fits in one time slot, rounds follow each other.
    slots = sorted({match["scheduled_at"] for match in schedule})
    assert len(slots) == 3


@pytest.mark.asyncio
async def test_alliance_score_is_the_sum_of_both_partners(client, auth_headers, event, db):
    teams = await _register(db, event, 4)
    phase = await _phase(
        client,
        auth_headers,
        event,
        "alliance",
        2,
        rounds=2,
        settings={"alliance_mode": "seeded"},
    )
    schedule = await _generate(client, auth_headers, event, phase["id"])
    assert len(schedule) == 4
    groups = {frozenset(p["team_id"] for p in match["participants"]) for match in schedule}
    assert groups == {
        frozenset({teams[0].id, teams[3].id}),
        frozenset({teams[1].id, teams[2].id}),
    }
    first_round = [match for match in schedule if match["round_number"] == 1]
    for match, (a, b) in zip(first_round, ((40.0, 60.0), (70.0, 50.0)), strict=True):
        ids = [p["team_id"] for p in sorted(match["participants"], key=lambda p: p["position"])]
        response = await client.post(
            f"/api/v1/events/{event.id}/schedule/{match['id']}/result",
            headers=auth_headers,
            json={"scores": {ids[0]: a, ids[1]: b}},
        )
        assert response.status_code == 200, response.text
    # A score entered through official scoring counts as well (DQ counts 0).
    second = next(
        match
        for match in schedule
        if match["round_number"] == 2
        and teams[0].id in {p["team_id"] for p in match["participants"]}
    )
    for team, total, dq in ((teams[0], 150.0, False), (teams[3], 80.0, True)):
        db.add(
            Match(
                season_id=event.season_id,
                event_id=event.id,
                scheduled_match_id=second["id"],
                team_id=team.id,
                total_score=total,
                is_disqualified=dq,
            )
        )
    await db.commit()

    standings = await client.get(
        f"/api/v1/events/{event.id}/phases/{phase['id']}/alliances", headers=auth_headers
    )
    assert standings.status_code == 200
    first, second_place = standings.json()
    assert set(first["team_ids"]) == {teams[0].id, teams[3].id}
    assert first["best_score"] == 150.0 and first["total_score"] == 250.0
    assert second_place["best_score"] == 120.0


@pytest.mark.asyncio
async def test_alliance_draw_is_stored_and_reproducible(client, auth_headers, event, db):
    await _register(db, event, 5)
    phase = await _phase(client, auth_headers, event, "alliance", 2, rounds=1)
    schedule = await _generate(client, auth_headers, event, phase["id"])
    assert sorted(len(match["participants"]) for match in schedule) == [1, 2, 2]
    stored = await db.get(EventPhase, phase["id"])
    await db.refresh(stored)
    assert len(stored.settings["alliances"]) == 3
    draw_seed = stored.settings["draw_seed"]
    again = await _generate(client, auth_headers, event, phase["id"], replace_existing=True)
    groups = sorted(sorted(p["team_id"] for p in match["participants"]) for match in again)
    assert groups == sorted(sorted(group) for group in stored.settings["alliances"])
    await db.refresh(stored)
    assert stored.settings["draw_seed"] == draw_seed


@pytest.mark.asyncio
async def test_event_bracket_weights_fall_back_to_the_season(client, auth_headers, event, db):
    from modules.scoring.formula_service import set_bracket_weights as set_season_weights

    await set_season_weights(db, event.season_id, "botball", {"A": 1.0, "B": 0.5})
    await db.commit()
    url = f"/api/v1/events/{event.id}/bracket-weights"
    assert (await client.get(url, headers=auth_headers)).json() == {"A": 1.0, "B": 0.5}
    response = await client.put(
        url, headers=auth_headers, json={"weights": {"A": 1.0, "B": 0.6, "C": 0.3}}
    )
    assert response.status_code == 200
    assert (await client.get(url, headers=auth_headers)).json() == {"A": 1.0, "B": 0.6, "C": 0.3}
    bad = await client.put(url, headers=auth_headers, json={"weights": {"A": -1}})
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_public_bracket_requires_public_schedule(client, auth_headers, event, db):
    event.public_schedule = False
    await db.commit()
    response = await client.get(f"/api/v1/public/events/{event.slug}/bracket")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_scheduled_match_links_are_exposed(client, auth_headers, event, db):
    await _register(db, event, 3)
    phase = await _phase(client, auth_headers, event, "final", 1)
    schedule = await _generate(client, auth_headers, event, phase["id"])
    assert len(schedule) == 2
    semi = next(match for match in schedule if len(match["participants"]) == 2)
    assert semi["next_winner_match_id"] and semi["next_winner_slot"] == 2
    assert semi["next_loser_match_id"] is None
    rows = (await db.execute(select(ScheduledMatch))).scalars().all()
    assert len(rows) == 2
