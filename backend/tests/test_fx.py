# backend/tests/test_fx.py
"""Currency-aware price display (Feature 35) — FX rate service tests.

Offline: yfinance is patched at ``fx.yf``; Redis is inert in tests (no pool →
``cache_get`` returns None, ``cache_set`` no-ops), with explicit patches where
a test asserts cache behaviour.
"""
import asyncio
from typing import Any, Coroutine
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

import fx
from routers.predict import PredictionResponse, _resolve_currency


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


def _hist(close: float) -> pd.DataFrame:
    return pd.DataFrame({"Close": [close]})


def _ticker_returning(close: float) -> MagicMock:
    t = MagicMock()
    t.history.return_value = _hist(close)
    return t


# ── get_usd_rate ─────────────────────────────────────────────────────────────

def test_usd_identity() -> None:
    """USD (and missing currency) short-circuit to 1.0 without any fetch."""
    with patch.object(fx.yf, "Ticker") as ticker:
        assert _run(fx.get_usd_rate("USD")) == 1.0
        assert _run(fx.get_usd_rate(None)) == 1.0
        assert _run(fx.get_usd_rate("")) == 1.0
        ticker.assert_not_called()


def test_gbp_pence_scaling() -> None:
    """GBp is a minor unit: GBPUSD=1.27 → one penny ≈ $0.0127."""
    with patch.object(fx.yf, "Ticker", return_value=_ticker_returning(1.27)) as ticker:
        rate = _run(fx.get_usd_rate("GBp"))
    assert rate == pytest.approx(0.0127)
    ticker.assert_called_once_with("GBPUSD=X")


def test_plain_currency() -> None:
    """Major-unit currencies use the raw pair close: EURUSD=1.08 → 1.08."""
    with patch.object(fx.yf, "Ticker", return_value=_ticker_returning(1.08)) as ticker:
        rate = _run(fx.get_usd_rate("EUR"))
    assert rate == pytest.approx(1.08)
    ticker.assert_called_once_with("EURUSD=X")


def test_failure_returns_none() -> None:
    """A fetch failure yields None (degrade to native display) and caches nothing."""
    boom = MagicMock()
    boom.history.side_effect = RuntimeError("yfinance down")
    with patch.object(fx.yf, "Ticker", return_value=boom), \
         patch("redis_cache.cache_set", new=AsyncMock()) as cache_set:
        assert _run(fx.get_usd_rate("EUR")) is None
        cache_set.assert_not_called()


def test_empty_history_returns_none() -> None:
    """An empty price frame (delisted pair) also yields None, not a crash."""
    with patch.object(fx.yf, "Ticker", return_value=_ticker_returning(0)) as ticker:
        ticker.return_value.history.return_value = pd.DataFrame()
        assert _run(fx.get_usd_rate("XYZ")) is None


def test_cache_hit_skips_fetch() -> None:
    """A cached rate is returned without touching yfinance."""
    with patch("redis_cache.cache_get", new=AsyncMock(return_value={"rate": 0.5})), \
         patch.object(fx.yf, "Ticker") as ticker:
        assert _run(fx.get_usd_rate("GBp")) == 0.5
        ticker.assert_not_called()


# ── /predict payload plumbing ────────────────────────────────────────────────

def _minimal_response(**overrides: object) -> PredictionResponse:
    base = dict(
        symbol="BP.L", currentPrice="516.50", rsi="55.00",
        prediction={"highRange": "520.00", "lowRange": "510.00", "trend": "Neutral"},
        analystNote="n", confidence="medium", history=[], forecastDays=[],
        modelStats={}, metrics={}, news=[], trending=[], indicators={},
        lastUpdated="2026-01-01T00:00:00", juryAnalysts=[], modelWeights={},
        sentiment={},
    )
    base.update(overrides)
    return PredictionResponse(**base)


def test_predict_payload_carries_currency() -> None:
    """metrics['currency'] → (currency, fxToUsd) → serialised /predict fields."""
    with patch("routers.predict.get_usd_rate", new=AsyncMock(return_value=0.0127)):
        currency, fx_to_usd = _run(_resolve_currency({"currency": "GBp"}))
    assert currency == "GBp"
    assert fx_to_usd == pytest.approx(0.0127)

    data = _minimal_response(currency=currency, fxToUsd=fx_to_usd).model_dump()
    assert data["currency"] == "GBp"
    assert data["fxToUsd"] == pytest.approx(0.0127)


def test_resolve_currency_defaults_to_usd() -> None:
    """Missing / N/A currency (failed fetch_info) resolves to USD @ 1.0."""
    for metrics in ({}, {"currency": "N/A"}, {"currency": None}):
        currency, fx_to_usd = _run(_resolve_currency(metrics))
        assert currency == "USD"
        assert fx_to_usd == 1.0


def test_resolve_currency_swallows_fx_errors() -> None:
    """An unexpected get_usd_rate crash degrades to fxToUsd=None, never raises."""
    with patch("routers.predict.get_usd_rate", new=AsyncMock(side_effect=RuntimeError("x"))):
        currency, fx_to_usd = _run(_resolve_currency({"currency": "EUR"}))
    assert currency == "EUR"
    assert fx_to_usd is None


def test_predict_response_defaults() -> None:
    """Fields default to USD / None so older cached payloads stay valid."""
    data = _minimal_response().model_dump()
    assert data["currency"] == "USD"
    assert data["fxToUsd"] is None
