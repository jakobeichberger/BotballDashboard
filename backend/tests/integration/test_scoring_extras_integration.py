"""The scoring extras on top of the event-centred scoring: seeding ranks per
category, bracket advancement from score entry, one DE placement, formula
inputs, archive guards and qualification alongside the season registration."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from modules.events.models import EventPhase, EventRegistration, MatchParticipant, ScheduledMatch
from modules.scoring import formula_service
from modules.scoring.competition_models import DEResult
from modules.seasons.models import Season
from modules.teams.models import Team

CUPS = {"key": "full_cups", "label": "Largest number of full Cups"}
CUPS_2 = {"full_cups": 2}


def _key() -> str:
    return uuid.uuid4().hex


async def _score(client, headers, event_id, team_id, raw, **extra):
    resp = await client.post(
        f"/api/v1/events/{event_id}/matches",
        headers=headers,
        json={"team_id": team_id, "raw_scores": raw, "idempotency_key": _key(), **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _rules(client, headers, season_id, tiebreakers=None):
    resp = await client.put(
        f"/api/scoring/seasons/{season_id}/rules",
        headers=headers,
        json={"tiebreakers": [CUPS] if tiebreakers is None else tiebreakers},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _teams(db, event, *specs: tuple[str, str]) -> list[Team]:
    teams = [Team(name=name) for name, _ in specs]
    db.add_all(teams)
    await db.flush()
    for team, (_, category) in zip(teams, specs, strict=True):
        db.add(EventRegistration(event_id=event.id, team_id=team.id, category=category))
    await db.commit()
    return teams


async def _ranking(client, headers, event_id) -> dict[str, dict]:
    resp = await client.get(f"/api/v1/events/{event_id}/ranking", headers=headers)
    assert resp.status_code == 200, resp.text
    return {row["team_id"]: row for row in resp.json()}


# ── Seeding ranking ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_seeding_ties_are_broken_per_category_and_shared_when_undecided(
    client, auth_headers, db, season, event
):
    a, b, c, o1, o2 = await _teams(
        db,
        event,
        ("A", "botball"),
        ("B", "botball"),
        ("C", "botball"),
        ("Open 1", "open"),
        ("Open 2", "open"),
    )
    for team in (a, b, c, o1, o2):
        await _score(client, auth_headers, event.id, team.id, {"points": 50})

    # No tie-breakers configured: equal seed scores share the rank, per category.
    ranking = await _ranking(client, auth_headers, event.id)
    assert {ranking[t.id]["rank"] for t in (a, b, c)} == {1}
    assert ranking[o1.id]["rank"] == ranking[o2.id]["rank"] == 1

    # With a criterion, the teams it separates are placed; the rest still share.
    await _rules(client, auth_headers, season.id)  # re-ranks the season's events
    ranking = await _ranking(client, auth_headers, event.id)
    assert {ranking[t.id]["rank"] for t in (a, b, c)} == {1}

    # C's second run keeps its seed score (50, 50) and records two full cups.
    await _score(client, auth_headers, event.id, c.id, {"points": 50}, tiebreak_values=CUPS_2)
    ranking = await _ranking(client, auth_headers, event.id)
    assert ranking[c.id]["rank"] == 1
    assert ranking[c.id]["tiebreaker"] == CUPS["label"]
    assert ranking[a.id]["rank"] == ranking[b.id]["rank"] == 2
    # The open category is ranked on its own and untouched by it.
    assert ranking[o1.id]["rank"] == ranking[o2.id]["rank"] == 1


@pytest.mark.asyncio
async def test_tiebreak_values_of_dq_and_uncounted_runs_do_not_count(
    client, auth_headers, db, season, event
):
    a, b = await _teams(db, event, ("A", "botball"), ("B", "botball"))
    await _rules(client, auth_headers, season.id)
    await _score(client, auth_headers, event.id, a.id, {"points": 50})
    await _score(client, auth_headers, event.id, b.id, {"points": 50})
    await _score(client, auth_headers, event.id, b.id, {"points": 0})
    # A disqualified run is a round with 0 points and its sheet is void.
    dq = await _score(client, auth_headers, event.id, a.id, {"points": 90}, tiebreak_values=CUPS_2)
    resp = await client.patch(
        f"/api/scoring/matches/{dq['id']}", headers=auth_headers, json={"is_disqualified": True}
    )
    assert resp.status_code == 200
    ranking = await _ranking(client, auth_headers, event.id)
    assert ranking[a.id]["seed_score"] == ranking[b.id]["seed_score"] == 25
    assert ranking[a.id]["rank"] == ranking[b.id]["rank"] == 1


# ── Head to head → bracket ────────────────────────────────────────────────────


@pytest.fixture
async def de_pair(db, event):
    """DE-1 (A v B) feeds its winner into DE-2 (slot 1) and its loser into L-1."""
    a, b, c = await _teams(db, event, ("A", "botball"), ("B", "botball"), ("C", "botball"))
    phase = EventPhase(event_id=event.id, name="DE", phase_type="double_elimination", sort_order=1)
    db.add(phase)
    await db.flush()
    second = ScheduledMatch(
        event_id=event.id, phase_id=phase.id, code="DE-2", round_number=2, sequence_number=2
    )
    loser = ScheduledMatch(
        event_id=event.id,
        phase_id=phase.id,
        code="L-1",
        round_number=1,
        sequence_number=3,
        bracket="loser",
    )
    db.add_all([second, loser])
    await db.flush()
    first = ScheduledMatch(
        event_id=event.id,
        phase_id=phase.id,
        code="DE-1",
        round_number=1,
        sequence_number=1,
        bracket="winner",
        next_winner_match_id=second.id,
        next_winner_slot=1,
        next_loser_match_id=loser.id,
        next_loser_slot=1,
    )
    db.add(first)
    await db.flush()
    db.add_all(
        [
            MatchParticipant(scheduled_match_id=first.id, team_id=a.id, position=1),
            MatchParticipant(scheduled_match_id=first.id, team_id=b.id, position=2),
            MatchParticipant(scheduled_match_id=second.id, team_id=c.id, position=2),
        ]
    )
    await db.commit()
    return a, b, first, second, loser


async def _participants(client, headers, event_id, code) -> dict[str, dict]:
    resp = await client.get(f"/api/v1/events/{event_id}/schedule", headers=headers)
    match = next(m for m in resp.json() if m["code"] == code)
    return {p["team_id"]: p | {"status": match["status"]} for p in match["participants"]}


@pytest.mark.asyncio
async def test_score_entry_records_the_bracket_result_with_tiebreakers(
    client, auth_headers, season, event, de_pair
):
    a, b, first, _, _ = de_pair
    await _rules(client, auth_headers, season.id)
    own = await _score(
        client,
        auth_headers,
        event.id,
        a.id,
        {"points": 100},
        scheduled_match_id=first.id,
        tiebreak_values={"full_cups": 0},
    )
    await _score(
        client,
        auth_headers,
        event.id,
        b.id,
        {"points": 100},
        scheduled_match_id=first.id,
        tiebreak_values={"full_cups": 1},
    )
    # Equal score, B wins on the tie-breaker: the bracket advances through
    # record_match_result — B into DE-2, A into the loser bracket.
    played = await _participants(client, auth_headers, event.id, "DE-1")
    assert played[b.id]["result"] == "win" and played[a.id]["result"] == "loss"
    assert played[a.id]["status"] == "completed"
    assert b.id in await _participants(client, auth_headers, event.id, "DE-2")
    assert a.id in await _participants(client, auth_headers, event.id, "L-1")

    # A correction that flips the outcome moves the teams (next match unplayed).
    resp = await client.patch(
        f"/api/scoring/matches/{own['id']}",
        headers=auth_headers,
        json={"raw_scores": {"points": 120}},
    )
    assert resp.status_code == 200, resp.text
    assert a.id in await _participants(client, auth_headers, event.id, "DE-2")
    assert b.id not in await _participants(client, auth_headers, event.id, "DE-2")
    assert b.id in await _participants(client, auth_headers, event.id, "L-1")


@pytest.mark.asyncio
async def test_undecided_elimination_tie_stays_open_for_a_replay(
    client, auth_headers, event, de_pair
):
    a, b, first, _, _ = de_pair
    await _score(client, auth_headers, event.id, a.id, {"points": 70}, scheduled_match_id=first.id)
    await _score(client, auth_headers, event.id, b.id, {"points": 70}, scheduled_match_id=first.id)
    played = await _participants(client, auth_headers, event.id, "DE-1")
    assert played[a.id]["status"] == "scheduled"
    assert played[a.id]["result"] == played[b.id]["result"] == "replay"
    assert played[a.id]["score"] == 70


# ── One DE placement ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bracket_view_and_de_placement_share_the_tiebreak_order(
    client, auth_headers, db, season, event
):
    teams = await _teams(db, event, *[(f"T{i}", "botball") for i in range(1, 7)])
    for seed, team in enumerate(teams, start=1):
        registration = (
            await db.execute(select(EventRegistration).where(EventRegistration.team_id == team.id))
        ).scalar_one()
        registration.seed_number = seed
    await db.commit()
    seed_of = {team.id: seed for seed, team in enumerate(teams, start=1)}
    phase = await client.post(
        f"/api/v1/events/{event.id}/phases",
        headers=auth_headers,
        json={"name": "DE", "phase_type": "double_elimination", "sort_order": 1},
    )
    phase_id = phase.json()["id"]
    resp = await client.post(
        f"/api/v1/events/{event.id}/schedule/generate",
        headers=auth_headers,
        json={"phase_id": phase_id, "starts_at": "2026-07-18T08:00:00+00:00", "slot_minutes": 10},
    )
    assert resp.status_code == 201, resp.text
    while True:
        schedule = await client.get(
            f"/api/v1/events/{event.id}/schedule",
            headers=auth_headers,
            params={"phase_id": phase_id},
        )
        ready = [
            m for m in schedule.json() if m["status"] == "scheduled" and len(m["participants"]) == 2
        ]
        if not ready:
            break
        match = min(ready, key=lambda m: m["sequence_number"])
        winner = min((p["team_id"] for p in match["participants"]), key=seed_of.__getitem__)
        resp = await client.post(
            f"/api/v1/events/{event.id}/schedule/{match['id']}/result",
            headers=auth_headers,
            json={"winner_team_id": winner},
        )
        assert resp.status_code == 200, resp.text

    [view] = (await client.get(f"/api/v1/events/{event.id}/bracket", headers=auth_headers)).json()
    by_rank: dict[int, list[str]] = {}
    for row in view["placements"]:
        by_rank.setdefault(row["rank"], []).append(row["team_id"])
    shared_rank, pair = next((r, ids) for r, ids in by_rank.items() if len(ids) == 2)
    # Nothing configured and no seeding: the pair keeps sharing its placement.
    assert {r["placement"] for r in view["placements"] if r["team_id"] in pair} == {shared_rank}

    await _rules(client, auth_headers, season.id)
    later = max(pair)
    played = next(
        m
        for m in schedule.json()
        if any(p["team_id"] == later for p in m["participants"]) and m["status"] == "completed"
    )
    await _score(
        client,
        auth_headers,
        event.id,
        later,
        {"points": 5},
        scheduled_match_id=played["id"],
        tiebreak_values={"full_cups": 4},
    )
    [view] = (await client.get(f"/api/v1/events/{event.id}/bracket", headers=auth_headers)).json()
    rows = {r["team_id"]: r for r in view["placements"]}
    assert rows[later]["placement"] == shared_rank
    assert rows[later]["rank"] == shared_rank  # the bracket rank itself stays shared
    other = min(pair)
    assert rows[other]["placement"] == shared_rank + 1
    assert rows[later]["decided_by"] == CUPS["label"]

    # The scoring DE placement reads the same ranks (written to de_results by
    # the bracket) and orders them with the same implementation.
    stored = (await db.execute(select(DEResult).where(DEResult.event_id == event.id))).scalars()
    assert {row.team_id for row in stored} == set(seed_of)
    resp = await client.get(f"/api/scoring/events/{event.id}/de-placement", headers=auth_headers)
    placement = {r["team_id"]: r for r in resp.json()}
    for team_id, row in rows.items():
        assert placement[team_id]["placement"] == row["placement"]
        assert placement[team_id]["de_rank"] == row["rank"]


# ── Formula inputs ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_formula_inputs_see_lost_rounds_and_contact_bonus(
    client, auth_headers, db, season, event
):
    a, b = await _teams(db, event, ("A", "botball"), ("B", "botball"))
    phase = EventPhase(event_id=event.id, name="DS", phase_type="double_seeding", sort_order=1)
    db.add(phase)
    await db.flush()
    duel = ScheduledMatch(
        event_id=event.id, phase_id=phase.id, code="DS-1", round_number=1, sequence_number=1
    )
    db.add(duel)
    await db.flush()
    db.add_all(
        [
            MatchParticipant(scheduled_match_id=duel.id, team_id=a.id, position=1),
            MatchParticipant(scheduled_match_id=duel.id, team_id=b.id, position=2),
        ]
    )
    await db.commit()

    await _score(client, auth_headers, event.id, a.id, {"points": 100})
    await _score(client, auth_headers, event.id, a.id, {"points": 400}, round_lost=True)
    await _score(client, auth_headers, event.id, a.id, {"points": 100}, scheduled_match_id=duel.id)
    await _score(
        client,
        auth_headers,
        event.id,
        b.id,
        {"points": 200},
        scheduled_match_id=duel.id,
        end_contact=True,
    )

    rows = {r["team_id"]: r for r in await formula_service.build_inputs(db, event.id, "botball")}
    # The lost round counts as a played seeding round with 0 points …
    assert sorted(rows[a.id]["seed_runs"]) == [0.0, 100.0]
    # … and the contact bonus (25 % of B's 200) is part of A's double-seeding run.
    assert rows[a.id]["double_seed_runs"] == [150.0]
    assert rows[b.id]["double_seed_runs"] == [200.0]
    ranking = await _ranking(client, auth_headers, event.id)
    assert ranking[a.id]["seed_score"] == 50 and ranking[a.id]["rounds_played"] == 2


# ── Archive guards ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_archived_season_blocks_the_extras_write_paths(
    client, auth_headers, db, season, event, team
):
    source = await client.post(
        f"/api/v1/events/{event.id}/scoring-schema/versions",
        headers=auth_headers,
        json={"fields": [{"key": "points", "label": "Points"}]},
    )
    assert source.status_code == 201, source.text
    external = await client.post(
        "/api/scoring/external-teams",
        headers=auth_headers,
        json={"season_id": season.id, "name": "Robo Masters"},
    )
    assert external.status_code == 201
    other = Team(name="Other Team")
    db.add(other)
    await db.commit()
    level = await client.post(
        "/api/seasons/competition-levels", headers=auth_headers, json={"name": "L", "code": "L1"}
    )

    row = await db.get(Season, season.id)
    row.status = "archived"
    await db.commit()

    attempts = [
        client.put(
            f"/api/scoring/seasons/{season.id}/rules",
            headers=auth_headers,
            json={"tiebreakers": []},
        ),
        client.post(
            f"/api/scoring/events/{event.id}/scoring-schema/clone",
            headers=auth_headers,
            json={"source_schema_id": source.json()["id"]},
        ),
        client.post(
            "/api/scoring/external-teams",
            headers=auth_headers,
            json={"season_id": season.id, "name": "Late"},
        ),
        client.patch(
            f"/api/scoring/external-teams/{external.json()['id']}",
            headers=auth_headers,
            json={"name": "Renamed"},
        ),
        client.post(
            f"/api/scoring/events/{event.id}/scouting/notes",
            headers=auth_headers,
            json={"external_team_id": external.json()["id"], "body": "fast"},
        ),
        client.post(
            f"/api/scoring/events/{event.id}/parts-challenges",
            headers=auth_headers,
            json={
                "challenger_team_id": team.id,
                "challenged_team_id": other.id,
                "description": "Non-kit servo",
            },
        ),
        client.post(
            f"/api/scoring/levels/{level.json()['id']}/qualify",
            headers=auth_headers,
            json={"season_id": season.id, "team_ids": [team.id]},
        ),
    ]
    for attempt in attempts:
        resp = await attempt
        assert resp.status_code == 409, (resp.request.url, resp.text)


# ── Qualification and the season registration ───────────────────────────────


@pytest.mark.asyncio
async def test_season_registration_for_a_qualifying_level(client, auth_headers, db, season, team):
    ecer = await client.post(
        "/api/seasons/competition-levels",
        headers=auth_headers,
        json={"name": "ECER", "code": "ECER", "order": 1},
    )
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
    gcer_id = gcer.json()["id"]
    body = {"team_id": team.id, "season_id": season.id, "competition_level_id": gcer_id}
    resp = await client.post("/api/teams/registrations", headers=auth_headers, json=body)
    assert resp.status_code == 422 and "not qualified" in resp.text

    resp = await client.post(
        f"/api/scoring/levels/{gcer_id}/qualify",
        headers=auth_headers,
        json={"season_id": season.id, "team_ids": [team.id]},
    )
    assert resp.status_code in (200, 201), resp.text
    resp = await client.post("/api/teams/registrations", headers=auth_headers, json=body)
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_closed_registration_window_still_applies_before_qualification(
    client, auth_headers, db, season, team
):
    from tests.integration.test_scouting_qualification import MENTOR, _user

    row = await db.get(Season, season.id)
    row.registration_close = date.today() - timedelta(days=1)
    await db.commit()
    mentor = await _user(db, [*MENTOR, "teams:write"], team)
    resp = await client.post(
        "/api/teams/registrations",
        headers=mentor,
        json={"team_id": team.id, "season_id": season.id},
    )
    assert resp.status_code == 409 and "closed" in resp.text
