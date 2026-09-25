"""Worker configuration, shared Redis usage, live fan-out, audit, printers and PDFs."""

import asyncio
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from starlette.websockets import WebSocketState

import core.live as live
from core import audit, database, rate_limit, redis_client
from core import celery_app as celery_module
from core.audit import AuditLog
from core.database import get_db
from main import app
from modules.printing import tasks as printing_tasks
from modules.printing.adapters import PrinterStatus
from modules.printing.models import Printer

REPO = Path(__file__).resolve().parents[3]

# ── Celery queues and beat ────────────────────────────────────────────────────


def test_ocr_and_periodic_tasks_are_routed_to_their_own_queues():
    conf = celery_module.celery_app.conf
    router = celery_module.celery_app.amqp.router
    assert conf.task_default_queue == "default"

    def queue_of(name: str) -> str:
        route = router.route({}, name)
        return route["queue"].name

    assert queue_of("score_sheets.process_scan") == "ocr"
    assert queue_of("score_sheets.extract_template") == "ocr"
    for name in (
        "printing.poll_printers",
        "notifications.deliver_outbox",
        "notifications.cleanup_outbox",
        "papers.process_review_deadlines",
    ):
        assert queue_of(name) == "periodic", name


def test_every_beat_entry_expires_and_runs_on_the_periodic_queue():
    schedule = celery_module.celery_app.conf.beat_schedule
    assert "cleanup-notification-outbox" in schedule
    for name, entry in schedule.items():
        assert entry["options"]["queue"] == "periodic", name
        assert entry["options"]["expires"] > 0, name


def test_compose_workers_consume_every_queue_and_ocr_separately():
    yaml = pytest.importorskip("yaml")
    services = yaml.safe_load((REPO / "docker-compose.yml").read_text())["services"]

    def queues(service: str) -> set[str]:
        command = services[service]["command"]
        text = command if isinstance(command, str) else " ".join(command)
        return set(text.split("-Q ", 1)[1].split()[0].split(","))

    assert queues("worker") == {"default", "periodic"}
    assert queues("worker-ocr") == {"ocr"}


def test_worker_engine_keeps_no_pool_and_the_api_engine_checks_connections():
    assert isinstance(database.worker_engine.pool, NullPool)
    assert database.engine.pool._pre_ping is True
    assert database.engine.pool._recycle == database.settings.db_pool_recycle_seconds
    assert database.engine.echo is False


def test_run_task_waits_for_after_commit_publishes(monkeypatch):
    sent: list[str] = []

    async def slow_publish(event_id, event, payload=None):
        await asyncio.sleep(0.01)
        sent.append(event)
        return True

    monkeypatch.setattr(live, "publish_live_event", slow_publish)

    async def main() -> str:
        # What an after-commit hook does: schedule the publish and return.
        task = asyncio.get_running_loop().create_task(
            live._publish_all([("e1", "schedule_updated", {})])
        )
        live._inflight.add(task)
        task.add_done_callback(live._inflight.discard)
        return "done"

    assert celery_module.run_task(main) == "done"
    assert sent == ["schedule_updated"]


# ── Shared Redis clients ──────────────────────────────────────────────────────


def test_shared_redis_client_is_reused_per_event_loop():
    redis_client.reset_clients()

    async def two() -> tuple:
        return redis_client.shared_redis("x"), redis_client.shared_redis("x")

    first, second = asyncio.run(two())
    assert first is second
    (third, _) = asyncio.run(two())
    # A new loop (Celery runs one per task) gets a client of its own.
    assert third is not first
    redis_client.reset_clients()


class _Counter:
    def __init__(self, results):
        self.results = list(results)
        self.calls: list[tuple] = []

    async def eval(self, script, numkeys, *args):
        self.calls.append((numkeys, *args))
        return self.results.pop(0)


def _request():
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(testing=False)),
        client=SimpleNamespace(host="1.2.3.4"),
    )


@pytest.mark.asyncio
async def test_rate_limit_counts_atomically_and_answers_429(monkeypatch):
    fake = _Counter([[1, 60], [2, 42], [3, 17]])
    monkeypatch.setattr(rate_limit, "_client", lambda: fake)
    check = rate_limit.rate_limit("login", 2, 60)
    await check(_request())
    await check(_request())
    with pytest.raises(HTTPException) as denied:
        await check(_request())
    assert denied.value.status_code == 429
    assert denied.value.headers == {"Retry-After": "17"}
    # One round trip per request: INCR and EXPIRE run in one script.
    assert fake.calls == [(1, "botball:rate:login:1.2.3.4", "60")] * 3
    assert "EXPIRE" in rate_limit._COUNT_SCRIPT and "INCR" in rate_limit._COUNT_SCRIPT


# ── Live fan-out: one subscription per process ────────────────────────────────


class _FakePubSub:
    instances: list["_FakePubSub"] = []

    def __init__(self) -> None:
        self.messages: asyncio.Queue = asyncio.Queue()
        self.patterns: list[str] = []
        self.closed = False
        _FakePubSub.instances.append(self)

    async def psubscribe(self, pattern: str) -> None:
        self.patterns.append(pattern)

    async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
        try:
            item = await asyncio.wait_for(self.messages.get(), timeout)
        except TimeoutError:
            return None
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self) -> None:
        self.closed = True


class _FakeRedis:
    def pubsub(self):
        return _FakePubSub()

    async def aclose(self) -> None:
        pass


def _pmessage(event_id: str, data: str) -> dict:
    return {"type": "pmessage", "channel": f"botball:live:{event_id}", "data": data}


@pytest.fixture
def fake_hub(monkeypatch):
    _FakePubSub.instances.clear()
    monkeypatch.setattr(live.LiveHub, "_client", lambda self: _FakeRedis())
    live._hub = None
    yield
    live._hub = None


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_hub")
async def test_hub_fans_one_subscription_out_by_channel():
    hub = live.live_hub()
    a1 = await hub.subscribe("botball:live:a")
    a2 = await hub.subscribe("botball:live:a")
    b = await hub.subscribe("botball:live:b")
    assert len(_FakePubSub.instances) == 1
    assert _FakePubSub.instances[0].patterns == ["botball:live:*"]
    pubsub = _FakePubSub.instances[0]
    await pubsub.messages.put(_pmessage("a", "for-a"))
    await pubsub.messages.put(_pmessage("b", "for-b"))
    assert await asyncio.wait_for(a1.get(), 1) == "for-a"
    assert await asyncio.wait_for(a2.get(), 1) == "for-a"
    assert await asyncio.wait_for(b.get(), 1) == "for-b"
    assert a1.empty() and b.empty()

    for channel, queue in (("botball:live:a", a1), ("botball:live:a", a2), ("botball:live:b", b)):
        hub.unsubscribe(channel, queue)
    await asyncio.sleep(0.01)
    # The last subscriber gone, the shared subscription is closed.
    assert pubsub.closed and hub.subscriber_count == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_hub")
async def test_hub_failure_disconnects_subscribers_and_restarts():
    hub = live.live_hub()
    queue = await hub.subscribe("botball:live:a")
    await _FakePubSub.instances[0].messages.put(ConnectionError("redis gone"))
    assert await asyncio.wait_for(queue.get(), 1) is None  # "lost"
    hub.unsubscribe("botball:live:a", queue)
    again = await hub.subscribe("botball:live:a")
    assert len(_FakePubSub.instances) == 2
    hub.unsubscribe("botball:live:a", again)


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list = []
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.closed_with: int | None = None
        self.application_state = WebSocketState.CONNECTING

    async def accept(self) -> None:
        self.application_state = WebSocketState.CONNECTED

    async def send_json(self, data) -> None:
        self.sent.append(data)

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def receive_text(self) -> str:
        item = await self.incoming.get()
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed_with = code


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_hub")
async def test_stream_forwards_messages_answers_pings_and_cleans_up():
    websocket = _FakeWebSocket()
    stream = asyncio.create_task(live.stream_live_events(websocket, "ev1"))
    while not _FakePubSub.instances or live.live_hub().subscriber_count == 0:
        await asyncio.sleep(0.005)
    await _FakePubSub.instances[0].messages.put(_pmessage("ev1", '{"event":"ranking_updated"}'))
    await _FakePubSub.instances[0].messages.put(_pmessage("other", "not for us"))
    await websocket.incoming.put("ping")
    while len(websocket.sent) < 3:
        await asyncio.sleep(0.005)
    await websocket.incoming.put(WebSocketDisconnect())
    await asyncio.wait_for(stream, 1)
    assert websocket.sent[0] == {"event": "connection", "payload": {"status": "connected"}}
    assert set(map(str, websocket.sent[1:])) == {'{"event":"ranking_updated"}', "{'event': 'pong'}"}
    assert live.live_hub().subscriber_count == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_hub")
async def test_stream_asks_the_client_to_reconnect_when_redis_fails():
    websocket = _FakeWebSocket()
    stream = asyncio.create_task(live.stream_live_events(websocket, "ev1"))
    while not _FakePubSub.instances or live.live_hub().subscriber_count == 0:
        await asyncio.sleep(0.005)
    await _FakePubSub.instances[0].messages.put(ConnectionError("down"))
    await asyncio.wait_for(stream, 1)
    assert websocket.sent[-1]["payload"] == {"status": "disconnected", "retry": True}
    assert websocket.closed_with == 1013


# ── Audit rows in the request transaction ─────────────────────────────────────


@pytest.fixture
def audited_app(db):
    """The app with audit on and a get_db override that behaves like get_db."""

    async def request_db():
        try:
            yield db
        except Exception:
            await db.rollback()
            raise
        else:
            audit.add_pending_audit_entry(db)
            await db.commit()

    app.dependency_overrides[get_db] = request_db
    app.state.testing = False
    yield
    app.dependency_overrides.clear()
    app.state.testing = True


@pytest.mark.asyncio
async def test_audit_row_is_written_in_the_request_transaction(
    client, db, auth_headers, admin_user, audited_app, monkeypatch
):
    def no_second_connection():
        raise AssertionError("the audit must not open a connection of its own")

    monkeypatch.setattr(audit, "_write_directly", no_second_connection)
    response = await client.post(
        "/api/teams", headers=auth_headers, json={"name": "Audited", "country": "AT"}
    )
    assert response.status_code == 201, response.text
    rows = (await db.execute(select(AuditLog))).scalars().all()
    assert [(r.action, r.user_id, r.resource_type) for r in rows] == [
        ("POST /api/teams", admin_user.id, "api")
    ]


@pytest.mark.asyncio
async def test_failed_requests_leave_no_audit_row(client, db, auth_headers, audited_app):
    response = await client.post("/api/teams", headers=auth_headers, json={})
    assert response.status_code == 422
    assert (await db.execute(select(AuditLog))).scalars().all() == []


@pytest.mark.asyncio
async def test_audit_falls_back_to_a_single_insert(
    client, db, auth_headers, monkeypatch, engine_in_test_transaction
):
    """Requests whose session never ran get_db's commit still get their row."""
    monkeypatch.setattr(database, "engine", engine_in_test_transaction)
    app.state.testing = False
    try:
        response = await client.post(
            "/api/teams", headers=auth_headers, json={"name": "Fallback", "country": "AT"}
        )
    finally:
        app.state.testing = True
    assert response.status_code == 201
    await db.commit()
    rows = (await db.execute(select(AuditLog.action))).scalars().all()
    assert rows == ["POST /api/teams"]


# ── Printer polling ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_printers_are_polled_concurrently_with_a_timeout(db, monkeypatch):
    for name in ("fast", "slow", "hung"):
        db.add(
            Printer(
                name=name,
                printer_type="octoprint",
                api_url=f"http://{name}",
                api_key_encrypted="enc",
                is_online=True,
            )
        )
    db.add(Printer(name="manual", printer_type="generic", is_online=True))
    await db.commit()
    monkeypatch.setattr(printing_tasks, "decrypt_credential", lambda value: value)

    def fake_poll(printer_type, api_url, api_key, device_id):
        delay = {"http://fast": 0.0, "http://slow": 0.2, "http://hung": 2.0}[api_url]
        time.sleep(delay)
        return PrinterStatus(online=True, state="idle")

    monkeypatch.setattr(printing_tasks, "poll_printer", fake_poll)
    factory = async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)
    started = time.monotonic()
    assert await printing_tasks.poll_all_printers(factory, timeout=0.5) == 3
    elapsed = time.monotonic() - started
    # Concurrent: bounded by the timeout, not by the sum of all delays.
    assert elapsed < 1.5
    db.expire_all()
    states = {
        p.name: (p.is_online, p.current_state)
        for p in (await db.execute(select(Printer))).scalars()
    }
    assert states["fast"] == (True, "idle") and states["slow"] == (True, "idle")
    assert states["hung"] == (False, "offline")
    assert states["manual"] == (True, None)


# ── PDFs off the event loop ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pdf_exports_are_built_in_the_threadpool(client, auth_headers, event, monkeypatch):
    import modules.exports.routes as export_routes

    threads: list[int] = []

    def fake_build(*args, **kwargs) -> bytes:
        threads.append(threading.get_ident())
        return b"%PDF-1.4 fake"

    monkeypatch.setattr(export_routes, "build_ranking_pdf", fake_build)
    response = await client.get(f"/api/exports/events/{event.id}/ranking.pdf", headers=auth_headers)
    assert response.status_code == 200 and response.content == b"%PDF-1.4 fake"
    assert threads and threads[0] != threading.get_ident()
