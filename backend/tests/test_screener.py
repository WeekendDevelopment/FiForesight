"""
Equity Screener endpoint tests (F24) — POST /screener.
build_universe_snapshot is mocked with a fixed 10-row universe; no network.
"""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from backend.routers import market

# 10 fake rows spanning a few sectors with varied PE / RSI / beta / cap.
_FAKE_UNIVERSE = [
    {
        "symbol": "AAA",
        "name": "Alpha",
        "sector": "Technology",
        "marketCap": 3_000e9,
        "peRatio": 35.0,
        "forwardPE": 30.0,
        "beta": 1.2,
        "dividendYield": 0.5,
        "revenueGrowth": 12.0,
        "rsi": 55.0,
        "price": 100.0,
    },
    {
        "symbol": "BBB",
        "name": "Bravo",
        "sector": "Technology",
        "marketCap": 2_000e9,
        "peRatio": 28.0,
        "forwardPE": 24.0,
        "beta": 1.1,
        "dividendYield": None,
        "revenueGrowth": 8.0,
        "rsi": 45.0,
        "price": 200.0,
    },
    {
        "symbol": "CCC",
        "name": "Charlie",
        "sector": "Technology",
        "marketCap": 1_500e9,
        "peRatio": 50.0,
        "forwardPE": 40.0,
        "beta": 1.5,
        "dividendYield": 0.2,
        "revenueGrowth": 20.0,
        "rsi": 72.0,
        "price": 300.0,
    },
    {
        "symbol": "DDD",
        "name": "Delta",
        "sector": "Financial",
        "marketCap": 500e9,
        "peRatio": 12.0,
        "forwardPE": 11.0,
        "beta": 0.9,
        "dividendYield": 2.5,
        "revenueGrowth": 4.0,
        "rsi": 30.0,
        "price": 50.0,
    },
    {
        "symbol": "EEE",
        "name": "Echo",
        "sector": "Financial",
        "marketCap": 400e9,
        "peRatio": 10.0,
        "forwardPE": 9.0,
        "beta": 1.0,
        "dividendYield": 3.0,
        "revenueGrowth": 2.0,
        "rsi": 41.0,
        "price": 40.0,
    },
    {
        "symbol": "FFF",
        "name": "Foxtrot",
        "sector": "Healthcare",
        "marketCap": 700e9,
        "peRatio": 18.0,
        "forwardPE": 16.0,
        "beta": 0.7,
        "dividendYield": 1.5,
        "revenueGrowth": 6.0,
        "rsi": 60.0,
        "price": 120.0,
    },
    {
        "symbol": "GGG",
        "name": "Golf",
        "sector": "Healthcare",
        "marketCap": 300e9,
        "peRatio": 22.0,
        "forwardPE": 19.0,
        "beta": 0.8,
        "dividendYield": 1.0,
        "revenueGrowth": 5.0,
        "rsi": 48.0,
        "price": 80.0,
    },
    {
        "symbol": "HHH",
        "name": "Hotel",
        "sector": "Energy",
        "marketCap": 250e9,
        "peRatio": 9.0,
        "forwardPE": 8.5,
        "beta": 1.3,
        "dividendYield": 4.0,
        "revenueGrowth": -2.0,
        "rsi": 25.0,
        "price": 60.0,
    },
    {
        "symbol": "III",
        "name": "India",
        "sector": "Energy",
        "marketCap": 200e9,
        "peRatio": None,
        "forwardPE": 7.0,
        "beta": 1.4,
        "dividendYield": 4.5,
        "revenueGrowth": -5.0,
        "rsi": None,
        "price": 55.0,
    },
    {
        "symbol": "JJJ",
        "name": "Juliet",
        "sector": "Consumer",
        "marketCap": 600e9,
        "peRatio": 26.0,
        "forwardPE": 23.0,
        "beta": 0.6,
        "dividendYield": 0.8,
        "revenueGrowth": 7.0,
        "rsi": 58.0,
        "price": 150.0,
    },
]


@pytest.fixture(autouse=True)
def _no_cache() -> Generator[None, None, None]:
    """Inert Redis so the endpoint always calls the (mocked) snapshot builder."""
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


def _post(client: TestClient, body: dict) -> dict:
    with patch.object(
        market, "build_universe_snapshot", AsyncMock(return_value=list(_FAKE_UNIVERSE))
    ):
        resp = client.post("/screener", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_screener_filters_by_sector() -> None:
    client = _build_app()
    data = _post(client, {"sector": "Technology", "limit": 25})
    assert len(data["results"]) == 3
    assert all(r["sector"] == "Technology" for r in data["results"])
    assert data["total"] == 3


def test_screener_filters_by_rsi() -> None:
    client = _build_app()
    data = _post(client, {"minRSI": 40, "maxRSI": 60, "limit": 25})
    assert len(data["results"]) > 0
    assert all(40 <= r["rsi"] <= 60 for r in data["results"])
    # Rows with rsi=None must be excluded.
    assert all(r["rsi"] is not None for r in data["results"])


def test_screener_sort_desc() -> None:
    client = _build_app()
    data = _post(client, {"sortBy": "marketCap", "sortDir": "desc", "limit": 25})
    caps = [r["marketCap"] for r in data["results"]]
    assert caps[0] >= caps[-1]
    assert caps == sorted(caps, reverse=True)


def test_screener_limit() -> None:
    client = _build_app()
    data = _post(client, {"limit": 5})
    assert len(data["results"]) <= 5
    # total reflects the full post-filter count, not the capped page.
    assert data["total"] == len(_FAKE_UNIVERSE)
