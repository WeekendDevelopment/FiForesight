"""
Market treemap endpoint tests (F32) — GET /market/treemap.
build_universe_snapshot + yf.download are mocked; no network.
"""
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from backend.routers import market

_FIELDS = ["Open", "High", "Low", "Close", "Volume"]

# 6 fake universe rows: one ETF proxy (SPY) and one row with no market cap —
# both must be excluded from the map.
_FAKE_UNIVERSE = [
    {"symbol": "CCC", "name": "Charlie", "sector": "Financial",  "marketCap": 500e9,   "price": 50.0},
    {"symbol": "AAA", "name": "Alpha",   "sector": "Technology", "marketCap": 3_000e9, "price": 100.0},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "sector": "—", "marketCap": 600e9,   "price": 500.0},
    {"symbol": "BBB", "name": "Bravo",   "sector": "Technology", "marketCap": 2_000e9, "price": 200.0},
    {"symbol": "EEE", "name": "Echo",    "sector": "Healthcare", "marketCap": None,    "price": 80.0},
    {"symbol": "DDD", "name": "Delta",   "sector": "Energy",     "marketCap": 250e9,   "price": 60.0},
]

_STOCKS = ["AAA", "BBB", "CCC", "DDD"]  # what survives the ETF/capless filter


@pytest.fixture(autouse=True)
def _no_cache() -> Generator[None, None, None]:
    """Inert Redis so the endpoint's caches (market:treemap, screener:universe)
    can't leak between tests and it always calls the patched builders."""
    with patch("redis_cache.get_redis", return_value=None):
        yield


def _build_app() -> TestClient:
    app = FastAPI()
    app.state.limiter = market.limiter

    async def _handler(req: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": "rate limited"})

    app.add_exception_handler(RateLimitExceeded, _handler)
    app.include_router(market.router)
    return TestClient(app)


client = _build_app()


def _grouped_frame(symbols: list[str]) -> pd.DataFrame:
    """A 5-row yfinance-style frame with MultiIndex (ticker, field) columns."""
    cols = pd.MultiIndex.from_product([symbols, _FIELDS])
    frame = pd.DataFrame(index=range(5), columns=cols, dtype="float64")
    for sym in symbols:
        closes = [100.0, 101.0, 102.0, 103.0, 104.0]
        for field in _FIELDS:
            frame[(sym, field)] = closes
    return frame


def _get(download_result: dict):
    """GET /market/treemap with a patched universe + yf.download.

    ``download_result`` is the kwargs for the yf.download patch, e.g.
    ``{"return_value": frame}`` or ``{"side_effect": RuntimeError(...)}``."""
    with patch.object(market, "build_universe_snapshot",
                      AsyncMock(return_value=list(_FAKE_UNIVERSE))), \
         patch("backend.routers.market.yf.download", **download_result):
        return client.get("/market/treemap")


def test_rows_shape_and_sorted() -> None:
    resp = _get({"return_value": _grouped_frame(_STOCKS)})
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [r["symbol"] for r in rows] == ["AAA", "BBB", "CCC", "DDD"]  # cap desc
    for row in rows:
        assert set(row) == {"symbol", "name", "sector", "marketCap", "changePct", "currency"}
        # 104/103 - 1 = +0.97%
        assert row["changePct"] == pytest.approx(0.97)


def test_etf_and_capless_excluded() -> None:
    resp = _get({"return_value": _grouped_frame(_STOCKS)})
    assert resp.status_code == 200
    symbols = {r["symbol"] for r in resp.json()}
    assert "SPY" not in symbols   # ETF proxy
    assert "EEE" not in symbols   # marketCap=None


def test_missing_price_symbol_kept_with_null_change() -> None:
    # DDD dropped from the download batch — still returned, changePct null.
    resp = _get({"return_value": _grouped_frame(["AAA", "BBB", "CCC"])})
    assert resp.status_code == 200
    rows = resp.json()
    by_symbol = {r["symbol"]: r for r in rows}
    assert "DDD" in by_symbol
    assert by_symbol["DDD"]["changePct"] is None
    assert by_symbol["AAA"]["changePct"] is not None


def test_total_failure_502() -> None:
    resp = _get({"side_effect": RuntimeError("yfinance down")})
    assert resp.status_code == 502
