"""Module activation on routes added by the packages merged next to it:
event-scoped scoring results, phase edits, paper deadlines, the 3D-print
checklist and the dashboard summary (see modules.events.module_access)."""

from datetime import date

import pytest

from modules.paper_review.models import PaperDeadline
from modules.seasons.models import Season


async def _set_modules(db, event, modules):
    event.active_modules = modules
    await db.commit()


class TestRoutesFromOtherPackages:
    """Routes added next to the module guard (event-scoped scoring, paper
    deadlines, the print checklist, the dashboard summary) follow the same
    switches."""

    @pytest.mark.asyncio
    async def test_event_scoped_result_routes_are_gated(
        self, client, db, auth_headers, season, event
    ):
        for kind in ("de-results", "aerial-results", "aerial-ranking", "doc-scores"):
            resp = await client.get(f"/api/scoring/events/{event.id}/{kind}", headers=auth_headers)
            assert resp.status_code == 404, (kind, resp.text)

        season_row = await db.get(Season, season.id)
        season_row.use_double_elimination = True
        await _set_modules(db, event, ["seeding", "double_elimination"])
        resp = await client.get(f"/api/scoring/events/{event.id}/de-results", headers=auth_headers)
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_switching_a_phase_to_a_disabled_module_is_refused(
        self, client, auth_headers, event
    ):
        created = await client.post(
            f"/api/v1/events/{event.id}/phases",
            headers=auth_headers,
            json={"name": "Seeding", "phase_type": "seeding", "sort_order": 7},
        )
        assert created.status_code == 201, created.text
        resp = await client.patch(
            f"/api/v1/events/{event.id}/phases/{created.json()['id']}",
            headers=auth_headers,
            json={"phase_type": "double_elimination"},
        )
        assert resp.status_code == 409
        assert "double_elimination" in resp.text

    @pytest.mark.asyncio
    async def test_paper_deadlines_follow_the_paper_module(
        self, client, db, auth_headers, season, event
    ):
        deadline = PaperDeadline(
            season_id=season.id, deadline_type="official_submission", due_date=date(2099, 3, 15)
        )
        db.add(deadline)
        await db.commit()
        url = f"/api/papers/deadlines/{deadline.id}"
        resp = await client.patch(url, headers=auth_headers, json={"label": "A"})
        assert resp.status_code == 200, resp.text

        await _set_modules(db, event, ["seeding"])
        resp = await client.patch(url, headers=auth_headers, json={"label": "B"})
        assert resp.status_code == 404
        resp = await client.get(
            f"/api/papers/deadlines?season_id={season.id}", headers=auth_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_print_checklist_follows_the_printing_module(
        self, client, db, auth_headers, season, event, team
    ):
        items = f"/api/teams/print-compliance/items?season_id={season.id}"
        status = f"/api/teams/{team.id}/seasons/{season.id}/print-compliance"
        assert (await client.get(items, headers=auth_headers)).status_code == 200
        assert (await client.get(status, headers=auth_headers)).status_code == 200

        await _set_modules(db, event, ["seeding", "paper"])
        assert (await client.get(items, headers=auth_headers)).status_code == 404
        assert (await client.get(status, headers=auth_headers)).status_code == 404
        created = await client.post(
            "/api/teams/print-compliance/items",
            headers=auth_headers,
            json={"season_id": season.id, "label": "Max. 20 cm"},
        )
        assert created.status_code == 404

    @pytest.mark.asyncio
    async def test_dashboard_summary_reports_effective_modules(
        self, client, db, auth_headers, event
    ):
        await _set_modules(db, event, ["seeding", "bots"])
        resp = await client.get(
            "/api/dashboard/summary", params={"event_id": event.id}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["modules"] == ["seeding", "bots"]
