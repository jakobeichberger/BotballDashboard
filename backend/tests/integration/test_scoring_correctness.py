"""Scoring rules from the Botball game review, end to end.

Covers: DQ rounds count 0, negative scores clamp to 0, non-seeding phases never
feed the seed score, n comes from the event field, per-category ranks with
shared ties, red cards, event scoping of DE/doc/aerial, the GCER and regional
presets, and the audit trail for match deletion and result upserts.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select


async def _teams(db, *names):
    from modules.teams.models import Team

    teams = [Team(name=n, country="AT") for n in names]
    db.add_all(teams)
    await db.flush()
    return teams


async def _register(db, event, team, category="botball"):
    from modules.events.models import EventRegistration

    db.add(EventRegistration(event_id=event.id, team_id=team.id, category=category))
    await db.flush()


async def _phase(db, event, phase_type, sort_order):
    from modules.events.models import EventPhase

    phase = EventPhase(
        event_id=event.id, name=phase_type, phase_type=phase_type, sort_order=sort_order
    )
    db.add(phase)
    await db.flush()
    return phase


async def _match(db, event, team, score, *, phase=None, dq=False, red=False, round_number=1):
    from modules.scoring.models import Match

    match = Match(
        season_id=event.season_id,
        event_id=event.id,
        team_id=team.id,
        event_phase_id=phase.id if phase else None,
        round_number=round_number,
        raw_scores={},
        total_score=score,
        is_disqualified=dq,
        red_card=red,
    )
    db.add(match)
    await db.flush()
    return match


async def _enable_competition_modules(db, season, *events):
    """DE, documentation and aerial results need their module switched on for
    the season and the event (modules.events.module_access)."""
    from modules.events.module_access import MODULE_KEYS

    season.use_double_elimination = True
    season.use_documentation_scoring = True
    season.use_aerial = True
    for event in events:
        event.active_modules = list(MODULE_KEYS)
    await db.flush()


async def _second_event(db, season):
    from modules.events.models import Event
    from modules.events.module_access import MODULE_KEYS

    event = Event(
        season_id=season.id,
        name="GCER",
        slug=f"gcer-{season.id}",
        status="published",
        starts_at=datetime(2099, 7, 1, tzinfo=UTC),
        active_modules=list(MODULE_KEYS),
    )
    db.add(event)
    await db.flush()
    return event


# ── Seeding inputs ────────────────────────────────────────────────────────────


class TestSeedRuns:
    @pytest.mark.asyncio
    async def test_dq_counts_zero_and_negative_clamps(self, db, season, event):
        from modules.scoring.formula_service import build_inputs

        (alpha,) = await _teams(db, "Alpha")
        await _match(db, event, alpha, 200.0, round_number=1)
        await _match(db, event, alpha, 300.0, dq=True, round_number=2)
        await _match(db, event, alpha, -40.0, round_number=3)

        rows = await build_inputs(db, event.id, "botball")
        assert rows[0]["seed_runs"] == [200.0, 0.0, 0.0]

    @pytest.mark.asyncio
    async def test_dq_round_is_one_of_the_best_two(self, db, season, event):
        """One good run and a DQ: the seed total is (run + 0) / 2, not the run alone."""
        from modules.scoring.formula_service import compute_category_ranking

        (alpha,) = await _teams(db, "Alpha")
        await _match(db, event, alpha, 200.0, round_number=1)
        await _match(db, event, alpha, 500.0, dq=True, round_number=2)

        ranked, run = await compute_category_ranking(db, event.id, "botball")
        assert run.ok, run.issues
        assert ranked[0]["seed_total"] == 100.0

    @pytest.mark.asyncio
    async def test_non_seeding_phases_are_excluded(self, db, season, event):
        from modules.scoring.formula_service import build_inputs

        (alpha,) = await _teams(db, "Alpha")
        seeding = await _phase(db, event, "seeding", 0)
        de = await _phase(db, event, "double_elimination", 1)
        alliance = await _phase(db, event, "alliance", 2)
        double_seeding = await _phase(db, event, "double_seeding", 3)
        await _match(db, event, alpha, 100.0, phase=seeding)
        await _match(db, event, alpha, 50.0)  # free-hand entry → seeding
        await _match(db, event, alpha, 900.0, phase=de)
        await _match(db, event, alpha, 800.0, phase=alliance)
        await _match(db, event, alpha, 70.0, phase=double_seeding, round_number=1)
        await _match(db, event, alpha, 30.0, phase=double_seeding, round_number=2)

        row = (await build_inputs(db, event.id, "botball"))[0]
        assert sorted(row["seed_runs"]) == [50.0, 100.0]
        assert sorted(row["double_seed_runs"]) == [30.0, 70.0]
        # Double seeding drops nothing: the mean of all runs.
        assert row["double_seed_total"] == 50.0

    @pytest.mark.asyncio
    async def test_phase_is_resolved_through_the_scheduled_match(self, db, season, event):
        from modules.events.models import ScheduledMatch
        from modules.scoring.formula_service import build_inputs
        from modules.scoring.models import Match

        (alpha,) = await _teams(db, "Alpha")
        de = await _phase(db, event, "double_elimination", 1)
        scheduled = ScheduledMatch(event_id=event.id, phase_id=de.id, code="DE1", sequence_number=1)
        db.add(scheduled)
        await db.flush()
        await _match(db, event, alpha, 40.0)
        db.add(
            Match(
                season_id=season.id,
                event_id=event.id,
                team_id=alpha.id,
                scheduled_match_id=scheduled.id,
                raw_scores={},
                total_score=999.0,
            )
        )
        await db.flush()
        assert (await build_inputs(db, event.id, "botball"))[0]["seed_runs"] == [40.0]


# ── Field of teams ────────────────────────────────────────────────────────────


class TestEventField:
    @pytest.mark.asyncio
    async def test_n_counts_event_participants_not_the_season(self, db, season, event):
        from modules.scoring.formula_service import compute_category_ranking
        from modules.teams.models import TeamSeasonRegistration

        alpha, beta, ghost = await _teams(db, "Alpha", "Beta", "Ghost")
        for t in (alpha, beta, ghost):
            db.add(TeamSeasonRegistration(team_id=t.id, season_id=season.id, category="botball"))
        await _match(db, event, alpha, 100.0)
        await _match(db, event, beta, 50.0)

        ranked, run = await compute_category_ranking(db, event.id, "botball")
        assert run.ok, run.issues
        assert {r["team_name"] for r in ranked} == {"Alpha", "Beta"}
        assert all(r["n"] == 2.0 for r in ranked)

    @pytest.mark.asyncio
    async def test_registered_team_without_results_is_in_the_field(self, db, season, event):
        from modules.scoring.formula_service import build_inputs

        alpha, beta = await _teams(db, "Alpha", "Beta")
        await _register(db, event, alpha)
        await _register(db, event, beta)
        await _match(db, event, alpha, 100.0)
        rows = await build_inputs(db, event.id, "botball")
        assert {r["team_name"] for r in rows} == {"Alpha", "Beta"}

    @pytest.mark.asyncio
    async def test_category_comes_from_the_event_registration(self, db, season, event):
        from modules.scoring.formula_service import build_inputs
        from modules.teams.models import TeamSeasonRegistration

        (alpha,) = await _teams(db, "Alpha")
        db.add(TeamSeasonRegistration(team_id=alpha.id, season_id=season.id, category="botball"))
        await _register(db, event, alpha, category="open")
        await _match(db, event, alpha, 100.0)

        assert await build_inputs(db, event.id, "botball") == []
        assert [r["team_name"] for r in await build_inputs(db, event.id, "open")] == ["Alpha"]


# ── Seeding ranking table ─────────────────────────────────────────────────────


class TestSeedingRankingTable:
    @pytest.mark.asyncio
    async def test_ranks_per_category_with_shared_ties(self, db, season, event):
        from modules.scoring.service import _recompute_ranking, get_ranking

        a, b, c, d, o = await _teams(db, "A", "B", "C", "D", "Open1")
        for t in (a, b, c, d):
            await _register(db, event, t)
        await _register(db, event, o, category="open")
        for team, score in ((a, 300.0), (b, 200.0), (c, 200.0), (d, 100.0), (o, 500.0)):
            await _match(db, event, team, score)
            await _recompute_ranking(db, event.id, team.id, None)

        ranking = await get_ranking(db, event_id=event.id)
        ranks = {r.team_id: (r.category, r.rank) for r in ranking}
        assert ranks[a.id] == ("botball", 1)
        assert ranks[b.id] == ("botball", 2)
        assert ranks[c.id] == ("botball", 2)
        assert ranks[d.id] == ("botball", 4)
        # Open is its own competition: the best Open team is rank 1 there, and
        # does not push the Botball teams down.
        assert ranks[o.id] == ("open", 1)

    @pytest.mark.asyncio
    async def test_de_matches_do_not_enter_the_seeding_table(self, db, season, event):
        from modules.scoring.service import _recompute_ranking, get_ranking

        (alpha,) = await _teams(db, "Alpha")
        de = await _phase(db, event, "double_elimination", 1)
        await _match(db, event, alpha, 100.0)
        await _match(db, event, alpha, 900.0, phase=de)
        await _recompute_ranking(db, event.id, alpha.id, None, de.id)

        ranking = await get_ranking(db, event_id=event.id)
        assert len(ranking) == 1
        assert ranking[0].best_score == 100.0
        assert ranking[0].rounds_played == 1
        assert await get_ranking(db, event_id=event.id, event_phase_id=de.id) == []

    @pytest.mark.asyncio
    async def test_extended_ranking_route_ranks_per_category(self, client, db, season, event):
        a, o = await _teams(db, "A", "Open1")
        await _register(db, event, a)
        await _register(db, event, o, category="open")
        from modules.scoring.service import _recompute_ranking

        await _match(db, event, a, 10.0)
        await _match(db, event, o, 20.0)
        await _recompute_ranking(db, event.id, a.id, None)
        await _recompute_ranking(db, event.id, o.id, None)
        await db.commit()

        resp = await client.get(f"/api/scoring/events/{event.id}/ranking/extended")
        assert resp.status_code == 200
        assert {(e["team_name"], e["category"], e["rank"]) for e in resp.json()} == {
            ("A", "botball", 1),
            ("Open1", "open", 1),
        }


# ── Red card ──────────────────────────────────────────────────────────────────


class TestRedCard:
    @pytest.mark.asyncio
    async def test_red_card_removes_the_team_from_the_seeding_ranking(self, db, season, event):
        from modules.scoring.service import _recompute_ranking, get_ranking, update_match

        alpha, beta = await _teams(db, "Alpha", "Beta")
        m = await _match(db, event, alpha, 300.0)
        await _match(db, event, beta, 100.0)
        await _recompute_ranking(db, event.id, alpha.id, None)
        await _recompute_ranking(db, event.id, beta.id, None)

        await update_match(db, m.id, red_card=True)

        public = await get_ranking(db, event_id=event.id)
        assert [r.team_id for r in public] == [beta.id]
        assert public[0].rank == 1
        full = await get_ranking(db, event_id=event.id, include_disqualified=True)
        flagged = next(r for r in full if r.team_id == alpha.id)
        assert flagged.disqualified is True
        assert flagged.rank is None

    @pytest.mark.asyncio
    async def test_red_card_in_de_disqualifies_from_the_overall_ranking(self, db, season, event):
        from modules.scoring.formula_service import compute_overall_ranking

        alpha, beta, gamma = await _teams(db, "Alpha", "Beta", "Gamma")
        de = await _phase(db, event, "double_elimination", 1)
        await _match(db, event, alpha, 300.0)
        await _match(db, event, beta, 200.0)
        await _match(db, event, gamma, 100.0)
        await _match(db, event, alpha, 0.0, phase=de, red=True)

        entries = await compute_overall_ranking(db, event.id, ["botball"])
        by_name = {e["team_name"]: e for e in entries}
        assert by_name["Alpha"]["disqualified"] is True
        assert by_name["Alpha"]["rank"] is None
        assert by_name["Beta"]["rank"] == 1
        assert by_name["Gamma"]["rank"] == 2
        # The disqualified team is out of the field, so n = 2 and max = 200:
        # Gamma = 3/4 · (2 − 2 + 1)/2 + 1/4 · 100/200 (with n = 3 it would be 0.625).
        assert by_name["Gamma"]["seeding_score"] == pytest.approx(0.5)
        assert by_name["Beta"]["seeding_score"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_overall_route_reports_disqualification(self, client, db, season, event):
        (alpha,) = await _teams(db, "Alpha")
        await _match(db, event, alpha, 100.0, red=True)
        await db.commit()
        resp = await client.get(f"/api/scoring/events/{event.id}/ranking/overall")
        assert resp.status_code == 200
        assert resp.json()[0]["rank"] is None
        assert resp.json()[0]["disqualified"] is True


# ── Event scoping ─────────────────────────────────────────────────────────────


class TestEventScoping:
    @pytest.mark.asyncio
    async def test_results_are_written_to_the_selected_event(
        self, client, db, season, event, auth_headers
    ):
        gcer = await _second_event(db, season)
        await _enable_competition_modules(db, season, event)
        alpha, beta = await _teams(db, "Alpha", "Beta")
        await db.commit()

        resp = await client.put(
            f"/api/scoring/events/{gcer.id}/de-results",
            json=[
                {"team_id": alpha.id, "bracket": "A", "de_rank": 1},
                {"team_id": beta.id, "bracket": "A", "de_rank": 2},
            ],
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert {r["event_id"] for r in resp.json()} == {gcer.id}

        resp = await client.put(
            f"/api/scoring/events/{gcer.id}/doc-scores/{alpha.id}",
            json={"part1": 100, "part2": 100, "part3": 100, "onsite": 50},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["event_id"] == gcer.id

        resp = await client.put(
            f"/api/scoring/events/{gcer.id}/aerial-results/{alpha.id}",
            json={"run1": 10, "run2": 30},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["event_id"] == gcer.id

        # Nothing leaked into the season's default (earliest) event.
        for kind in ("de-results", "doc-scores", "aerial-results"):
            default = await client.get(
                f"/api/scoring/seasons/{season.id}/{kind}", headers=auth_headers
            )
            assert default.json() == [], kind
            scoped = await client.get(
                f"/api/scoring/seasons/{season.id}/{kind}?event_id={gcer.id}",
                headers=auth_headers,
            )
            assert scoped.json() != [], kind

    @pytest.mark.asyncio
    async def test_season_overall_route_uses_the_same_default_event(
        self, client, db, season, event, auth_headers
    ):
        """Season routes write the default event; the overall ranking must read it too."""
        later = await _second_event(db, season)
        (alpha,) = await _teams(db, "Alpha")
        await _match(db, event, alpha, 100.0)
        await db.commit()

        resp = await client.get(f"/api/scoring/seasons/{season.id}/ranking/overall")
        assert [e["team_name"] for e in resp.json()] == ["Alpha"]
        resp = await client.get(
            f"/api/scoring/seasons/{season.id}/ranking/overall?event_id={later.id}"
        )
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_legacy_displays_follow_the_game_review(
        self, client, db, season, event, auth_headers
    ):
        a, b, c = await _teams(db, "A", "B", "C")
        await _enable_competition_modules(db, season, event)
        await db.commit()
        resp = await client.put(
            f"/api/scoring/events/{event.id}/de-results",
            json=[
                {"team_id": a.id, "bracket": "A", "de_rank": 1},
                {"team_id": b.id, "bracket": "A", "de_rank": 2},
                {"team_id": c.id, "bracket": "A", "de_rank": 3},
            ],
            headers=auth_headers,
        )
        scores = {r["team_id"]: r["bracket_score"] for r in resp.json()}
        # (n − rank + 1) / n with n = 3, not 1 − (rank − 1)/(n − 1).
        assert scores[a.id] == pytest.approx(1.0)
        assert scores[b.id] == pytest.approx(2 / 3)
        assert scores[c.id] == pytest.approx(1 / 3)

        resp = await client.put(
            f"/api/scoring/events/{event.id}/aerial-results",
            json=[
                {"team_id": a.id, "run1": 20, "run2": 100, "run3": 80, "run4": 0},
                {"team_id": b.id, "run1": 50, "run2": 50, "run3": 50, "run4": 50},
            ],
            headers=auth_headers,
        )
        aerial = {r["team_id"]: r for r in resp.json()}
        assert aerial[a.id]["score"] == pytest.approx(50.0)  # mean of all four runs
        assert aerial[a.id]["rank"] == aerial[b.id]["rank"] == 1  # tie shares the rank

        resp = await client.put(
            f"/api/scoring/events/{event.id}/doc-scores/{a.id}",
            json={"part1": 100, "part2": 100, "part3": None, "onsite": 50},
            headers=auth_headers,
        )
        # 0.2 + 0.2 + 0 (missing) + 0.4 · 0.5
        assert resp.json()["doc_score"] == pytest.approx(0.6)


# ── Presets ───────────────────────────────────────────────────────────────────


class TestPresets:
    @pytest.mark.asyncio
    async def test_gcer_preset_runs_on_real_data(self, client, db, season, event, auth_headers):
        from modules.scoring.competition_models import DocumentationScore
        from modules.scoring.formula_service import compute_category_ranking

        alpha, beta = await _teams(db, "Alpha", "Beta")
        ds = await _phase(db, event, "double_seeding", 1)
        for team, seed, runs, onsite in ((alpha, 200.0, [80, 20], 90), (beta, 100.0, [40, 40], 30)):
            await _match(db, event, team, seed)
            for i, r in enumerate(runs, start=1):
                await _match(db, event, team, float(r), phase=ds, round_number=i)
            db.add(
                DocumentationScore(
                    season_id=season.id,
                    event_id=event.id,
                    team_id=team.id,
                    part1=0,
                    part2=0,
                    part3=0,
                    onsite=onsite,
                )
            )
        await db.commit()

        resp = await client.post(
            f"/api/scoring/formulas/seasons/{season.id}/presets/gcer_2026_botball",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

        ranked, run = await compute_category_ranking(db, event.id, "botball")
        assert run.ok, run.issues  # no "unknown variable" for double_seed_*
        alpha_row = next(r for r in ranked if r["team_name"] == "Alpha")
        assert alpha_row["doc_score"] == pytest.approx(0.9)  # onsite only
        assert alpha_row["double_seed_total"] == pytest.approx(50.0)
        assert "double_seed_score" in alpha_row

    @pytest.mark.asyncio
    async def test_regional_preset_and_unknown_preset(self, client, db, season, auth_headers):
        resp = await client.post(
            f"/api/scoring/formulas/seasons/{season.id}/presets/regional_2026_botball",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        doc = next(f for f in resp.json() if f["key"] == "doc_score")
        assert "0.4 * (onsite/100)" in doc["expression"]

        resp = await client.post(
            f"/api/scoring/formulas/seasons/{season.id}/presets/nope", headers=auth_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reference_lists_presets(self, client, auth_headers):
        resp = await client.get("/api/scoring/formulas/reference", headers=auth_headers)
        ids = {p["id"] for p in resp.json()["presets"]}
        assert {"ecer_2025_botball", "regional_2026_botball", "gcer_2026_botball"} <= ids


# ── Audit trail ───────────────────────────────────────────────────────────────


class TestAuditTrail:
    @pytest.mark.asyncio
    async def test_revisions_survive_match_deletion(
        self, client, db, season, event, auth_headers, admin_user
    ):
        from modules.scoring.models import ScoreRevision

        (alpha,) = await _teams(db, "Alpha")
        await db.commit()
        resp = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            json={"team_id": alpha.id, "raw_scores": {"points": 10}},
            headers=auth_headers,
        )
        match_id = resp.json()["id"]
        await client.patch(
            f"/api/scoring/matches/{match_id}",
            json={"raw_scores": {"points": 20}},
            headers=auth_headers,
        )
        resp = await client.delete(
            f"/api/scoring/matches/{match_id}?reason=entered+twice", headers=auth_headers
        )
        assert resp.status_code == 204

        history = await client.get(
            f"/api/scoring/matches/{match_id}/revisions", headers=auth_headers
        )
        assert history.status_code == 200
        revisions = history.json()
        assert [r["revision"] for r in revisions] == [1, 2, 3]
        assert all(r["match_id"] is None and r["match_ref"] == match_id for r in revisions)
        last = revisions[-1]
        assert last["new_value"]["deleted"] is True
        assert last["reason"] == "entered twice"
        assert last["changed_by"] == admin_user.id

        rows = (await db.execute(select(ScoreRevision))).scalars().all()
        assert len(rows) == 3

        event_log = await client.get(
            f"/api/scoring/events/{event.id}/revisions", headers=auth_headers
        )
        assert len(event_log.json()) == 3

    @pytest.mark.asyncio
    async def test_result_upserts_are_audited(self, client, db, season, event, auth_headers):
        (alpha,) = await _teams(db, "Alpha")
        await _enable_competition_modules(db, season, event)
        await db.commit()
        url = f"/api/scoring/events/{event.id}/doc-scores/{alpha.id}"
        await client.put(url, json={"part1": 50}, headers=auth_headers)
        await client.put(url, json={"part1": 80}, headers=auth_headers)
        await client.put(url, json={"part1": 80}, headers=auth_headers)  # no change → no entry
        await client.put(
            f"/api/scoring/events/{event.id}/de-results/{alpha.id}",
            json={"bracket": "A", "de_rank": 1},
            headers=auth_headers,
        )

        resp = await client.get(
            f"/api/scoring/events/{event.id}/result-revisions?kind=doc", headers=auth_headers
        )
        assert resp.status_code == 200
        doc_log = resp.json()
        assert len(doc_log) == 2
        values = sorted((r["previous_value"] or {}).get("part1") or 0 for r in doc_log)
        assert values == [0, 50]
        resp = await client.get(
            f"/api/scoring/events/{event.id}/result-revisions", headers=auth_headers
        )
        assert {r["kind"] for r in resp.json()} == {"doc", "de"}
