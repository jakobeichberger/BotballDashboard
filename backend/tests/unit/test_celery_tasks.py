"""The Celery task entry points, called directly.

Each task hands its coroutine to ``core.celery_app.run_task`` (a fresh event
loop) and opens its own session from ``WorkerSessionLocal``. The tests hand the
task the test session instead and run the coroutine on the test's event loop,
so the task bodies (and what they write) are checked without a broker, a
worker or a second database.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from modules.dashboard import tasks as dashboard_tasks
from modules.paper_review import tasks as paper_tasks
from modules.printing import tasks as printing_tasks
from modules.printing.adapters import PrinterStatus
from modules.printing.models import Printer
from modules.scoring.score_sheets import tasks as sheet_tasks
from modules.scoring.score_sheets.models import ScoreSheetScan, ScoreSheetTemplate


class _SessionContext:
    """Stands in for ``WorkerSessionLocal()``: yields the test session, never closes it."""

    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def run_task(db, monkeypatch):
    """Call a task function and await the coroutine it would have passed to run_task."""

    async def run(module, task, *args):
        captured: list = []
        monkeypatch.setattr(module, "run_task", captured.append)
        monkeypatch.setattr(module, "WorkerSessionLocal", lambda: _SessionContext(db))
        task(*args)
        assert len(captured) == 1, "the task must hand exactly one coroutine to run_task"
        await captured[0]()

    return run


# ── Printing ──────────────────────────────────────────────────────────────────


async def _printer(db, name, **fields) -> Printer:
    printer = Printer(
        name=name,
        printer_type=fields.pop("printer_type", "octoprint"),
        api_url=fields.pop("api_url", "http://printer.local"),
        api_key_encrypted=fields.pop("api_key_encrypted", "cipher"),
        **fields,
    )
    db.add(printer)
    await db.flush()
    return printer


async def test_poll_printers_stores_status_and_marks_failures_offline(db, run_task, monkeypatch):
    online = await _printer(db, "Online", api_key_encrypted="cipher-online")
    broken = await _printer(
        db, "Broken", api_key_encrypted="cipher-broken", is_online=True, current_state="idle"
    )
    generic = await _printer(db, "Manual", printer_type="generic")
    no_key = await _printer(db, "No key", api_key_encrypted=None)
    await db.commit()

    polled: list[str] = []

    def fake_poll(printer_type, api_url, api_key, device_id):
        polled.append(api_key)
        if api_key == "key-broken":
            raise ConnectionError("printer unreachable")
        return PrinterStatus(online=True, state="idle", message="Ready")

    monkeypatch.setattr(printing_tasks, "poll_printer", fake_poll)
    monkeypatch.setattr(
        printing_tasks, "decrypt_credential", lambda value: value.replace("cipher", "key")
    )

    await run_task(printing_tasks, printing_tasks.poll_printers)

    assert sorted(polled) == ["key-broken", "key-online"]  # generic and keyless skipped
    await db.refresh(online)
    await db.refresh(broken)
    assert online.is_online and online.current_state == "idle"
    assert online.status_message == "Ready"
    assert not broken.is_online and broken.current_state == "offline"
    for skipped in (generic, no_key):
        await db.refresh(skipped)
        assert not skipped.is_online


# ── Score sheets ──────────────────────────────────────────────────────────────


async def _template(db, season, admin_user, tmp_path) -> ScoreSheetTemplate:
    pdf = tmp_path / "sheet.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    template = ScoreSheetTemplate(
        season_id=season.id,
        label="Sheet",
        year=2026,
        file_url=str(pdf),
        file_name="sheet.pdf",
        file_size_bytes=pdf.stat().st_size,
        uploaded_by=admin_user.id,
    )
    db.add(template)
    await db.commit()
    return template


async def test_extract_template_runs_the_ocr_pipeline(
    db, run_task, monkeypatch, season, admin_user, tmp_path
):
    template = await _template(db, season, admin_user, tmp_path)
    monkeypatch.setattr(
        "modules.scoring.score_sheets.service.extract_text_from_pdf",
        lambda path: "Area 1\nSorted Poms ×5\nBotguy ×15\n",
    )

    await run_task(sheet_tasks, sheet_tasks.extract_template, template.id)

    await db.refresh(template)
    assert template.ocr_status == "done"
    assert template.raw_text.startswith("Area 1")
    assert template.extracted_fields


async def test_extract_template_records_a_failure(
    db, run_task, monkeypatch, season, admin_user, tmp_path
):
    template = await _template(db, season, admin_user, tmp_path)

    def broken(path):
        raise RuntimeError("pdftotext crashed")

    monkeypatch.setattr("modules.scoring.score_sheets.service.extract_text_from_pdf", broken)

    await run_task(sheet_tasks, sheet_tasks.extract_template, template.id)

    await db.refresh(template)
    assert template.ocr_status == "failed"
    assert "pdftotext crashed" in template.ocr_error


async def _scan(db, event, team, template, admin_user, tmp_path) -> ScoreSheetScan:
    image = tmp_path / "scan.png"
    image.write_bytes(b"not really a png")
    scan = ScoreSheetScan(
        event_id=event.id,
        template_id=template.id,
        team_id=team.id,
        file_url=str(image),
        file_name="scan.png",
        status="queued",
        created_by=admin_user.id,
    )
    db.add(scan)
    await db.commit()
    return scan


async def test_process_scan_moves_the_scan_to_review(
    db, run_task, monkeypatch, season, event, team, admin_user, tmp_path
):
    template = await _template(db, season, admin_user, tmp_path)
    scan = await _scan(db, event, team, template, admin_user, tmp_path)
    values = [{"key": "cubes", "value": 3, "confidence": 0.9}]
    monkeypatch.setattr(sheet_tasks, "run_local_ocr", lambda scan, template: values)

    await run_task(sheet_tasks, sheet_tasks.process_scan, scan.id)

    await db.refresh(scan)
    assert scan.status == "review"
    assert scan.extracted_values == values
    assert scan.processed_at is not None and scan.error is None


async def test_process_scan_failure_is_shown_on_the_scan(
    db, run_task, monkeypatch, season, event, team, admin_user, tmp_path
):
    template = await _template(db, season, admin_user, tmp_path)
    scan = await _scan(db, event, team, template, admin_user, tmp_path)

    def unreadable(scan, template):
        raise RuntimeError("Uploaded score sheet is not a readable image")

    monkeypatch.setattr(sheet_tasks, "run_local_ocr", unreadable)

    await run_task(sheet_tasks, sheet_tasks.process_scan, scan.id)

    await db.refresh(scan)
    assert scan.status == "failed"
    assert "not a readable image" in scan.error


async def test_process_scan_ignores_unknown_ids(db, run_task):
    await run_task(sheet_tasks, sheet_tasks.process_scan, "does-not-exist")
    assert (await db.execute(select(ScoreSheetScan))).scalars().all() == []


# ── Paper review ──────────────────────────────────────────────────────────────


async def test_process_review_deadlines_marks_overdue_and_reminds(
    db, run_task, monkeypatch, season, team, admin_user
):
    from modules.paper_review.models import Paper, ReviewerAssignment

    paper = Paper(season_id=season.id, team_id=team.id, title="Paper")
    db.add(paper)
    await db.flush()
    now = datetime.now(UTC)
    overdue = ReviewerAssignment(
        paper_id=paper.id, reviewer_id=admin_user.id, due_at=now - timedelta(hours=2)
    )
    db.add(overdue)
    await db.commit()

    reminded: list[str] = []

    async def fake_mark(db, paper_id, assignment_id):
        reminded.append(assignment_id)

    monkeypatch.setattr(paper_tasks, "mark_reminder_sent", fake_mark)

    await run_task(paper_tasks, paper_tasks.process_review_deadlines)

    await db.refresh(overdue)
    assert overdue.status == "overdue"
    assert reminded == [overdue.id]


async def test_paper_deadline_reminders_queue_and_commit(db, run_task, monkeypatch):
    calls: list = []

    async def fake_queue(session):
        calls.append(session)
        return 2

    monkeypatch.setattr("modules.paper_review.deadlines.queue_paper_deadline_reminders", fake_queue)
    await run_task(paper_tasks, paper_tasks.paper_deadline_reminders)
    assert calls == [db]


# ── Notifications ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "task_name, target",
    [
        ("match_reminders", "modules.events.notifications.queue_match_reminders"),
        ("deadline_reminders", "modules.events.notifications.queue_deadline_reminders"),
        ("deliver_outbox", "modules.dashboard.tasks.deliver_pending"),
    ],
)
async def test_notification_tasks_call_their_service(db, run_task, monkeypatch, task_name, target):
    calls: list = []

    async def fake(session):
        calls.append(session)
        return 1

    monkeypatch.setattr(target, fake)
    await run_task(dashboard_tasks, getattr(dashboard_tasks, task_name))
    assert calls == [db]
