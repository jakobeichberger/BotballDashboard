"""Versioned cache of computed read payloads (rankings, results) with ETags.

Scoreboards and ranking pages poll, and every poll used to recompute the
seeding and formula rankings from scratch. The serialized response is now
cached per event under a version number:

    botball:cache-version:{event_id}                    → integer (INCR)
    botball:cache:{kind}:{event_id}:v{version}:{params} → etag + body (TTL)

Every committed ``ranking_updated`` / ``schedule_updated`` live event bumps the
event's version (core.live), so the next read computes afresh; entries of
old versions simply expire. A reader that computed from pre-commit data can
only store it under the version it read before the bump, which is never
read again. The TTL (RANKING_CACHE_TTL_SECONDS) bounds how long a change that
announces nothing — a renamed team, an edited formula — can take to show up.

Each payload carries a strong ETag (hash of the body). Clients send it back as
``If-None-Match`` and get ``304 Not Modified`` without a body; the browser does
this on its own for responses marked ``Cache-Control: no-cache``.

Redis being down never fails a read: the payload is computed as without a
cache, and Redis is left alone for a few seconds before it is tried again.
``CACHE_BACKEND=memory`` keeps everything in-process (tests, single
instance), ``none`` disables caching (ETags still work).
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from fastapi import Request, Response
from pydantic import TypeAdapter

from core.config import get_settings
from core.logging import get_logger
from core.metrics import record_redis_fail_open
from core.redis_client import REDIS_ERRORS, shared_redis

logger = get_logger("cache")

_VERSION_PREFIX = "botball:cache-version:"
_ENTRY_PREFIX = "botball:cache:"
# After a Redis error the cache is skipped for this long, so an outage costs
# one timeout every few seconds instead of one per request.
_BACKOFF_SECONDS = 5.0
# Version counters outlive any entry by far; they only need to survive the
# entries' TTL, but a long expiry keeps an idle event's counter from resetting
# to a number an old entry might still carry.
_VERSION_TTL_SECONDS = 7 * 24 * 3600

#: How long one instance may compute an entry before others compute too.
_LOCK_TTL_MS = 2000
_LOCK_POLL_SECONDS = 0.05
# Delete the lock only if it is still ours (it may have expired and been
# taken by another instance meanwhile).
_RELEASE_LOCK = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

_down_until = 0.0
_memory: dict[str, tuple[float, bytes]] = {}
_memory_versions: dict[str, int] = {}
# Entries being computed in this process: key → the leader's result.
_flights: dict[str, asyncio.Future[Payload]] = {}


@dataclass(frozen=True)
class Payload:
    body: bytes
    etag: str

    def encode(self) -> bytes:
        return self.etag.encode() + b"\n" + self.body

    @classmethod
    def decode(cls, raw: bytes) -> Payload:
        etag, _, body = raw.partition(b"\n")
        return cls(body=body, etag=etag.decode())

    @classmethod
    def of(cls, body: bytes) -> Payload:
        return cls(body=body, etag=f'"{hashlib.sha256(body).hexdigest()[:32]}"')


def _backend() -> str:
    return get_settings().cache_backend


def _redis_usable() -> bool:
    return _backend() == "redis" and time.monotonic() >= _down_until


def _mark_down(op: str, exc: Exception) -> None:
    global _down_until
    _down_until = time.monotonic() + _BACKOFF_SECONDS
    logger.warning("cache_unavailable", op=op, error=str(exc))
    record_redis_fail_open("cache")


def _client():
    return shared_redis("cache", timeout=0.5, decode_responses=False)


async def current_version(event_id: str) -> int | None:
    """The event's cache version, or None when no cache is usable."""
    backend = _backend()
    if backend == "memory":
        return _memory_versions.get(event_id, 0)
    if not _redis_usable():
        return None
    try:
        value = await _client().get(f"{_VERSION_PREFIX}{event_id}")
    except REDIS_ERRORS as exc:
        _mark_down("version", exc)
        return None
    return int(value or 0)


async def bump_version(event_id: str) -> None:
    """Invalidate every cached payload of the event (called after commit)."""
    backend = _backend()
    if backend == "memory":
        _memory_versions[event_id] = _memory_versions.get(event_id, 0) + 1
        return
    if backend != "redis":
        return
    # Tried even while backing off: a missed bump would leave a stale entry
    # for a whole TTL once Redis answers again.
    try:
        key = f"{_VERSION_PREFIX}{event_id}"
        async with _client().pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, _VERSION_TTL_SECONDS)
            await pipe.execute()
    except REDIS_ERRORS as exc:
        _mark_down("bump", exc)


def _entry_key(kind: str, event_id: str, version: int, params: str) -> str:
    return f"{_ENTRY_PREFIX}{kind}:{event_id}:v{version}:{params}"


async def _load(key: str) -> Payload | None:
    if _backend() == "memory":
        entry = _memory.get(key)
        if entry is None or entry[0] < time.monotonic():
            return None
        return Payload.decode(entry[1])
    try:
        raw = await _client().get(key)
    except REDIS_ERRORS as exc:
        _mark_down("get", exc)
        return None
    return Payload.decode(raw) if raw else None


async def _store(key: str, payload: Payload) -> None:
    ttl = get_settings().ranking_cache_ttl_seconds
    if _backend() == "memory":
        _memory[key] = (time.monotonic() + ttl, payload.encode())
        return
    try:
        await _client().set(key, payload.encode(), ex=ttl)
    except REDIS_ERRORS as exc:
        _mark_down("set", exc)


async def cached_payload(
    kind: str,
    event_id: str,
    params: str,
    compute: Callable[[], Awaitable[bytes]],
) -> Payload:
    """The cached payload of (`kind`, `event_id`, `params`), computed on a miss.

    Single flight: every committed score bumps the version, and all open
    scoreboards ask again at once. Of the concurrent misses for one key only
    the first computes; the others in this process wait for its result, and
    other API instances wait for its Redis entry (see ``_compute_and_store``).
    """
    version = await current_version(event_id)
    if version is None:
        return Payload.of(await compute())
    key = _entry_key(kind, event_id, version, params)
    hit = await _load(key)
    if hit is not None:
        return hit

    leader = _flights.get(key)
    if leader is not None and not leader.done():
        try:
            return await asyncio.shield(leader)
        except asyncio.CancelledError:
            if not leader.cancelled():
                raise  # this request itself was cancelled
        except Exception:  # noqa: BLE001, S110 - the leader failed: compute ourselves
            pass
        return await _compute_and_store(key, compute)

    flight: asyncio.Future[Payload] = asyncio.get_running_loop().create_future()
    # Nobody may be waiting; retrieve the exception so it is not reported.
    flight.add_done_callback(lambda f: f.cancelled() or f.exception())
    _flights[key] = flight
    try:
        payload = await _compute_and_store(key, compute)
    except BaseException as exc:
        if isinstance(exc, asyncio.CancelledError):
            flight.cancel()
        else:
            flight.set_exception(exc)
        raise
    else:
        flight.set_result(payload)
        return payload
    finally:
        if _flights.get(key) is flight:
            del _flights[key]


async def _compute_and_store(key: str, compute: Callable[[], Awaitable[bytes]]) -> Payload:
    """Compute and store one entry; across instances only one computes.

    With Redis, ``SET key:lock NX PX`` elects the instance that computes; the
    others poll for the entry for as long as the lock lives and compute
    themselves only if it does not show up (slow leader, lost lock, Redis
    trouble) — the lock only saves work, it never blocks a read for long.
    """
    lock_key = f"{key}:lock"
    token = await _acquire_lock(lock_key)
    if token is False:
        deadline = time.monotonic() + _LOCK_TTL_MS / 1000
        while time.monotonic() < deadline:
            await asyncio.sleep(_LOCK_POLL_SECONDS)
            hit = await _load(key)
            if hit is not None:
                return hit
        token = None
    try:
        payload = Payload.of(await compute())
        await _store(key, payload)
        return payload
    finally:
        if isinstance(token, str):
            await _release_lock(lock_key, token)


async def _acquire_lock(lock_key: str) -> str | Literal[False] | None:
    """A token when this instance holds the lock, False when another one does,
    None when there is no shared lock (memory backend, Redis unavailable)."""
    if not _redis_usable():
        return None
    token = uuid.uuid4().hex
    try:
        acquired = await _client().set(lock_key, token, nx=True, px=_LOCK_TTL_MS)
    except REDIS_ERRORS as exc:
        _mark_down("lock", exc)
        return None
    return token if acquired else False


async def _release_lock(lock_key: str, token: str) -> None:
    try:
        await _client().eval(_RELEASE_LOCK, 1, lock_key, token)
    except REDIS_ERRORS as exc:
        # The lock expires on its own within _LOCK_TTL_MS.
        _mark_down("unlock", exc)


@lru_cache(maxsize=64)
def _adapter(model: Any) -> TypeAdapter:
    return TypeAdapter(model)


def dump_json(model: Any, data: Any) -> bytes:
    """Serialize `data` as FastAPI would for ``response_model=model``."""
    adapter = _adapter(model)
    return adapter.dump_json(adapter.validate_python(data, from_attributes=True), by_alias=True)


def _etag_matches(header: str | None, etag: str) -> bool:
    if not header:
        return False
    if header.strip() == "*":
        return True
    candidates = {item.strip().removeprefix("W/") for item in header.split(",")}
    return etag in candidates


def conditional_response(request: Request, payload: Payload, *, public: bool) -> Response:
    """200 with the body, or 304 when the client already has this version."""
    headers = {
        "ETag": payload.etag,
        # no-cache: the browser may keep the body but must revalidate it
        # (If-None-Match) before every use — cheap thanks to the 304.
        "Cache-Control": "public, no-cache" if public else "private, no-cache",
    }
    if _etag_matches(request.headers.get("if-none-match"), payload.etag):
        return Response(status_code=304, headers=headers)
    return Response(content=payload.body, media_type="application/json", headers=headers)


def clear_memory() -> None:
    """Forget the in-process cache and the Redis backoff (tests)."""
    global _down_until
    _memory.clear()
    _memory_versions.clear()
    _flights.clear()
    _down_until = 0.0
