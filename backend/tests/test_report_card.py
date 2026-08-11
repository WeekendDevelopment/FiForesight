"""
Stock Report Card endpoint tests (F31) — GET /report-card/{symbol}.
yfinance is mocked (no network); Redis is inert so the endpoint always fetches.
Mirrors the mocking style of test_dividends.py / test_analyst_targets_endpoint.py.
"""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from backend.routers import market


@pytest.fixture(autouse=True)
def _no_cache() -> Generator[None, None, None]:
    """Inert Redis so every call hits the (mocked) yfinance fetch."""
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


def _mock_ticker(info: dict) -> MagicMock:
    t = MagicMock()
    t.info = info
    return t


def test_strong_company_high_grade() -> None:
    client = _build_app()
    info = {
        "trailingPE": 12,
        "priceToBook": 2,
        "pegRatio": 0.8,
        "revenueGrowth": 0.20,
        "earningsGrowth": 0.30,
        "profitMargins": 0.25,
        "returnOnEquity": 0.30,
        "currentPrice": 95,
        "fiftyTwoWeekHigh": 100,
        "fiftyTwoWeekLow": 50,
        "debtToEquity": 30,
        "currentRatio": 2.5,
    }
    with patch.object(market.yf, "Ticker", return_value=_mock_ticker(info)):
        resp = client.get("/report-card/AAA")
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["symbol"] == "AAA"
    assert d["overall"] is not None and d["overall"] >= 80
    assert d["grade"] in ("A", "B")
    for cat in d["categories"].values():
        assert cat is not None


def test_weak_company_low_grade() -> None:
    client = _build_app()
    info = {
        "trailingPE": 90,
        "priceToBook": 15,
        "pegRatio": 4,
        "revenueGrowth": -0.20,
        "earningsGrowth": -0.30,
        "profitMargins": -0.10,
        "returnOnEquity": -0.20,
        "currentPrice": 55,
        "fiftyTwoWeekHigh": 100,
        "fiftyTwoWeekLow": 50,
        "debtToEquity": 300,
        "currentRatio": 0.3,
    }
    with patch.object(market.yf, "Ticker", return_value=_mock_ticker(info)):
        resp = client.get("/report-card/BBB")
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["overall"] is not None and d["overall"] <= 35
    assert d["grade"] in ("D", "F")


def test_missing_fields_partial() -> None:
    client = _build_app()
    # Only value/growth-relevant fields present — profitability/momentum/health
    # inputs are entirely absent, so those categories must degrade to null
    # without a 500.
    info = {"trailingPE": 20, "revenueGrowth": 0.05}
    with patch.object(market.yf, "Ticker", return_value=_mock_ticker(info)):
        resp = client.get("/report-card/CCC")
    assert resp.status_code == 200, resp.text
    d = resp.json()
    cats = d["categories"]
    assert cats["value"] is not None
    assert cats["growth"] is not None
    assert cats["profitability"] is None
    assert cats["momentum"] is None
    assert cats["financialHealth"] is None
    assert d["overall"] is not None


def test_missing_info_all_null() -> None:
    client = _build_app()
    with patch.object(market.yf, "Ticker", return_value=_mock_ticker({})):
        resp = client.get("/report-card/DDD")
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["overall"] is None
    assert d["grade"] is None
    assert all(v is None for v in d["categories"].values())


def test_invalid_symbol_422() -> None:
    client = _build_app()
    resp = client.get("/report-card/not_a_symbol!!!")
    assert resp.status_code == 422
