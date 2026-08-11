"""
Fibonacci retracement helper tests (F25) — calculate_fibonacci_levels.
Pure unit tests, no network. Mirrors test_regime.py / test_screener.py style.
"""

import itertools

from backend.models import calculate_fibonacci_levels

_RATIOS = ["0.0", "0.236", "0.382", "0.5", "0.618", "0.786", "1.0"]


def test_levels_ordered_and_bounded():
    # Ascending then descending price series → swing_high=20, swing_low=10.
    highs = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 18, 16, 14]
    lows = [10, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 17, 15, 13]
    fib = calculate_fibonacci_levels(highs, lows)
    assert fib is not None
    levels = fib["levels"]
    # All 7 ratios present.
    assert sorted(levels.keys(), key=float) == _RATIOS
    # 0% anchors at swing high, 100% at swing low.
    assert levels["0.0"] == fib["swing_high"] == 20.0
    assert levels["1.0"] == fib["swing_low"] == 10.0
    # Level prices are monotonically decreasing from 0.0 → 1.0.
    ordered = [levels[r] for r in _RATIOS]
    assert all(a > b for a, b in itertools.pairwise(ordered))


def test_direction_up_when_low_precedes_high():
    # Low at start, high at end → uptrend retracement.
    highs = [10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]
    lows = [9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29]
    fib = calculate_fibonacci_levels(highs, lows)
    assert fib is not None
    assert fib["direction"] == "up"


def test_direction_down_when_high_precedes_low():
    # High at start, low at end → downtrend retracement.
    highs = [30, 28, 26, 24, 22, 20, 18, 16, 14, 12, 10]
    lows = [29, 27, 25, 23, 21, 19, 17, 15, 13, 11, 9]
    fib = calculate_fibonacci_levels(highs, lows)
    assert fib is not None
    assert fib["direction"] == "down"


def test_insufficient_data_returns_none():
    assert calculate_fibonacci_levels([1, 2, 3], [1, 2, 3]) is None
    assert calculate_fibonacci_levels([], []) is None


def test_flat_series_returns_none():
    flat = [50.0] * 15
    assert calculate_fibonacci_levels(flat, flat) is None
