"""
Direction-forecast classifier tests.
All tests run offline — no network, no InfluxDB, no Groq.
"""
import math
from backend.direction import _build_direction_dataset, compute_direction_forecast


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_series(n: int, start: float = 100.0, step: float = 0.0) -> list[float]:
    """Flat or linearly trending close-price series."""
    return [start + i * step for i in range(n)]


def _sine_series(n: int, amplitude: float = 5.0) -> list[float]:
    """Oscillating series that produces both up and down labels."""
    return [100.0 + math.sin(i * 0.3) * amplitude for i in range(n)]


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
# _build_direction_dataset
# ---------------------------------------------------------------------------

def test_dataset_shape_sensible() -> None:
    """Dataset has rows and exactly 10 features when all indicators present."""
    n = 150
    closes = _sine_series(n)
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    X, y = _build_direction_dataset(closes, rsi_s, bbu, bbl, mh, vols)
    assert len(X) > 0
    assert X.shape[1] == 10
    assert len(X) == len(y)


def test_dataset_labels_both_classes() -> None:
    """An oscillating series produces both up and down labels."""
    n = 150
    closes = _sine_series(n)
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    _, y = _build_direction_dataset(closes, rsi_s, bbu, bbl, mh, vols)
    assert y.sum() > 0          # at least one "up" day
    assert (1 - y).sum() > 0    # at least one "down" day


def test_dataset_skips_none_indicators() -> None:
    """Bars with None RSI are excluded from the dataset."""
    n = 100
    closes = _sine_series(n)
    rsi_s = [None] * n
    bbu   = [110.0] * n
    bbl   = [90.0]  * n
    mh    = [0.001] * n
    vols  = [1000.0] * n
    X, y = _build_direction_dataset(closes, rsi_s, bbu, bbl, mh, vols)
    assert len(X) == 0


# ---------------------------------------------------------------------------
# compute_direction_forecast
# ---------------------------------------------------------------------------

def test_returns_none_when_too_few_samples() -> None:
    """Returns None when history is shorter than MIN_SAMPLES."""
    n = 30
    closes = _sine_series(n)
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    result = compute_direction_forecast(closes, rsi_s, bbu, bbl, mh, vols)
    assert result is None


def test_returns_dict_with_sufficient_data() -> None:
    """Returns a valid dict when enough history with both labels is present."""
    n = 300
    closes = _sine_series(n)
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    result = compute_direction_forecast(closes, rsi_s, bbu, bbl, mh, vols)
    assert result is not None
    assert "direction"      in result
    assert "confidence_pct" in result
    assert "edge_pct"       in result
    assert "top_features"   in result
    assert "trained_on"     in result


def test_direction_valid_value() -> None:
    """direction must be 'up' or 'down'."""
    n = 300
    closes = _sine_series(n)
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    result = compute_direction_forecast(closes, rsi_s, bbu, bbl, mh, vols)
    if result is None:
        return
    assert result["direction"] in ("up", "down")


def test_confidence_in_range() -> None:
    """confidence_pct must be an integer in [50, 100]."""
    n = 300
    closes = _sine_series(n)
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    result = compute_direction_forecast(closes, rsi_s, bbu, bbl, mh, vols)
    if result is None:
        return
    assert isinstance(result["confidence_pct"], int)
    assert 50 <= result["confidence_pct"] <= 100


def test_edge_equals_confidence_minus_50() -> None:
    """edge_pct must equal confidence_pct - 50."""
    n = 300
    closes = _sine_series(n)
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    result = compute_direction_forecast(closes, rsi_s, bbu, bbl, mh, vols)
    if result is None:
        return
    assert result["edge_pct"] == result["confidence_pct"] - 50


def test_top_features_non_empty_strings() -> None:
    """top_features must be a non-empty list of non-empty strings."""
    n = 300
    closes = _sine_series(n)
    rsi_s, bbu, bbl, mh, vols = _constant_indicators(n)
    result = compute_direction_forecast(closes, rsi_s, bbu, bbl, mh, vols)
    if result is None:
        return
    assert len(result["top_features"]) > 0
    for f in result["top_features"]:
        assert isinstance(f, str) and len(f) > 0
