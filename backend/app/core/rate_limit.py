"""Rate limiting using Redis sliding window."""

from __future__ import annotations

import time
from typing import Annotated

from redis import asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status

from app.config import settings

# Default limits per tier (requests per minute)
RPM_LIMITS: dict[str, int] = {
    "free": 10,       # 10 requests/minute (~sandbox)
    "developer": 300,  # 300 requests/minute (5 RPS)
    "enterprise": 3000,  # 3000 requests/minute (50 RPS)
}

DEFAULT_RPM = RPM_LIMITS["free"]


class RedisRateLimiter:
    """Sliding window rate limiter using Redis sorted sets.

    Pattern: `ratelimit:{identifier}` — sorted set with timestamps.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def check(
        self,
        identifier: str,
        max_requests: int = DEFAULT_RPM,
        window_seconds: int = 60,
    ) -> dict[str, int]:
        """Check rate limit. Raises HTTPException 429 if exceeded.

        Returns header info dict with limit/remaining/reset values.
        """
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"ratelimit:{identifier}"

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        pipe.zadd(redis_key, {str(now): now})
        pipe.expire(redis_key, window_seconds * 2)
        _, current_count, _, _ = await pipe.execute()

        remaining = max(0, max_requests - current_count)
        reset_at = int(now) + window_seconds

        if current_count > max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": max_requests,
                    "remaining": 0,
                    "reset_at": reset_at,
                },
                headers={
                    "x-ratelimit-limit": str(max_requests),
                    "x-ratelimit-remaining": "0",
                    "x-ratelimit-reset": str(reset_at),
                },
            )

        return {
            "limit": max_requests,
            "remaining": remaining,
            "reset_at": reset_at,
        }


# Global Redis client (lazy singleton)
_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=2
        )
    return _redis_client


async def get_rate_limiter(
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> RedisRateLimiter:
    return RedisRateLimiter(redis)


async def rate_limit_dependency(
    request: Request,
    limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
) -> None:
    """FastAPI dependency for rate limiting based on client IP.

    Use for unauthenticated endpoints. For API-key endpoints,
    use the key-specific rate limiter that reads tier limits.
    """
    identifier = f"ip:{request.client.host}" if request.client else "ip:unknown"
    await limiter.check(identifier)

