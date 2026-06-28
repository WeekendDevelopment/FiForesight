"""
Earnings Calendar endpoint tests (issue #283) — GET /earnings/calendar.

yfinance is fully mocked (no network). Covers:
  - MU (and other added semis) is in the watchlist.
  - calendar=None falls back to get_earnings_dates → ticker still appears.
  - one bad ticker is skipped, the rest of the batch still returns.
"""
from collections.abc import Generator
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from backend.routers import market


class _FakeFastInfo:
    def __init__(self, market_cap: float = 1_000e9) -> None:
        self.market_cap = market_cap


class _FakeTicker:
    """Mimics the slice of yf.Ticker the endpoint touches."""

    def __init__(
        self,
        calendar: object | None = None,
        earnings_dates: "pd.DataFrame | None" = None,
        raise_on: str | None = None,
    ) -> None:
        self._calendar = calendar
        self._earnings_dates = earnings_dates
        self._raise_on = raise_on
        self.fast_info = _FakeFastInfo()

    @property
    def calendar(self) -> object | None:
        if self._raise_on == "calendar":
            raise RuntimeError("yfinance boom")
        return self._calendar

    def get_earnings_dates(self, limit: int = 8) -> "pd.DataFrame":
        if self._earnings_dates is None:
            raise RuntimeError("no earnings dates for this ticker")
        return self._earnings_dates


@pytest.fixture(autouse=True)
def _no_cache() -> Generator[None, None, None]:
    """Inert Redis so the endpoint always runs the (mocked) fetch."""
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


def _symbols_in(payload: dict) -> set[str]:
    out: set[str] = set()
    for entries in payload["calendar"].values():
        for e in entries:
            out.add(e["symbol"])
    return out


def test_mu_in_watchlist() -> None:
    # Issue #283: MU (and the added semis) must be fetched.
    assert "MU" in market.EARNINGS_NAMES
    assert "MU" in market.EARNINGS_WATCHLIST
    for sym in ("LRCX", "KLAC", "ADI", "PANW", "SNPS", "CDNS"):
        assert sym in market.EARNINGS_NAMES


def test_calendar_fallback_to_earnings_dates() -> None:
    future = pd.Timestamp.now().normalize() + pd.Timedelta(days=10)
    df = pd.DataFrame(index=pd.DatetimeIndex([future]), data={"EPS Estimate": [1.23]})
    # calendar is None, but get_earnings_dates carries a future date.
    fake = _FakeTicker(calendar=None, earnings_dates=df)

    client = _build_app()
    with patch.object(market, "EARNINGS_WATCHLIST", ["MU"]), \
            patch.object(market.yf, "Ticker", return_value=fake):
        resp = client.get("/earnings/calendar")

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert "MU" in _symbols_in(payload)
    assert future.strftime("%Y-%m-%d") in payload["calendar"]


def test_fallback_ignores_past_only_dates() -> None:
    # earnings_dates carries only past dates → no upcoming date → ticker dropped,
    # never surfaced under a stale date key.
    past = pd.Timestamp.now().normalize() - pd.Timedelta(days=30)
    df = pd.DataFrame(index=pd.DatetimeIndex([past]), data={"EPS Estimate": [1.0]})
    fake = _FakeTicker(calendar=None, earnings_dates=df)

    client = _build_app()
    with patch.object(market, "EARNINGS_WATCHLIST", ["MU"]), \
            patch.object(market.yf, "Ticker", return_value=fake):
        resp = client.get("/earnings/calendar")

    assert resp.status_code == 200, resp.text
    assert resp.json()["calendar"] == {}


def test_bad_ticker_skipped() -> None:
    good = _FakeTicker(calendar={"Earnings Date": ["2026-07-15"]})
    bad = _FakeTicker(raise_on="calendar")

    def _factory(symbol: str) -> _FakeTicker:
        return bad if symbol == "BADX" else good

    client = _build_app()
    with patch.object(market, "EARNINGS_WATCHLIST", ["GOODX", "BADX"]), \
            patch.object(market.yf, "Ticker", side_effect=_factory):
        resp = client.get("/earnings/calendar")

    assert resp.status_code == 200, resp.text
    symbols = _symbols_in(resp.json())
    assert "GOODX" in symbols      # batch survived the bad ticker
    assert "BADX" not in symbols
