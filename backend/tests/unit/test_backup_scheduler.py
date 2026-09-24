"""backup_scheduler.py: status tracking, retry timing, healthcheck and metrics."""

import os
import stat
from pathlib import Path

import pytest

from scripts import backup_scheduler as bs

HOUR = 3600


def _script(tmp_path: Path, body: str) -> list[str]:
    script = tmp_path / "fake-backup.sh"
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return [str(script)]


def test_successful_run_records_archive_and_resets_failures(tmp_path):
    archive = tmp_path / "botball-1.tar.gz.age"
    archive.write_bytes(b"x" * 123)
    previous = bs.BackupStatus(last_run_ok=False, consecutive_failures=2, last_error="boom")
    status = bs.run_backup(
        _script(tmp_path, f'echo "Encrypted backup created: {archive}"\n'), previous
    )
    assert status.last_run_ok is True
    assert status.last_success_at == status.last_run_at
    assert status.last_archive == str(archive)
    assert status.last_size_bytes == 123
    assert status.consecutive_failures == 0
    assert status.last_error is None


def test_failed_run_is_recorded_with_reason(tmp_path):
    ok = bs.BackupStatus(last_run_at=1.0, last_run_ok=True, last_success_at=1.0)
    status = bs.run_backup(
        _script(tmp_path, 'echo "BACKUP FAILED: AGE_RECIPIENT is empty" >&2\nexit 1\n'), ok
    )
    assert status.last_run_ok is False
    assert status.consecutive_failures == 1
    assert "AGE_RECIPIENT is empty" in (status.last_error or "")
    # The last success is kept so staleness keeps counting from it.
    assert status.last_success_at == 1.0


def test_missing_backup_command_counts_as_failure(tmp_path):
    status = bs.run_backup([str(tmp_path / "missing.sh")], None)
    assert status.last_run_ok is False
    assert status.consecutive_failures == 1


def test_failure_is_retried_soon_instead_of_after_a_day():
    now = 100 * HOUR
    failed = bs.BackupStatus(last_run_at=now - 10, last_run_ok=False)
    assert bs.next_delay(failed, now, interval=24 * HOUR, retry=HOUR) == HOUR - 10
    ok = bs.BackupStatus(last_run_at=now - HOUR, last_run_ok=True, last_success_at=now - HOUR)
    assert bs.next_delay(ok, now, interval=24 * HOUR, retry=HOUR) == 23 * HOUR
    assert bs.next_delay(None, now, interval=24 * HOUR, retry=HOUR) == 0


def test_healthcheck():
    now = 100 * HOUR
    assert bs.check_status(None, now, 26) == "no backup has run yet"
    failed = bs.BackupStatus(last_run_at=now, last_run_ok=False, last_error="exit code 1")
    assert "failed" in (bs.check_status(failed, now, 26) or "")
    stale = bs.BackupStatus(
        last_run_at=now - 30 * HOUR, last_run_ok=True, last_success_at=now - 30 * HOUR
    )
    assert "old" in (bs.check_status(stale, now, 26) or "")
    fresh = bs.BackupStatus(last_run_at=now - HOUR, last_run_ok=True, last_success_at=now - HOUR)
    assert bs.check_status(fresh, now, 26) is None


def test_status_file_roundtrip_and_corruption(tmp_path):
    path = tmp_path / "status" / "last-run.json"
    status = bs.BackupStatus(last_run_at=5.0, last_run_ok=True, last_success_at=5.0)
    bs.save_status(path, status)
    assert bs.load_status(path) == status
    path.write_text("{not json")
    assert bs.load_status(path) is None


def test_metrics_render_failure_signal():
    text = bs.render_metrics(
        bs.BackupStatus(last_run_at=10.0, last_run_ok=False, consecutive_failures=3)
    )
    assert "botball_backup_last_run_success 0" in text
    assert "botball_backup_consecutive_failures 3" in text
    assert "botball_backup_status_known 1" in text
    # No success yet: the timestamp series is absent, not 0.
    assert "\nbotball_backup_last_success_timestamp_seconds " not in text
    assert "botball_backup_status_known 0" in bs.render_metrics(None)


def test_check_cli_exit_codes(tmp_path, monkeypatch, capsys):
    path = tmp_path / "last-run.json"
    monkeypatch.setenv("BACKUP_STATUS_FILE", str(path))
    assert bs.main(["x", "check"]) == 1
    assert "UNHEALTHY" in capsys.readouterr().out
    import time

    now = time.time()
    bs.save_status(path, bs.BackupStatus(last_run_at=now, last_run_ok=True, last_success_at=now))
    assert bs.main(["x", "check"]) == 0


def test_once_cli_runs_backup_and_writes_status(tmp_path, monkeypatch):
    path = tmp_path / "last-run.json"
    monkeypatch.setenv("BACKUP_STATUS_FILE", str(path))
    monkeypatch.setenv("BACKUP_SCRIPT", _script(tmp_path, "exit 3\n")[0])
    assert bs.main(["x", "once"]) == 1
    loaded = bs.load_status(path)
    assert loaded is not None and loaded.last_run_ok is False
    assert "exit code 3" in (loaded.last_error or "")


@pytest.mark.skipif(os.name != "posix", reason="POSIX shell required")
def test_backup_sh_fails_loudly_without_age_recipient(tmp_path):
    import subprocess

    script = Path(__file__).resolve().parents[2] / "scripts" / "backup.sh"
    env = {"PATH": os.environ.get("PATH", ""), "BACKUP_DIR": str(tmp_path)}
    result = subprocess.run(["sh", str(script)], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "BACKUP FAILED" in result.stderr
    assert "AGE_RECIPIENT" in result.stderr
    assert not list(tmp_path.glob("botball-*"))
