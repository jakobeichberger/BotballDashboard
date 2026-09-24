"""Backup scheduler for the `backup` compose service.

Runs ``scripts/backup.sh`` periodically, records the outcome in a JSON status
file and exposes it to Prometheus and to the Docker healthcheck:

    python scripts/backup_scheduler.py run     # loop (container command)
    python scripts/backup_scheduler.py check   # healthcheck, exit 1 = unhealthy
    python scripts/backup_scheduler.py once    # single backup, exit code = result

A failed backup is retried after ``BACKUP_RETRY_SECONDS`` instead of waiting a
full interval, the healthcheck turns unhealthy and
``botball_backup_last_run_success`` drops to 0, so a broken backup never goes
unnoticed for a day.

Environment:
    BACKUP_DIR               target directory (default /backups)
    BACKUP_STATUS_FILE       status JSON (default $BACKUP_DIR/status/last-run.json)
    BACKUP_SCRIPT            backup command (default /app/scripts/backup.sh)
    BACKUP_INTERVAL_SECONDS  time between successful backups (default 86400)
    BACKUP_RETRY_SECONDS     time before retrying a failed backup (default 3600)
    BACKUP_MAX_AGE_HOURS     healthcheck: max age of the last success (default 26)
    BACKUP_METRICS_PORT      Prometheus port, 0 disables (default 9101)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ARCHIVE_MARKER = "Encrypted backup created: "


@dataclass
class BackupStatus:
    last_run_at: float | None = None
    last_run_ok: bool | None = None
    last_success_at: float | None = None
    last_duration_seconds: float | None = None
    last_archive: str | None = None
    last_size_bytes: int | None = None
    last_error: str | None = None
    consecutive_failures: int = 0


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def status_path() -> Path:
    explicit = os.environ.get("BACKUP_STATUS_FILE")
    if explicit:
        return Path(explicit)
    return Path(os.environ.get("BACKUP_DIR", "/backups")) / "status" / "last-run.json"


def load_status(path: Path) -> BackupStatus | None:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        # A corrupt status file must not crash the scheduler; the next run
        # overwrites it.
        return None
    known = BackupStatus.__dataclass_fields__
    return BackupStatus(**{key: value for key, value in data.items() if key in known})


def save_status(path: Path, status: BackupStatus) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(status), indent=2))
    tmp.replace(path)


def run_backup(command: list[str], previous: BackupStatus | None) -> BackupStatus:
    """Run the backup command once and return the updated status."""
    status = BackupStatus(**asdict(previous)) if previous else BackupStatus()
    started = time.time()
    archive: str | None = None
    tail: list[str] = []
    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            tail = (tail + [line.rstrip()])[-5:]
            if line.startswith(ARCHIVE_MARKER):
                archive = line[len(ARCHIVE_MARKER) :].strip()
        returncode = proc.wait()
    except OSError as exc:
        returncode = 127
        tail = [f"cannot execute {command[0]}: {exc}"]

    status.last_run_at = started
    status.last_duration_seconds = round(time.time() - started, 3)
    if returncode == 0:
        status.last_run_ok = True
        status.last_success_at = started
        status.last_archive = archive
        status.last_size_bytes = _file_size(archive)
        status.last_error = None
        status.consecutive_failures = 0
    else:
        status.last_run_ok = False
        status.last_error = f"exit code {returncode}: " + " | ".join(tail)
        status.consecutive_failures += 1
    return status


def _file_size(path: str | None) -> int | None:
    if not path:
        return None
    try:
        return Path(path).stat().st_size
    except OSError:
        return None


def next_delay(status: BackupStatus | None, now: float, interval: int, retry: int) -> float:
    """Seconds until the next backup should start."""
    if status is None or status.last_run_at is None:
        return 0
    if status.last_run_ok is False:
        return max(0.0, status.last_run_at + retry - now)
    reference = status.last_success_at or status.last_run_at
    return max(0.0, reference + interval - now)


def check_status(status: BackupStatus | None, now: float, max_age_hours: float) -> str | None:
    """Return a problem description, or None when the backup is healthy."""
    if status is None or status.last_run_at is None:
        return "no backup has run yet"
    if status.last_run_ok is False:
        return f"last backup failed ({status.last_error or 'unknown error'})"
    if status.last_success_at is None:
        return "no successful backup recorded"
    age_hours = (now - status.last_success_at) / 3600
    if age_hours > max_age_hours:
        return f"last successful backup is {age_hours:.1f}h old (limit {max_age_hours}h)"
    return None


def render_metrics(status: BackupStatus | None) -> str:
    def gauge(name: str, help_text: str, value: float | int | None) -> list[str]:
        lines = [f"# HELP {name} {help_text}", f"# TYPE {name} gauge"]
        if value is not None:
            lines.append(f"{name} {value}")
        return lines

    status = status or BackupStatus()
    lines: list[str] = []
    lines += gauge(
        "botball_backup_status_known",
        "1 when a backup status file exists.",
        0 if status.last_run_at is None else 1,
    )
    lines += gauge(
        "botball_backup_last_run_success",
        "1 if the last backup run succeeded, 0 if it failed.",
        None if status.last_run_ok is None else int(status.last_run_ok),
    )
    lines += gauge(
        "botball_backup_last_run_timestamp_seconds",
        "Start time of the last backup run.",
        status.last_run_at,
    )
    lines += gauge(
        "botball_backup_last_success_timestamp_seconds",
        "Start time of the last successful backup.",
        status.last_success_at,
    )
    lines += gauge(
        "botball_backup_last_duration_seconds",
        "Duration of the last backup run.",
        status.last_duration_seconds,
    )
    lines += gauge(
        "botball_backup_last_size_bytes",
        "Size of the last encrypted backup archive.",
        status.last_size_bytes,
    )
    lines += gauge(
        "botball_backup_consecutive_failures",
        "Number of failed backup runs since the last success.",
        status.consecutive_failures,
    )
    return "\n".join(lines) + "\n"


def _serve_metrics(port: int, path: Path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 – http.server API
            if self.path.split("?")[0] != "/metrics":
                self.send_error(404)
                return
            body = render_metrics(load_status(path)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return  # Prometheus scrapes every 15s; keep the log readable.

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


def _log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[backup-scheduler {stamp}] {message}", file=sys.stderr, flush=True)


def _command() -> list[str]:
    return [os.environ.get("BACKUP_SCRIPT", "/app/scripts/backup.sh")]


def run_once(path: Path) -> BackupStatus:
    status = run_backup(_command(), load_status(path))
    save_status(path, status)
    if status.last_run_ok:
        _log(f"backup succeeded: {status.last_archive}")
    else:
        _log(
            f"BACKUP FAILED ({status.consecutive_failures} in a row): {status.last_error}. "
            f"Retrying in {_env_int('BACKUP_RETRY_SECONDS', 3600)}s."
        )
    return status


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "run"
    path = status_path()
    if mode == "check":
        problem = check_status(load_status(path), time.time(), _env_int("BACKUP_MAX_AGE_HOURS", 26))
        if problem:
            print(f"UNHEALTHY: {problem}")
            return 1
        print("OK")
        return 0
    if mode == "once":
        return 0 if run_once(path).last_run_ok else 1
    if mode != "run":
        print(f"usage: {argv[0]} [run|check|once]", file=sys.stderr)
        return 2

    interval = _env_int("BACKUP_INTERVAL_SECONDS", 86400)
    retry = _env_int("BACKUP_RETRY_SECONDS", 3600)
    port = _env_int("BACKUP_METRICS_PORT", 9101)
    if port:
        _serve_metrics(port, path)
        _log(f"metrics on :{port}/metrics")
    announced = None
    while True:
        delay = next_delay(load_status(path), time.time(), interval, retry)
        if delay > 0:
            if announced is None or abs(delay - announced) > 600:
                _log(f"next backup in {int(delay)}s")
            announced = delay
            # Sleep in slices and re-read the status, so a manual run
            # (`backup_scheduler.py once`, e.g. a failure) moves the schedule.
            time.sleep(min(delay, 300))
            announced -= min(delay, 300)
            continue
        announced = None
        run_once(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
