"""
Tests for Market Regime Intelligence (Feature 16):
  - RegimeService          (3-state Gaussian HMM detection + graceful fallback)
  - adjust_weights_for_regime (regime-adaptive ensemble weight tilt)
  - detect_dissent         (2-1 jury-split minority surfacing)

The real HMM-detection test requires hmmlearn (built wheel) and is skipped
where it isn't installed (e.g. a Python build with no prebuilt wheel). The
fallback / pure-function tests run everywhere — no network, no native deps.
"""
import asyncio
import math
from typing import Any, Coroutine
from unittest.mock import patch

import pytest

from backend.services import RegimeService
from backend.models import adjust_weights_for_regime, BASE_ENSEMBLE_WEIGHTS
from backend.jury_graph import detect_dissent


def run(coro: "Coroutine[Any, Any, Any]") -> Any:
    return asyncio.run(coro)


def _trending_series(n: int = 60, drift: float = 0.012) -> list:
    """Deterministic upward series with mild oscillation so both HMM features
    (log return + rolling vol) have non-degenerate variance."""
    out = []
    price = 100.0
    for i in range(n):
        price *= (1.0 + drift + 0.004 * math.sin(i))
        out.append(round(price, 4))
    return out


# ---------------------------------------------------------------------------
# RegimeService — HMM detection (needs hmmlearn)
# ---------------------------------------------------------------------------

class TestRegimeDetection:
    def test_trending_series_detects_trend(self):
        pytest.importorskip("hmmlearn")
        result = RegimeService()._detect(_trending_series())
        # A strong drift must land in a *trending* state — never ranging/unknown.
        assert result["regime"] in ("trending_up", "trending_down")
        assert result["regime"] == "trending_up"
        assert result["confidence"] > 0.5
        assert result["bars_in_current_regime"] >= 1
        assert "state_means" in result


# ---------------------------------------------------------------------------
# RegimeService — graceful fallbacks (run everywhere, no hmmlearn needed)
# ---------------------------------------------------------------------------

class TestRegimeFallbacks:
    def test_few_bars_returns_unknown(self):
        result = RegimeService()._detect([100.0 + i for i in range(20)])  # < 30
        assert result == {"regime": "unknown", "confidence": 0.0}

    def test_detection_failure_does_not_raise(self):
        # Force a failure deep in the fit path; must degrade to unknown, not raise.
        with patch("sklearn.preprocessing.StandardScaler", side_effect=RuntimeError("boom")):
            result = RegimeService()._detect(_trending_series())
        assert result["regime"] == "unknown"
        assert result["confidence"] == 0.0

    def test_get_regime_async_returns_dict(self):
        # No Redis configured in tests → cache is a no-op; still returns a dict.
        result = run(RegimeService().get_regime("AAPL", [100.0 + i for i in range(10)]))
        assert result["regime"] == "unknown"

    def test_get_regime_rejects_bad_symbol(self):
        result = run(RegimeService().get_regime('BAD" or 1==1', _trending_series()))
        assert result["regime"] == "unknown"


# ---------------------------------------------------------------------------
# Regime-adaptive ensemble weights
# ---------------------------------------------------------------------------

class TestRegimeWeights:
    def test_trending_boosts_sarima_at_full_confidence(self):
        w = adjust_weights_for_regime(BASE_ENSEMBLE_WEIGHTS, "trending_up", 1.0)
        assert abs(sum(w.values()) - 1.0) < 1e-9
        assert w["sarima"] > w["prophet"] and w["sarima"] > w["rf"]
        assert abs(w["sarima"] - 0.523) < 0.01   # 0.56 / 1.07 normalised

    def test_ranging_boosts_rf_at_full_confidence(self):
        w = adjust_weights_for_regime(BASE_ENSEMBLE_WEIGHTS, "ranging", 1.0)
        assert abs(sum(w.values()) - 1.0) < 1e-9
        assert w["rf"] > w["sarima"] and w["rf"] > w["prophet"]
        assert w["rf"] > 0.40   # boosted well above the 0.30 base

    def test_unknown_leaves_base_unchanged(self):
        w = adjust_weights_for_regime(BASE_ENSEMBLE_WEIGHTS, "unknown", 0.9)
        assert w == BASE_ENSEMBLE_WEIGHTS

    def test_zero_confidence_leaves_base_unchanged(self):
        w = adjust_weights_for_regime(BASE_ENSEMBLE_WEIGHTS, "trending_up", 0.0)
        assert w == BASE_ENSEMBLE_WEIGHTS

    def test_low_confidence_is_a_gentler_shift(self):
        full = adjust_weights_for_regime(BASE_ENSEMBLE_WEIGHTS, "trending_up", 1.0)
        half = adjust_weights_for_regime(BASE_ENSEMBLE_WEIGHTS, "trending_up", 0.5)
        # SARIMA boosted, but less so than at full confidence.
        assert BASE_ENSEMBLE_WEIGHTS["sarima"] < half["sarima"] < full["sarima"]

    def test_failed_model_stays_zero(self):
        # A model the ensemble zeroed out (failed) must not be revived by the tilt.
        base = {"prophet": 0.5, "sarima": 0.5, "rf": 0.0}
        w = adjust_weights_for_regime(base, "ranging", 1.0)
        assert w["rf"] == 0.0


# ---------------------------------------------------------------------------
# Jury dissent detection
# ---------------------------------------------------------------------------

def _verdict(pid: str, rating: str, *, model: str = "groq", note: str = "rationale") -> dict:
    return {
        "id": pid, "title": f"{pid} Lens", "rating": rating,
        "note": note, "confidence": 60, "model": model,
    }


class TestDissent:
    def test_two_one_split_surfaces_minority(self):
        verdicts = [
            _verdict("A", "Buy"),
            _verdict("B", "Accumulate"),                 # same bullish bucket as Buy
            _verdict("C", "Sell", note="yield inversion suggests downside"),
        ]
        d = detect_dissent(verdicts)
        assert d is not None
        assert d["verdict"] == "Sell"
        assert d["analyst"] == "C Lens"
        assert "inversion" in d["rationale"]

    def test_unanimous_has_no_dissent(self):
        verdicts = [_verdict("A", "Buy"), _verdict("B", "Buy"), _verdict("C", "Strong Buy")]
        assert detect_dissent(verdicts) is None

    def test_three_way_split_has_no_dissent(self):
        verdicts = [_verdict("A", "Buy"), _verdict("B", "Hold"), _verdict("C", "Sell")]
        assert detect_dissent(verdicts) is None

    def test_failed_analyst_suppresses_dissent(self):
        verdicts = [
            _verdict("A", "Buy"),
            _verdict("B", "Buy"),
            _verdict("C", "Hold", model="error"),        # fallback, not real dissent
        ]
        assert detect_dissent(verdicts) is None

    def test_incomplete_jury_has_no_dissent(self):
        assert detect_dissent([_verdict("A", "Buy"), _verdict("B", "Sell")]) is None
        assert detect_dissent([]) is None
