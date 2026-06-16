"""
Tests for the Gap Explainer (Feature 22):
  - _compute_gap_alert — detects >=3% daily moves and builds the alert dict.

The Groq call is never exercised here (groq_call=None), so these run with no
network and no native deps — only the pure gap-detection logic is under test.
"""
import asyncio
from typing import Any, Coroutine, List

import pandas as pd

from backend.routers.predict import _compute_gap_alert


def run(coro: "Coroutine[Any, Any, Any]") -> Any:
    """Run an async coroutine to completion in a fresh event loop."""
    return asyncio.run(coro)


def _df(closes: List[float]) -> pd.DataFrame:
    """Build a minimal OHLCV frame carrying just the Close column the helper reads."""
    return pd.DataFrame({"Close": closes})


def test_gap_alert_triggers_on_large_move():
    # prev_close=100, last_close=104 → +4.0% up gap
    df = _df([98.0, 100.0, 104.0])
    result = run(_compute_gap_alert("AAPL", df, [], None))
    assert result is not None
    assert result["gapPct"] == 4.0
    assert result["direction"] == "up"
    # No groq_call + no headlines → empty explanation, empty headline list.
    assert result["explanation"] == ""
    assert result["headlines"] == []


def test_gap_alert_triggers_on_large_down_move():
    # prev_close=100, last_close=95 → -5.0% down gap
    df = _df([101.0, 100.0, 95.0])
    result = run(_compute_gap_alert("AAPL", df, [], None))
    assert result is not None
    assert result["gapPct"] == -5.0
    assert result["direction"] == "down"


def test_gap_alert_none_on_small_move():
    # prev_close=100, last_close=101.5 → +1.5% → below the 3% threshold
    df = _df([100.0, 101.5])
    result = run(_compute_gap_alert("AAPL", df, [], None))
    assert result is None


def test_gap_alert_graceful_empty_df():
    # Fewer than 2 rows → cannot compute a gap → None (never raises)
    df = _df([100.0])
    assert run(_compute_gap_alert("AAPL", df, [], None)) is None
    assert run(_compute_gap_alert("AAPL", None, [], None)) is None
