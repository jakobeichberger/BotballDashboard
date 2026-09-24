"""Printer adapters and how polled status moves print jobs along."""

import pytest

from modules.printing.adapters import BambuLanAdapter, OctoPrintAdapter, PrinterStatus
from modules.printing.service import (
    apply_printer_status,
    approve_print_job,
    create_print_job,
    create_printer,
    update_print_job,
)


class TestOctoPrintParse:
    def test_printing(self):
        status = OctoPrintAdapter.parse(
            {"state": "Printing", "progress": {"completion": 41.5, "printTimeLeft": 1200}}
        )
        assert status.state == "printing"
        assert status.progress == 41.5
        assert status.remaining_seconds == 1200
        assert status.error is None

    def test_operational_after_finished_print_is_completed(self):
        status = OctoPrintAdapter.parse(
            {"state": "Operational", "progress": {"completion": 100.0, "printTimeLeft": 0}}
        )
        assert status.state == "completed"

    def test_operational_without_job_is_idle(self):
        status = OctoPrintAdapter.parse({"state": "Operational", "progress": {"completion": None}})
        assert status.state == "idle"

    def test_error_state(self):
        status = OctoPrintAdapter.parse(
            {"state": "Offline after error: Thermal runaway", "progress": {}}
        )
        assert status.state == "failed"
        assert status.online is True
        assert "Thermal runaway" in status.error

    def test_offline(self):
        status = OctoPrintAdapter.parse({"state": "Offline", "progress": {}})
        assert status.online is False


class TestBambuParse:
    def test_running(self):
        status = BambuLanAdapter.parse(
            {"gcode_state": "RUNNING", "mc_percent": 12, "mc_remaining_time": 30}
        )
        assert status.state == "printing"
        assert status.progress == 12.0
        assert status.remaining_seconds == 1800

    def test_finish_and_error(self):
        assert BambuLanAdapter.parse({"gcode_state": "FINISH"}).state == "completed"
        failed = BambuLanAdapter.parse({"gcode_state": "FAILED", "print_error": 50348044})
        assert failed.state == "failed"
        assert failed.error == "Bambu error 0300400C"


def _status(state, progress=None, **extra):
    return PrinterStatus(online=True, state=state, progress=progress, message=state, **extra)


@pytest.fixture
async def printer(db):
    return await create_printer(db, {"name": "P1", "printer_type": "bambu"})


async def _job(db, season, team, admin_user, printer, target="queued"):
    job = await create_print_job(
        db,
        {"team_id": team.id, "season_id": season.id, "file_name": "p.3mf", "material": "PLA"},
        admin_user.id,
    )
    await db.flush()
    await approve_print_job(db, job.id, admin_user.id)
    await update_print_job(db, job.id, status="queued", printer_id=printer.id)
    if target == "printing":
        await update_print_job(db, job.id, status="printing")
    await db.flush()
    return job


class TestApplyPrinterStatus:
    @pytest.mark.asyncio
    async def test_bambu_finish_does_not_complete_freshly_queued_job(
        self, db, season, team, admin_user, printer
    ):
        job = await _job(db, season, team, admin_user, printer)
        # The printer still reports the previous print as finished.
        await apply_printer_status(db, printer, _status("completed", 100.0))
        assert job.status == "queued"
        assert printer.current_state == "completed"

    @pytest.mark.asyncio
    async def test_finish_completes_only_the_printing_job(
        self, db, season, team, admin_user, printer
    ):
        running = await _job(db, season, team, admin_user, printer, "printing")
        waiting = await _job(db, season, team, admin_user, printer)
        await apply_printer_status(db, printer, _status("completed", 100.0))
        assert running.status == "completed"
        assert running.completed_at is not None
        assert waiting.status == "queued"

    @pytest.mark.asyncio
    async def test_queued_job_starts_when_printer_prints(
        self, db, season, team, admin_user, printer
    ):
        job = await _job(db, season, team, admin_user, printer)
        await apply_printer_status(db, printer, _status("printing", 5.0, remaining_seconds=600))
        assert job.status == "printing"
        assert job.started_at is not None
        assert job.progress == 5.0
        assert job.remaining_seconds == 600

    @pytest.mark.asyncio
    async def test_octoprint_idle_after_printing_completes(
        self, db, season, team, admin_user, printer
    ):
        job = await _job(db, season, team, admin_user, printer, "printing")
        await apply_printer_status(db, printer, _status("printing", 99.5))
        await apply_printer_status(db, printer, _status("idle", None))
        assert job.status == "completed"
        assert job.progress == 100.0
        assert job.remaining_seconds == 0

    @pytest.mark.asyncio
    async def test_idle_mid_print_marks_failed(self, db, season, team, admin_user, printer):
        job = await _job(db, season, team, admin_user, printer, "printing")
        await apply_printer_status(db, printer, _status("idle", 40.0))
        assert job.status == "failed"
        assert "stopped" in job.error_message

    @pytest.mark.asyncio
    async def test_failure_stores_error(self, db, season, team, admin_user, printer):
        job = await _job(db, season, team, admin_user, printer, "printing")
        await apply_printer_status(db, printer, _status("failed", 20.0, error="Nozzle clog"))
        assert job.status == "failed"
        assert job.error_message == "Nozzle clog"
        assert printer.status_message == "Nozzle clog"
        # A retry clears the old error.
        await update_print_job(db, job.id, status="queued")
        assert job.error_message is None

    @pytest.mark.asyncio
    async def test_offline_report_leaves_jobs_alone(self, db, season, team, admin_user, printer):
        job = await _job(db, season, team, admin_user, printer, "printing")
        job.progress = 30.0
        await apply_printer_status(db, printer, PrinterStatus(False, "offline", message="timeout"))
        assert printer.is_online is False
        assert job.status == "printing"
        assert job.progress == 30.0

    @pytest.mark.asyncio
    async def test_other_printers_jobs_untouched(self, db, season, team, admin_user, printer):
        other = await create_printer(db, {"name": "P2", "printer_type": "octoprint"})
        job = await _job(db, season, team, admin_user, other, "printing")
        await apply_printer_status(db, printer, _status("completed", 100.0))
        assert job.status == "printing"
