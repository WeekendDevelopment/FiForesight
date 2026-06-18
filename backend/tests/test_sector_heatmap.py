"""
Sector heatmap endpoint tests (F23) — GET /sectors/heatmap.
yf.download is mocked; no network required.
"""
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from backend.routers import market
from backend.routers.market import SECTOR_ETF_MAP

_FIELDS = ["Open", "High", "Low", "Close", "Volume"]


@pytest.fixture(autouse=True)
def _no_cache():
    """Force the Redis cache inert so the endpoint's cache (sectors:heatmap:f23)
    can't leak between tests and skip the patched yf.download. The endpoint imports
    cache_get/cache_set from redis_cache, which short-circuit when get_redis() is None."""
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


def _grouped_frame(empty_etf: str | None = None, all_empty: bool = False) -> pd.DataFrame:
    """A 6-row yfinance-style frame with MultiIndex (ticker, field) columns."""
    etfs = list(SECTOR_ETF_MAP.values())
    cols = pd.MultiIndex.from_product([etfs, _FIELDS])
    frame = pd.DataFrame(index=range(6), columns=cols, dtype="float64")
    for etf in etfs:
        empty = all_empty or etf == empty_etf
        closes = [None] * 6 if empty else [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        for field in _FIELDS:
            frame[(etf, field)] = closes
    return frame


def test_sector_heatmap_returns_11_sectors() -> None:
    with patch("backend.routers.market.yf.download", return_value=_grouped_frame()):
        resp = client.get("/sectors/heatmap")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 11
    for row in rows:
        assert "sector" in row and "etf" in row and "return1d" in row
        assert isinstance(row["return1d"], (int, float))
        assert row["source"] == "yfinance"


def test_sector_heatmap_skips_bad_ticker() -> None:
    bad = SECTOR_ETF_MAP["Technology"]  # XLK returns all-NaN closes
    with patch("backend.routers.market.yf.download", return_value=_grouped_frame(empty_etf=bad)):
        resp = client.get("/sectors/heatmap")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 10
    assert all(row["etf"] != bad for row in rows)


def test_sector_heatmap_all_empty_returns_502() -> None:
    # Structurally-valid download but no usable rows for any ETF => upstream failure.
    with patch("backend.routers.market.yf.download", return_value=_grouped_frame(all_empty=True)):
        resp = client.get("/sectors/heatmap")
    assert resp.status_code == 502
