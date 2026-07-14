# backend/routers/watchlist.py
"""
Watchlist persistence (Feature 13).

Endpoints:
  GET    /watchlist         — list user's saved symbols; [] for anonymous
  POST   /watchlist         — add a symbol (upsert; no 409 on duplicate)
  DELETE /watchlist/{symbol} — remove a symbol; 204 on success, 404 if not found

Write endpoints (POST/DELETE) are auth-gated via require_user.
GET is public — anonymous callers receive an empty list without a 401.

  GET    /watchlist/metrics — live fundamentals/technicals for a CSV of symbols (public)
"""
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, field_validator
from slowapi.util import get_remote_address

import supabase_rest
from config import Config
from dependencies import limiter, require_user, get_user_id, _user_rate_key
from redis_cache import cache_get, cache_set, get_redis
from watchlist_metrics_service import fetch_watchlist_metrics

router = APIRouter()
logger = logging.getLogger(__name__)

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-:]{1,15}$")
_GET_TTL = 60   # 1 min cache per user


def _cache_key(user_id: str) -> str:
    return f"watchlist:{user_id}"


def _bearer(authorization: str) -> str:
    return authorization.removeprefix("Bearer ").strip()


def _handle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, supabase_rest.SupabaseConfigError):
        logger.error("[WATCHLIST] Supabase not configured.")
        return HTTPException(status_code=503, detail="Watchlist storage is not configured.")
    if isinstance(exc, supabase_rest.SupabaseRestError):
        logger.error("[WATCHLIST] Supabase REST error (HTTP %s): %s", exc.status_code, exc)
        return HTTPException(status_code=502, detail="Could not reach the watchlist store.")
    logger.error("[WATCHLIST] unexpected error: %s", exc)
    return HTTPException(status_code=500, detail="An internal server error occurred.")


async def _invalidate(user_id: str) -> None:
    try:
        r = get_redis()
        if r is not None:
            await r.delete(_cache_key(user_id))
    except Exception as exc:
        logger.debug("[WATCHLIST] cache invalidation skipped: %s", exc)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class WatchlistAdd(BaseModel):
    symbol: str

    @field_validator("symbol")
    @classmethod
    def _validate(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not _SYMBOL_RE.match(v):
            raise ValueError("Invalid symbol.")
        return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/watchlist")
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=_user_rate_key)
async def list_watchlist(
    request: Request,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    """Return saved watchlist. [] for anonymous callers."""
    user_id = get_user_id(authorization)
    if not user_id:
        return {"watchlist": []}

    cached = await cache_get(_cache_key(user_id))
    if cached is not None:
        return {"watchlist": cached}

    try:
        rows = await supabase_rest.list_watchlist(_bearer(authorization))
    except Exception as exc:
        raise _handle_error(exc)

    await cache_set(_cache_key(user_id), rows, ttl_seconds=_GET_TTL)
    return {"watchlist": rows}


@router.post("/watchlist")
@limiter.limit(lambda: Config.RATE_LIMIT_PORTFOLIO, key_func=_user_rate_key)
async def add_to_watchlist(
    request: Request,
    body: WatchlistAdd,
    user_id: str = Depends(require_user),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    """Add a symbol. Upsert — returns 200 even on duplicate."""
    try:
        row = await supabase_rest.upsert_watchlist(_bearer(authorization), body.symbol)
    except Exception as exc:
        raise _handle_error(exc)
    await _invalidate(user_id)
    return {"item": row}


@router.delete("/watchlist/{symbol}", status_code=204)
@limiter.limit(lambda: Config.RATE_LIMIT_PORTFOLIO, key_func=_user_rate_key)
async def remove_from_watchlist(
    request: Request,
    symbol: str,
    user_id: str = Depends(require_user),
    authorization: str = Header(default=""),
) -> None:
    """Remove a symbol. 204 on success, 404 if not found."""
    sym = symbol.strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=422, detail="Invalid symbol.")
    try:
        removed = await supabase_rest.delete_watchlist_item(_bearer(authorization), sym)
    except Exception as exc:
        raise _handle_error(exc)
    if not removed:
        raise HTTPException(status_code=404, detail="Symbol not in watchlist.")
    await _invalidate(user_id)


@router.get("/watchlist/metrics")
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def watchlist_metrics(request: Request, symbols: str = "") -> list[dict[str, Any]]:
    """Live table columns (price/%chg/PE/RSI/52w/mktcap/earnings) for a CSV of symbols.

    Public (no auth) — same pattern as /sparklines. Each symbol is cached in
    Redis independently for 5 min so a shared watchlist across users is cheap.
    """
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()][:30]
    syms = [s for s in syms if _SYMBOL_RE.match(s)]
    if not syms:
        return []

    out: list[dict[str, Any]] = []
    missing: list[str] = []
    for s in syms:
        cached = await cache_get(f"wl_metrics:{s}")
        if cached:
            out.append(cached)
        else:
            missing.append(s)

    if missing:
        for row in await fetch_watchlist_metrics(missing):
            await cache_set(f"wl_metrics:{row['symbol']}", row, ttl_seconds=300)
            out.append(row)

    order = {s: i for i, s in enumerate(syms)}
    return sorted(out, key=lambda r: order.get(r["symbol"], 999))
