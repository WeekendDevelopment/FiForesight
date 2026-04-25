# backend/redis_cache.py
import json
import logging
import os
from upstash_redis.asyncio import Redis

logger = logging.getLogger(__name__)

_client: Redis | None = None
_cache_disabled: bool = False  # set once when env vars are confirmed absent


def get_redis() -> Redis | None:
    global _client, _cache_disabled
    if _cache_disabled:
        return None
    if _client is not None:
        return _client
    url   = os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        logger.warning("[REDIS] UPSTASH_REDIS_REST_URL/TOKEN not set — caching disabled")
        _cache_disabled = True
        return None
    _client = Redis(url=url, token=token)
    return _client


async def cache_get(key: str) -> list | dict | None:
    r = get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(key)
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(f"[REDIS] cache_get({key}) failed: {e}")
        return None


async def cache_set(key: str, value: list | dict, ttl_seconds: int) -> None:
    r = get_redis()
    if r is None:
        return
    try:
        await r.set(key, json.dumps(value), ex=ttl_seconds)
    except Exception as e:
        logger.warning(f"[REDIS] cache_set({key}) failed: {e}")
