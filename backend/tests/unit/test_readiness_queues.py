"""Readiness per Celery queue and the operational metrics (review 2026-09, #3).

The old check pinged the workers with ``limit=1``: the first reply of *any*
worker made readiness green, so a dead ``worker`` (queues default/periodic:
outbox, push, mail, printer polling) stayed invisible while ``worker-ocr``
answered. Readiness now asks every worker which queues it consumes.
"""

import json
import types

import pytest

import main


class _Engine:
    def connect(self):
        class _Connection:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def execute(self, statement):
                return None

        return _Connection()


class _Redis:
    heartbeat: bytes | None = None
    fail = False

    @classmethod
    def from_url(cls, url):
        return cls()

    async def ping(self):
        return True

    async def get(self, key):
        if self.fail:
            raise ConnectionError("redis down")
        assert key == "botball:beat:heartbeat"
        return self.heartbeat

    async def aclose(self):
        return None


WORKER = {"celery@worker": [{"name": "default"}, {"name": "periodic"}]}
WORKER_OCR = {"celery@worker-ocr": [{"name": "ocr"}]}


@pytest.fixture
def cluster(monkeypatch):
    """Fake broker: ``state["replies"]`` is what the workers answer."""
    import redis.asyncio

    import core.celery_app
    import core.database

    state: dict = {"replies": {**WORKER, **WORKER_OCR}, "broadcasts": 0}

    class _Inspect:
        def __init__(self, timeout):
            state["timeout"] = timeout

        def active_queues(self):
            state["broadcasts"] += 1
            return state["replies"]

        def ping(self):  # pragma: no cover - the old single-reply check
            return state["replies"]

    def ping(timeout=1.0, limit=None):
        # The pre-fix implementation: with limit=1 only the first reply counts.
        state["broadcasts"] += 1
        replies = [{name: {"ok": "pong"}} for name in state["replies"]]
        return replies[:limit] if limit else replies

    monkeypatch.setattr(core.database, "engine", _Engine())
    monkeypatch.setattr(redis.asyncio, "Redis", _Redis)
    monkeypatch.setattr(
        core.celery_app,
        "celery_app",
        types.SimpleNamespace(control=types.SimpleNamespace(ping=ping, inspect=_Inspect)),
    )
    monkeypatch.setattr(main, "_worker_check", None)
    _Redis.heartbeat = None
    _Redis.fail = False
    yield state


async def _readiness():
    response = await main.readiness()
    return response.status_code, json.loads(response.body)


async def test_all_queues_consumed_is_ready(cluster):
    status, body = await _readiness()
    assert status == 200
    assert body["checks"] == {"postgresql": True, "redis": True, "worker": True}
    assert body["queues"] == {"default": True, "periodic": True, "ocr": True}


async def test_dead_default_worker_is_not_hidden_by_the_ocr_worker(cluster):
    """Only worker-ocr answers: outbox, push and printer polling are dead."""
    cluster["replies"] = dict(WORKER_OCR)
    status, body = await _readiness()
    assert status == 503
    assert body["checks"]["worker"] is False
    assert body["queues"] == {"default": False, "periodic": False, "ocr": True}


async def test_dead_ocr_worker_is_reported(cluster):
    cluster["replies"] = dict(WORKER)
    status, body = await _readiness()
    assert status == 503
    assert body["queues"] == {"default": True, "periodic": True, "ocr": False}


async def test_broker_error_marks_every_queue_unconsumed(cluster, monkeypatch):
    import core.celery_app

    class _Broken:
        def __init__(self, timeout):
            pass

        def active_queues(self):
            raise OSError("broker unreachable")

    monkeypatch.setattr(
        core.celery_app,
        "celery_app",
        types.SimpleNamespace(control=types.SimpleNamespace(inspect=_Broken)),
    )
    status, body = await _readiness()
    assert status == 503
    assert set(body["queues"].values()) == {False}


async def test_queue_check_is_cached(cluster, monkeypatch):
    await _readiness()
    await _readiness()
    assert cluster["broadcasts"] == 1
    monkeypatch.setattr(main, "_WORKER_CHECK_TTL", 0.0)
    await _readiness()
    assert cluster["broadcasts"] == 2


async def test_metrics_export_consumers_per_queue_and_beat_heartbeat(cluster):
    cluster["replies"] = {**WORKER, **WORKER_OCR, "celery@worker-2": [{"name": "default"}]}
    _Redis.heartbeat = b"1790000000.5"
    request = types.SimpleNamespace(headers={})
    text = await main.metrics(request)
    assert 'botball_celery_queue_consumers{queue="default"} 2' in text
    assert 'botball_celery_queue_consumers{queue="periodic"} 1' in text
    assert 'botball_celery_queue_consumers{queue="ocr"} 1' in text
    assert "botball_beat_heartbeat_known 1" in text
    assert "botball_beat_last_heartbeat_timestamp_seconds 1790000000.5" in text


async def test_metrics_without_beat_heartbeat(cluster):
    _Redis.fail = True
    text = await main.metrics(types.SimpleNamespace(headers={}))
    assert "botball_beat_heartbeat_known 0" in text
    samples = [line for line in text.splitlines() if not line.startswith("#")]
    assert not [s for s in samples if s.startswith("botball_beat_last_heartbeat")]


def test_beat_writes_its_heartbeat_to_redis(monkeypatch, tmp_path):
    """Beat publishes the heartbeat where the API (another container) can read it."""
    import core.celery_app as celery_module

    written: dict = {}

    class _SyncRedis:
        def set(self, key, value, ex=None):
            written[key] = (value, ex)

    monkeypatch.setattr(celery_module, "BEAT_HEARTBEAT_FILE", tmp_path / "hb")
    monkeypatch.setattr(celery_module, "_beat_running", True)
    monkeypatch.setattr(celery_module, "_heartbeat_redis", lambda: _SyncRedis())
    monkeypatch.setattr(celery_module, "_last_redis_heartbeat", 0.0)
    celery_module._beat_heartbeat()
    assert (tmp_path / "hb").exists()
    value, ttl = written[celery_module.BEAT_HEARTBEAT_KEY]
    assert float(value) > 0
    assert ttl and ttl >= 3600


def test_non_beat_processes_do_not_write_the_heartbeat(monkeypatch, tmp_path):
    import core.celery_app as celery_module

    monkeypatch.setattr(celery_module, "BEAT_HEARTBEAT_FILE", tmp_path / "hb")
    monkeypatch.setattr(celery_module, "_beat_running", False)
    monkeypatch.setattr(
        celery_module, "_heartbeat_redis", lambda: pytest.fail("API/worker wrote a heartbeat")
    )
    celery_module._beat_heartbeat()
    assert not (tmp_path / "hb").exists()
