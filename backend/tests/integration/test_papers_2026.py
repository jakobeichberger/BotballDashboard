"""Call for Papers 2026: page limit, notification of acceptance, on-stage flag."""

import io
from datetime import date

import pytest

from modules.paper_review.deadlines import queue_paper_deadline_reminders
from modules.paper_review.models import PaperDeadline
from modules.teams.models import Team, TeamMember, TeamSeasonRegistration
from tests.paper_helpers import PDF, make_user


def _pdf(pages: int) -> bytes:
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for number in range(pages):
        pdf.drawString(72, 800, f"Page {number + 1}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


async def _paper(client, headers, season, team):
    resp = await client.post(
        "/api/papers",
        headers=headers,
        json={"season_id": season.id, "team_id": team.id, "title": "Warehouse robots"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _upload(client, headers, paper_id, content: bytes):
    return await client.post(
        f"/api/papers/{paper_id}/upload",
        headers=headers,
        files={"file": ("paper.pdf", content, "application/pdf")},
    )


@pytest.mark.asyncio
async def test_papers_above_five_pages_are_refused(client, auth_headers, season, team):
    paper = await _paper(client, auth_headers, season, team)
    too_long = await _upload(client, auth_headers, paper["id"], _pdf(6))
    assert too_long.status_code == 422
    assert "6 pages" in too_long.text and "at most 5" in too_long.text

    ok = await _upload(client, auth_headers, paper["id"], _pdf(5))
    assert ok.status_code == 200, ok.text
    assert ok.json()["versions"][-1]["page_count"] == 5
    # The refused upload left no version behind.
    assert [v["version_number"] for v in ok.json()["versions"]] == [1]


@pytest.mark.asyncio
async def test_unreadable_pdf_is_not_blocked_by_the_page_check(client, auth_headers, season, team):
    paper = await _paper(client, auth_headers, season, team)
    resp = await _upload(client, auth_headers, paper["id"], PDF)
    assert resp.status_code == 200, resp.text
    assert resp.json()["versions"][-1]["page_count"] is None


@pytest.mark.asyncio
async def test_page_limit_can_be_switched_off(client, auth_headers, season, team, monkeypatch):
    from modules.paper_review import service

    monkeypatch.setattr(service.settings, "paper_max_pages", 0)
    paper = await _paper(client, auth_headers, season, team)
    resp = await _upload(client, auth_headers, paper["id"], _pdf(7))
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_presented_on_stage_is_an_organiser_flag(client, auth_headers, season, team):
    paper = await _paper(client, auth_headers, season, team)
    assert paper["presented_on_stage"] is False
    resp = await client.put(
        f"/api/papers/{paper['id']}/score", headers=auth_headers, json={"presented_on_stage": True}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["presented_on_stage"] is True


@pytest.mark.asyncio
async def test_notification_of_acceptance_is_a_date_not_a_deadline(
    client, db, auth_headers, season
):
    body = {
        "season_id": season.id,
        "deadline_type": "official_notification",
        "due_date": "2026-03-29",
    }
    resp = await client.post("/api/papers/deadlines", headers=auth_headers, json=body)
    assert resp.status_code == 201, resp.text
    blocking = {**body, "is_hard_block": True}
    resp = await client.post("/api/papers/deadlines", headers=auth_headers, json=blocking)
    assert resp.status_code == 422

    # A registered team without a paper is not reminded of it.
    team = Team(name="No paper yet", country="AT")
    db.add(team)
    await db.flush()
    user = await make_user(db, "mentor26@test.com", ("papers:read",))
    db.add(TeamMember(team_id=team.id, user_id=user.id, name="M", role="mentor"))
    db.add(TeamSeasonRegistration(team_id=team.id, season_id=season.id))
    await db.commit()
    assert await queue_paper_deadline_reminders(db, date(2026, 3, 28)) == 0
    db.add(
        PaperDeadline(
            season_id=season.id, deadline_type="official_submission", due_date=date(2026, 3, 29)
        )
    )
    await db.commit()
    assert await queue_paper_deadline_reminders(db, date(2026, 3, 28)) == 1
