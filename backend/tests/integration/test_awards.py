"""Awards: templates, computed placings, nominations, jury decision, publishing, export.
Also the timeout card (one per team and tournament)."""

import uuid

import pytest

from modules.awards.service import placings
from modules.events.models import EventRegistration
from modules.paper_review.models import Paper
from modules.teams.models import Team
from tests.paper_helpers import headers_for, make_user


@pytest.fixture(autouse=True)
async def _modules_on(db, season, event):
    season.use_double_elimination = True
    season.use_documentation_scoring = True
    event.active_modules = ["seeding", "double_elimination", "documentation"]
    await db.commit()


async def _teams(db, event, *specs: tuple[str, str]) -> list[Team]:
    teams = [Team(name=name, team_number=f"26-{i:04d}") for i, (name, _) in enumerate(specs)]
    db.add_all(teams)
    await db.flush()
    for team, (_, category) in zip(teams, specs, strict=True):
        db.add(EventRegistration(event_id=event.id, team_id=team.id, category=category))
    await db.commit()
    return teams


async def _seed(client, headers, event_id, team_id, points):
    resp = await client.post(
        f"/api/v1/events/{event_id}/matches",
        headers=headers,
        json={
            "team_id": team_id,
            "raw_scores": {"points": points},
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 201, resp.text


def _by_key(data):
    return {award["key"]: award for award in data["awards"]}


def test_placings_share_places_and_respect_courses():
    rows = [
        {"team_id": "a", "rank": 1, "overall": 2.5, "de_bracket": "A", "de_rank": 1},
        {"team_id": "b", "rank": 2, "overall": 2.0, "de_bracket": "A", "de_rank": 2},
        {"team_id": "c", "rank": 2, "overall": 2.0, "de_bracket": "B", "de_rank": 1},
        {"team_id": "d", "rank": 4, "overall": 1.0, "de_bracket": "B", "de_rank": 2},
        {"team_id": "x", "rank": None, "overall": 3.0, "disqualified": True},
    ]
    assert [(p["team_id"], p["place"]) for p in placings(rows, "overall", 2, False)] == [
        ("a", 1),
        ("b", 2),
        ("c", 2),
    ]
    per_course = placings(rows, "de", 1, True)
    assert sorted((p["course"], p["team_id"]) for p in per_course) == [("A", "a"), ("B", "c")]
    # A team without a value takes no place.
    assert placings([{"team_id": "z", "rank": 1, "paper": 0.0}], "paper", 3, False) == []


@pytest.mark.asyncio
async def test_ecer_awards_are_computed_from_the_rankings(client, db, auth_headers, season, event):
    a, b, c, o = await _teams(
        db, event, ("Alpha", "botball"), ("Beta", "botball"), ("Gamma", "botball"), ("Opa", "open")
    )
    for team, points in ((a, 300), (b, 200), (c, 100), (o, 50)):
        await _seed(client, auth_headers, event.id, team.id, points)
    await client.put(
        f"/api/scoring/events/{event.id}/de-results",
        headers=auth_headers,
        json=[
            {"team_id": b.id, "bracket": "A", "de_rank": 1},
            {"team_id": a.id, "bracket": "A", "de_rank": 2},
            {"team_id": c.id, "bracket": "A", "de_rank": 3},
        ],
    )
    db.add(Paper(season_id=season.id, team_id=c.id, title="P", final_score=0.9))
    db.add(
        Paper(
            season_id=season.id, team_id=o.id, title="Q", final_score=0.8, presented_on_stage=True
        )
    )
    await db.commit()

    templates = (await client.get("/api/awards/templates", headers=auth_headers)).json()
    assert {t["id"] for t in templates} == {"ecer", "gcer"}
    resp = await client.post(f"/api/awards/events/{event.id}/templates/ecer", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["awards"]) == 15
    # Applying twice adds nothing.
    again = await client.post(f"/api/awards/events/{event.id}/templates/ecer", headers=auth_headers)
    assert len(again.json()["awards"]) == 15

    data = (
        await client.post(f"/api/awards/events/{event.id}/compute", headers=auth_headers)
    ).json()
    awards = _by_key(data)
    seeding = [(r["team_id"], r["place"]) for r in awards["botball_seeding"]["results"]]
    assert seeding == [(a.id, 1)]
    assert [r["team_id"] for r in awards["botball_de"]["results"]] == [b.id]
    overall = [(r["place"], r["team_id"]) for r in awards["botball_overall"]["results"]]
    # Alpha (seeding 1st, DE 2nd) and Beta (seeding 2nd, DE 1st) tie: shared place.
    assert [place for place, _ in overall] == [1, 1, 3]
    assert {team for _, team in overall} == {a.id, b.id, c.id}
    # Best Paper ranks Botball and Open together.
    assert [r["team_id"] for r in awards["best_paper"]["results"]] == [c.id]
    assert [r["team_id"] for r in awards["open_overall"]["results"]] == [o.id]
    # Best Paper Presentation: the on-stage paper is nominated.
    nominations = awards["best_paper_presentation"]["nominations"]
    assert [n["team_id"] for n in nominations] == [o.id]
    assert awards["spirit_of_ecer"]["results"] == []


@pytest.mark.asyncio
async def test_judged_award_nominations_decision_and_publishing(
    client, db, auth_headers, season, event
):
    a, b = await _teams(db, event, ("Alpha", "botball"), ("Beta", "botball"))
    await client.post(f"/api/awards/events/{event.id}/templates/ecer", headers=auth_headers)
    spirit = _by_key(
        (await client.get(f"/api/awards/events/{event.id}", headers=auth_headers)).json()
    )["spirit_of_ecer"]

    # Mentors hold scoring:write for their own team: they may not nominate.
    mentor = await make_user(db, "mentor@test.com", ("scoring:read", "scoring:write"))
    mentor_headers = headers_for(mentor)
    resp = await client.post(
        f"/api/awards/{spirit['id']}/nominations",
        headers=mentor_headers,
        json={"team_id": a.id},
    )
    assert resp.status_code == 403
    # The jury (awards:admin) nominates and decides.
    jury = await make_user(db, "jury@test.com", ("scoring:read", "awards:admin"))
    jury_headers = headers_for(jury)
    resp = await client.post(
        f"/api/awards/{spirit['id']}/nominations",
        headers=jury_headers,
        json={"team_id": a.id, "note": "Helped every team"},
    )
    assert resp.status_code == 201, resp.text
    await client.post(
        f"/api/awards/{spirit['id']}/nominations", headers=auth_headers, json={"team_id": b.id}
    )
    decision = {"placements": [{"team_id": a.id, "place": 1}]}
    forbidden = await client.put(
        f"/api/awards/{spirit['id']}/results", headers=mentor_headers, json=decision
    )
    assert forbidden.status_code == 403
    too_far = {"placements": [{"team_id": a.id, "place": 2}]}
    resp = await client.put(
        f"/api/awards/{spirit['id']}/results", headers=auth_headers, json=too_far
    )
    assert resp.status_code == 422
    resp = await client.put(
        f"/api/awards/{spirit['id']}/results", headers=auth_headers, json=decision
    )
    assert resp.status_code == 200, resp.text
    assert [(r["team_id"], r["place"]) for r in resp.json()["results"]] == [(a.id, 1)]
    assert len(resp.json()["nominations"]) == 2

    public_url = f"/api/v1/public/events/{event.slug}/awards"
    assert (await client.get(public_url)).status_code == 404
    resp = await client.put(
        f"/api/awards/events/{event.id}/publish", headers=auth_headers, json={"published": True}
    )
    assert resp.json()["published"] is True
    public = (await client.get(public_url)).json()
    assert public == [
        {
            "key": "spirit_of_ecer",
            "label": "Spirit of ECER",
            "results": [
                {
                    "team_id": a.id,
                    "team_name": "Alpha",
                    "team_number": "26-0000",
                    "place": 1,
                    "course": None,
                    "score": None,
                    "note": None,
                }
            ],
        }
    ]

    csv = await client.get(f"/api/awards/events/{event.id}/export.csv", headers=auth_headers)
    assert csv.status_code == 200
    assert csv.text.splitlines() == [
        "Award,Course,Place,Team ID,Team,Score",
        "Spirit of ECER,,1,26-0000,Alpha,",
    ]
    pdf = await client.get(f"/api/awards/events/{event.id}/export.pdf", headers=auth_headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_custom_awards_and_gcer_courses(client, db, auth_headers, season, event):
    teams = await _teams(db, event, *[(f"T{i}", "botball") for i in range(4)])
    await client.put(
        f"/api/scoring/events/{event.id}/de-results",
        headers=auth_headers,
        json=[
            {"team_id": teams[0].id, "bracket": "A", "de_rank": 1},
            {"team_id": teams[1].id, "bracket": "A", "de_rank": 2},
            {"team_id": teams[2].id, "bracket": "B", "de_rank": 1},
            {"team_id": teams[3].id, "bracket": "B", "de_rank": 2},
        ],
    )
    resp = await client.post(f"/api/awards/events/{event.id}/templates/gcer", headers=auth_headers)
    assert resp.json()["template"] == "gcer"
    data = (
        await client.post(f"/api/awards/events/{event.id}/compute", headers=auth_headers)
    ).json()
    de = _by_key(data)["de"]["results"]
    assert sorted((r["course"], r["place"], r["team_id"]) for r in de) == sorted(
        [
            ("A", 1, teams[0].id),
            ("A", 2, teams[1].id),
            ("B", 1, teams[2].id),
            ("B", 2, teams[3].id),
        ]
    )

    bad = {"key": "fast", "label": "Fastest", "kind": "computed"}
    resp = await client.post(
        f"/api/awards/events/{event.id}/awards", headers=auth_headers, json=bad
    )
    assert resp.status_code == 422
    good = {"key": "rookie", "label": "Best Rookie", "kind": "judged"}
    resp = await client.post(
        f"/api/awards/events/{event.id}/awards", headers=auth_headers, json=good
    )
    assert resp.status_code == 201, resp.text
    award_id = resp.json()["id"]
    dup = await client.post(
        f"/api/awards/events/{event.id}/awards", headers=auth_headers, json=good
    )
    assert dup.status_code == 409
    resp = await client.put(
        f"/api/awards/{award_id}", headers=auth_headers, json={**good, "places": 3}
    )
    assert resp.json()["places"] == 3
    assert (await client.delete(f"/api/awards/{award_id}", headers=auth_headers)).status_code == 204


@pytest.mark.asyncio
async def test_one_timeout_card_per_team_and_tournament(client, db, auth_headers, event):
    (team,) = await _teams(db, event, ("Alpha", "botball"))
    url = f"/api/scoring/events/{event.id}/timeouts"
    resp = await client.post(
        url, headers=auth_headers, json={"team_id": team.id, "round_number": 2}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["team_name"] == "Alpha"
    second = await client.post(url, headers=auth_headers, json={"team_id": team.id})
    assert second.status_code == 409
    listed = (await client.get(url, headers=auth_headers)).json()
    assert [(t["team_id"], t["round_number"], t["reason"]) for t in listed] == [
        (team.id, 2, "before_hands_off")
    ]
    assert (await client.delete(f"{url}/{team.id}", headers=auth_headers)).status_code == 204
    assert (await client.get(url, headers=auth_headers)).json() == []
