"""
/history endpoint tests — dynamic chart intervals.

yfinance, InfluxDB, and the Redis cache are all mocked; no network required.
"""
from unittest.mock import patch, AsyncMock, MagicMock

import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Lightweight app with only the history router — avoids the Redis lifespan in
# main.py while exercising the real validation + metric computation.
from backend.routers import history

_test_app = FastAPI()
_test_app.include_router(history.router)
client = TestClient(_test_app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv_df(rows: int, freq: str, start: str = "2026-01-02 09:30") -> pd.DataFrame:
    """OHLCV frame with a tz-aware UTC DatetimeIndex, shaped like a yfinance
    download result (single-level columns)."""
    idx  = pd.date_range(start, periods=rows, freq=freq, tz="UTC")
    base = np.linspace(100.0, 120.0, rows)
    return pd.DataFrame(
        {
            "Open":   base,
            "High":   base + 1.0,
            "Low":    base - 1.0,
            "Close":  base + 0.5,
            "Volume": np.full(rows, 1_000_000.0),
        },
        index=idx,
    )


def _cache_patches():
    """Force a cache miss and a no-op cache write."""
    return (
        patch("backend.routers.history.cache_get", AsyncMock(return_value=None)),
        patch("backend.routers.history.cache_set", AsyncMock(return_value=None)),
    )


# ---------------------------------------------------------------------------
# Shape + metrics
# ---------------------------------------------------------------------------

def test_history_intraday_shape_and_metrics() -> None:
    """1d/5m is intraday: skips InfluxDB, returns VWAP-bearing bars + stats."""
    df = _make_ohlcv_df(40, "5min")
    cg, cs = _cache_patches()
    with cg, cs, patch("yfinance.download", MagicMock(return_value=df)):
        resp = client.get("/history?symbol=aapl&period=1d&interval=5m")

    assert resp.status_code == 200
    d = resp.json()
    assert d["symbol"]   == "AAPL"   # uppercased
    assert d["period"]   == "1d"
    assert d["interval"] == "5m"
    assert len(d["history"]) == 40

    bar = d["history"][0]
    for key in ("date", "time", "price", "open", "high", "low", "volume", "rsi"):
        assert key in bar, f"missing bar key: {key}"
    # Intraday bars carry a per-bar VWAP.
    assert "vwap" in bar

    stats = d["stats"]
    for key in ("change_pct", "period_high", "period_low", "sma20", "ann_vol"):
        assert key in stats, f"missing stats key: {key}"
    assert stats["period_high"] >= stats["period_low"]
    assert isinstance(d["rsi_series"], list)


def test_history_daily_yfinance_fallback() -> None:
    """3mo/1d is daily: InfluxDB is consulted first; sparse data falls back to
    yfinance. Daily bars carry no VWAP."""
    df = _make_ohlcv_df(120, "D", start="2026-01-02")
    mock_influx = MagicMock()
    mock_influx.query_history.return_value = []   # below the min-rows threshold
    cg, cs = _cache_patches()
    with cg, cs, \
         patch("backend.routers.history.influx_svc", mock_influx), \
         patch("yfinance.download", MagicMock(return_value=df)):
        resp = client.get("/history?symbol=MSFT&period=3mo&interval=1d")

    assert resp.status_code == 200
    d = resp.json()
    assert d["interval"] == "1d"
    assert len(d["history"]) == 120
    assert "vwap" not in d["history"][0]
    mock_influx.query_history.assert_called_once()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_history_invalid_interval_for_period_returns_400() -> None:
    cg, cs = _cache_patches()
    with cg, cs:
        resp = client.get("/history?symbol=AAPL&period=1d&interval=1d")
    assert resp.status_code == 400


def test_history_invalid_period_returns_400() -> None:
    cg, cs = _cache_patches()
    with cg, cs:
        resp = client.get("/history?symbol=AAPL&period=10y&interval=1d")
    assert resp.status_code == 400


def test_history_empty_data_returns_404() -> None:
    cg, cs = _cache_patches()
    with cg, cs, patch("yfinance.download", MagicMock(return_value=pd.DataFrame())):
        resp = client.get("/history?symbol=ZZZZ&period=1d&interval=5m")
    assert resp.status_code == 404
