"""Day-trade setup — VWAP-anchored Opening Range Breakout (intraday ORB).

Covers the pure strategy core (compute_intraday_levels + build_orb_setup): the
opening-range/VWAP math and the coherence gate that keeps an intraday trade from
fighting the daily bias.
"""

from backend.day_trade_service import build_orb_setup, compute_intraday_levels


def _bar(op, hi, lo, cl, v=1000.0):
    return {"t": "09:30", "o": op, "h": hi, "l": lo, "c": cl, "v": v}


def _levels(or_high=102.0, or_low=98.0, vwap=100.0, last=103.0, or_complete=True, n_bars=20):
    return {
        "or_high": or_high,
        "or_low": or_low,
        "vwap": vwap,
        "session_high": max(or_high, last),
        "session_low": min(or_low, last),
        "last": last,
        "n_bars": n_bars,
        "or_complete": or_complete,
    }


# ── compute_intraday_levels ───────────────────────────────────────────────────


def test_levels_opening_range_is_first_six_bars():
    bars = [
        _bar(100, 105, 99, 104),  # 1
        _bar(104, 106, 103, 105),  # 2
        _bar(105, 105, 100, 101),  # 3
        _bar(101, 103, 100, 102),  # 4
        _bar(102, 104, 101, 103),  # 5
        _bar(103, 104, 102, 103),  # 6  → OR = high 106, low 99
        _bar(103, 110, 103, 109),  # 7  (after OR; pushes session high to 110)
        _bar(109, 111, 108, 110),  # 8
    ]
    lv = compute_intraday_levels(bars)
    assert lv is not None
    assert lv["or_high"] == 106.0  # max high of first 6
    assert lv["or_low"] == 99.0  # min low of first 6
    assert lv["session_high"] == 111.0
    assert lv["last"] == 110.0
    assert lv["n_bars"] == 8 and lv["or_complete"] is True
    assert lv["session_low"] <= lv["vwap"] <= lv["session_high"]


def test_levels_none_on_empty():
    assert compute_intraday_levels([]) is None


def test_levels_or_incomplete_under_six_bars():
    lv = compute_intraday_levels([_bar(100, 101, 99, 100) for _ in range(3)])
    assert lv["or_complete"] is False and lv["n_bars"] == 3


# ── build_orb_setup: states ───────────────────────────────────────────────────


def test_orb_market_closed_when_no_levels():
    s = build_orb_setup(None, "Bullish")
    assert s["available"] is False and s["status"] == "market_closed"


def test_orb_forming_before_range_completes():
    s = build_orb_setup(_levels(or_complete=False, n_bars=3), "Bullish")
    assert s["available"] is False and s["status"] == "forming"


def test_orb_long_aligned_with_uptrend():
    s = build_orb_setup(_levels(last=103.0), "Bullish")  # last>vwap, daily up
    assert s["available"] is True and s["status"] == "ok"
    assert s["direction"] == "Long"
    assert s["entry"] == 102.0  # OR high
    assert s["stop"] < s["entry"]  # defined risk below
    assert s["targets"] == sorted(s["targets"])  # ascending for a long
    assert s["risk_reward"].startswith("1:")
    assert s["cfd_side"] == "Buy" and "NO overnight financing" in s["cfd_note"]


def test_orb_short_aligned_with_downtrend():
    s = build_orb_setup(_levels(last=97.0), "Bearish")  # last<vwap, daily down
    assert s["direction"] == "Short"
    assert s["entry"] == 98.0  # OR low
    assert s["stop"] > s["entry"]  # stop above for a short
    assert s["targets"] == sorted(s["targets"], reverse=True)
    assert s["cfd_side"] == "Sell"


def test_orb_conflict_when_intraday_fights_daily():
    # Price above VWAP (intraday up) but the daily trend is bearish → no trade.
    s = build_orb_setup(_levels(last=103.0), "Bearish")
    assert s["available"] is False and s["status"] == "conflict"
    assert s["direction"] == "Neutral"
    assert "VWAP" in s["message"]


def test_orb_neutral_daily_uses_pure_vwap_momentum():
    up = build_orb_setup(_levels(last=103.0), "Neutral")
    dn = build_orb_setup(_levels(last=97.0), "Neutral")
    assert up["direction"] == "Long"
    assert dn["direction"] == "Short"


def test_orb_active_vs_pending_confirmation():
    active = build_orb_setup(_levels(last=103.0), "Bullish")  # last >= or_high
    pending = build_orb_setup(_levels(last=101.0), "Bullish")  # above vwap, below or_high
    assert active["confirmation"] == "active"
    assert pending["confirmation"] == "pending"
