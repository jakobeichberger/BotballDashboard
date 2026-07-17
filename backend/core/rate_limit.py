"""Redis-backed rate limits shared by all API instances."""

from collections.abc import Callable

from fastapi import HTTPException, Request
from redis.asyncio import Redis

from core.config import get_settings
from core.logging import get_logger

logger = get_logger("rate_limit")


def rate_limit(bucket: str, limit: int, window_seconds: int) -> Callable:
    async def check(request: Request) -> None:
        if getattr(request.app.state, "testing", False):
            return
        address = request.client.host if request.client else "unknown"
        redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
        key = f"botball:rate:{bucket}:{address}"
        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, window_seconds)
            if count > limit:
                ttl = max(1, await redis.ttl(key))
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "rate_limit_exceeded",
                        "message": "Too many requests. Please try again later.",
                        "retryAfter": ttl,
                    },
                    headers={"Retry-After": str(ttl)},
                )
        except HTTPException:
            raise
        except Exception as exc:
            # The readiness check reports Redis failure. Auth remains available for recovery.
            logger.warning("rate_limit_unavailable", bucket=bucket, error=str(exc))
        finally:
            await redis.aclose()

    return check
