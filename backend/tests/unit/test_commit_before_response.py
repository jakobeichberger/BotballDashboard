"""CommitBeforeResponseMiddleware: a write response leaves only after the commit.

FastAPI runs the teardown of ``yield`` dependencies (where get_db commits)
after the response has been sent. These tests drive the ASGI app directly and
record the order of "committed" and "response.start", which an HTTP client
test cannot see: httpx's ASGI transport waits for the whole app anyway.
"""

import asyncio

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError

from core.transactions import CommitBeforeResponseMiddleware


def _app(events: list[str], fail: Exception | None = None) -> FastAPI:
    app = FastAPI()

    async def fake_db():
        yield None
        await asyncio.sleep(0.01)
        if fail is not None:
            raise fail
        events.append("committed")

    @app.post("/items", status_code=201)
    async def create(_=Depends(fake_db)):
        return {"ok": True}

    @app.get("/stream")
    async def stream():
        async def body():
            yield b"first"
            events.append("app still running")
            yield b"second"

        return StreamingResponse(body())

    app.add_middleware(CommitBeforeResponseMiddleware)
    return app


async def _call(app, method: str, path: str, events: list[str]) -> tuple[int, bytes]:
    status = 0
    body = b""
    request_sent = False

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.sleep(3600)

    async def send(message):
        nonlocal status, body
        if message["type"] == "http.response.start":
            status = message["status"]
            events.append("response.start")
        elif message["type"] == "http.response.body":
            body += message.get("body", b"")
            if message.get("body"):
                events.append(f"body:{message['body'].decode()[:12]}")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)
    return status, body


async def test_write_response_is_sent_after_the_commit():
    events: list[str] = []
    status, _ = await _call(_app(events), "POST", "/items", events)
    assert status == 201
    assert events.index("committed") < events.index("response.start")


async def test_without_the_middleware_the_client_would_see_the_response_first():
    # Documents the FastAPI behaviour the middleware exists for.
    events: list[str] = []
    app = _app(events)
    app.user_middleware.clear()
    app.middleware_stack = None
    status, _ = await _call(app, "POST", "/items", events)
    assert status == 201
    assert events.index("response.start") < events.index("committed")


async def test_constraint_failing_at_commit_is_a_409_not_a_201():
    events: list[str] = []
    error = IntegrityError("INSERT", {}, Exception("duplicate key"))
    status, body = await _call(_app(events, fail=error), "POST", "/items", events)
    assert status == 409
    assert b"data_conflict" in body
    assert b"ok" not in body


async def test_other_commit_failure_is_a_500():
    events: list[str] = []
    app = _app(events, fail=OSError("connection lost"))
    status, body = await _call(app, "POST", "/items", events)
    assert status == 500
    assert b"internal_error" in body


async def test_reads_are_streamed_not_buffered():
    events: list[str] = []
    status, body = await _call(_app(events), "GET", "/stream", events)
    assert status == 200
    assert body == b"firstsecond"
    assert events.index("body:first") < events.index("app still running")
