"""Redis-backed rate limits shared by all API instances."""

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request
from redis.asyncio import Redis

from core.logging import get_logger
from core.metrics import record_redis_fail_open
from core.redis_client import REDIS_ERRORS, shared_redis

logger = get_logger("rate_limit")

# Fixed window counter in one atomic step. INCR and EXPIRE used to be two
# commands: a failure between them left a counter without expiry that locked
# the client out for good. The script also repairs such a key (TTL -1).
# Returns {count, seconds until the window resets}.
_COUNT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if count == 1 or ttl < 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


def _client() -> Redis:
    return shared_redis("rate_limit", timeout=0.5)


async def _count(key: str, window_seconds: int) -> tuple[int, int]:
    result: Any = _client().eval(_COUNT_SCRIPT, 1, key, str(window_seconds))
    count, ttl = await result
    return int(count), int(ttl)


def rate_limit(bucket: str, limit: int, window_seconds: int) -> Callable:
    async def check(request: Request) -> None:
        if getattr(request.app.state, "testing", False):
            return
        address = request.client.host if request.client else "unknown"
        key = f"botball:rate:{bucket}:{address}"
        try:
            count, ttl = await _count(key, window_seconds)
        except REDIS_ERRORS as exc:
            # The readiness check reports Redis failure. Auth remains available for recovery.
            logger.warning("rate_limit_unavailable", bucket=bucket, error=str(exc))
            record_redis_fail_open("rate_limit")
            return
        if count > limit:
            retry_after = max(1, ttl)
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "rate_limit_exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retryAfter": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

    return check
