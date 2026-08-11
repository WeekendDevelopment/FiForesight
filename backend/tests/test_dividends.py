"""
Dividend & Income endpoint tests (F26) — GET /dividends/{symbol}.
yfinance is mocked (no network); Redis is inert so the endpoint always fetches.
Mirrors the mocking style of test_screener.py / test_alternative_data.py.
"""

from collections.abc import Generator
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
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


def _two_year_div_series() -> pd.Series:
    """A dividend series spanning ~2 years: $0.40/qtr last year, $0.50/qtr this year.
    Trailing-12mo = 2.0, prior-12mo = 1.6 → +25% growth."""
    idx = pd.to_datetime(
        [
            "2024-03-15",
            "2024-06-15",
            "2024-09-15",
            "2024-12-15",  # prior 12mo: 1.6
            "2025-03-15",
            "2025-06-15",
            "2025-09-15",
            "2025-12-15",  # last 12mo: 2.0
        ]
    )
    return pd.Series([0.40] * 4 + [0.50] * 4, index=idx)


def _mock_ticker(info: dict, divs: pd.Series | None = None) -> MagicMock:
    t = MagicMock()
    t.info = info
    t.dividends = divs if divs is not None else pd.Series(dtype=float)
    return t


def test_dividend_payer_shape() -> None:
    client = _build_app()
    ex_ts = int(datetime(2026, 1, 9, tzinfo=timezone.utc).timestamp())
    # yfinance (1.2.x) hands back dividendYield / fiveYearAvgDividendYield already
    # as percentages (KO ≈ 2.64 / 2.89); payoutRatio is a fraction (0.55 → 55%).
    info = {
        "dividendYield": 2.64,  # already percent → passes through
        "dividendRate": 2.0,
        "payoutRatio": 0.55,  # fraction → 55.0%
        "fiveYearAvgDividendYield": 2.89,
        "exDividendDate": ex_ts,
    }
    with patch.object(market.yf, "Ticker", return_value=_mock_ticker(info, _two_year_div_series())):
        resp = client.get("/dividends/KO")
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["symbol"] == "KO"
    assert d["paysDividend"] is True
    assert d["dividendYield"] == 2.64  # percent, not re-scaled
    assert d["dividendRate"] == 2.0
    assert d["payoutRatio"] == 55.0
    assert d["fiveYearAvgYield"] == 2.89
    assert d["exDividendDate"] == "2026-01-09"
    assert d["dividendGrowthPct"] == 25.0  # computed from the series


def test_non_payer() -> None:
    client = _build_app()
    info = {"dividendYield": None, "dividendRate": None}
    with patch.object(market.yf, "Ticker", return_value=_mock_ticker(info)):
        resp = client.get("/dividends/TSLA")
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["paysDividend"] is False
    assert d["dividendYield"] is None
    assert d["dividendRate"] is None
    assert d["payoutRatio"] is None
    assert d["dividendGrowthPct"] is None


def test_invalid_symbol_422() -> None:
    client = _build_app()
    resp = client.get("/dividends/not_a_symbol!!!")
    assert resp.status_code == 422


def test_nan_is_sanitized() -> None:
    client = _build_app()
    info = {
        "dividendYield": 0.03,
        "dividendRate": 1.5,
        "payoutRatio": float("nan"),  # must coerce to null, not 500
    }
    with patch.object(market.yf, "Ticker", return_value=_mock_ticker(info)):
        resp = client.get("/dividends/AAA")
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["paysDividend"] is True
    assert d["payoutRatio"] is None
