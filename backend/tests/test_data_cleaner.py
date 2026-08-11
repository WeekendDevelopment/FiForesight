"""
Regression tests for DataCleaner.clean() — short-history handling.

A just-listed ticker (e.g. SPCX/SpaceX) can have only a couple of OHLCV bars.
The 4σ outlier step uses rolling(min_periods=5); with <5 bars the rolling band
is NaN, and a NaN comparison is False, so without a guard every row gets masked
out → empty df → /predict spuriously 404s. These tests lock the fix in.
"""

import pandas as pd

from backend.services import DataCleaner


def _ohlcv(closes, start="2026-06-12"):
    idx = pd.bdate_range(start=start, periods=len(closes), tz="UTC")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes],
            "Close": closes,
            "Volume": [1_000_000] * len(closes),
        },
        index=idx,
    )


class TestDataCleanerShortHistory:
    def test_two_bar_history_not_emptied(self):
        # The SPCX case: 2 bars must survive cleaning (was → empty → 404).
        df = _ohlcv([160.95, 192.50])
        out = DataCleaner.clean(df)
        assert not out.empty
        assert len(out) >= 2

    def test_four_bar_history_not_emptied(self):
        # Anything below min_periods=5 previously wiped out.
        df = _ohlcv([10.0, 11.0, 10.5, 12.0])
        out = DataCleaner.clean(df)
        assert not out.empty

    def test_long_history_still_filters_outlier(self):
        # Guard must not disable outlier removal for normal-length series.
        closes = [100.0 + (i % 3) for i in range(60)]
        closes[30] = 100_000.0  # blatant >4σ spike
        out = DataCleaner.clean(_ohlcv(closes))
        assert out["Close"].max() < 1_000.0  # the spike was removed
        assert not out.empty
