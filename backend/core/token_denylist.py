"""Deny-list of logged-out access tokens.

Access tokens are stateless JWTs that live ``JWT_ACCESS_TOKEN_EXPIRE_MINUTES``
(15 min). ``token_version`` revokes *all* of a user's tokens (password change,
deactivation); a plain logout must only end the one session, so the logged-out
token's ``jti`` is stored here until the token would have expired anyway.

The list lives in Redis so every API instance sees it. Entries expire on
their own (``SET … EX``), so the list never holds more than the tokens logged
out within the last 15 minutes. If Redis is unreachable the check fails open:
authentication keeps working (the readiness probe reports Redis down) and the
token simply stays valid until its expiry, as it did before this list existed.

``TOKEN_DENYLIST_BACKEND=memory`` keeps the list in-process instead (tests,
single-instance development setups without Redis).
"""

import time
from datetime import UTC, datetime

from redis.asyncio import Redis

from core.config import get_settings
from core.logging import get_logger
from core.metrics import record_redis_fail_open
from core.redis_client import REDIS_ERRORS

logger = get_logger("token_denylist")

_KEY_PREFIX = "botball:denied-jti:"

# In-process fallback: jti -> unix time at which the entry may be dropped.
_memory: dict[str, float] = {}
_redis: Redis | None = None


def _use_memory() -> bool:
    return get_settings().token_denylist_backend == "memory"


def _client() -> Redis:
    """One shared client (and connection pool) per process.

    Short timeouts: this runs on every authenticated request, and an
    unreachable Redis must not stall the API.
    """
    global _redis
    if _redis is None:
        _redis = Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
    return _redis


def _ttl_seconds(expires_at: datetime | int | float | None) -> int:
    """Seconds until ``expires_at`` (the token's ``exp``), at least 1."""
    if expires_at is None:
        return get_settings().jwt_access_token_expire_minutes * 60
    if isinstance(expires_at, datetime):
        exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
        remaining = exp.timestamp() - time.time()
    else:
        remaining = float(expires_at) - time.time()
    return max(1, int(remaining) + 1)


async def deny(jti: str, expires_at: datetime | int | float | None) -> None:
    """Deny the token with ``jti`` until ``expires_at``."""
    ttl = _ttl_seconds(expires_at)
    if _use_memory():
        now = time.time()
        for key in [k for k, until in _memory.items() if until <= now]:
            del _memory[key]
        _memory[jti] = now + ttl
        return
    try:
        await _client().set(f"{_KEY_PREFIX}{jti}", "1", ex=ttl)
    except REDIS_ERRORS as exc:  # fail open while Redis is unreachable
        logger.warning("token_denylist_unavailable", op="deny", error=str(exc))


async def is_denied(jti: str) -> bool:
    if _use_memory():
        until = _memory.get(jti)
        return until is not None and until > time.time()
    try:
        return bool(await _client().exists(f"{_KEY_PREFIX}{jti}"))
    except REDIS_ERRORS as exc:  # fail open while Redis is unreachable
        logger.warning("token_denylist_unavailable", op="check", error=str(exc))
        record_redis_fail_open("token_denylist")
        return False


def clear_memory() -> None:
    """Forget every in-process entry (tests)."""
    _memory.clear()
