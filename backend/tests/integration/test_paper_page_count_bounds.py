"""The paper page check runs off the event loop and with bounded work.

pypdf used to flatten the whole page tree on the event loop: a crafted PDF
with ~100,000 empty pages stalled every request for seconds, and a tree
above pypdf's internal limit made the count fail, which let the paper pass
the five-page rule. Now the count runs in a worker thread, stops early,
and a PDF whose pages cannot be counted within the bounds is refused.
"""

import asyncio
import time

import pytest

from modules.paper_review import service

PAGES = 30_000


def _crafted_pdf(pages: int, declared: int | None = None, empty_nodes: int = 0) -> bytes:
    """A flat page tree: ``pages`` empty pages (and ``empty_nodes`` empty /Pages nodes)."""
    parts = [b"%PDF-1.4\n"]
    offsets: dict[int, int] = {}
    position = len(parts[0])

    def add(number: int, body: bytes) -> None:
        nonlocal position
        chunk = b"%d 0 obj\n" % number + body + b"\nendobj\n"
        offsets[number] = position
        parts.append(chunk)
        position += len(chunk)

    total = pages + empty_nodes
    add(1, b"<</Type/Catalog/Pages 2 0 R>>")
    kids = b" ".join(b"%d 0 R" % (i + 3) for i in range(total))
    count = pages if declared is None else declared
    add(2, b"<</Type/Pages/Count %d/Kids[%s]>>" % (count, kids))
    for i in range(total):
        if i < empty_nodes:
            add(i + 3, b"<</Type/Pages/Parent 2 0 R/Count 0/Kids[]>>")
        else:
            add(i + 3, b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>")
    xref_at = position
    size = total + 3
    xref = [b"xref\n0 %d\n" % size, b"0000000000 65535 f \n"]
    xref += [b"%010d 00000 n \n" % offsets[i] for i in range(1, size)]
    parts += xref
    parts.append(b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (size, xref_at))
    return b"".join(parts)


async def _paper(client, headers, season, team) -> str:
    resp = await client.post(
        "/api/papers",
        headers=headers,
        json={"season_id": season.id, "team_id": team.id, "title": "Page bomb"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _upload_measuring_loop(client, headers, paper_id, content: bytes):
    done = False
    max_gap = 0.0

    async def ticker():
        nonlocal max_gap
        last = time.perf_counter()
        while not done:
            await asyncio.sleep(0.005)
            now = time.perf_counter()
            max_gap = max(max_gap, now - last)
            last = now

    async def upload():
        nonlocal done
        try:
            return await client.post(
                f"/api/papers/{paper_id}/upload",
                headers=headers,
                files={"file": ("paper.pdf", content, "application/pdf")},
            )
        finally:
            done = True

    resp, _ = await asyncio.gather(upload(), ticker())
    return resp, max_gap


@pytest.mark.asyncio
async def test_many_page_pdf_is_refused_without_stalling_the_event_loop(
    client, auth_headers, season, team
):
    paper_id = await _paper(client, auth_headers, season, team)
    resp, stall = await _upload_measuring_loop(client, auth_headers, paper_id, _crafted_pdf(PAGES))
    assert resp.status_code == 422, resp.text
    assert "at most 5" in resp.text
    # Before: pypdf flattened all 30,000 pages on the loop (> 1 s stall).
    assert stall < 0.5, f"event loop stalled for {stall:.2f}s"


@pytest.mark.asyncio
async def test_understated_page_count_does_not_hide_the_pages(client, auth_headers, season, team):
    paper_id = await _paper(client, auth_headers, season, team)
    resp = await client.post(
        f"/api/papers/{paper_id}/upload",
        headers=auth_headers,
        files={"file": ("paper.pdf", _crafted_pdf(40, declared=3), "application/pdf")},
    )
    assert resp.status_code == 422, resp.text
    assert "40 pages" in resp.text


def test_count_is_exact_for_normal_papers(tmp_path):
    path = tmp_path / "p.pdf"
    path.write_bytes(_crafted_pdf(4))
    assert service.pdf_page_count(path) == 4


def test_page_tree_beyond_the_work_bound_is_refused(tmp_path):
    # Few real pages hidden among thousands of empty /Pages nodes: counting
    # them all is unbounded work, so the file is refused, not passed.
    path = tmp_path / "p.pdf"
    path.write_bytes(_crafted_pdf(2, empty_nodes=service.PAGE_TREE_MAX_NODES + 10))
    with pytest.raises(service.PageCountError):
        service.pdf_page_count(path)
    with pytest.raises(Exception) as refused:
        service.check_page_limit(path)
    assert "could not be counted" in str(refused.value)
    assert not path.exists()


def test_huge_page_tree_is_reported_as_too_long(tmp_path):
    path = tmp_path / "p.pdf"
    path.write_bytes(_crafted_pdf(service.PAGE_COUNT_CAP + 50))
    with pytest.raises(Exception) as refused:
        service.check_page_limit(path)
    assert f"more than {service.PAGE_COUNT_CAP} pages" in str(refused.value)


@pytest.mark.asyncio
async def test_count_that_takes_too_long_is_refused(
    client, auth_headers, season, team, monkeypatch
):
    def slow(path):
        time.sleep(0.5)
        return 1

    monkeypatch.setattr(service, "pdf_page_count", slow)
    monkeypatch.setattr(service, "PAGE_COUNT_TIMEOUT_SECONDS", 0.1)
    paper_id = await _paper(client, auth_headers, season, team)
    resp = await client.post(
        f"/api/papers/{paper_id}/upload",
        headers=auth_headers,
        files={"file": ("paper.pdf", _crafted_pdf(1), "application/pdf")},
    )
    assert resp.status_code == 422, resp.text
    assert "could not be counted" in resp.text
