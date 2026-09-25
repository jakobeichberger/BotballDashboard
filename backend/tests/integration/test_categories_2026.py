"""Category registry, aerial run lists, JBC points and per-course overall ranks."""

import pytest

from modules.teams.models import Team


@pytest.fixture(autouse=True)
async def _modules_on(db, season, event):
    season.use_aerial = True
    season.use_double_elimination = True
    season.use_documentation_scoring = True
    event.active_modules = ["seeding", "double_elimination", "documentation", "aerial"]
    await db.commit()


async def _team(db, name: str) -> Team:
    team = Team(name=name, country="AT")
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team


async def _register(client, headers, event_id, team_id, category):
    return await client.post(
        f"/api/v1/events/{event_id}/registrations",
        headers=headers,
        json={"team_id": team_id, "category": category},
    )


@pytest.mark.asyncio
async def test_default_registry_keeps_the_historical_keys(client, auth_headers, season):
    resp = await client.get(f"/api/seasons/{season.id}/categories", headers=auth_headers)
    assert resp.status_code == 200
    entries = {e["key"]: e for e in resp.json()}
    assert list(entries) == ["botball", "open", "aerial_junior", "aerial", "jbc"]
    assert entries["open"]["label_en"] == "ECER Open"
    assert entries["aerial"]["label_en"] == "Aerial Senior"
    assert (entries["aerial_junior"]["kind"], entries["aerial_junior"]["counted_runs"]) == (
        "aerial",
        3,
    )


@pytest.mark.asyncio
async def test_registrations_are_checked_against_the_registry(
    client, auth_headers, db, season, event
):
    junior = await _team(db, "Junior")
    assert (
        await _register(client, auth_headers, event.id, junior.id, "aerial_junior")
    ).status_code == 201
    other = await _team(db, "Other")
    resp = await _register(client, auth_headers, event.id, other.id, "rookies")
    assert resp.status_code == 422

    # A custom category is valid once the season lists it.
    registry = (
        await client.get(f"/api/seasons/{season.id}/categories", headers=auth_headers)
    ).json()
    registry.append(
        {"key": "rookies", "label_de": "Neulinge", "label_en": "Rookies", "kind": "custom"}
    )
    resp = await client.put(
        f"/api/seasons/{season.id}/categories", headers=auth_headers, json=registry
    )
    assert resp.status_code == 200, resp.text
    assert (await _register(client, auth_headers, event.id, other.id, "rookies")).status_code == 201

    # Formulas can be stored for it; an unknown category is refused.
    formulas = {"formulas": [{"key": "overall", "expression": "seed_rank"}]}
    ok = await client.put(
        f"/api/scoring/formulas/seasons/{season.id}/rookies", headers=auth_headers, json=formulas
    )
    assert ok.status_code == 200, ok.text
    bad = await client.put(
        f"/api/scoring/formulas/seasons/{season.id}/nope", headers=auth_headers, json=formulas
    )
    assert bad.status_code == 400

    # A category still used by a registration cannot be removed.
    resp = await client.put(
        f"/api/seasons/{season.id}/categories",
        headers=auth_headers,
        json=[e for e in registry if e["key"] != "rookies"],
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_registry_validation(client, auth_headers, season):
    url = f"/api/seasons/{season.id}/categories"
    entry = {"key": "a", "label_de": "A", "label_en": "A", "kind": "custom"}
    assert (await client.put(url, headers=auth_headers, json=[entry, entry])).status_code == 422
    bad_key = {**entry, "key": "Has Space"}
    assert (await client.put(url, headers=auth_headers, json=[bad_key])).status_code == 422
    preset = {**entry, "formula_preset": "nope"}
    assert (await client.put(url, headers=auth_headers, json=[preset])).status_code == 422
    runs = {**entry, "kind": "aerial", "run_count": 3, "counted_runs": 4}
    assert (await client.put(url, headers=auth_headers, json=[runs])).status_code == 422
    assert (await client.put(url, headers=auth_headers, json=[])).status_code == 422


@pytest.mark.asyncio
async def test_aerial_runs_are_a_list_and_ranked_per_category(
    client, auth_headers, db, season, event
):
    junior_a, junior_b, senior = [await _team(db, n) for n in ("EVA-01", "BGZ2", "Senior")]
    for team, category in (
        (junior_a, "aerial_junior"),
        (junior_b, "aerial_junior"),
        (senior, "aerial"),
    ):
        assert (
            await _register(client, auth_headers, event.id, team.id, category)
        ).status_code == 201
    resp = await client.put(
        f"/api/scoring/events/{event.id}/aerial-results",
        headers=auth_headers,
        json=[
            {"team_id": junior_a.id, "runs": [75, 0, 30, 125, 75, 110]},
            {"team_id": junior_b.id, "runs": [55, 20, 85, 30, 30, 85]},
            {"team_id": senior.id, "runs": [10, 20, None, 30]},
        ],
    )
    assert resp.status_code == 200, resp.text
    rows = {r["team_id"]: r for r in resp.json()}
    # ECER 2026: EVA-01 103.33 (rank 2 there), BGZ2 75 — best three of six.
    assert rows[junior_a.id]["score"] == pytest.approx(103.3333333)
    assert rows[junior_b.id]["score"] == pytest.approx(75.0)
    assert rows[senior.id]["runs"] == [10, 20, None, 30]
    assert rows[senior.id]["score"] == pytest.approx(20.0)  # senior: mean of all runs
    assert (rows[junior_a.id]["rank"], rows[junior_b.id]["rank"], rows[senior.id]["rank"]) == (
        1,
        2,
        1,
    )
    ranking = (
        await client.get(f"/api/scoring/events/{event.id}/aerial-ranking", headers=auth_headers)
    ).json()
    assert {r["category"] for r in ranking} == {"aerial", "aerial_junior"}
    overall = (
        await client.get(
            f"/api/scoring/events/{event.id}/ranking/overall?category=aerial_junior",
            headers=auth_headers,
        )
    ).json()
    junior_entry = next(e for e in overall if e["team_id"] == junior_a.id)
    assert junior_entry["category"] == "aerial_junior"
    assert junior_entry["aerial_score"] == pytest.approx(103.3333333)

    too_many = [{"team_id": senior.id, "runs": [1] * 21}]
    resp = await client.put(
        f"/api/scoring/events/{event.id}/aerial-results", headers=auth_headers, json=too_many
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_jbc_points_rank_and_feed_the_formula(client, auth_headers, db, season, event):
    a, b, c = [await _team(db, n) for n in ("3aSiegharts_A", "Biis", "EMS Prinzersdorf 2")]
    for team in (a, b, c):
        await _register(client, auth_headers, event.id, team.id, "jbc")
    resp = await client.put(
        f"/api/scoring/events/{event.id}/jbc-results",
        headers=auth_headers,
        json=[
            {"team_id": a.id, "points": 18},
            {"team_id": b.id, "points": 15},
            # the challenge list sums up to the points
            {
                "team_id": c.id,
                "challenges": [{"key": "c1", "points": 10}, {"key": "c4", "points": 5}],
            },
        ],
    )
    assert resp.status_code == 200, resp.text
    rows = {r["team_id"]: r for r in resp.json()}
    assert rows[c.id]["points"] == 15
    assert (rows[a.id]["rank"], rows[b.id]["rank"], rows[c.id]["rank"]) == (1, 2, 2)
    ranking = (
        await client.get(f"/api/scoring/events/{event.id}/jbc-ranking", headers=auth_headers)
    ).json()
    assert [r["team_id"] for r in ranking][0] == a.id

    await client.post(
        f"/api/scoring/formulas/seasons/{season.id}/presets/jbc_2026", headers=auth_headers
    )
    overall = (
        await client.get(
            f"/api/scoring/events/{event.id}/ranking/overall?category=jbc", headers=auth_headers
        )
    ).json()
    assert {e["team_id"]: (e["rank"], e["overall_score"]) for e in overall} == {
        a.id: (1, 18.0),
        b.id: (2, 15.0),
        c.id: (2, 15.0),
    }
    revisions = (
        await client.get(
            f"/api/scoring/events/{event.id}/result-revisions?kind=jbc", headers=auth_headers
        )
    ).json()
    assert len(revisions) == 3


@pytest.mark.asyncio
async def test_overall_is_ranked_per_course_when_configured(
    client, auth_headers, db, season, event
):
    teams = [await _team(db, f"T{i}") for i in range(4)]
    for team in teams:
        await _register(client, auth_headers, event.id, team.id, "botball")
    registry = (
        await client.get(f"/api/seasons/{season.id}/categories", headers=auth_headers)
    ).json()
    for entry in registry:
        if entry["key"] == "botball":
            entry["rank_per_bracket"] = True
    await client.put(f"/api/seasons/{season.id}/categories", headers=auth_headers, json=registry)
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
    overall = (
        await client.get(
            f"/api/scoring/events/{event.id}/ranking/overall?category=botball",
            headers=auth_headers,
        )
    ).json()
    courses = {e["team_id"]: (e["course"], e["course_rank"]) for e in overall}
    assert courses == {
        teams[0].id: ("A", 1),
        teams[1].id: ("A", 2),
        teams[2].id: ("B", 1),
        teams[3].id: ("B", 2),
    }


@pytest.mark.asyncio
async def test_rules_carry_the_2026_switches_and_checklist_preset(client, auth_headers, season):
    presets = (
        await client.get("/api/scoring/referee-checklist-presets", headers=auth_headers)
    ).json()
    preset = next(p for p in presets if p["id"] == "botball_2026")
    packaging = next(i for i in preset["items"] if i["key"] == "packaging_center")
    # Game Review v1.4, scoring rule 9, verbatim.
    assert packaging["description"].startswith(
        "Packaging Bin Rule: In order for a Packaging Bin to count as returned"
    )
    assert (
        "only be touching the surface of the game table in the Packaging Center"
        in (packaging["description"])
    )

    url = f"/api/scoring/seasons/{season.id}/rules"
    rules = (await client.get(url, headers=auth_headers)).json()
    assert rules["seeding_tiebreakers"] is False
    assert rules["doc_max_points"] == {"p1": 100, "p2": 100, "p3": 100, "onsite": 100}
    rules.update(
        seeding_tiebreakers=True,
        referee_checklist=preset["items"],
        doc_max_points={"p1": 100, "p2": 95, "p3": 100, "onsite": 100},
    )
    resp = await client.put(url, headers=auth_headers, json=rules)
    assert resp.status_code == 200, resp.text
    stored = resp.json()
    assert stored["seeding_tiebreakers"] is True
    assert stored["doc_max_points"]["p2"] == 95
    assert len(stored["referee_checklist"]) == len(preset["items"])

    # A cloned season keeps the rules and the category registry.
    registry = (
        await client.get(f"/api/seasons/{season.id}/categories", headers=auth_headers)
    ).json()
    registry[0]["label_en"] = "Botball (renamed)"
    await client.put(f"/api/seasons/{season.id}/categories", headers=auth_headers, json=registry)
    clone = await client.post(
        f"/api/seasons/{season.id}/clone", headers=auth_headers, json={"name": "2027", "year": 2027}
    )
    assert clone.status_code == 201, clone.text
    clone_id = clone.json()["id"]
    cloned_rules = (
        await client.get(f"/api/scoring/seasons/{clone_id}/rules", headers=auth_headers)
    ).json()
    assert cloned_rules["seeding_tiebreakers"] is True
    assert cloned_rules["doc_max_points"]["p2"] == 95
    cloned_registry = (
        await client.get(f"/api/seasons/{clone_id}/categories", headers=auth_headers)
    ).json()
    assert cloned_registry[0]["label_en"] == "Botball (renamed)"
