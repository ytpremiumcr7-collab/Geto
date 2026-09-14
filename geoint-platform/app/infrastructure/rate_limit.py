"""Rate limiting con Redis (fail-open si Redis no está disponible)."""

from __future__ import annotations

import time

import structlog

from app.core.config import settings

log = structlog.get_logger()

_redis = None


def _client():
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis.asyncio as redis

        _redis = redis.from_url(settings.redis_url, decode_responses=True)
        return _redis
    except Exception:
        log.warning("rate_limit_redis_unavailable")
        return None


async def check_rate_limit(
    key: str,
    *,
    limit: int = 60,
    window_seconds: int = 60,
) -> bool:
    """True = permitido. Fail-open si no hay Redis."""
    fail_open = bool(getattr(settings, "rate_limit_fail_open", False))
    client = _client()
    if client is None:
        if fail_open:
            return True
        log.warning("rate_limit_redis_unavailable_fail_closed")
        return False
    try:
        bucket = f"rl:{key}:{int(time.time()) // window_seconds}"
        count = await client.incr(bucket)
        if count == 1:
            await client.expire(bucket, window_seconds + 1)
        return count <= limit
    except Exception:
        log.warning("rate_limit_check_failed", key=key)
        return True if fail_open else False
