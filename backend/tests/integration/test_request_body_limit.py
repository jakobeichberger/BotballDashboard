"""The request-size limit counts streamed bytes (security review 2026-09, #1).

The old check only read Content-Length; a chunked request has none, so
Starlette buffered the whole body — before authentication.
"""

import pytest

from core.config import get_settings

MB = 1024 * 1024

_PART_HEAD = (
    b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.stl"\r\n'
    b"Content-Type: application/octet-stream\r\n\r\n"
)
_PART_TAIL = b"\r\n--x--\r\n"


@pytest.fixture
def small_limits(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    monkeypatch.setattr(settings, "print_upload_max_mb", 4)


def _chunked(total_mb: int, sent: list[int], head: bytes = b"", tail: bytes = b""):
    """A generator body: httpx sends it chunked, without Content-Length."""

    async def body():
        yield head
        for _ in range(total_mb):
            sent[0] += MB
            yield b"a" * MB
        yield tail

    return body()


@pytest.mark.asyncio
async def test_chunked_body_over_the_limit_is_cut_off(client, small_limits):
    sent = [0]
    resp = await client.post(
        "/api/auth/login",
        content=_chunked(50, sent),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 413, resp.text
    assert resp.json()["code"] == "request_too_large"
    assert resp.json()["requestId"]
    # Aborted while streaming: nowhere near the 50 MB the client offered.
    assert sent[0] <= 3 * MB


@pytest.mark.asyncio
async def test_small_chunked_body_still_works(client, small_limits):
    async def body():
        yield b'{"email": "nobody@test.com", '
        yield b'"password": "wrong-password"}'

    resp = await client.post(
        "/api/auth/login", content=body(), headers={"content-type": "application/json"}
    )
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_declared_content_length_is_refused_up_front(client, small_limits):
    resp = await client.post(
        "/api/auth/login",
        content=b"a" * (3 * MB),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 413
    assert resp.json()["code"] == "request_too_large"


@pytest.mark.asyncio
async def test_print_upload_keeps_its_larger_limit(client, auth_headers, small_limits):
    headers = {**auth_headers, "content-type": "multipart/form-data; boundary=x"}
    within = await client.post(
        "/api/printing/jobs/missing/file",
        content=_chunked(3, [0], _PART_HEAD, _PART_TAIL),
        headers=headers,
    )
    # Parsed completely and handed to the route, which knows no such job.
    assert within.status_code == 404, within.text
    sent = [0]
    beyond = await client.post(
        "/api/printing/jobs/missing/file",
        content=_chunked(40, sent, _PART_HEAD, _PART_TAIL),
        headers=headers,
    )
    assert beyond.status_code == 413, beyond.text
    assert sent[0] <= 6 * MB
