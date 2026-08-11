"""
Sector rotation endpoint tests (F27) — GET /sectors/rotation.
yf.download is mocked; no network required.
"""

from collections.abc import Generator
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from backend.routers import market
from backend.routers.market import SECTOR_ETF_MAP

_FIELDS = ["Open", "High", "Low", "Close", "Volume"]
_N = 140  # enough rows for the 126-bar (6M) lookback


@pytest.fixture(autouse=True)
def _no_cache() -> Generator[None, None, None]:
    """Force the Redis cache inert so the endpoint's cache (sectors:rotation:f27)
    can't leak between tests and skip the patched yf.download."""
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


def _ramp(total_return_pct: float) -> list[float]:
    """A monotonic close series from 100 to 100*(1+total_return_pct/100) over _N bars."""
    end = 100.0 * (1 + total_return_pct / 100.0)
    return list(np.linspace(100.0, end, _N))


def _frame(
    series_by_ticker: dict[str, list[float] | None], drop: str | None = None
) -> pd.DataFrame:
    """A grouped yfinance-style frame (MultiIndex [ticker, field]).

    `series_by_ticker` maps ticker -> close list (or None for all-NaN).
    `drop` omits that ticker's columns entirely (simulates a dropped batch member).
    """
    tickers = [t for t in series_by_ticker if t != drop]
    cols = pd.MultiIndex.from_product([tickers, _FIELDS])
    frame = pd.DataFrame(index=range(_N), columns=cols, dtype="float64")
    for t in tickers:
        closes = series_by_ticker[t]
        vals = [np.nan] * _N if closes is None else closes
        for field in _FIELDS:
            frame[(t, field)] = vals
    return frame


def test_rotation_computes_relative_strength() -> None:
    # SPY flat-ish; XLK strongly outperforms, XLE underperforms.
    leader = SECTOR_ETF_MAP["Technology"]  # XLK
    laggard = SECTOR_ETF_MAP["Energy"]  # XLE
    series = {etf: _ramp(5.0) for etf in SECTOR_ETF_MAP.values()}
    series["SPY"] = _ramp(5.0)
    series[leader] = _ramp(25.0)
    series[laggard] = _ramp(-10.0)

    with patch("backend.routers.market.yf.download", return_value=_frame(series)):
        resp = client.get("/sectors/rotation")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == len(SECTOR_ETF_MAP)

    by_etf = {r["etf"]: r for r in rows}
    assert by_etf[leader]["rs_1m"] > 0
    assert by_etf[laggard]["rs_1m"] < 0
    # Sorted by rs_1m desc → strongest outperformer first, weakest last.
    assert rows[0]["etf"] == leader
    assert rows[-1]["etf"] == laggard
    # SPY is the benchmark, never an output row.
    assert all(r["etf"] != "SPY" for r in rows)


def test_quadrant_classification() -> None:
    rows = [
        {"rs_3m": 5.0, "rs_momentum": 2.0, "quadrant": "leading"},
        {"rs_3m": 5.0, "rs_momentum": -2.0, "quadrant": "weakening"},
        {"rs_3m": -5.0, "rs_momentum": 2.0, "quadrant": "improving"},
        {"rs_3m": -5.0, "rs_momentum": -2.0, "quadrant": "lagging"},
    ]
    for case in rows:
        level, mom = case["rs_3m"], case["rs_momentum"]
        # Mirrors the endpoint's classification; the guards after the first branch
        # are deliberately reduced (the static analyzer flags the implied ones).
        if level >= 0 and mom >= 0:
            q = "leading"
        elif level >= 0:
            q = "weakening"
        elif mom >= 0:
            q = "improving"
        else:
            q = "lagging"
        assert q == case["quadrant"]


def test_quadrant_classification_endpoint() -> None:
    """Drive each quadrant through the real endpoint by shaping rs_3m / rs_momentum.

    SPY is a flat constant series (1M/3M/6M returns all 0), so for each ETF
    rs_1m == its own 1M return and rs_3m == its own 3M return, and
    rs_momentum == rs_1m − rs_3m. We pin the close at the 1M and 3M lookback
    anchors (bars −22 and −64) with last close = 100 to hit exact returns.
    """
    series: dict[str, list[float] | None] = {}
    # SPY flat over every window → RS == the ETF's own returns.
    series["SPY"] = [100.0] * _N

    def _shaped(r1: float, r3: float) -> list[float]:
        s = [100.0] * _N
        s[-1] = 100.0
        s[-22] = 100.0 / (1 + r1 / 100.0)  # r1 = (last/anchor − 1)·100
        s[-64] = 100.0 / (1 + r3 / 100.0)
        return s

    # leading: level>0, momentum>=0  (r1 >= r3 > 0)
    series[SECTOR_ETF_MAP["Technology"]] = _shaped(8.0, 4.0)
    # weakening: level>0, momentum<0  (0 < r1 < r3)
    series[SECTOR_ETF_MAP["Healthcare"]] = _shaped(2.0, 6.0)
    # improving: level<0, momentum>=0  (r3 < 0, r1 >= r3)
    series[SECTOR_ETF_MAP["Energy"]] = _shaped(-2.0, -6.0)
    # lagging: level<0, momentum<0  (r1 < r3 < 0)
    series[SECTOR_ETF_MAP["Utilities"]] = _shaped(-8.0, -4.0)

    # Remaining sectors get a flat series so they don't interfere.
    for etf in SECTOR_ETF_MAP.values():
        series.setdefault(etf, [100.0] * _N)

    with patch("backend.routers.market.yf.download", return_value=_frame(series)):
        resp = client.get("/sectors/rotation")
    assert resp.status_code == 200
    by_etf = {r["etf"]: r for r in resp.json()}
    assert by_etf[SECTOR_ETF_MAP["Technology"]]["quadrant"] == "leading"
    assert by_etf[SECTOR_ETF_MAP["Healthcare"]]["quadrant"] == "weakening"
    assert by_etf[SECTOR_ETF_MAP["Energy"]]["quadrant"] == "improving"
    assert by_etf[SECTOR_ETF_MAP["Utilities"]]["quadrant"] == "lagging"


def test_missing_etf_skipped() -> None:
    dropped = SECTOR_ETF_MAP["Industrials"]  # XLI omitted from the batch entirely
    series = {etf: _ramp(5.0) for etf in SECTOR_ETF_MAP.values()}
    series["SPY"] = _ramp(5.0)

    with patch("backend.routers.market.yf.download", return_value=_frame(series, drop=dropped)):
        resp = client.get("/sectors/rotation")
    assert resp.status_code == 200
    rows = resp.json()
    assert all(r["etf"] != dropped for r in rows)
    assert len(rows) == len(SECTOR_ETF_MAP) - 1


def test_total_failure_502() -> None:
    with patch("backend.routers.market.yf.download", side_effect=RuntimeError("boom")):
        resp = client.get("/sectors/rotation")
    assert resp.status_code == 502


def test_empty_rows_502() -> None:
    # Download succeeds structurally but every series is too short for the 1M
    # lookback (len < 22), so no sector yields a row → empty result → 502.
    tickers = list(SECTOR_ETF_MAP.values()) + ["SPY"]
    cols = pd.MultiIndex.from_product([tickers, _FIELDS])
    short = pd.DataFrame(index=range(10), columns=cols, dtype="float64")
    for t in tickers:
        for field in _FIELDS:
            short[(t, field)] = list(np.linspace(100.0, 105.0, 10))

    with patch("backend.routers.market.yf.download", return_value=short):
        resp = client.get("/sectors/rotation")
    assert resp.status_code == 502
