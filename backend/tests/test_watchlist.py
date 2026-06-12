"""
Watchlist (Feature 13) + sparklines intraday-bars tests.
All external calls (Supabase, yfinance, Redis) are mocked; no network required.

Coverage:
  • auth enforcement — POST/DELETE require a Bearer token
  • anonymous GET returns [] without hitting Supabase
  • authenticated GET returns items from the (mocked) Supabase store
  • POST validation — invalid symbol chars → 422 before touching Supabase
  • POST success — upsert returns created item
  • DELETE 404 — symbol not in watchlist
  • DELETE 204 — symbol removed successfully
  • sparklines bars — /sparklines returns a list with {symbol, price, change_pct, bars}
  • sparklines partial failure — one symbol erroring out does not suppress the rest
  • sparklines extra param — ?extra= symbols are merged and deduplicated
"""
from unittest.mock import AsyncMock, patch
import importlib as _il

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from backend.routers import watchlist, predict

_deps = _il.import_module("dependencies")
require_user = _deps.require_user
limiter = _deps.limiter


# ---------------------------------------------------------------------------
# Shared rate-limit error handler (mirrors production)
# ---------------------------------------------------------------------------

async def _rl_handler(req, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Too many requests."})


# ---------------------------------------------------------------------------
# Anon test app — no dependency overrides, auth is enforced
# ---------------------------------------------------------------------------

_anon_app = FastAPI()
_anon_app.state.limiter = limiter
_anon_app.add_exception_handler(RateLimitExceeded, _rl_handler)
_anon_app.include_router(watchlist.router)

anon = TestClient(_anon_app, raise_server_exceptions=False)

# ---------------------------------------------------------------------------
# Auth-bypassed test app — require_user returns a fixed user_id
# ---------------------------------------------------------------------------

_auth_app = FastAPI()
_auth_app.state.limiter = limiter
_auth_app.add_exception_handler(RateLimitExceeded, _rl_handler)
_auth_app.include_router(watchlist.router)
_auth_app.dependency_overrides[require_user] = lambda: "test-user-uuid"

auth = TestClient(_auth_app, raise_server_exceptions=False)

# ---------------------------------------------------------------------------
# Sparklines test app — predict router only
# ---------------------------------------------------------------------------

_spark_app = FastAPI()
_spark_app.state.limiter = limiter
_spark_app.add_exception_handler(RateLimitExceeded, _rl_handler)
_spark_app.include_router(predict.router)

spark = TestClient(_spark_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Watchlist — auth enforcement
# ---------------------------------------------------------------------------

def test_watchlist_post_requires_auth() -> None:
    """POST /watchlist without a Bearer token → 401."""
    resp = anon.post("/watchlist", json={"symbol": "AAPL"})
    assert resp.status_code == 401


def test_watchlist_delete_requires_auth() -> None:
    """DELETE /watchlist/{symbol} without a Bearer token → 401."""
    resp = anon.delete("/watchlist/AAPL")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Watchlist — anonymous GET
# ---------------------------------------------------------------------------

def test_watchlist_get_anon_returns_empty() -> None:
    """GET /watchlist with no valid JWT → 200 {"watchlist": []}."""
    # get_user_id is called directly inside the handler (not via Depends).
    # Return empty string to simulate an anonymous caller.
    with patch("backend.routers.watchlist.get_user_id", return_value=""):
        resp = anon.get("/watchlist")
    assert resp.status_code == 200
    assert resp.json() == {"watchlist": []}


# ---------------------------------------------------------------------------
# Watchlist — authenticated GET
# ---------------------------------------------------------------------------

def test_watchlist_get_authed_returns_items() -> None:
    """GET /watchlist with a valid user → returns items from Supabase."""
    items = [
        {"id": "aa", "symbol": "AAPL", "added_at": "2025-01-01T00:00:00Z"},
        {"id": "bb", "symbol": "NVDA", "added_at": "2025-01-02T00:00:00Z"},
    ]
    # Redis pool is not initialised in tests → cache_get returns None (miss) and
    # cache_set is a no-op, so no mocking needed for cache helpers here.
    with (
        patch("backend.routers.watchlist.get_user_id", return_value="u-1"),
        patch("supabase_rest.list_watchlist", new_callable=AsyncMock, return_value=items),
    ):
        resp = auth.get("/watchlist", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200
    assert resp.json() == {"watchlist": items}


# ---------------------------------------------------------------------------
# Watchlist — POST (validation + success)
# ---------------------------------------------------------------------------

def test_watchlist_post_rejects_bad_symbol() -> None:
    """POST /watchlist with invalid symbol characters → 422 (Pydantic)."""
    resp = auth.post("/watchlist", json={"symbol": "BAD SYMBOL!"})
    assert resp.status_code == 422


def test_watchlist_post_rejects_empty_symbol() -> None:
    """POST /watchlist with empty symbol → 422."""
    resp = auth.post("/watchlist", json={"symbol": ""})
    assert resp.status_code == 422


def test_watchlist_post_accepts_valid_symbol() -> None:
    """POST /watchlist with a well-formed symbol → 200 with the created item."""
    created = {"id": "cc", "symbol": "TSLA", "added_at": "2025-01-03T00:00:00Z"}
    with patch("supabase_rest.upsert_watchlist", new_callable=AsyncMock, return_value=created):
        resp = auth.post(
            "/watchlist",
            json={"symbol": "TSLA"},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    assert resp.json()["item"]["symbol"] == "TSLA"


# ---------------------------------------------------------------------------
# Watchlist — DELETE
# ---------------------------------------------------------------------------

def test_watchlist_delete_not_found() -> None:
    """DELETE /watchlist/{symbol} when symbol is absent → 404."""
    with patch("supabase_rest.delete_watchlist_item", new_callable=AsyncMock, return_value=False):
        resp = auth.delete("/watchlist/AAPL", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 404


def test_watchlist_delete_found() -> None:
    """DELETE /watchlist/{symbol} when symbol exists → 204 No Content."""
    with patch("supabase_rest.delete_watchlist_item", new_callable=AsyncMock, return_value=True):
        resp = auth.delete("/watchlist/AAPL", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Sparklines — intraday bars
# ---------------------------------------------------------------------------

_BARS_AAPL = {
    "price": 150.0,
    "change_pct": 1.5,
    "bars": [
        {"t": "2025-01-01T14:30:00", "c": 148.0},
        {"t": "2025-01-01T20:00:00", "c": 150.0},
    ],
}

_BARS_MSFT = {
    "price": 400.0,
    "change_pct": -0.5,
    "bars": [
        {"t": "2025-01-01T14:30:00", "c": 402.0},
        {"t": "2025-01-01T20:00:00", "c": 400.0},
    ],
}

_BARS_NVDA = {
    "price": 500.0,
    "change_pct": 2.0,
    "bars": [
        {"t": "2025-01-01T14:30:00", "c": 490.0},
        {"t": "2025-01-01T20:00:00", "c": 500.0},
    ],
}


def test_sparklines_returns_bars() -> None:
    """GET /sparklines?tickers=AAPL → list containing bars for AAPL."""
    with patch("backend.routers.predict._fetch_intraday_bars", return_value=_BARS_AAPL):
        resp = spark.get("/sparklines?tickers=AAPL")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    item = data[0]
    assert item["symbol"] == "AAPL"
    assert item["price"] == 150.0
    assert item["change_pct"] == 1.5
    assert isinstance(item["bars"], list)
    assert len(item["bars"]) == 2
    assert item["bars"][0] == {"t": "2025-01-01T14:30:00", "c": 148.0}


def test_sparklines_partial_failure_returns_other_symbols() -> None:
    """If one symbol fails (_fetch_intraday_bars returns {}), the rest are still returned."""
    def _fake(sym: str) -> dict:
        return {} if sym == "AAPL" else _BARS_MSFT

    with patch("backend.routers.predict._fetch_intraday_bars", side_effect=_fake):
        resp = spark.get("/sparklines?tickers=AAPL,MSFT")
    assert resp.status_code == 200
    data = resp.json()
    symbols = [d["symbol"] for d in data]
    assert "AAPL" not in symbols
    assert "MSFT" in symbols
    msft = next(d for d in data if d["symbol"] == "MSFT")
    assert msft["price"] == 400.0
    assert len(msft["bars"]) == 2


def test_sparklines_extra_param_merged() -> None:
    """?extra=NVDA symbols are merged with ?tickers= and returned."""
    def _fake(sym: str) -> dict:
        if sym == "NVDA":
            return _BARS_NVDA
        return {}   # AAPL has no data

    with patch("backend.routers.predict._fetch_intraday_bars", side_effect=_fake):
        resp = spark.get("/sparklines?tickers=AAPL&extra=NVDA")
    assert resp.status_code == 200
    data = resp.json()
    symbols = [d["symbol"] for d in data]
    assert "NVDA" in symbols
    nvda = next(d for d in data if d["symbol"] == "NVDA")
    assert nvda["price"] == 500.0


def test_sparklines_deduplication() -> None:
    """A symbol appearing in both ?tickers= and ?extra= is only fetched once."""
    call_count = 0

    def _fake(sym: str) -> dict:
        nonlocal call_count
        call_count += 1
        return _BARS_AAPL

    with patch("backend.routers.predict._fetch_intraday_bars", side_effect=_fake):
        resp = spark.get("/sparklines?tickers=AAPL&extra=AAPL")
    assert resp.status_code == 200
    data = resp.json()
    # Deduplicated → only one AAPL entry and only one fetch call.
    aapl_items = [d for d in data if d["symbol"] == "AAPL"]
    assert len(aapl_items) == 1
    assert call_count == 1
