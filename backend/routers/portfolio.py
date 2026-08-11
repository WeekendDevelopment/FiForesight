# backend/routers/portfolio.py
"""
Portfolio Manager (Feature 10) — a user's REAL holdings with live P&L.

Distinct from the /simulation "race" engine (a backtest simulator): these
endpoints persist actual positions in the Supabase `holdings` table and value
them against live prices. Every endpoint is auth-gated via `require_user`
(401 when unauthenticated). Holdings are read/written through Supabase PostgREST
using the caller's own forwarded JWT, so Row-Level Security scopes all access to
`auth.uid() = user_id`.

Endpoints:
  GET    /portfolio/holdings       — list the user's holdings
  POST   /portfolio/holdings       — add or update a holding (upsert by symbol)
  DELETE /portfolio/holdings/{id}  — remove a holding (ownership enforced by RLS)
  GET    /portfolio/summary        — live P&L, sector allocation, diversification,
                                     portfolio forecast (Redis-cached 15 min)
"""

import logging
import re

import portfolio_service
import supabase_rest
from config import Config
from dependencies import _user_rate_key, limiter, require_user, yf_svc
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, field_validator
from redis_cache import cache_get, cache_set

router = APIRouter()
logger = logging.getLogger(__name__)

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-:]{1,15}$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_SUMMARY_TTL = 900  # 15 minutes

# Mirrors the CHECK constraint in supabase/migrations/0002_holdings_currency.sql.
# GBp = London Stock Exchange pence (yfinance native unit for LSE tickers).
_ALLOWED_CURRENCIES = frozenset(
    {
        "USD",
        "GBP",
        "GBp",
        "CAD",
        "AUD",
        "INR",
        "EUR",
        "JPY",
        "HKD",
        "SGD",
        "CHF",
        "SEK",
        "NOK",
        "DKK",
        "NZD",
        "ZAR",
        "BRL",
        "MXN",
        "KRW",
        "TWD",
        "CNY",
    }
)


def _bearer(authorization: str) -> str:
    """Extract the raw JWT. require_user already guarantees it's present+valid."""
    return authorization.removeprefix("Bearer ").strip()


def _summary_cache_key(user_id: str) -> str:
    return f"portfolio:summary:{user_id}"


def _handle_store_error(exc: Exception) -> HTTPException:
    """Map Supabase helper errors to clean HTTP errors (no traceback leakage)."""
    if isinstance(exc, supabase_rest.SupabaseConfigError):
        logger.error(
            "[PORTFOLIO] Supabase not configured — SUPABASE_URL / SUPABASE_ANON_KEY missing."
        )
        return HTTPException(status_code=503, detail="Portfolio storage is not configured.")
    if isinstance(exc, supabase_rest.SupabaseRestError):
        # Status 0 = network / connection error (httpx.HTTPError wrapped by supabase_rest).
        # Any other status = PostgREST responded with an error — migration not applied,
        # invalid JWT, or misconfigured URL are the most common causes.
        logger.error(
            "[PORTFOLIO] Supabase REST error (HTTP %s): %s — "
            "if HTTP 404/42P01, the holdings migration may not have been applied; "
            "if HTTP 0, the backend cannot reach SUPABASE_URL.",
            exc.status_code,
            exc,
        )
        return HTTPException(status_code=502, detail="Could not reach the holdings store.")
    logger.error("[PORTFOLIO] unexpected store error: %s", exc)
    return HTTPException(status_code=500, detail="An internal server error occurred.")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class HoldingCreate(BaseModel):
    symbol: str
    shares: float
    cost_basis: float
    currency: str = "USD"

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not _SYMBOL_RE.match(v):
            raise ValueError("Invalid symbol.")
        return v

    @field_validator("shares")
    @classmethod
    def _validate_shares(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("shares must be > 0")
        return v

    @field_validator("cost_basis")
    @classmethod
    def _validate_cost_basis(cls, v: float) -> float:
        if v < 0:
            raise ValueError("cost_basis must be >= 0")
        return v

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: str) -> str:
        v = (v or "USD").strip()
        if v not in _ALLOWED_CURRENCIES:
            raise ValueError(
                f"Unsupported currency '{v}'. Allowed: {', '.join(sorted(_ALLOWED_CURRENCIES))}"
            )
        return v


# ---------------------------------------------------------------------------
# Holdings CRUD
# ---------------------------------------------------------------------------


@router.get("/portfolio/holdings")
@limiter.limit(lambda: Config.RATE_LIMIT_PORTFOLIO, key_func=_user_rate_key)
async def list_holdings(
    request: Request,
    user_id: str = Depends(require_user),
    authorization: str = Header(default=""),
):
    try:
        holdings = await supabase_rest.list_holdings(_bearer(authorization))
    except Exception as exc:
        raise _handle_store_error(exc)
    return {"holdings": holdings}


@router.post("/portfolio/holdings")
@limiter.limit(lambda: Config.RATE_LIMIT_PORTFOLIO, key_func=_user_rate_key)
async def add_holding(
    request: Request,
    body: HoldingCreate,
    user_id: str = Depends(require_user),
    authorization: str = Header(default=""),
):
    try:
        row = await supabase_rest.upsert_holding(
            _bearer(authorization), body.symbol, body.shares, body.cost_basis, body.currency
        )
    except Exception as exc:
        raise _handle_store_error(exc)
    await _invalidate_summary(user_id)
    return {"holding": row}


@router.delete("/portfolio/holdings/{holding_id}")
@limiter.limit(lambda: Config.RATE_LIMIT_PORTFOLIO, key_func=_user_rate_key)
async def delete_holding(
    request: Request,
    holding_id: str,
    user_id: str = Depends(require_user),
    authorization: str = Header(default=""),
):
    if not _UUID_RE.match(holding_id):
        raise HTTPException(status_code=422, detail="Invalid holding id.")
    try:
        removed = await supabase_rest.delete_holding(_bearer(authorization), holding_id)
    except Exception as exc:
        raise _handle_store_error(exc)
    if not removed:
        # Either no such id, or RLS hid another user's row — same 404 either way.
        raise HTTPException(status_code=404, detail="Holding not found.")
    await _invalidate_summary(user_id)
    return {"deleted": True, "id": holding_id}


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


@router.get("/portfolio/summary")
@limiter.limit(lambda: Config.RATE_LIMIT_PORTFOLIO_SUMMARY, key_func=_user_rate_key)
async def portfolio_summary(
    request: Request,
    refresh: bool = False,
    user_id: str = Depends(require_user),
    authorization: str = Header(default=""),
):
    cache_key = _summary_cache_key(user_id)
    if not refresh:
        cached = await cache_get(cache_key)
        if cached:
            return cached

    try:
        holdings = await supabase_rest.list_holdings(_bearer(authorization))
    except Exception as exc:
        raise _handle_store_error(exc)

    summary = await portfolio_service.build_summary(holdings, yf_svc)
    # Only cache populated summaries — an empty result may just mean the user
    # hasn't added holdings yet, and we don't want to pin a transient yfinance
    # outage (all holdings skipped) for 15 minutes.
    if summary.get("holdings"):
        await cache_set(cache_key, summary, ttl_seconds=_SUMMARY_TTL)
    return summary


async def _invalidate_summary(user_id: str) -> None:
    """Drop the cached summary so the next read reflects the mutation."""
    try:
        from redis_cache import get_redis

        r = get_redis()
        if r is not None:
            await r.delete(_summary_cache_key(user_id))
    except Exception as exc:
        logger.debug("[PORTFOLIO] summary cache invalidation skipped: %s", exc)
