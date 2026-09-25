"""Structured score sheets, templates/clone, special rules, tie-breakers,
referee checklist and parts challenges through the API."""

import uuid

import pytest

from modules.events.models import EventPhase, MatchParticipant, ScheduledMatch
from modules.scoring.competition_models import DEResult
from modules.scoring.sheet_templates import TEMPLATES
from modules.seasons.models import CompetitionLevel
from modules.teams.models import Team


def _key() -> str:
    return uuid.uuid4().hex


async def _structured_schema(client, headers, event_id, template="botball_2025", **extra):
    resp = await client.post(
        f"/api/v1/events/{event_id}/scoring-schema/versions",
        headers=headers,
        json={"definition": TEMPLATES[template]["definition"], **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _score(client, headers, event_id, team_id, raw, **extra):
    resp = await client.post(
        f"/api/v1/events/{event_id}/matches",
        headers=headers,
        json={"team_id": team_id, "raw_scores": raw, "idempotency_key": _key(), **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
async def rival(db):
    team = Team(name="Rival Robotics", team_number="RR-02", country="AT")
    db.add(team)
    await db.commit()
    return team


@pytest.fixture
async def duel(db, event, team, rival):
    """A DE head-to-head match between `team` and `rival`."""
    phase = EventPhase(
        event_id=event.id, name="Double Elimination", phase_type="double_elimination", sort_order=1
    )
    db.add(phase)
    await db.flush()
    scheduled = ScheduledMatch(
        event_id=event.id,
        phase_id=phase.id,
        code="DE-1",
        round_number=1,
        sequence_number=1,
        bracket="winner",
    )
    db.add(scheduled)
    await db.flush()
    db.add_all(
        [
            MatchParticipant(scheduled_match_id=scheduled.id, team_id=team.id, position=1),
            MatchParticipant(scheduled_match_id=scheduled.id, team_id=rival.id, position=2),
        ]
    )
    await db.commit()
    return scheduled


# ── Structured schemas ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_templates_endpoint_lists_2024_to_2026(client, auth_headers):
    resp = await client.get("/api/scoring/schema-templates", headers=auth_headers)
    assert resp.status_code == 200
    templates = {t["id"]: t for t in resp.json()}
    assert set(templates) == {"botball_2024", "botball_2025", "botball_2026"}
    assert templates["botball_2026"]["complete"] is True
    assert templates["botball_2025"]["definition"]["sides"] == ["A", "B"]


@pytest.mark.asyncio
async def test_structured_schema_scores_like_the_paper_sheet(client, auth_headers, event, team):
    schema = await _structured_schema(client, auth_headers, event.id)
    assert schema["definition"]["sections"][0]["key"] == "prep_station"
    assert any(f["key"] == "B.fry_potato" for f in schema["fields"])

    match = await _score(
        client,
        auth_headers,
        event.id,
        team.id,
        {
            "A.fry_potato": 1,
            "A.fry_no_fries": True,
            "B.serving_red_pom": 3,
            "B.serving_orange_pom": 3,
            "B.serving_yellow_pom": 3,
            "B.serving_full_pom_sets": 3,
            "B.serving_full_trays": 1,
        },
    )
    assert match["total_score"] == 100 + 135
    assert match["sheet_score"] == 235
    assert match["schema_snapshot"]["definition"]["sides"] == ["A", "B"]

    # Corrections are recomputed from the snapshot, with the same semantics.
    resp = await client.patch(
        f"/api/scoring/matches/{match['id']}",
        headers=auth_headers,
        json={"raw_scores": {"A.fry_potato": 2}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_score"] == 100  # no "no fries" ×2 any more

    bad = await client.post(
        f"/api/v1/events/{event.id}/matches",
        headers=auth_headers,
        json={"team_id": team.id, "raw_scores": {"fry_potato": 1}, "idempotency_key": _key()},
    )
    assert bad.status_code == 422
    assert "not part of the active scoring schema" in bad.text


@pytest.mark.asyncio
async def test_schema_version_rejects_invalid_definition(client, auth_headers, event):
    definition = {
        "sides": ["A"],
        "sections": [
            {
                "key": "zone",
                "label": "Zone",
                "fields": [{"key": "x", "label": "X"}],
                "multipliers": [{"key": "x", "label": "Dup", "type": "boolean", "factor": 2}],
            }
        ],
    }
    resp = await client.post(
        f"/api/v1/events/{event.id}/scoring-schema/versions",
        headers=auth_headers,
        json={"definition": definition},
    )
    assert resp.status_code == 422
    resp = await client.post(
        f"/api/v1/events/{event.id}/scoring-schema/versions", headers=auth_headers, json={}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_flat_schemas_keep_working(client, auth_headers, event, team):
    resp = await client.post(
        f"/api/v1/events/{event.id}/scoring-schema/versions",
        headers=auth_headers,
        json={"fields": [{"key": "pieces", "label": "Pieces", "multiplier": 4}]},
    )
    assert resp.status_code == 201
    assert resp.json()["definition"] is None
    match = await _score(client, auth_headers, event.id, team.id, {"pieces": 5})
    assert match["total_score"] == 20


@pytest.mark.asyncio
async def test_clone_schema_from_another_event_and_level(client, auth_headers, db, season, event):
    gcer = CompetitionLevel(name="GCER", code="GCER-T")
    db.add(gcer)
    await db.commit()
    source = await _structured_schema(client, auth_headers, event.id)
    target = await client.post(
        "/api/v1/events",
        headers=auth_headers,
        json={"season_id": season.id, "name": "GCER 2026", "slug": "gcer-2026"},
    )
    target_id = target.json()["id"]

    listing = await client.get(
        "/api/scoring/schemas", headers=auth_headers, params={"season_id": season.id}
    )
    assert listing.status_code == 200
    assert [s["id"] for s in listing.json()] == [source["id"]]
    assert listing.json()[0]["structured"] is True
    assert listing.json()[0]["event_name"] == event.name

    resp = await client.post(
        f"/api/scoring/events/{target_id}/scoring-schema/clone",
        headers=auth_headers,
        json={"source_schema_id": source["id"], "competition_level_id": gcer.id},
    )
    assert resp.status_code == 201, resp.text
    clone = resp.json()
    assert clone["id"] != source["id"]
    assert clone["event_id"] == target_id
    assert clone["competition_level_id"] == gcer.id
    assert clone["definition"] == source["definition"]

    active = await client.get(
        f"/api/v1/events/{target_id}/scoring-schema",
        headers=auth_headers,
        params={"competition_level_id": gcer.id},
    )
    assert active.json()["id"] == clone["id"]


# ── Special rules ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_contact_gives_the_opponent_25_percent(
    client, auth_headers, event, team, rival, duel
):
    own = await _score(
        client, auth_headers, event.id, team.id, {"points": 100}, scheduled_match_id=duel.id
    )
    other = await _score(
        client,
        auth_headers,
        event.id,
        rival.id,
        {"points": 200},
        scheduled_match_id=duel.id,
        end_contact=True,
    )
    # The rival touched our side at the end: we receive 25 % of its 200 points.
    refreshed = (await client.get(f"/api/scoring/matches/{own['id']}", headers=auth_headers)).json()
    assert refreshed["bonus_score"] == 50
    assert refreshed["total_score"] == 150
    assert other["total_score"] == 200

    outcome = await client.get(
        f"/api/scoring/scheduled-matches/{duel.id}/outcome", headers=auth_headers
    )
    assert outcome.json()["winner"] == rival.id
    assert outcome.json()["reason"] == "score"

    # Clearing the flag removes the bonus again.
    resp = await client.patch(
        f"/api/scoring/matches/{other['id']}", headers=auth_headers, json={"end_contact": False}
    )
    assert resp.status_code == 200
    refreshed = (await client.get(f"/api/scoring/matches/{own['id']}", headers=auth_headers)).json()
    assert refreshed["bonus_score"] == 0 and refreshed["total_score"] == 100

    schedule = await client.get(f"/api/v1/events/{event.id}/schedule", headers=auth_headers)
    participants = {p["team_id"]: p for p in schedule.json()[0]["participants"]}
    assert participants[rival.id]["result"] == "win"
    assert participants[team.id]["result"] == "loss"
    assert participants[team.id]["score"] == 100


@pytest.mark.asyncio
async def test_lose_the_round_scores_zero_but_is_not_a_dq(
    client, auth_headers, event, team, rival, duel
):
    own = await _score(
        client,
        auth_headers,
        event.id,
        team.id,
        {"points": 300},
        scheduled_match_id=duel.id,
        round_lost=True,
        round_lost_reason="motors_running",
    )
    assert own["total_score"] == 0 and own["sheet_score"] == 300
    assert own["is_disqualified"] is False
    await _score(
        client, auth_headers, event.id, rival.id, {"points": 10}, scheduled_match_id=duel.id
    )
    outcome = (
        await client.get(f"/api/scoring/scheduled-matches/{duel.id}/outcome", headers=auth_headers)
    ).json()
    assert outcome["winner"] == rival.id and outcome["reason"] == "round_lost"

    # In seeding the round simply counts 0 — it still is a played round.
    seeding = await _score(client, auth_headers, event.id, team.id, {"points": 80}, round_lost=True)
    assert seeding["total_score"] == 0
    ranking = await client.get(f"/api/v1/events/{event.id}/ranking", headers=auth_headers)
    row = next(r for r in ranking.json() if r["team_id"] == team.id)
    assert row["rounds_played"] == 1 and row["seed_score"] == 0

    bad = await client.post(
        f"/api/v1/events/{event.id}/matches",
        headers=auth_headers,
        json={
            "team_id": team.id,
            "raw_scores": {},
            "round_lost": True,
            "round_lost_reason": "fell asleep",
            "idempotency_key": _key(),
        },
    )
    assert bad.status_code == 422


# ── Tie-breakers ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rules_crud_and_presets(client, auth_headers, season):
    presets = await client.get("/api/scoring/tiebreaker-presets", headers=auth_headers)
    assert {p["id"] for p in presets.json()} == {"botball_2024", "botball_2025", "botball_2026"}
    preset = next(p for p in presets.json() if p["id"] == "botball_2026")

    empty = await client.get(f"/api/scoring/seasons/{season.id}/rules", headers=auth_headers)
    assert empty.json()["tiebreakers"] == [] and empty.json()["end_contact_bonus_percent"] == 25

    resp = await client.put(
        f"/api/scoring/seasons/{season.id}/rules",
        headers=auth_headers,
        json={
            "tiebreakers": preset["tiebreakers"],
            "finals_replay": True,
            "referee_checklist": [{"key": "setup_ok", "label": "Setup checked"}],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["finals_replay"] is True
    assert len(resp.json()["tiebreakers"]) == 12

    bad = await client.put(
        f"/api/scoring/seasons/{season.id}/rules",
        headers=auth_headers,
        json={"tiebreakers": [{"key": "x", "label": "X", "source": "sheet"}]},
    )
    assert bad.status_code == 422


async def _rules(client, headers, season_id, **extra):
    resp = await client.put(
        f"/api/scoring/seasons/{season_id}/rules",
        headers=headers,
        json={
            "tiebreakers": [
                {"key": "full_cups", "label": "Largest number of full Cups"},
                {
                    "key": "full_trays",
                    "label": "Largest number of full Trays",
                    "source": "sheet",
                    "sheet_keys": ["serving_full_trays"],
                },
            ],
            **extra,
        },
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_seeding_ties_are_ordered_by_tiebreakers(
    client, auth_headers, season, event, team, rival
):
    await _structured_schema(client, auth_headers, event.id)
    await _rules(client, auth_headers, season.id)
    # Both teams: one run of 50 points (potato); rival has more full trays.
    await _score(client, auth_headers, event.id, team.id, {"A.fry_potato": 1})
    await _score(
        client, auth_headers, event.id, rival.id, {"A.fry_potato": 1, "B.serving_full_trays": 1}
    )
    # By default seeding ties share the rank (game review, ECER 2026).
    ranking = (await client.get(f"/api/v1/events/{event.id}/ranking", headers=auth_headers)).json()
    assert [(r["rank"], r["tiebreaker"]) for r in ranking] == [(1, None), (1, None)]

    await _rules(client, auth_headers, season.id, seeding_tiebreakers=True)
    ranking = (await client.get(f"/api/v1/events/{event.id}/ranking", headers=auth_headers)).json()
    assert [(r["team_id"], r["rank"], r["tiebreaker"]) for r in ranking] == [
        (rival.id, 1, "Largest number of full Trays"),
        (team.id, 2, "Largest number of full Trays"),
    ]

    # A juror-entered criterion earlier in the list overrides it.
    await _score(
        client,
        auth_headers,
        event.id,
        team.id,
        {"A.fry_potato": 1},
        tiebreak_values={"full_cups": 2},
    )
    ranking = (await client.get(f"/api/v1/events/{event.id}/ranking", headers=auth_headers)).json()
    assert ranking[0]["team_id"] == team.id
    assert ranking[0]["tiebreaker"] == "Largest number of full Cups"


@pytest.mark.asyncio
async def test_head_to_head_tie_and_finals_replay(
    client, auth_headers, db, season, event, team, rival, duel
):
    await _rules(client, auth_headers, season.id, finals_replay=True)
    await _score(
        client,
        auth_headers,
        event.id,
        team.id,
        {"points": 100},
        scheduled_match_id=duel.id,
        tiebreak_values={"full_cups": 1},
    )
    await _score(
        client,
        auth_headers,
        event.id,
        rival.id,
        {"points": 100},
        scheduled_match_id=duel.id,
        tiebreak_values={"full_cups": 0},
    )
    outcome = (
        await client.get(f"/api/scoring/scheduled-matches/{duel.id}/outcome", headers=auth_headers)
    ).json()
    assert outcome["winner"] == team.id
    assert outcome["reason"] == "tiebreaker"
    assert outcome["decided_by"] == "Largest number of full Cups"

    duel.bracket = "final"
    await db.commit()
    outcome = (
        await client.get(f"/api/scoring/scheduled-matches/{duel.id}/outcome", headers=auth_headers)
    ).json()
    assert outcome["winner"] is None and outcome["replay"] is True
    assert outcome["reason"] == "finals_replay"


@pytest.mark.asyncio
async def test_de_placement_orders_equal_ranks(
    client, auth_headers, db, season, event, team, rival, duel
):
    await _rules(client, auth_headers, season.id)
    third = Team(name="Third Team", country="DE")
    db.add(third)
    await db.flush()
    db.add_all(
        [
            DEResult(
                season_id=season.id, event_id=event.id, team_id=team.id, bracket="A", de_rank=3
            ),
            DEResult(
                season_id=season.id, event_id=event.id, team_id=rival.id, bracket="A", de_rank=3
            ),
            DEResult(
                season_id=season.id, event_id=event.id, team_id=third.id, bracket="A", de_rank=1
            ),
        ]
    )
    await db.commit()
    await _score(
        client,
        auth_headers,
        event.id,
        rival.id,
        {"points": 10},
        scheduled_match_id=duel.id,
        tiebreak_values={"full_cups": 3},
    )
    resp = await client.get(f"/api/scoring/events/{event.id}/de-placement", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    placement = [(r["team_id"], r["placement"], r["decided_by"]) for r in resp.json()]
    assert placement == [
        (third.id, 1, None),
        (rival.id, 2, "Largest number of full Cups"),
        (team.id, 3, "Largest number of full Cups"),
    ]


# ── Referee checklist ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_requires_the_referee_checklist(client, auth_headers, season, event, team):
    await client.put(
        f"/api/scoring/seasons/{season.id}/rules",
        headers=auth_headers,
        json={
            "referee_checklist": [
                {"key": "setup_ok", "label": "Setup within 2 minutes"},
                {"key": "sheet_signed", "label": "Team signed the sheet"},
                {"key": "photo", "label": "Photo taken", "required": False},
            ]
        },
    )
    match = await _score(client, auth_headers, event.id, team.id, {"points": 5})
    resp = await client.put(f"/api/scoring/matches/{match['id']}/confirm", headers=auth_headers)
    assert resp.status_code == 422
    assert "Setup within 2 minutes" in resp.text

    resp = await client.put(
        f"/api/scoring/matches/{match['id']}/confirm",
        headers=auth_headers,
        json={"checklist": {"setup_ok": True}},
    )
    assert resp.status_code == 422 and "Team signed the sheet" in resp.text

    resp = await client.put(
        f"/api/scoring/matches/{match['id']}/confirm",
        headers=auth_headers,
        json={"checklist": {"setup_ok": True, "sheet_signed": True}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["confirmed_by"] is not None
    assert resp.json()["checklist"] == {"setup_ok": True, "sheet_signed": True}

    unknown = await client.put(
        f"/api/scoring/matches/{match['id']}/confirm",
        headers=auth_headers,
        json={"checklist": {"bogus": True}},
    )
    assert unknown.status_code == 422


@pytest.mark.asyncio
async def test_confirm_without_checklist_still_works(client, auth_headers, event, team):
    match = await _score(client, auth_headers, event.id, team.id, {"points": 5})
    resp = await client.put(f"/api/scoring/matches/{match['id']}/confirm", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["checklist"] is None


# ── Parts challenge ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parts_challenge_ruling_disqualifies_the_loser(
    client, auth_headers, event, team, rival, duel
):
    await _score(
        client, auth_headers, event.id, team.id, {"points": 10}, scheduled_match_id=duel.id
    )
    await _score(
        client, auth_headers, event.id, rival.id, {"points": 90}, scheduled_match_id=duel.id
    )
    resp = await client.post(
        f"/api/scoring/events/{event.id}/parts-challenges",
        headers=auth_headers,
        json={
            "scheduled_match_id": duel.id,
            "challenger_team_id": team.id,
            "challenged_team_id": rival.id,
            "description": "Non-kit servo on the arm",
        },
    )
    assert resp.status_code == 201, resp.text
    challenge = resp.json()
    assert challenge["upheld"] is None

    resp = await client.put(
        f"/api/scoring/parts-challenges/{challenge['id']}/ruling",
        headers=auth_headers,
        json={"upheld": True, "ruling_note": "Servo is not in the kit"},
    )
    assert resp.status_code == 200, resp.text
    outcome = (
        await client.get(f"/api/scoring/scheduled-matches/{duel.id}/outcome", headers=auth_headers)
    ).json()
    assert outcome["winner"] == team.id and outcome["reason"] == "disqualified"

    again = await client.put(
        f"/api/scoring/parts-challenges/{challenge['id']}/ruling",
        headers=auth_headers,
        json={"upheld": False},
    )
    assert again.status_code == 409
    listing = await client.get(
        f"/api/scoring/events/{event.id}/parts-challenges", headers=auth_headers
    )
    assert listing.json()[0]["upheld"] is True
