"""Shared Redis clients: one connection pool per purpose, process and event loop.

Creating a client per call (as live publishing and the rate limiter used to)
opens and tears down a TCP connection for every request. The clients here are
created once and reused, with short timeouts so an unreachable Redis costs a
request at most a fraction of a second (see core.token_denylist for the same
pattern).

redis-py's asyncio connections belong to the event loop that opened them. The
API runs one loop for its lifetime, but Celery tasks run each job in a fresh
loop (asyncio.run), so a client is only reused within the loop that created
it; a new loop gets a new client.
"""

import asyncio

from redis.asyncio import Redis

from core.config import get_settings

_clients: dict[str, tuple[asyncio.AbstractEventLoop, Redis]] = {}


def shared_redis(
    name: str,
    *,
    timeout: float | None = 1.0,
    connect_timeout: float = 0.5,
    decode_responses: bool = True,
) -> Redis:
    """The process-wide client called `name` for the running event loop."""
    loop = asyncio.get_running_loop()
    cached = _clients.get(name)
    if cached is not None and cached[0] is loop:
        return cached[1]
    client = Redis.from_url(
        get_settings().redis_url,
        decode_responses=decode_responses,
        socket_connect_timeout=connect_timeout,
        socket_timeout=timeout,
        health_check_interval=30,
    )
    _clients[name] = (loop, client)
    return client


def reset_clients() -> None:
    """Forget every client (tests switching the Redis URL)."""
    _clients.clear()


async def close_clients() -> None:
    """Close and forget the clients of the running event loop (end of a loop's life)."""
    loop = asyncio.get_running_loop()
    for name, (owner, client) in list(_clients.items()):
        if owner is loop:
            del _clients[name]
            await client.aclose()
