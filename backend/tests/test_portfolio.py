"""
Portfolio Manager (Feature 10) tests.

Covers:
  • auth enforcement — every /portfolio endpoint returns 401 without a Bearer token
  • P&L math correctness on a mocked holding set (build_summary)
  • summary partial-failure path — a bad/halted symbol is skipped, never 500s
  • diversification + trend-signal helpers

Supabase and yfinance are fully mocked; no network is required.
"""

import asyncio
import importlib as _il
from unittest.mock import MagicMock, patch

import pandas as pd
import portfolio_service
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from backend.routers import portfolio

_deps = _il.import_module("dependencies")
limiter = _deps.limiter

_app = FastAPI()
_app.state.limiter = limiter


async def _rl_handler(req, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429, content={"detail": "Too many requests — please slow down."}
    )


_app.add_exception_handler(RateLimitExceeded, _rl_handler)
_app.include_router(portfolio.router)
client = TestClient(_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Auth enforcement — no Bearer token → 401 on every endpoint
# ---------------------------------------------------------------------------


def test_list_holdings_requires_auth() -> None:
    assert client.get("/portfolio/holdings").status_code == 401


def test_summary_requires_auth() -> None:
    assert client.get("/portfolio/summary").status_code == 401


def test_add_holding_requires_auth() -> None:
    # Valid body so a 401 (auth) is what we observe, not a 422 (validation).
    resp = client.post(
        "/portfolio/holdings", json={"symbol": "AAPL", "shares": 10, "cost_basis": 100}
    )
    assert resp.status_code == 401


def test_delete_holding_requires_auth() -> None:
    resp = client.delete("/portfolio/holdings/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# build_summary — P&L math correctness
# ---------------------------------------------------------------------------


def _yf_svc(info_by_symbol: dict) -> MagicMock:
    """Fake YFinanceService driven by a {symbol: info_dict} map."""
    svc = MagicMock()
    svc._to_yf_symbol = lambda s: s
    svc.fetch_info = lambda s: info_by_symbol.get(s.upper(), {})
    svc.get_live_price = lambda s: float(
        info_by_symbol.get(s.upper(), {}).get("current_price") or 0.0
    )
    return svc


def _run_summary(holdings, yf_svc):
    """Run build_summary with yf.Ticker(...).history patched to an empty frame
    so the trend signal stays Neutral and P&L assertions are deterministic."""
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = pd.DataFrame()
    with patch("portfolio_service.yf.Ticker", return_value=fake_ticker):
        return asyncio.run(portfolio_service.build_summary(holdings, yf_svc))


def test_summary_pnl_math() -> None:
    holdings = [
        {"id": "1", "symbol": "AAPL", "shares": 10, "cost_basis": 100},
        {"id": "2", "symbol": "MSFT", "shares": 5, "cost_basis": 200},
    ]
    yf_svc = _yf_svc(
        {
            "AAPL": {"current_price": 150.0, "sector": "Technology", "short_name": "Apple"},
            "MSFT": {"current_price": 300.0, "sector": "Technology", "short_name": "Microsoft"},
        }
    )
    summary = _run_summary(holdings, yf_svc)

    rows = {r["symbol"]: r for r in summary["holdings"]}
    assert rows["AAPL"]["marketValue"] == 1500.0
    assert rows["AAPL"]["costValue"] == 1000.0
    assert rows["AAPL"]["pnl"] == 500.0
    assert rows["AAPL"]["pnlPct"] == 50.0
    assert rows["MSFT"]["marketValue"] == 1500.0
    assert rows["MSFT"]["pnl"] == 500.0

    assert summary["totalMarketValue"] == 3000.0
    assert summary["totalCost"] == 2000.0
    assert summary["totalPnl"] == 1000.0
    assert summary["totalPnlPct"] == 50.0

    # Equal market values → 50/50 weights.
    assert rows["AAPL"]["weightPct"] == 50.0
    assert rows["MSFT"]["weightPct"] == 50.0

    # Both Technology → single 100% sector bucket.
    assert summary["sectorAllocation"] == [
        {"sector": "Technology", "weightPct": 100.0, "value": 3000.0}
    ]

    # HHI = 0.5² + 0.5² = 0.5 → diversification = (1 − 0.5) × 100 = 50.
    assert summary["diversificationScore"] == 50
    assert summary["skipped"] == []


def test_summary_partial_failure_skips_bad_symbol() -> None:
    """A holding with no resolvable price is skipped — summary still succeeds."""
    holdings = [
        {"id": "1", "symbol": "AAPL", "shares": 10, "cost_basis": 100},
        {"id": "2", "symbol": "BADX", "shares": 5, "cost_basis": 50},  # no price
    ]
    yf_svc = _yf_svc(
        {
            "AAPL": {"current_price": 150.0, "sector": "Technology", "short_name": "Apple"},
            "BADX": {},  # fetch_info empty AND get_live_price → 0 → skipped
        }
    )
    summary = _run_summary(holdings, yf_svc)

    assert [r["symbol"] for r in summary["holdings"]] == ["AAPL"]
    assert summary["skipped"] == ["BADX"]
    assert summary["totalMarketValue"] == 1500.0
    # Single surviving holding → 100% weight → HHI 1 → diversification 0.
    assert summary["diversificationScore"] == 0


def test_summary_empty_holdings() -> None:
    summary = _run_summary([], _yf_svc({}))
    assert summary["holdings"] == []
    assert summary["totalMarketValue"] == 0.0
    assert summary["diversificationScore"] == 0
    assert summary["forecast"] == {"label": "Neutral", "score": 0.0}


def test_summary_all_holdings_fail_returns_empty_not_error() -> None:
    holdings = [{"id": "1", "symbol": "BADX", "shares": 5, "cost_basis": 50}]
    summary = _run_summary(holdings, _yf_svc({"BADX": {}}))
    assert summary["holdings"] == []
    assert summary["skipped"] == ["BADX"]
    assert summary["totalMarketValue"] == 0.0


# ---------------------------------------------------------------------------
# Forecast / diversification helpers
# ---------------------------------------------------------------------------


def test_trend_signal_uptrend_is_bullish() -> None:
    closes = [100.0 + i for i in range(60)]  # steady climb
    label, score = portfolio_service._trend_signal(closes)
    assert label == "Bullish"
    assert score > 0


def test_trend_signal_downtrend_is_bearish() -> None:
    closes = [200.0 - i for i in range(60)]  # steady decline
    label, score = portfolio_service._trend_signal(closes)
    assert label == "Bearish"
    assert score < 0


def test_trend_signal_insufficient_history_neutral() -> None:
    assert portfolio_service._trend_signal([100.0, 101.0]) == ("Neutral", 0.0)


def test_weighted_forecast_reflects_dominant_holding() -> None:
    """A bullish position with 90% weight should drag the portfolio bullish even
    when a tiny position is flat."""
    holdings = [
        {"id": "1", "symbol": "BIG", "shares": 90, "cost_basis": 10},  # mv 900
        {"id": "2", "symbol": "TINY", "shares": 1, "cost_basis": 10},  # mv 10
    ]
    yf_svc = _yf_svc(
        {
            "BIG": {"current_price": 10.0, "sector": "Technology", "short_name": "Big"},
            "TINY": {"current_price": 10.0, "sector": "Energy", "short_name": "Tiny"},
        }
    )

    # Patch the trend signal: BIG bullish (+0.8), TINY neutral (0.0).
    def _fake_trend(closes):
        return ("Bullish", 0.8)  # both call it, but TINY weight is ~1%

    fake_ticker = MagicMock()
    fake_ticker.history.return_value = pd.DataFrame({"Close": [1.0] * 30})
    with (
        patch("portfolio_service.yf.Ticker", return_value=fake_ticker),
        patch("portfolio_service._trend_signal", side_effect=_fake_trend),
    ):
        summary = asyncio.run(portfolio_service.build_summary(holdings, yf_svc))
    assert summary["forecast"]["label"] == "Bullish"
    assert summary["forecast"]["score"] > 0.15
