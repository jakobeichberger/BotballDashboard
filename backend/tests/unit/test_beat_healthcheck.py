"""Beat liveness: the heartbeat written by core.celery_app and its healthcheck."""

import importlib.util
import os
import time
from pathlib import Path

from core import celery_app

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "beat_healthcheck.py"
_spec = importlib.util.spec_from_file_location("beat_healthcheck", _SCRIPT)
assert _spec and _spec.loader
beat_healthcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(beat_healthcheck)


def test_only_the_beat_process_writes_the_heartbeat(tmp_path, monkeypatch):
    heartbeat = tmp_path / "celerybeat-heartbeat"
    monkeypatch.setattr(celery_app, "BEAT_HEARTBEAT_FILE", heartbeat)
    monkeypatch.setattr(celery_app, "_beat_running", False)

    # The API publishing a task (e.g. OCR) is no sign of life of beat.
    celery_app._beat_heartbeat(sender="score_sheets.extract_template")
    assert not heartbeat.exists()

    celery_app._mark_beat_process(sender=None)
    celery_app._beat_heartbeat(sender="notifications.deliver_outbox")
    assert heartbeat.exists()


def test_missing_heartbeat_is_unhealthy(tmp_path, capsys):
    assert beat_healthcheck.main(["check", str(tmp_path / "celerybeat-heartbeat")]) == 1
    assert "no heartbeat file" in capsys.readouterr().out


def test_fresh_heartbeat_is_healthy(tmp_path):
    heartbeat = tmp_path / "celerybeat-heartbeat"
    heartbeat.touch()
    assert beat_healthcheck.main(["check", str(heartbeat)]) == 0


def test_stale_heartbeat_is_unhealthy(tmp_path, capsys):
    heartbeat = tmp_path / "celerybeat-heartbeat"
    heartbeat.touch()
    old = time.time() - beat_healthcheck.MAX_AGE_SECONDS - 60
    os.utime(heartbeat, (old, old))
    assert beat_healthcheck.main(["check", str(heartbeat)]) == 1
    assert "has not sent a task" in capsys.readouterr().out
