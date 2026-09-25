"""Fail-open paths catch the infrastructure errors they expect, not every bug.

Redis, the broker and the audit insert may fail; the request goes on. A
programming error in the same code (a TypeError, a bad key) must still surface
instead of being logged away.
"""

from types import SimpleNamespace

import pytest
from kombu.exceptions import OperationalError as BrokerError
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy.exc import OperationalError

from core import audit, live, rate_limit, task_queue


def _request():
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(testing=False)),
        client=SimpleNamespace(host="203.0.113.7"),
    )


@pytest.mark.asyncio
async def test_rate_limit_fails_open_on_redis_errors_only(monkeypatch):
    check = rate_limit.rate_limit("login", limit=1, window_seconds=60)

    async def unreachable(key, window):
        raise RedisConnectionError("down")

    monkeypatch.setattr(rate_limit, "_count", unreachable)
    assert await check(_request()) is None  # allowed while Redis is down

    async def broken(key, window):
        raise TypeError("bug")

    monkeypatch.setattr(rate_limit, "_count", broken)
    with pytest.raises(TypeError):
        await check(_request())


class _Pipeline:
    def __init__(self, error: Exception):
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def publish(self, channel, message):
        return None

    async def execute(self):
        raise self.error


@pytest.mark.asyncio
async def test_live_publish_reports_redis_errors_and_raises_bugs(monkeypatch):
    error: list[Exception] = [RedisTimeoutError("slow")]
    client = SimpleNamespace(pipeline=lambda transaction: _Pipeline(error[0]))
    monkeypatch.setattr(live, "_publisher", lambda: client)
    assert await live.publish_live_event("e1", "ranking_updated") is False

    error[0] = KeyError("bug")
    with pytest.raises(KeyError):
        await live.publish_live_event("e1", "ranking_updated")


def test_task_enqueue_logs_broker_errors(monkeypatch):
    logged: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        task_queue.logger, "warning", lambda event, **fields: logged.append((event, fields))
    )

    def delay(*args):
        raise BrokerError("broker unreachable")

    task_queue._send(SimpleNamespace(name="demo.task", delay=delay), ("x",))
    assert logged[0][0] == "task_enqueue_failed"
    assert logged[0][1]["task"] == "demo.task"


@pytest.mark.asyncio
async def test_audit_fallback_logs_a_failed_insert(monkeypatch):
    class _Engine:
        def begin(self):
            raise OperationalError("INSERT", {}, Exception("database gone"))

    from core import database

    logged: list[tuple[str, dict]] = []
    monkeypatch.setattr(database, "engine", _Engine())
    monkeypatch.setattr(
        audit.logger, "warning", lambda event, **fields: logged.append((event, fields))
    )
    entry = audit.PendingAudit(
        action="POST /api/teams", user_id=None, resource_id="/api/teams", ip_address=None
    )
    await audit._write_directly(entry)
    assert not entry.written
    assert logged[0][0] == "audit_write_failed"


def test_audit_subject_of_an_invalid_token_is_unknown():
    headers = [(b"authorization", b"Bearer not-a-jwt")]
    assert audit._bearer_subject(headers) is None
