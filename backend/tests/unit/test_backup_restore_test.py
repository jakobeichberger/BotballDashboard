"""Automated restore test and derived backup age limit (review 2026-09, #10).

- ``BackupStale`` was fixed at 26 h; the limit now follows
  ``BACKUP_INTERVAL_SECONDS`` (exported as ``botball_backup_max_age_seconds``).
- The restore test ran only by hand. The scheduler now runs it every
  ``BACKUP_RESTORE_TEST_INTERVAL_SECONDS`` with a server-side test key and
  exports its result and age; manual runs are recorded the same way.
- ``once --verify`` (used by scripts/update.sh before migrations) restores
  the fresh archive before it reports success.
"""

import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

from scripts import backup_scheduler as bs

HOUR = 3600
DAY = 24 * HOUR
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _script(path: Path, body: str) -> str:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def _backup_script(tmp_path: Path) -> str:
    """Fake backup.sh: writes an archive and records the extra recipients it got."""
    archive = tmp_path / "botball-20260926T000000Z.tar.gz.age"
    return _script(
        tmp_path / "backup.sh",
        f'echo "$BACKUP_EXTRA_RECIPIENTS" > {tmp_path}/recipients\n'
        f"echo data > {archive}\n"
        f'echo "Encrypted backup created: {archive}"\n',
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in list(os.environ):
        if name.startswith("BACKUP_") or name in ("AGE_IDENTITY",):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("BACKUP_STATUS_FILE", str(tmp_path / "status" / "last-run.json"))
    monkeypatch.setenv("BACKUP_SCRIPT", _backup_script(tmp_path))
    monkeypatch.setenv("BACKUP_RESTORE_TEST_IDENTITY", str(tmp_path / "key" / "identity.txt"))
    return tmp_path


# ── Backup age limit ─────────────────────────────────────────────────────────


def test_max_age_follows_the_backup_interval(env, monkeypatch):
    assert bs.max_age_hours() == 26  # daily backups: 24 h + 2 h slack
    monkeypatch.setenv("BACKUP_INTERVAL_SECONDS", str(3 * DAY))
    assert bs.max_age_hours() == 74
    monkeypatch.setenv("BACKUP_INTERVAL_SECONDS", str(HOUR))
    assert bs.max_age_hours() == 3
    # An explicit limit wins.
    monkeypatch.setenv("BACKUP_MAX_AGE_HOURS", "30")
    assert bs.max_age_hours() == 30


def test_healthcheck_uses_the_derived_limit(env, monkeypatch, capsys):
    monkeypatch.setenv("BACKUP_INTERVAL_SECONDS", str(3 * DAY))
    now = time.time()
    status = bs.BackupStatus(last_run_at=now - 2 * DAY, last_run_ok=True)
    status.last_success_at = now - 2 * DAY
    bs.save_status(bs.status_path(), status)
    # 48 h old: stale for a daily schedule, fine for a three-day one.
    assert bs.main(["x", "check"]) == 0
    assert "OK" in capsys.readouterr().out


def test_metrics_export_the_age_limit(env, monkeypatch):
    monkeypatch.setenv("BACKUP_INTERVAL_SECONDS", str(2 * DAY))
    text = bs.render_metrics(bs.BackupStatus())
    assert f"botball_backup_max_age_seconds {50 * HOUR}" in text


# ── Restore test ─────────────────────────────────────────────────────────────


@pytest.mark.skipif(not shutil.which("age-keygen"), reason="age-keygen not installed")
def test_restore_test_key_is_created_once_and_private(env):
    identity = Path(os.environ["BACKUP_RESTORE_TEST_IDENTITY"])
    recipient = bs.ensure_restore_test_key(identity)
    assert recipient and recipient.startswith("age1")
    assert stat.S_IMODE(identity.stat().st_mode) == 0o600
    assert stat.S_IMODE(identity.parent.stat().st_mode) == 0o700
    assert bs.ensure_restore_test_key(identity) == recipient  # not regenerated


def test_backups_are_also_encrypted_to_the_test_key(env, monkeypatch):
    monkeypatch.setattr(bs, "ensure_restore_test_key", lambda path: "age1testrecipient")
    status = bs.run_once(bs.status_path())
    assert status.last_run_ok is True
    assert (env / "recipients").read_text().strip() == "age1testrecipient"


def test_without_automatic_test_no_extra_recipient(env, monkeypatch):
    monkeypatch.setenv("BACKUP_RESTORE_TEST_INTERVAL_SECONDS", "0")
    monkeypatch.setattr(
        bs, "ensure_restore_test_key", lambda path: pytest.fail("no key when disabled")
    )
    bs.run_once(bs.status_path())
    assert (env / "recipients").read_text().strip() == ""


def test_restore_test_result_is_recorded(env, monkeypatch):
    archive = env / "a.tar.gz.age"
    archive.write_text("x")
    monkeypatch.setenv("BACKUP_RESTORE_TEST_SCRIPT", _script(env / "rt-ok.sh", "exit 0\n"))
    status = bs.run_restore_test(str(archive), identity="/key", automatic=True)
    assert status.last_ok is True
    assert status.last_success_at == status.last_run_at
    assert status.last_archive == str(archive)
    assert status.automatic is True

    monkeypatch.setenv(
        "BACKUP_RESTORE_TEST_SCRIPT",
        _script(env / "rt-bad.sh", 'echo "ERROR: relation events does not exist" >&2\nexit 3\n'),
    )
    failed = bs.run_restore_test(str(archive), identity="/key", automatic=True)
    assert failed.last_ok is False
    assert "relation events does not exist" in (failed.last_error or "")
    assert failed.consecutive_failures == 1
    # The earlier success is kept, so the age alert keeps counting from it.
    assert failed.last_success_at == status.last_success_at
    assert bs.load_restore_status(bs.restore_status_path()) == failed


def test_restore_test_is_due_weekly_and_retried_after_a_failure():
    now = 100 * DAY
    week = 7 * DAY
    assert bs.restore_test_due(None, now, week, HOUR)
    ok = bs.RestoreTestStatus(last_run_at=now - DAY, last_ok=True, last_success_at=now - DAY)
    assert not bs.restore_test_due(ok, now, week, HOUR)
    ok_old = bs.RestoreTestStatus(last_run_at=now - 8 * DAY, last_ok=True)
    ok_old.last_success_at = now - 8 * DAY
    assert bs.restore_test_due(ok_old, now, week, HOUR)
    failed = bs.RestoreTestStatus(last_run_at=now - 2 * HOUR, last_ok=False)
    assert bs.restore_test_due(failed, now, week, HOUR)
    failed_recent = bs.RestoreTestStatus(last_run_at=now - 60, last_ok=False)
    assert not bs.restore_test_due(failed_recent, now, week, HOUR)
    assert not bs.restore_test_due(None, now, 0, HOUR)  # disabled


def test_scheduled_backup_runs_the_due_restore_test(env, monkeypatch):
    monkeypatch.setattr(bs, "ensure_restore_test_key", lambda path: "age1testrecipient")
    ran: list = []
    monkeypatch.setattr(
        bs,
        "run_restore_test",
        lambda archive, identity, automatic: (
            ran.append((archive, identity, automatic)) or bs.RestoreTestStatus(last_ok=True)
        ),
    )
    bs.run_once(bs.status_path(), scheduled=True)
    [(archive, identity, automatic)] = ran
    assert archive.endswith(".tar.gz.age")
    assert identity == os.environ["BACKUP_RESTORE_TEST_IDENTITY"]
    assert automatic is True
    # Not due again right after a success.
    bs.save_restore_status(
        bs.restore_status_path(),
        bs.RestoreTestStatus(last_run_at=time.time(), last_ok=True, last_success_at=time.time()),
    )
    bs.run_once(bs.status_path(), scheduled=True)
    assert len(ran) == 1


def test_once_verify_fails_when_the_restore_test_fails(env, monkeypatch):
    monkeypatch.setattr(bs, "ensure_restore_test_key", lambda path: "age1testrecipient")
    Path(os.environ["BACKUP_RESTORE_TEST_IDENTITY"]).parent.mkdir(parents=True)
    Path(os.environ["BACKUP_RESTORE_TEST_IDENTITY"]).write_text("AGE-SECRET-KEY-1")
    monkeypatch.setenv("BACKUP_RESTORE_TEST_SCRIPT", _script(env / "rt.sh", "exit 1\n"))
    assert bs.main(["x", "once", "--verify"]) == 1
    monkeypatch.setenv("BACKUP_RESTORE_TEST_SCRIPT", _script(env / "rt2.sh", "exit 0\n"))
    assert bs.main(["x", "once", "--verify"]) == 0
    assert bs.load_restore_status(bs.restore_status_path()).last_ok is True


def test_once_verify_without_test_key_checks_the_archive_checksum(env, monkeypatch):
    monkeypatch.setenv("BACKUP_RESTORE_TEST_INTERVAL_SECONDS", "0")
    script = env / "backup-sum.sh"
    archive = env / "botball-x.tar.gz.age"
    _script(
        script,
        f"echo data > {archive}\n"
        f"(cd {env} && sha256sum botball-x.tar.gz.age > botball-x.tar.gz.age.sha256)\n"
        f'echo "Encrypted backup created: {archive}"\n',
    )
    monkeypatch.setenv("BACKUP_SCRIPT", str(script))
    assert bs.main(["x", "once", "--verify"]) == 0
    # A corrupted archive fails the verification.
    _script(
        script,
        f"echo data > {archive}\n"
        f"(cd {env} && sha256sum botball-x.tar.gz.age > botball-x.tar.gz.age.sha256)\n"
        f"echo tampered >> {archive}\n"
        f'echo "Encrypted backup created: {archive}"\n',
    )
    assert bs.main(["x", "once", "--verify"]) == 1


def test_manual_restore_test_cli_records_the_result(env, monkeypatch):
    archive = env / "a.tar.gz.age"
    archive.write_text("x")
    monkeypatch.setenv("AGE_IDENTITY", "/restore-work/age-identity")
    seen = env / "seen"
    monkeypatch.setenv(
        "BACKUP_RESTORE_TEST_SCRIPT", _script(env / "rt.sh", f'echo "$AGE_IDENTITY $1" > {seen}\n')
    )
    assert bs.main(["x", "restore-test", str(archive)]) == 0
    assert seen.read_text().split() == ["/restore-work/age-identity", str(archive)]
    status = bs.load_restore_status(bs.restore_status_path())
    assert status.last_ok is True and status.automatic is False


def test_restore_test_metrics(env, monkeypatch):
    now = time.time()
    monkeypatch.setenv("BACKUP_RESTORE_TEST_INTERVAL_SECONDS", str(7 * DAY))
    status = bs.RestoreTestStatus(
        last_run_at=now, last_ok=False, last_success_at=now - DAY, consecutive_failures=2
    )
    text = bs.render_restore_metrics(status)
    assert "botball_restore_test_enabled 1" in text
    assert "botball_restore_test_last_success 0" in text
    assert f"botball_restore_test_last_success_timestamp_seconds {now - DAY}" in text
    # Two missed weekly runs plus a day of slack.
    assert f"botball_restore_test_max_age_seconds {15 * DAY}" in text
    # Manual only: the monthly routine, 35 days.
    monkeypatch.setenv("BACKUP_RESTORE_TEST_INTERVAL_SECONDS", "0")
    text = bs.render_restore_metrics(None, tracking_since=now)
    assert "botball_restore_test_enabled 0" in text
    assert f"botball_restore_test_max_age_seconds {35 * DAY}" in text
    # Never succeeded: the age counts from when tracking started.
    assert f"botball_restore_test_last_success_timestamp_seconds {now}" in text
    samples = [line.split()[0] for line in text.splitlines() if not line.startswith("#")]
    assert "botball_restore_test_last_success" not in samples


def test_restore_test_sh_can_drop_its_database(tmp_path):
    text = (SCRIPTS / "restore-test.sh").read_text()
    assert "RESTORE_TEST_DROP_DB" in text
    result = subprocess.run(["sh", "-n", str(SCRIPTS / "restore-test.sh")], capture_output=True)
    assert result.returncode == 0, result.stderr
