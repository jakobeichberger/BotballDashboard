"""Per-event module activation (spec 01/03): Event.active_modules combined with
the season's competition flags decides which feature routes answer for an event.
Disabled modules answer 404 (routes) or 409 (creating a phase of that kind)."""

from types import SimpleNamespace

import pytest

from modules.bots.models import Bot
from modules.events.models import Event
from modules.events.module_access import effective_modules, modules_for_season
from modules.paper_review.models import Paper
from modules.printing.models import PrintJob
from modules.seasons.models import Season


def _season(**flags):
    base = {
        "use_seeding": True,
        "use_double_elimination": False,
        "use_documentation_scoring": False,
        "use_aerial": False,
        "use_paper_scoring": False,
    }
    return SimpleNamespace(**{**base, **flags})


class TestEffectiveModules:
    def test_season_flag_switches_off_an_event_module(self):
        event = SimpleNamespace(active_modules=["seeding", "aerial", "printing"])
        assert effective_modules(event, _season()) == ["seeding", "printing"]
        assert effective_modules(event, _season(use_aerial=True)) == [
            "seeding",
            "aerial",
            "printing",
        ]

    def test_event_switch_is_required_too(self):
        event = SimpleNamespace(active_modules=["seeding"])
        assert effective_modules(event, _season(use_aerial=True)) == ["seeding"]

    def test_paper_review_does_not_depend_on_paper_scoring(self):
        event = SimpleNamespace(active_modules=["paper"])
        assert effective_modules(event, _season(use_paper_scoring=False)) == ["paper"]

    def test_new_event_defaults_follow_the_season(self):
        assert modules_for_season(_season()) == ["seeding", "paper", "printing", "bots"]
        assert modules_for_season(_season(use_seeding=False, use_aerial=True)) == [
            "paper",
            "aerial",
            "printing",
            "bots",
        ]


async def _set_modules(db, event, modules):
    event.active_modules = modules
    await db.commit()


class TestEventModulesApi:
    @pytest.mark.asyncio
    async def test_create_event_derives_modules_from_season(self, client, auth_headers, season):
        resp = await client.post(
            "/api/v1/events",
            headers=auth_headers,
            json={"season_id": season.id, "name": "Regional", "slug": "regional-x"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["active_modules"] == ["seeding", "paper", "printing", "bots"]

    @pytest.mark.asyncio
    async def test_unknown_module_is_rejected(self, client, auth_headers, event):
        resp = await client.patch(
            f"/api/v1/events/{event.id}", headers=auth_headers, json={"active_modules": ["x"]}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_modules_endpoint_resolves_season_flags(
        self, client, db, auth_headers, season, event
    ):
        await _set_modules(db, event, ["seeding", "aerial", "printing"])
        resp = await client.get(f"/api/v1/events/{event.id}/modules", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["active_modules"] == ["seeding", "aerial", "printing"]
        assert body["effective_modules"] == ["seeding", "printing"]
        assert body["season_flags"]["use_aerial"] is False
        assert "bots" in body["available_modules"]


class TestPaperGating:
    @pytest.mark.asyncio
    async def test_disabled_paper_module_hides_event_papers(
        self, client, db, auth_headers, season, event, team
    ):
        paper = Paper(season_id=season.id, event_id=event.id, team_id=team.id, title="T")
        db.add(paper)
        await db.commit()
        assert (
            await client.get(f"/api/papers/{paper.id}", headers=auth_headers)
        ).status_code == 200

        await _set_modules(db, event, ["seeding"])
        for url in (
            f"/api/papers/{paper.id}",
            f"/api/papers/{paper.id}/history",
            f"/api/papers?event_id={event.id}",
        ):
            resp = await client.get(url, headers=auth_headers)
            assert resp.status_code == 404, (url, resp.text)
            assert "not active" in resp.text
        created = await client.post(
            "/api/papers",
            headers=auth_headers,
            json={"season_id": season.id, "event_id": event.id, "team_id": team.id, "title": "N"},
        )
        assert created.status_code == 404

    @pytest.mark.asyncio
    async def test_season_level_request_needs_one_event_with_the_module(
        self, client, db, auth_headers, season, event, team
    ):
        await _set_modules(db, event, ["seeding"])
        body = {"season_id": season.id, "team_id": team.id, "title": "Season paper"}
        assert (
            await client.post("/api/papers", headers=auth_headers, json=body)
        ).status_code == 404

        db.add(
            Event(season_id=season.id, name="Second", slug="second-ev", active_modules=["paper"])
        )
        await db.commit()
        assert (
            await client.post("/api/papers", headers=auth_headers, json=body)
        ).status_code == 201

    @pytest.mark.asyncio
    async def test_anonymous_callers_get_401_not_a_module_hint(self, client, db, event):
        await _set_modules(db, event, ["seeding"])
        assert (await client.get(f"/api/papers?event_id={event.id}")).status_code == 401


class TestPrintingAndBotsGating:
    @pytest.mark.asyncio
    async def test_print_jobs_of_a_disabled_event(
        self, client, db, auth_headers, season, event, team
    ):
        job = PrintJob(season_id=season.id, event_id=event.id, team_id=team.id, file_name="a.stl")
        db.add(job)
        await db.commit()
        await _set_modules(db, event, ["seeding", "paper"])
        assert (
            await client.get(f"/api/printing/jobs?event_id={event.id}", headers=auth_headers)
        ).status_code == 404
        assert (
            await client.put(f"/api/printing/jobs/{job.id}/approve", headers=auth_headers)
        ).status_code == 404
        # Printers are shared infrastructure, not event data.
        assert (await client.get("/api/printing/printers", headers=auth_headers)).status_code == 200

    @pytest.mark.asyncio
    async def test_bots_of_a_season_without_the_module(
        self, client, db, auth_headers, season, event, team
    ):
        bot = Bot(name="Robo", team_id=team.id, season_id=season.id)
        db.add(bot)
        await db.commit()
        assert (await client.get(f"/api/bots/{bot.id}", headers=auth_headers)).status_code == 200

        await _set_modules(db, event, ["seeding"])
        assert (await client.get(f"/api/bots/{bot.id}", headers=auth_headers)).status_code == 404
        assert (
            await client.get(f"/api/bots?event_id={event.id}", headers=auth_headers)
        ).status_code == 404
        # The unfiltered gallery is not tied to an event.
        assert (await client.get("/api/bots", headers=auth_headers)).status_code == 200


class TestCompetitionGating:
    @pytest.mark.asyncio
    async def test_aerial_routes_follow_the_event_switch(
        self, client, db, auth_headers, season, event, team
    ):
        url = f"/api/scoring/events/{event.id}/aerial-results/{team.id}"
        assert (await client.put(url, headers=auth_headers, json={"run1": 10})).status_code == 404
        # Public ranking of the module is gone as well.
        assert (
            await client.get(f"/api/scoring/events/{event.id}/aerial-ranking")
        ).status_code == 404

        season_row = await db.get(Season, season.id)
        season_row.use_aerial = True
        await _set_modules(db, event, ["seeding", "aerial"])
        assert (await client.put(url, headers=auth_headers, json={"run1": 10})).status_code == 200

    @pytest.mark.asyncio
    async def test_each_event_has_its_own_switch(self, client, db, auth_headers, season, event):
        season_row = await db.get(Season, season.id)
        season_row.use_documentation_scoring = True
        other = Event(
            season_id=season.id, name="Doc", slug="doc-ev", active_modules=["documentation"]
        )
        db.add(other)
        await db.commit()
        path = "/api/scoring/events/{}/doc-scores"
        assert (await client.get(path.format(event.id), headers=auth_headers)).status_code == 404
        assert (await client.get(path.format(other.id), headers=auth_headers)).status_code == 200

    @pytest.mark.asyncio
    async def test_de_phase_needs_the_module(self, client, db, auth_headers, season, event):
        body = {"name": "DE", "phase_type": "double_elimination", "sort_order": 5}
        resp = await client.post(
            f"/api/v1/events/{event.id}/phases", headers=auth_headers, json=body
        )
        assert resp.status_code == 409
        assert "double_elimination" in resp.text

        season_row = await db.get(Season, season.id)
        season_row.use_double_elimination = True
        await _set_modules(db, event, ["seeding", "double_elimination"])
        resp = await client.post(
            f"/api/v1/events/{event.id}/phases", headers=auth_headers, json=body
        )
        assert resp.status_code == 201, resp.text
