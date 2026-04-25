# backend/redis_cache.py
import json
import logging
import os
from upstash_redis.asyncio import Redis

logger: logging.Logger = logging.getLogger(__name__)

_DISABLED: object = object()  # sentinel — assigned to _client when env vars are absent
_client: Redis | object | None = None  # None=unchecked, _DISABLED=no creds, Redis=ready  # noqa: F841


def get_redis() -> Redis | None:
    global _client
    if _client is _DISABLED:
        return None
    if _client is not None:
        return _client  # type: ignore[return-value]
    url   = os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        logger.warning("[REDIS] UPSTASH_REDIS_REST_URL/TOKEN not set — caching disabled")
        _client = _DISABLED
        return None
    _client = Redis(url=url, token=token)
    return _client  # type: ignore[return-value]


async def cache_get(key: str) -> list | dict | None:
    r = get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(key)
        if not raw:
            return None
        parsed = json.loads(raw)
        if not isinstance(parsed, (list, dict)):
            logger.warning(f"[REDIS] cache_get({key}) — unexpected type {type(parsed).__name__}, discarding")
            return None
        return parsed
    except json.JSONDecodeError as e:
        logger.warning(f"[REDIS] cache_get({key}) — invalid JSON: {e}")
        return None
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
