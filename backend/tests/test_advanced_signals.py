"""Feature 14 — Advanced Technical Signals.

Covers ATR, Stochastic, ADX, OBV, RSI/MACD divergence, RF feature importance,
and the earnings-surprise graceful-degradation path.
"""
import numpy as np
import pytest

from backend.models import (
    MODELS_AVAILABLE,
    calculate_atr, calculate_stochastic, calculate_adx, calculate_obv,
    detect_divergences, run_ensemble_forecast, classify_trend,
    detect_candle_patterns,
)


# ── ATR ──────────────────────────────────────────────────────────────────────

def test_atr_constant_true_range():
    """Flat closes with a constant 2.0 high-low range → ATR == 2.0."""
    highs  = [102.0] * 30
    lows   = [100.0] * 30
    closes = [101.0] * 30
    atr = calculate_atr(highs, lows, closes, period=14)
    assert atr is not None
    assert abs(atr - 2.0) < 0.01


def test_atr_insufficient_data_returns_none():
    assert calculate_atr([1, 2], [1, 2], [1, 2], period=14) is None


def test_atr_mismatched_lengths_returns_none():
    assert calculate_atr([1, 2, 3], [1, 2], [1, 2, 3]) is None


# ── Stochastic ───────────────────────────────────────────────────────────────

def test_stochastic_known_fixture():
    """Close at the top of a flat range → %K == 100."""
    highs  = [10.0] * 20
    lows   = [0.0] * 20
    closes = [5.0] * 19 + [10.0]   # last close at the high
    out = calculate_stochastic(highs, lows, closes, k_period=14, d_period=3)
    assert out["stoch_k"] is not None
    assert abs(out["stoch_k"] - 100.0) < 0.01


def test_stochastic_bottom_of_range():
    highs  = [10.0] * 20
    lows   = [0.0] * 20
    closes = [5.0] * 19 + [0.0]    # last close at the low
    out = calculate_stochastic(highs, lows, closes)
    assert out["stoch_k"] is not None
    assert abs(out["stoch_k"] - 0.0) < 0.01


def test_stochastic_insufficient_data():
    out = calculate_stochastic([1, 2], [1, 2], [1, 2])
    assert out == {"stoch_k": None, "stoch_d": None}


# ── ADX ──────────────────────────────────────────────────────────────────────

def test_adx_strong_uptrend_high():
    """A clean, monotone uptrend should yield a high ADX (strong trend)."""
    closes = [100.0 + i for i in range(60)]
    highs  = [c + 1 for c in closes]
    lows   = [c - 1 for c in closes]
    out = calculate_adx(highs, lows, closes, period=14)
    assert out["adx_14"] is not None
    assert out["plus_di"] is not None and out["minus_di"] is not None
    # In a pure uptrend +DI dominates −DI and the trend is strong.
    assert out["plus_di"] > out["minus_di"]
    assert out["adx_14"] > 25


def test_adx_insufficient_data():
    out = calculate_adx([1, 2, 3], [1, 2, 3], [1, 2, 3])
    assert out == {"adx_14": None, "plus_di": None, "minus_di": None}


# ── OBV ──────────────────────────────────────────────────────────────────────

def test_obv_accumulates_on_up_days():
    closes  = [10.0, 11.0, 12.0, 13.0]   # all up days
    volumes = [100.0, 100.0, 100.0, 100.0]
    obv = calculate_obv(closes, volumes, history=30)
    assert obv is not None
    # First bar contributes 0 (no prior close); then +100 ×3.
    assert obv[-1] == 300.0


def test_obv_history_capped():
    closes  = list(range(1, 60))
    volumes = [1.0] * 59
    obv = calculate_obv([float(c) for c in closes], volumes, history=30)
    assert obv is not None
    assert len(obv) == 30


def test_obv_mismatched_lengths_returns_none():
    assert calculate_obv([1, 2, 3], [1, 2]) is None


# ── Divergence ───────────────────────────────────────────────────────────────

def _bullish_div_inputs():
    closes = [100.0] * 40
    rsi    = [50.0] * 40
    for i in range(20, 40):
        closes[i] = 110.0
        rsi[i]    = 55.0
    closes[25], closes[33] = 95.0, 90.0   # price: lower low
    rsi[25],    rsi[33]    = 30.0, 40.0    # rsi:   higher low
    return closes, rsi


def test_divergence_bullish_detected():
    closes, rsi = _bullish_div_inputs()
    out = detect_divergences(closes, rsi, [0.0] * 40)
    assert out["rsi_bullish"] is True
    assert out["rsi_bearish"] is False


def test_divergence_bearish_detected():
    closes = [100.0] * 40
    rsi    = [50.0] * 40
    for i in range(20, 40):
        closes[i] = 90.0
        rsi[i]    = 45.0
    closes[25], closes[33] = 105.0, 110.0  # price: higher high
    rsi[25],    rsi[33]    = 70.0, 60.0    # rsi:   lower high
    out = detect_divergences(closes, rsi, [0.0] * 40)
    assert out["rsi_bearish"] is True
    assert out["rsi_bullish"] is False


def test_divergence_flat_series_all_false():
    closes = [100.0] * 40
    out = detect_divergences(closes, [50.0] * 40, [0.0] * 40)
    assert out == {
        "rsi_bullish": False, "rsi_bearish": False,
        "macd_bullish": False, "macd_bearish": False,
    }


def test_divergence_insufficient_bars_all_false():
    out = detect_divergences([1.0, 2.0, 3.0], [50.0, 51.0, 52.0], [0.0, 0.0, 0.0])
    assert out == {
        "rsi_bullish": False, "rsi_bearish": False,
        "macd_bullish": False, "macd_bearish": False,
    }


# ── RF feature importance ────────────────────────────────────────────────────

@pytest.mark.skipif(not MODELS_AVAILABLE, reason="ML models unavailable in this environment")
@pytest.mark.parametrize("seed", [0, 1])
def test_rf_feature_importance_sorted_and_normalised(seed):
    """run_ensemble_forecast exposes top-5 RF importances, sorted, summing ~1.0."""
    rng = np.random.default_rng(seed)
    n = 120
    closes = list(100.0 + np.cumsum(rng.normal(0, 1, n)))
    opens  = [c - 0.2 for c in closes]
    highs  = [c + 1.0 for c in closes]
    lows   = [c - 1.0 for c in closes]
    vols   = list(1_000_000 + rng.integers(0, 100_000, n).astype(float))

    result = run_ensemble_forecast(
        closes, "TEST", opens=opens, highs=highs, lows=lows, volumes=vols
    )
    imp = result.get("rf_feature_importance", [])
    # On this clean fixture with models available, RF should fit and report
    # importances — assert non-empty so a regression can't silently pass.
    assert imp, "Expected non-empty rf_feature_importance on clean fixture"
    assert len(imp) <= 5
    importances = [d["importance"] for d in imp]
    assert importances == sorted(importances, reverse=True)
    # Normalised to 1.0; tolerance covers 4-decimal rounding of 5 terms.
    assert abs(sum(importances) - 1.0) < 1e-3
    for d in imp:
        assert isinstance(d["feature"], str) and d["feature"]


# ── Earnings surprise (graceful degradation) ─────────────────────────────────

def test_fetch_earnings_surprise_graceful_on_none(monkeypatch):
    from backend import services
    svc = services.YFinanceService()

    class _FakeTicker:
        earnings_history = None

    monkeypatch.setattr(services, "yf", type("YF", (), {"Ticker": staticmethod(lambda t: _FakeTicker())}))
    monkeypatch.setattr(services, "YFINANCE_AVAILABLE", True)
    assert svc.fetch_earnings_surprise("AAPL") == []


def test_fetch_earnings_surprise_graceful_on_raise(monkeypatch):
    from backend import services
    svc = services.YFinanceService()

    def _boom(_t):
        raise RuntimeError("network down")

    monkeypatch.setattr(services, "yf", type("YF", (), {"Ticker": staticmethod(_boom)}))
    monkeypatch.setattr(services, "YFINANCE_AVAILABLE", True)
    assert svc.fetch_earnings_surprise("AAPL") == []


# == classify_trend (composite trend label) =================================

def test_classify_trend_all_bullish():
    """Price > SMA50 > SMA200, positive slope, MACD > signal → Bullish."""
    assert classify_trend(
        price=110.0, sma50=105.0, sma200=100.0,
        trend_slope=0.5, macd=1.2, macd_signal=0.8, rsi=58.0,
    ) == "Bullish"


def test_classify_trend_all_bearish():
    assert classify_trend(
        price=90.0, sma50=95.0, sma200=100.0,
        trend_slope=-0.5, macd=0.4, macd_signal=0.9, rsi=42.0,
    ) == "Bearish"


def test_classify_trend_mixed_is_neutral():
    """Long-term up (price>SMA200, SMA50>SMA200) but short-term down (slope<0,
    MACD<signal) and a mid RSI → honestly Neutral, not forced to a side."""
    label = classify_trend(
        price=101.0, sma50=100.0, sma200=98.0,
        trend_slope=-0.3, macd=0.2, macd_signal=0.5, rsi=50.0,
    )
    assert label == "Neutral"


def test_classify_trend_mixed_rsi_breaks_tie_when_stretched():
    """Same mixed structure, but a stretched RSI tips the neutral band."""
    assert classify_trend(
        price=101.0, sma50=100.0, sma200=98.0,
        trend_slope=-0.3, macd=0.2, macd_signal=0.5, rsi=65.0,
    ) == "Bullish"
    assert classify_trend(
        price=101.0, sma50=100.0, sma200=98.0,
        trend_slope=-0.3, macd=0.2, macd_signal=0.5, rsi=35.0,
    ) == "Bearish"


def test_classify_trend_no_structure_falls_back_to_rsi():
    """With no SMAs/slope/MACD, the legacy RSI>50 rule is the floor (never empty)."""
    assert classify_trend(
        price=100.0, sma50=None, sma200=None,
        trend_slope=None, macd=None, macd_signal=None, rsi=55.0,
    ) == "Bullish"
    assert classify_trend(
        price=100.0, sma50=None, sma200=None,
        trend_slope=None, macd=None, macd_signal=None, rsi=45.0,
    ) == "Bearish"


# == detect_candle_patterns (daily candle confirmation) =====================

def test_candle_bullish_engulfing():
    # prior bearish (100→96), last bullish body engulfs it (95→102)
    op = [100.0, 95.0]
    hi = [101.0, 103.0]
    lo = [95.0, 94.0]
    cl = [96.0, 102.0]
    out = detect_candle_patterns(op, hi, lo, cl)
    assert out and out["pattern"] == "Bullish Engulfing" and out["direction"] == "bullish"


def test_candle_bearish_engulfing():
    # prior bullish (100→104), last bearish body engulfs it (105→99)
    op = [100.0, 105.0]
    hi = [105.0, 106.0]
    lo = [99.0, 98.0]
    cl = [104.0, 99.0]
    out = detect_candle_patterns(op, hi, lo, cl)
    assert out and out["pattern"] == "Bearish Engulfing" and out["direction"] == "bearish"


def test_candle_hammer():
    # last bar: small body near top, long lower wick (lower >= 2x body)
    op = [100.0, 100.0]
    hi = [101.0, 101.5]
    lo = [98.0, 96.0]
    cl = [99.0, 101.0]
    out = detect_candle_patterns(op, hi, lo, cl)
    assert out and out["pattern"] == "Hammer" and out["direction"] == "bullish"


def test_candle_shooting_star():
    # last bar: small body near bottom, long upper wick (upper >= 2x body).
    # prior bar bearish so the engulfing checks don't fire first.
    op = [105.0, 101.0]
    hi = [106.0, 106.0]
    lo = [99.0, 99.5]
    cl = [100.0, 100.0]
    out = detect_candle_patterns(op, hi, lo, cl)
    assert out and out["pattern"] == "Shooting Star" and out["direction"] == "bearish"


def test_candle_inside_bar():
    # last range contained in prior; not engulfing/hammer/star → Inside Bar (neutral)
    op = [100.0, 98.0]
    hi = [110.0, 105.0]
    lo = [90.0, 95.0]
    cl = [108.0, 102.0]
    out = detect_candle_patterns(op, hi, lo, cl)
    assert out and out["pattern"] == "Inside Bar" and out["direction"] == "neutral"


def test_candle_none_when_no_pattern():
    op = [100.0, 100.5]
    hi = [110.0, 110.5]
    lo = [90.0, 90.2]
    cl = [100.2, 100.4]
    assert detect_candle_patterns(op, hi, lo, cl) is None


def test_candle_insufficient_or_mismatched_returns_none():
    assert detect_candle_patterns([100.0], [101.0], [99.0], [100.0]) is None
    assert detect_candle_patterns([100.0, 101.0], [101.0], [99.0], [100.0, 101.0]) is None
