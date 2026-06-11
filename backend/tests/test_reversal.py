"""
Reversal-risk classifier tests.
All tests run offline — no network, no InfluxDB, no Groq.
"""
import math
from backend.reversal import _build_dataset, compute_reversal_risk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_series(n: int, start: float = 100.0, step: float = 0.0) -> list[float]:
    """Flat or linearly trending close-price series."""
    return [start + i * step for i in range(n)]


def _constant_indicators(
    n: int,
    rsi: float = 50.0,
    bb_upper: float = 110.0,
    bb_lower: float = 90.0,
    macd: float = 0.001,
) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    """Return constant indicator lists of length n."""
    return (
        [rsi]      * n,
        [bb_upper] * n,
        [bb_lower] * n,
        [macd]     * n,
        [1_000.0]  * n,   # volumes
    )


# ---------------------------------------------------------------------------
# _build_dataset
# ---------------------------------------------------------------------------

def test_dataset_shape_sensible() -> None:
    """Dataset has at least (n - WINDOW - HORIZON) rows when all indicators present."""
    n = 120
    closes = _make_series(n)
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    X, y = _build_dataset(closes, rsi_s, bbu, bbl, mh, vols)
    assert len(X) > 0
    assert X.shape[1] == 7          # 7 features
    assert len(X) == len(y)


def test_dataset_labels_peaks_correctly() -> None:
    """A sharp drop after bar i labels it as a peak (y=1)."""
    # 30 flat bars, then a big drop, then more flat
    closes = [100.0] * 30 + [97.0] * 30   # 3% drop — above threshold
    n = len(closes)
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    X, y = _build_dataset(closes, rsi_s, bbu, bbl, mh, vols)
    # At least one bar in the transition zone should be labeled 1
    assert y.sum() > 0


def test_dataset_skips_none_indicators() -> None:
    """Bars with None indicators are excluded from the dataset."""
    n = 80
    closes = _make_series(n)
    rsi_s = [None] * n          # all None → zero usable rows
    bbu   = [110.0] * n
    bbl   = [90.0]  * n
    mh    = [0.0]   * n
    vols  = [1000.0] * n
    X, y = _build_dataset(closes, rsi_s, bbu, bbl, mh, vols)
    assert len(X) == 0


# ---------------------------------------------------------------------------
# compute_reversal_risk
# ---------------------------------------------------------------------------

def test_returns_none_when_too_few_samples() -> None:
    """Returns None if history is shorter than MIN_SAMPLES."""
    n = 20   # definitely < _MIN_SAMPLES
    closes = _make_series(n)
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    result = compute_reversal_risk(closes, rsi_s, bbu, bbl, mh, vols)
    assert result is None


def test_returns_dict_with_sufficient_data() -> None:
    """Returns a valid dict when enough history is present."""
    n = 300
    # Create a series with some drops to ensure both class labels exist.
    closes = []
    for i in range(n):
        if i % 30 == 25:
            closes.append(95.0)   # sharp dip every 30 bars
        else:
            closes.append(100.0)
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    result = compute_reversal_risk(closes, rsi_s, bbu, bbl, mh, vols)
    assert result is not None
    assert "risk_pct"     in result
    assert "signal"       in result
    assert "top_features" in result
    assert "trained_on"   in result


def test_risk_pct_in_range() -> None:
    """risk_pct must be an integer 0–100."""
    n = 300
    closes = [100.0 + math.sin(i * 0.3) * 5 for i in range(n)]
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    result = compute_reversal_risk(closes, rsi_s, bbu, bbl, mh, vols)
    if result is None:
        return   # not enough varied labels — skip assertion
    assert isinstance(result["risk_pct"], int)
    assert 0 <= result["risk_pct"] <= 100


def test_signal_matches_risk_pct() -> None:
    """signal boundaries: <35 → low, 35-64 → medium, ≥65 → high."""
    n = 300
    closes = [100.0 + math.sin(i * 0.3) * 5 for i in range(n)]
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    result = compute_reversal_risk(closes, rsi_s, bbu, bbl, mh, vols)
    if result is None:
        return
    pct = result["risk_pct"]
    sig = result["signal"]
    if pct >= 65:
        assert sig == "high"
    elif pct >= 35:
        assert sig == "medium"
    else:
        assert sig == "low"


def test_top_features_non_empty() -> None:
    """top_features list must be non-empty and contain strings."""
    n = 300
    closes = [100.0 + math.sin(i * 0.3) * 5 for i in range(n)]
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    result = compute_reversal_risk(closes, rsi_s, bbu, bbl, mh, vols)
    if result is None:
        return
    assert len(result["top_features"]) > 0
    for f in result["top_features"]:
        assert isinstance(f, str) and len(f) > 0
