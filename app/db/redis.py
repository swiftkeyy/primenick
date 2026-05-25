from __future__ import annotations

from redis.asyncio import Redis

from app.core.settings import get_settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = Redis.from_url(str(settings.redis_url), encoding="utf-8", decode_responses=True, max_connections=500, health_check_interval=30)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
