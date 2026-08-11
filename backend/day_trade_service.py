"""Intraday day-trade setup — VWAP-anchored Opening Range Breakout (ORB).

Strategy (deterministic):
    • Uses a SINGLE 5-minute daily snapshot (yfinance period=1d interval=5m) —
      no streaming, no per-minute engine. Same bars in → same setup out.
    • Opening Range (OR) = high/low of the first 30 min (first 6 bars).
    • VWAP = Σ(typical×vol)/Σ(vol), typical = (H+L+C)/3, cumulative on the session.
    • BIAS GATE (the part that keeps it coherent): only take a trade when the
      intraday VWAP position AGREES with the daily trend. If price is below VWAP
      while the daily bias is up (or vice-versa) → "no clean intraday setup".
      A Neutral daily trend falls back to pure VWAP momentum.
    • Entry  = break of the OR edge in the bias direction.
      Stop   = nearest of {VWAP, opposite OR edge} → defined risk.
      Targets= 1R / 2R / measured-move (OR height).

Day trades close intraday, so — unlike the swing setup — they avoid overnight
CFD financing, which is surfaced in the CFD note.

Every public entry point fails soft: a fetch failure or thin data returns an
``available: False`` payload with a human ``message`` rather than raising.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# First 6 five-minute bars = the 09:30–10:00 ET opening range.
_OPENING_RANGE_BARS = 6
_CFD_LEVERAGE = 5.0  # typical EU retail major-stock CFD cap (broker-dependent)


def _fetch_intraday_ohlcv(symbol: str) -> list[dict]:
    """One 5-min OHLCV snapshot for the latest session (RTH only).

    Returns a list of ``{t, o, h, l, c, v}`` (ET-naive timestamps) or ``[]`` on
    any failure / no data. Synchronous — call via ``asyncio.to_thread``.
    Mirrors the pre/post-market strip used by the sparklines fetch.
    """
    import yfinance as _yf

    try:
        df = _yf.download(
            symbol,
            period="1d",
            interval="5m",
            progress=False,
            auto_adjust=True,
            timeout=10,
        )
        if df is None or df.empty:
            return []

        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)

        idx = df.index
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        idx_et = idx.tz_convert("America/New_York")
        mask = (
            ((idx_et.hour == 9) & (idx_et.minute >= 30))
            | ((idx_et.hour > 9) & (idx_et.hour < 16))
            | ((idx_et.hour == 16) & (idx_et.minute == 0))
        )
        df = df[mask][:78]
        if df.empty:
            return []

        def _col(name: str) -> str:
            return name if name in df.columns else name.lower()

        o_c, h_c, l_c = _col("Open"), _col("High"), _col("Low")
        c_c, v_c = _col("Close"), _col("Volume")
        ts_et = df.index.tz_convert("America/New_York")

        bars: list[dict] = []
        for i in range(len(df)):
            try:
                bars.append(
                    {
                        "t": ts_et[i].strftime("%H:%M"),
                        "o": float(df[o_c].iloc[i]),
                        "h": float(df[h_c].iloc[i]),
                        "l": float(df[l_c].iloc[i]),
                        "c": float(df[c_c].iloc[i]),
                        "v": float(df[v_c].iloc[i]) if v_c in df.columns else 0.0,
                    }
                )
            except Exception as exc:
                logger.debug("[day-trade] skipped malformed bar at %s: %s", ts_et[i], exc)
                continue  # skip a malformed bar, keep the rest
        # Drop any NaN-laden bars
        bars = [b for b in bars if all(b[k] == b[k] for k in ("o", "h", "l", "c"))]
        return bars
    except Exception as exc:  # pragma: no cover - network/parse guard
        logger.debug("[day-trade] _fetch_intraday_ohlcv(%s) error: %s", symbol, exc)
        return []


def compute_intraday_levels(bars: list[dict]) -> dict | None:
    """Pure: derive opening range, VWAP, session H/L and last from 5-min bars.

    Returns ``None`` when there aren't enough bars to be meaningful.
    """
    if not bars:
        return None

    or_bars = bars[:_OPENING_RANGE_BARS]
    or_complete = len(bars) >= _OPENING_RANGE_BARS
    or_high = max(b["h"] for b in or_bars)
    or_low = min(b["l"] for b in or_bars)

    # Cumulative VWAP over the whole session so far.
    cum_pv = 0.0
    cum_v = 0.0
    for b in bars:
        typical = (b["h"] + b["l"] + b["c"]) / 3.0
        vol = b["v"] if b["v"] > 0 else 0.0
        cum_pv += typical * vol
        cum_v += vol
    last = bars[-1]["c"]
    vwap = (cum_pv / cum_v) if cum_v > 0 else last  # fall back to last if no volume

    return {
        "or_high": round(or_high, 2),
        "or_low": round(or_low, 2),
        "vwap": round(vwap, 2),
        "session_high": round(max(b["h"] for b in bars), 2),
        "session_low": round(min(b["l"] for b in bars), 2),
        "last": round(last, 2),
        "n_bars": len(bars),
        "or_complete": or_complete,
    }


def _cfd_block(direction: str) -> dict:
    side = "Buy" if direction == "Long" else "Sell"
    margin = round(100.0 / _CFD_LEVERAGE, 1)
    note = (
        f"Place as a {side} CFD — same stop & targets. At {_CFD_LEVERAGE:.0f}:1, "
        f"margin ≈ {margin:.0f}% of notional (size by the stop, not the margin). "
        f"Closed intraday, so NO overnight financing — just spread. Flat by the close."
    )
    return {"cfd_side": side, "cfd_margin_pct": margin, "cfd_note": note}


def build_orb_setup(levels: dict | None, daily_trend: str) -> dict:
    """Pure strategy core — turn intraday levels + the daily bias into a setup.

    ``daily_trend`` is the composite trend label ("Bullish"/"Bearish"/"Neutral").
    Returns a fully-formed payload with a ``status`` describing what to do.
    """
    base = {
        "available": False,
        "strategy": "Opening Range Breakout (VWAP-filtered)",
        "direction": "Neutral",
        "status": "market_closed",
        "message": "Intraday data unavailable — day-trade setups need US market-hours 5-min bars.",
        "entry": None,
        "stop": None,
        "targets": None,
        "risk_reward": None,
        "entry_trigger": None,
        "confirmation": None,
        "levels": None,
        "cfd_side": None,
        "cfd_margin_pct": None,
        "cfd_note": None,
    }
    if not levels:
        return base

    base["levels"] = levels
    if not levels["or_complete"]:
        base.update(
            status="forming",
            message=(
                f"Opening range still forming ({levels['n_bars']} of "
                f"{_OPENING_RANGE_BARS} bars) — no trigger until the first 30 min completes."
            ),
        )
        return base

    last = levels["last"]
    vwap = levels["vwap"]
    or_high = levels["or_high"]
    or_low = levels["or_low"]
    or_range = or_high - or_low
    if or_range <= 0:
        base.update(status="no_setup", message="Opening range is degenerate (no range) — skip.")
        return base

    vwap_bias = "up" if last >= vwap else "down"
    daily_dir = {"Bullish": "up", "Bearish": "down"}.get(daily_trend, "flat")

    # Coherence gate: intraday momentum must not fight the daily bias.
    if daily_dir != "flat" and daily_dir != vwap_bias:
        base.update(
            status="conflict",
            direction="Neutral",
            message=(
                f"No clean day trade: price is {'above' if vwap_bias == 'up' else 'below'} VWAP "
                f"(intraday {vwap_bias}) but the daily trend is {daily_trend.lower()}. "
                f"Wait for them to align."
            ),
        )
        return base

    bias = vwap_bias  # aligned, or daily neutral → pure VWAP momentum

    if bias == "up":
        direction = "Long"
        entry = or_high
        stop = max(or_low, vwap)
        if stop >= entry:
            stop = or_low
        risk = max(entry - stop, 0.01)
        targets = sorted(
            [round(entry + risk, 2), round(entry + 2 * risk, 2), round(entry + or_range, 2)]
        )
        active = last >= or_high
        edge = "high"
    else:
        direction = "Short"
        entry = or_low
        stop = min(or_high, vwap)
        if stop <= entry:
            stop = or_high
        risk = max(stop - entry, 0.01)
        targets = sorted(
            [round(entry - risk, 2), round(entry - 2 * risk, 2), round(entry - or_range, 2)],
            reverse=True,
        )
        active = last <= or_low
        edge = "low"

    reward = abs(targets[1] - entry)  # T2 ≈ 2R by construction
    rr = f"1:{reward / risk:.1f}"
    confirmation = "active" if active else "pending"
    trigger = (
        "Breakout active — price has cleared the opening range; manage the open trade."
        if active
        else f"Enter on a 5-min close beyond the opening-range {edge} (${entry:.2f}); don't pre-empt it."
    )

    base.update(
        available=True,
        status="ok",
        direction=direction,
        entry=round(entry, 2),
        stop=round(stop, 2),
        targets=targets,
        risk_reward=rr,
        confirmation=confirmation,
        entry_trigger=trigger,
        message=(
            f"{direction} opening-range breakout, aligned with VWAP"
            + ("" if daily_dir == "flat" else f" and the {daily_trend.lower()} daily trend")
            + "."
        ),
        **_cfd_block(direction),
    )
    return base


async def build_day_trade_setup(symbol: str, daily_trend: str) -> dict:
    """Fetch the intraday snapshot (off-thread) and build the ORB setup."""
    import asyncio

    try:
        bars = await asyncio.wait_for(asyncio.to_thread(_fetch_intraday_ohlcv, symbol), timeout=12)
    except Exception as exc:
        logger.warning("[day-trade] intraday fetch failed for %s: %s", symbol, exc)
        bars = []

    levels = compute_intraday_levels(bars)
    setup = build_orb_setup(levels, daily_trend)
    logger.info(
        "[day-trade] %s → status=%s direction=%s (bars=%d, trend=%s)",
        symbol,
        setup["status"],
        setup["direction"],
        len(bars),
        daily_trend,
    )
    return setup
