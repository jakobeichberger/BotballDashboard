"""Where the performance work (pagination, cached rankings, OCR queue) meets
the security review (practice scoping, draft events, queue-after-commit).

Both landed in parallel; these tests pin down that the new paths keep the
access rules of the old ones.
"""

import io

import pytest
from sqlalchemy import select

import core.live as live
from core import cache
from core import celery_app as celery_module
from core.config import get_settings
from modules.events.models import Event, EventRegistration
from modules.scoring.models import Match
from tests.integration.test_security_regressions_3 import GUEST, MENTOR, _user


@pytest.fixture
def memory_cache(monkeypatch):
    monkeypatch.setattr(get_settings(), "cache_backend", "memory")
    cache.clear_memory()
    yield
    cache.clear_memory()


@pytest.fixture
def no_publish(monkeypatch):
    async def fake_publish(event_id, event, payload=None):
        return True

    monkeypatch.setattr(live, "publish_live_event", fake_publish)


@pytest.fixture
async def rival(db):
    from modules.teams.models import Team

    team = Team(name="Rival", country="AT")
    db.add(team)
    await db.commit()
    return team


@pytest.fixture
async def runs(client, db, auth_headers, season, event, team, rival):
    """Two rival practice runs between official runs, plus one own practice run."""
    db.add_all(
        [
            EventRegistration(event_id=event.id, team_id=rival.id),
            EventRegistration(event_id=event.id, team_id=team.id),
        ]
    )
    await db.commit()
    created: dict[str, str] = {}
    plan = (
        ("official_1", team, False, 1, "juror note own"),
        ("rival_practice_1", rival, True, 1, "rival secret 1"),
        ("rival_official", rival, False, 2, "juror note rival"),
        ("rival_practice_2", rival, True, 2, "rival secret 2"),
        ("own_practice", team, True, 3, "own practice note"),
        ("official_2", team, False, 3, None),
    )
    for key, owner, practice, round_number, notes in plan:
        resp = await client.post(
            f"/api/scoring/seasons/{season.id}/matches",
            headers=auth_headers,
            json={
                "team_id": owner.id,
                "event_id": event.id,
                "is_practice": practice,
                "round_number": round_number,
                "raw_scores": {},
                "notes": notes,
            },
        )
        assert resp.status_code == 201, resp.text
        created[key] = resp.json()["id"]
    return created


async def _pages(client, url, headers, size):
    rows, offset = [], 0
    while True:
        sep = "&" if "?" in url else "?"
        resp = await client.get(f"{url}{sep}limit={size}&offset={offset}", headers=headers)
        assert resp.status_code == 200, resp.text
        page = resp.json()
        rows.extend(page)
        if len(page) < size:
            return rows
        offset += size


# ── Paginated match lists keep the practice scoping ──────────────────────────


@pytest.mark.asyncio
async def test_paged_match_lists_skip_foreign_practice_before_paging(
    client, db, season, event, team, runs
):
    _, mentor = await _user(db, "m-paged@test.com", MENTOR, team)
    visible = {runs[key] for key in ("official_1", "rival_official", "own_practice", "official_2")}
    for url in (
        f"/api/scoring/seasons/{season.id}/matches",
        f"/api/v1/events/{event.id}/matches",
    ):
        full = (await client.get(url, headers=mentor)).json()
        assert {row["id"] for row in full} == visible, url
        # Pages of two: the hidden rows are filtered in the query, so every
        # page is full, nothing repeats and nothing is skipped.
        paged = await _pages(client, url, mentor, 2)
        assert [row["id"] for row in paged] == [row["id"] for row in full], url
        first = (await client.get(f"{url}?limit=2", headers=mentor)).json()
        assert len(first) == 2, url
        for row in paged:
            # MatchListItem: no schema snapshot in lists.
            assert "schema_snapshot" not in row, url
            if row["id"] == runs["rival_official"]:
                assert row["notes"] is None, url
            if row["id"] == runs["own_practice"]:
                assert row["notes"] == "own practice note", url


@pytest.mark.asyncio
async def test_organizers_page_through_every_run(client, auth_headers, season, runs):
    url = f"/api/scoring/seasons/{season.id}/matches"
    paged = await _pages(client, url, auth_headers, 4)
    assert {row["id"] for row in paged} == set(runs.values())
    by_id = {row["id"]: row for row in paged}
    assert by_id[runs["rival_practice_2"]]["notes"] == "rival secret 2"


@pytest.mark.asyncio
async def test_audit_trail_stays_scoped(client, db, event, team, runs):
    _, mentor = await _user(db, "m-trail@test.com", MENTOR, team)
    resp = await client.get(f"/api/scoring/events/{event.id}/revisions", headers=mentor)
    assert resp.status_code == 200, resp.text
    refs = {row["match_ref"] for row in resp.json()}
    assert runs["rival_practice_1"] not in refs and runs["rival_practice_2"] not in refs
    assert runs["own_practice"] in refs


# ── Cached rankings and results: public-safe and never of a draft ───────────


@pytest.mark.asyncio
@pytest.mark.usefixtures("memory_cache", "no_publish")
async def test_cached_public_results_and_ranking_never_contain_practice(client, db, event, runs):
    event.status = "live"
    event.public_results = True
    await db.commit()
    practice = {runs["rival_practice_1"], runs["rival_practice_2"], runs["own_practice"]}
    results_url = f"/api/v1/public/events/{event.slug}/results"
    for query in ("", "?order=desc", "?limit=2&offset=1"):
        for _ in range(2):  # a miss, then a hit of the same key
            resp = await client.get(results_url + query)
            assert resp.status_code == 200, resp.text
            assert not practice & {row["id"] for row in resp.json()}, query
            assert all("notes" not in row for row in resp.json())
    ranking = await client.get(f"/api/v1/public/events/{event.slug}/ranking")
    assert ranking.status_code == 200
    # Official runs only: the own team's practice run (round 3) is not counted.
    official = (
        await db.execute(
            select(Match.team_id).where(Match.event_id == event.id, Match.is_practice.is_(False))
        )
    ).scalars()
    assert {row["team_id"] for row in ranking.json()} == set(official)
    assert all(row["rounds_played"] <= 2 for row in ranking.json())


@pytest.mark.asyncio
@pytest.mark.usefixtures("memory_cache", "no_publish")
async def test_published_event_of_a_draft_season_is_not_public(client, db, season, event):
    event.public_results = True
    await db.commit()
    urls = [
        f"/api/v1/public/events/{event.slug}/ranking",
        f"/api/v1/public/events/{event.slug}/results",
        f"/api/v1/public/events/{event.slug}/schedule",
    ]
    for url in urls:
        assert (await client.get(url)).status_code == 200, url  # cached now
    season.status = "draft"
    await db.commit()
    for url in urls:
        assert (await client.get(url)).status_code == 404, url


@pytest.mark.asyncio
@pytest.mark.usefixtures("memory_cache")
async def test_season_ranking_of_a_draft_default_event_is_hidden(
    client, db, auth_headers, season, event
):
    """No event id in the path or query: the router guard cannot see the event,
    the ranking route checks it before reading the (shared) cache."""
    season.status = "draft"
    await db.commit()
    _, guest = await _user(db, "guest-rank@test.com", GUEST)
    _, organizer = await _user(
        db, "org-rank@test.com", ["events:read", "events:write", "scoring:read"]
    )
    for kind in ("extended", "overall"):
        url = f"/api/scoring/seasons/{season.id}/ranking/{kind}"
        # The organizer warms the cache first; the guest must still get 404.
        assert (await client.get(url, headers=organizer)).status_code == 200, kind
        assert (await client.get(url, headers=guest)).status_code == 404, kind
        assert (await client.get(url)).status_code == 401, kind
        by_event = f"/api/scoring/events/{event.id}/ranking/{kind}"
        assert (await client.get(by_event, headers=guest)).status_code == 404, kind
    season.status = "active"
    await db.commit()
    url = f"/api/scoring/seasons/{season.id}/ranking/extended"
    assert (await client.get(url, headers=guest)).status_code == 200


@pytest.mark.asyncio
async def test_new_list_params_do_not_bypass_the_draft_guard(client, db, season, team):
    draft = Event(season_id=season.id, name="Hidden Cup", slug="hidden-cup", status="draft")
    db.add(draft)
    await db.commit()
    _, guest = await _user(db, "guest-paged@test.com", GUEST)
    for url in (
        f"/api/v1/events/{draft.id}/matches?limit=5&offset=0",
        f"/api/scoring/seasons/{season.id}/matches?event_id={draft.id}&limit=5",
        f"/api/scoring/events/{draft.id}/ranking/extended",
    ):
        assert (await client.get(url, headers=guest)).status_code == 404, url
    assert (await client.get("/api/v1/public/events/hidden-cup/results?limit=5")).status_code == 404


# ── OCR queue: queued after the commit, routed to worker-ocr ────────────────


@pytest.mark.asyncio
async def test_template_extraction_is_queued_after_commit_on_the_ocr_queue(
    client, db, auth_headers, season, monkeypatch
):
    from core.task_queue import drain_pending_tasks
    from modules.scoring.score_sheets import tasks

    queued: list[str] = []
    monkeypatch.setattr(tasks.extract_template, "delay", lambda tid: queued.append(tid))

    resp = await client.post(
        f"/api/scoring/seasons/{season.id}/score-sheets",
        headers=auth_headers,
        files={"file": ("sheet.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")},
        data={"label": "Sheet", "year": "2026"},
    )
    assert resp.status_code == 201, resp.text
    template_id = resp.json()["id"]
    # Tests share the request session and do not commit it for the request.
    await drain_pending_tasks()
    assert queued == []
    await db.commit()
    await drain_pending_tasks()
    assert queued == [template_id]
    route = celery_module.celery_app.amqp.router.route({}, tasks.extract_template.name)
    assert route["queue"].name == celery_module.OCR_QUEUE


def test_run_task_sends_tasks_queued_after_commit():
    """A Celery task that queues another one (enqueue_after_commit) must not
    lose it when run_task's event loop shuts down."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from core.task_queue import enqueue_after_commit

    sent: list[str] = []

    class FakeTask:
        name = "score_sheets.process_scan"

        def delay(self, *args):
            sent.append(args[0])

    async def main() -> None:
        engine = create_async_engine("sqlite+aiosqlite://")
        try:
            async with AsyncSession(engine) as session:
                enqueue_after_commit(session, FakeTask(), "scan-1")
                await session.commit()
        finally:
            await engine.dispose()

    celery_module.run_task(main)
    assert sent == ["scan-1"]
