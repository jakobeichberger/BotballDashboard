"""Exports (security review 2026-09, #7 and #15).

User text went unescaped into reportlab markup (500 for an unclosed tag), and
the scouting report put the raw event id into Content-Disposition.
"""

import pytest

from modules.events.models import Event


@pytest.mark.asyncio
async def test_paper_title_markup_does_not_break_the_export(client, db, auth_headers, season, team):
    from modules.paper_review.models import Paper

    db.add(Paper(season_id=season.id, team_id=team.id, title="<b>unclosed <font"))
    await db.commit()
    resp = await client.get(f"/api/exports/seasons/{season.id}/papers.pdf", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_level_name_markup_does_not_break_the_ranking_export(client, auth_headers, season):
    resp = await client.get(
        f"/api/exports/seasons/{season.id}/ranking.pdf",
        headers=auth_headers,
        params={"level_name": "<para><img src='/etc/passwd'/>"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_scouting_report_file_name_is_safe(client, db, auth_headers, season):
    event = Event(id='ev"x;y', season_id=season.id, name="Cup", slug="cup-2026", status="live")
    db.add(event)
    await db.commit()
    resp = await client.get('/api/scoring/events/ev"x;y/scouting/report.pdf', headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-disposition"] == 'attachment; filename="scouting-cup-2026.pdf"'
