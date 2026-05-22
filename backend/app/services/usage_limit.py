from __future__ import annotations

from datetime import date

from fastapi import HTTPException, status

from app.config import settings
from app.models.user import User

# Fallback без Redis (тесты, локальный dev)
_memory_views: dict[tuple[int, str], int] = {}
_redis_client = None
_redis_unavailable = False


def _today_key() -> str:
    return date.today().isoformat()


def _free_daily_limit() -> int:
    return int(getattr(settings, "free_niche_views_per_day", 5))


def _redis_key(user_id: int) -> str:
    return f"niche_views:{user_id}:{_today_key()}"


async def _get_redis():
    global _redis_client, _redis_unavailable
    if _redis_unavailable:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        _redis_client = client
        return client
    except Exception:
        _redis_unavailable = True
        return None


async def _increment_redis(user_id: int) -> int:
    client = await _get_redis()
    if client is None:
        key = (user_id, _today_key())
        count = _memory_views.get(key, 0) + 1
        _memory_views[key] = count
        return count
    rkey = _redis_key(user_id)
    count = int(await client.incr(rkey))
    if count == 1:
        await client.expire(rkey, 86_400)
    return count


async def enforce_niche_view_quota(user: User) -> None:
    if user.is_pro:
        return
    limit = _free_daily_limit()
    count = await _increment_redis(user.id)
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Free tier: не более {limit} просмотров карточек ниш в сутки. Оформите Pro.",
        )


def reset_memory_views_for_tests() -> None:
    _memory_views.clear()
