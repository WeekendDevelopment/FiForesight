"""
Rule-based strategy backtester tests (F28).

Service functions (_signals / _run) are exercised directly on synthetic DataFrames
(no network). The POST /backtest endpoint is tested with a mini app, run_backtest
patched, and Redis inert.
"""
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from backend import backtester_service as bt
from backend.routers import market


def _df(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2022-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"Close": closes}, index=idx)


# ── Service: simulation logic ─────────────────────────────────────────────────

def test_sma_cross_uptrend_profitable() -> None:
    closes = [100.0 + i for i in range(120)]  # monotonically rising
    df = _df(closes)
    in_pos = bt._signals(df, "sma_cross", {"fast": 20, "slow": 50})
    result = bt._run(df, in_pos)
    assert result["totalReturnPct"] > 0
    assert len(result["equityCurve"]) == len(closes)


def test_no_lookahead() -> None:
    # A signal that only fires on the LAST bar must contribute zero return,
    # because positions are entered on the bar AFTER the signal.
    closes = [100.0 + i for i in range(40)]
    df = _df(closes)
    in_pos = pd.Series([False] * 40, index=df.index)
    in_pos.iloc[-1] = True
    result = bt._run(df, in_pos)
    assert result["totalReturnPct"] == 0.0


def test_max_drawdown_negative_or_zero() -> None:
    closes = [100, 110, 95, 130, 80, 120, 105, 90, 140, 70] * 3
    df = _df([float(c) for c in closes])
    in_pos = pd.Series([True] * len(closes), index=df.index)
    result = bt._run(df, in_pos)
    assert result["maxDrawdownPct"] <= 0


def test_win_rate_and_trade_count() -> None:
    # in_pos shifts to held = [F,F,T,T,F,F,T,T,F,F] →
    #   trade 1: entry@close[2]=100 exit@close[4]=120  (win)
    #   trade 2: entry@close[6]=120 exit@close[8]=80   (loss)
    in_pos_vals = [False, True, True, False, False, True, True, False, False, False]
    closes = [100, 100, 100, 110, 120, 120, 120, 90, 80, 80]
    df = _df([float(c) for c in closes])
    in_pos = pd.Series(in_pos_vals, index=df.index)
    result = bt._run(df, in_pos)
    assert result["numTrades"] == 2
    assert result["winRatePct"] == 50.0


# ── Endpoint ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_cache() -> Generator[None, None, None]:
    """Inert Redis so the endpoint always runs the (mocked) backtest."""
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


def test_backtest_success_200() -> None:
    client = _build_app()
    payload = {
        "totalReturnPct": 12.34, "buyHoldReturnPct": 8.0, "cagrPct": 5.6,
        "winRatePct": 60.0, "numTrades": 5, "maxDrawdownPct": -10.0,
        "sharpe": 1.1, "equityCurve": [{"date": "2024-01-01", "strategy": 1.0, "buyHold": 1.0}],
    }
    with patch.object(market, "run_backtest", AsyncMock(return_value=payload)):
        resp = client.post("/backtest",
                           json={"symbol": "AAPL", "strategy": "sma_cross",
                                 "params": {"fast": 20, "slow": 50}, "period": "2y"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == payload
    assert set(body) >= {"totalReturnPct", "numTrades", "sharpe", "equityCurve"}


def test_unknown_strategy_422() -> None:
    client = _build_app()
    resp = client.post("/backtest", json={"symbol": "AAPL", "strategy": "bogus"})
    assert resp.status_code == 422


def test_insufficient_history_422() -> None:
    client = _build_app()
    with patch.object(market, "run_backtest",
                      AsyncMock(side_effect=ValueError("insufficient history"))):
        resp = client.post("/backtest",
                           json={"symbol": "AAPL", "strategy": "sma_cross"})
    assert resp.status_code == 422
    assert "insufficient history" in resp.json()["detail"]


def test_invalid_symbol_422() -> None:
    client = _build_app()
    resp = client.post("/backtest", json={"symbol": "@@@@", "strategy": "sma_cross"})
    assert resp.status_code == 422
