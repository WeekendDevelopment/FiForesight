import json
import logging

from redis.asyncio import ConnectionPool, Redis

logger: logging.Logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def init_redis(url: str) -> None:
    global _pool
    _pool = ConnectionPool.from_url(url, decode_responses=True, max_connections=10)
    logger.info("[REDIS] Connection pool initialized (max_connections=10)")


async def close_redis() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
        logger.info("[REDIS] Connection pool closed")


def get_redis() -> Redis | None:
    if _pool is None:
        return None
    return Redis(connection_pool=_pool)


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
            logger.warning(
                f"[REDIS] cache_get({key}) — unexpected type {type(parsed).__name__}, discarding"
            )
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
