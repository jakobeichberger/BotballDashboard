"""Structured logging, the access log and the readiness probe."""

import io
import json
import logging
import types

import pytest
import structlog
from httpx import ASGITransport, AsyncClient

import main
from core import logging as app_logging

# ── configure_logging ─────────────────────────────────────────────────────────


@pytest.fixture
def production_logging(monkeypatch):
    """Configure logging as in production (JSON, INFO) and restore it afterwards."""
    stream = io.StringIO()
    monkeypatch.setattr(app_logging.sys, "stdout", stream)
    monkeypatch.setattr(
        app_logging, "get_settings", lambda: types.SimpleNamespace(log_level="", is_dev=False)
    )
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    app_logging.configure_logging()
    try:
        yield stream
    finally:
        monkeypatch.undo()
        root.handlers[:], level = saved
        root.setLevel(level)
        app_logging.configure_logging()
        structlog.contextvars.clear_contextvars()


def _lines(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_stdlib_and_structlog_records_share_the_json_format(production_logging):
    structlog.contextvars.bind_contextvars(request_id="req-1")
    logging.getLogger("third.party").warning("disk %s", "almost full")
    structlog.get_logger("app.module").error("thing_happened", count=3)
    logging.getLogger("third.party").debug("below the level")

    stdlib, own = _lines(production_logging)
    assert stdlib["event"] == "disk almost full"
    assert stdlib["level"] == "warning"
    assert stdlib["logger"] == "third.party"
    assert stdlib["request_id"] == "req-1"
    assert "timestamp" in stdlib
    assert own["event"] == "thing_happened"
    assert own["level"] == "error"
    assert own["count"] == 3
    assert own["logger"] == "app.module"
    assert own["request_id"] == "req-1"


def test_exceptions_are_rendered_into_the_json_line(production_logging):
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logging.getLogger("worker").exception("task_failed")
    [line] = _lines(production_logging)
    assert line["event"] == "task_failed"
    assert "RuntimeError: boom" in line["exception"]


@pytest.mark.parametrize(
    "configured, is_dev, expected",
    [
        ("", True, logging.DEBUG),
        ("", False, logging.INFO),
        ("warning", True, logging.WARNING),
        ("nonsense", False, logging.INFO),
    ],
)
def test_log_level_setting(monkeypatch, configured, is_dev, expected):
    monkeypatch.setattr(
        app_logging,
        "get_settings",
        lambda: types.SimpleNamespace(log_level=configured, is_dev=is_dev),
    )
    assert app_logging._log_level() == expected


# ── Access log ────────────────────────────────────────────────────────────────


class _Recorder:
    def __init__(self):
        self.entries: list[tuple[str, str, dict, dict]] = []

    def _record(self, level):
        def log(event, **fields):
            context = structlog.contextvars.get_contextvars()
            self.entries.append((level, event, fields, context))

        return log

    def __getattr__(self, level):
        return self._record(level)


@pytest.fixture
async def access_log(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(app_logging, "_access_logger", recorder)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as ac:
        yield recorder, ac


async def test_access_log_carries_the_request_id(access_log):
    recorder, client = access_log
    response = await client.get("/api/does-not-exist", headers={"X-Request-ID": "abc-123"})
    assert response.status_code == 404

    [(level, event, fields, context)] = recorder.entries
    assert (level, event) == ("info", "request")
    assert fields["method"] == "GET"
    assert fields["path"] == "/api/does-not-exist"
    assert fields["status"] == 404
    assert fields["duration_ms"] >= 0
    # Bound for everything logged while the request runs, and the same id the
    # client gets back.
    assert context["request_id"] == "abc-123"
    assert response.headers["X-Request-ID"] == "abc-123"


async def test_probe_requests_are_logged_at_debug(access_log):
    recorder, client = access_log
    assert (await client.get("/api/system/health")).status_code == 200
    [(level, _, fields, context)] = recorder.entries
    assert level == "debug"
    assert fields["path"] == "/api/system/health"
    # Without a client-supplied id the middleware generates one.
    assert len(context["request_id"]) == 36


# ── IntegrityError handler ────────────────────────────────────────────────────


async def test_integrity_errors_are_logged_but_not_leaked(monkeypatch):
    from sqlalchemy.exc import IntegrityError

    logged: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        main,
        "logger",
        types.SimpleNamespace(warning=lambda event, **fields: logged.append((event, fields))),
    )
    request = types.SimpleNamespace(
        state=types.SimpleNamespace(request_id="rid-9"),
        url=types.SimpleNamespace(path="/api/teams"),
        headers={},
    )
    exc = IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: teams.name"))

    response = await main.integrity_error_handler(request, exc)

    body = json.loads(response.body)
    assert response.status_code == 409
    assert "teams.name" not in body["message"]
    [(event, fields)] = logged
    assert event == "integrity_error"
    assert fields["request_id"] == "rid-9"
    assert fields["path"] == "/api/teams"
    assert "teams.name" in fields["error"]


# ── Readiness ─────────────────────────────────────────────────────────────────


class _Engine:
    def __init__(self, ok: bool):
        self.ok = ok

    def connect(self):
        engine = self

        class _Connection:
            async def __aenter__(self):
                if not engine.ok:
                    raise OSError("connection refused")
                return self

            async def __aexit__(self, *exc):
                return False

            async def execute(self, statement):
                return None

        return _Connection()


class _Redis:
    ok = True

    @classmethod
    def from_url(cls, url):
        return cls()

    async def ping(self):
        if not self.ok:
            raise ConnectionError("redis down")
        return True

    async def aclose(self):
        return None


@pytest.fixture
def probe(monkeypatch):
    import redis.asyncio

    import core.celery_app
    import core.database

    state = {"db": True, "redis": True, "workers": [{"worker@host": {"ok": "pong"}}], "pings": 0}

    def ping(timeout, limit):
        state["pings"] += 1
        assert limit == 1  # answer as soon as one worker replied
        return state["workers"]

    monkeypatch.setattr(core.database, "engine", _Engine(True))
    monkeypatch.setattr(redis.asyncio, "Redis", _Redis)
    monkeypatch.setattr(
        core.celery_app,
        "celery_app",
        types.SimpleNamespace(control=types.SimpleNamespace(ping=ping)),
    )
    monkeypatch.setattr(main, "_worker_check", None)

    def apply():
        monkeypatch.setattr(core.database, "engine", _Engine(state["db"]))
        _Redis.ok = state["redis"]

    state["apply"] = apply
    yield state
    _Redis.ok = True


async def _readiness():
    response = await main.readiness()
    return response.status_code, json.loads(response.body)


async def test_readiness_all_checks_pass(probe):
    status, body = await _readiness()
    assert status == 200
    assert body == {
        "status": "ready",
        "checks": {"postgresql": True, "redis": True, "worker": True},
    }


async def test_readiness_reports_each_failed_dependency(probe):
    probe["db"] = False
    probe["redis"] = False
    probe["workers"] = []
    probe["apply"]()
    status, body = await _readiness()
    assert status == 503
    assert body["checks"] == {"postgresql": False, "redis": False, "worker": False}


async def test_worker_ping_is_cached(probe, monkeypatch):
    await _readiness()
    await _readiness()
    assert probe["pings"] == 1
    # After the TTL the broker is asked again.
    monkeypatch.setattr(main, "_WORKER_CHECK_TTL", 0.0)
    await _readiness()
    assert probe["pings"] == 2
