"""
Smart Watchlist Columns — GET /watchlist/metrics tests.
watchlist_metrics_service.fetch_watchlist_metrics is mocked; no network.
Redis pool is not initialised in tests, so cache_get/cache_set are inert no-ops
(mirrors test_watchlist.py's documented behaviour).

Coverage:
  • metrics shape — returns price/peRatio/rsi/pctFrom52wHigh/marketCap/etc per symbol
  • a symbol whose fetch fails is omitted, the rest still returned (never 500)
  • >30 symbols are capped; invalid symbol chars are filtered out
  • no symbols → [] without calling the fetcher
"""
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from backend.routers import watchlist

_app = FastAPI()
_app.state.limiter = watchlist.limiter


async def _rl_handler(req, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Too many requests."})


_app.add_exception_handler(RateLimitExceeded, _rl_handler)
_app.include_router(watchlist.router)

client = TestClient(_app, raise_server_exceptions=False)

_AAPL = {
    "symbol": "AAPL", "price": 150.0, "changePct": 1.2, "peRatio": 28.5,
    "rsi": 55.0, "pctFrom52wHigh": -5.25, "marketCap": 2_500_000_000_000,
    "nextEarnings": "2025-01-30",
}
_MSFT = {
    "symbol": "MSFT", "price": 400.0, "changePct": -0.8, "peRatio": 32.0,
    "rsi": 48.0, "pctFrom52wHigh": -2.1, "marketCap": 3_000_000_000_000,
    "nextEarnings": "2025-01-28",
}


def test_metrics_shape() -> None:
    with patch.object(watchlist, "fetch_watchlist_metrics",
                       AsyncMock(return_value=[_AAPL, _MSFT])):
        resp = client.get("/watchlist/metrics?symbols=AAPL,MSFT")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    row = next(r for r in data if r["symbol"] == "AAPL")
    for key in ("price", "changePct", "peRatio", "rsi", "pctFrom52wHigh", "marketCap", "nextEarnings"):
        assert key in row


def test_bad_symbol_skipped() -> None:
    """One symbol's fetch fails (service returns only the survivor) → no 500."""
    with patch.object(watchlist, "fetch_watchlist_metrics",
                       AsyncMock(return_value=[_MSFT])):
        resp = client.get("/watchlist/metrics?symbols=BADTICKERX,MSFT")
    assert resp.status_code == 200
    data = resp.json()
    symbols = [r["symbol"] for r in data]
    assert "MSFT" in symbols
    assert "BADTICKERX" not in symbols


def test_symbol_cap_and_validation() -> None:
    """>30 symbols are trimmed to 30; invalid characters are filtered before fetch."""
    many = [f"S{i}" for i in range(40)]
    called_with: list[str] = []

    async def _fake(symbols: list[str]) -> list[dict]:
        called_with.extend(symbols)
        return [{"symbol": s, "price": 1.0, "changePct": None, "peRatio": None,
                  "rsi": None, "pctFrom52wHigh": None, "marketCap": None,
                  "nextEarnings": None} for s in symbols]

    with patch.object(watchlist, "fetch_watchlist_metrics", side_effect=_fake):
        resp = client.get(f"/watchlist/metrics?symbols={','.join(many)},BAD SYMBOL!")
    assert resp.status_code == 200
    assert len(called_with) <= 30
    assert "BAD SYMBOL!" not in called_with


def test_empty_symbols_returns_empty_list() -> None:
    with patch.object(watchlist, "fetch_watchlist_metrics", AsyncMock()) as mocked:
        resp = client.get("/watchlist/metrics?symbols=")
    assert resp.status_code == 200
    assert resp.json() == []
    mocked.assert_not_called()
