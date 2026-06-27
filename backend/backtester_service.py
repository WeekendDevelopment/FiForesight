# backend/backtester_service.py
"""Rule-based strategy backtester (F28) — on-demand, long-only, single-position.

Curated strategy set only; pure pandas simulation over a yfinance history window.
No cron, no leverage, no costs (documented out-of-scope v1).

Indicator math is reused from ``models.py`` (calculate_sma_series / calculate_rsi_series /
calculate_macd / calculate_bollinger_bands) — not reimplemented here.
"""
import asyncio
import logging

import numpy as np
import pandas as pd
import yfinance as yf

from models import (
    calculate_bollinger_bands,
    calculate_macd,
    calculate_rsi_series,
    calculate_sma_series,
)

logger = logging.getLogger(__name__)

STRATEGIES = {"sma_cross", "rsi_reversion", "macd_cross", "bollinger_bounce"}
_PERIOD_MAP = {"1y": "1y", "2y": "2y", "5y": "5y"}


def _signals(df: pd.DataFrame, strategy: str, params: dict) -> pd.Series:
    """Return a boolean 'in position' Series aligned to df.index.

    Indicator series come from the shared ``models.py`` helpers (List[float] in,
    list-with-None out); we map those into a per-bar long/flat boolean.
    """
    closes = df["Close"].tolist()
    idx = df.index

    if strategy == "sma_cross":
        fast = calculate_sma_series(closes, int(params.get("fast", 20)))
        slow = calculate_sma_series(closes, int(params.get("slow", 50)))
        pos = [f is not None and s is not None and f > s for f, s in zip(fast, slow)]
        return pd.Series(pos, index=idx)

    if strategy == "rsi_reversion":
        rsi = calculate_rsi_series(closes, 14)
        lo = float(params.get("oversold", 30))
        hi = float(params.get("overbought", 70))
        pos, holding = [], False
        for v in rsi:
            if v is not None:
                if not holding and v <= lo:
                    holding = True
                elif holding and v >= hi:
                    holding = False
            pos.append(holding)
        return pd.Series(pos, index=idx)

    if strategy == "macd_cross":
        m = calculate_macd(closes)
        macd, signal = m["macd"], m["signal"]
        pos = [a is not None and b is not None and a > b for a, b in zip(macd, signal)]
        return pd.Series(pos, index=idx)

    if strategy == "bollinger_bounce":
        bb = calculate_bollinger_bands(closes, 20, 2.0)
        lower, mid = bb["lower"], bb["middle"]
        pos, holding = [], False
        for c, lo, m in zip(closes, lower, mid):
            if not holding and lo is not None and c <= lo:
                holding = True
            elif holding and m is not None and c >= m:
                holding = False
            pos.append(holding)
        return pd.Series(pos, index=idx)

    raise ValueError(f"unknown strategy {strategy}")


def _run(df: pd.DataFrame, in_pos: pd.Series) -> dict:
    close = df["Close"]
    # enter/exit on the NEXT bar (shift the position) to avoid lookahead bias
    held = in_pos.shift(1).fillna(False)
    ret = close.pct_change().fillna(0)
    strat_ret = ret.where(held, 0.0)
    equity = (1 + strat_ret).cumprod()
    bh = (1 + ret).cumprod()
    # trades = transitions flat->held (entry) and held->flat (exit)
    entries = held & ~held.shift(1).fillna(False)
    exits = ~held & held.shift(1).fillna(False)
    # Trade P&L uses the SAME shifted interval as strat_ret: a position held over
    # bars [e, x-1] earns close[x-1]/close[e-1]-1, so entry/exit prices reference
    # the prior bar's close. Keeps the trades table coherent with the equity curve.
    trade_returns, in_trade, entry_px = [], False, None
    for i in range(len(close)):
        if entries.iloc[i]:
            in_trade = True
            entry_px = close.iloc[i - 1] if i > 0 else close.iloc[i]
        elif exits.iloc[i] and in_trade and entry_px is not None:
            exit_px = close.iloc[i - 1] if i > 0 else close.iloc[i]
            trade_returns.append(exit_px / entry_px - 1)
            in_trade = False
    if in_trade and entry_px is not None:  # close any position still open on the last bar
        trade_returns.append(close.iloc[-1] / entry_px - 1)
    wins = sum(1 for r in trade_returns if r > 0)
    n = len(trade_returns)
    roll_max = equity.cummax()
    drawdown = equity / roll_max - 1
    years = max((df.index[-1] - df.index[0]).days / 365.25, 0.01)
    cagr = equity.iloc[-1] ** (1 / years) - 1
    sharpe = (strat_ret.mean() / strat_ret.std() * np.sqrt(252)) if strat_ret.std() else 0.0
    curve = [
        {
            "date": d.strftime("%Y-%m-%d"),
            "strategy": round(float(e), 4),
            "buyHold": round(float(b), 4),
        }
        for d, e, b in zip(df.index, equity, bh)
    ]
    return {
        "totalReturnPct": round(float(equity.iloc[-1] - 1) * 100, 2),
        "buyHoldReturnPct": round(float(bh.iloc[-1] - 1) * 100, 2),
        "cagrPct": round(float(cagr) * 100, 2),
        "winRatePct": round(wins / n * 100, 1) if n else None,
        "numTrades": n,
        "maxDrawdownPct": round(float(drawdown.min()) * 100, 2),
        "sharpe": round(float(sharpe), 2),
        "equityCurve": curve,
    }


async def run_backtest(symbol: str, strategy: str, params: dict, period: str) -> dict:
    """Fetch the window and simulate the curated strategy (bounded 12s)."""
    if strategy not in STRATEGIES:
        raise ValueError("unknown strategy")
    per = _PERIOD_MAP.get(period, "2y")

    def _work() -> dict:
        df = yf.Ticker(symbol).history(period=per, auto_adjust=True)
        if df is None or len(df) < 60:
            raise ValueError("insufficient history")
        in_pos = _signals(df, strategy, params)
        return _run(df, in_pos)

    try:
        return await asyncio.wait_for(asyncio.to_thread(_work), timeout=12.0)
    except asyncio.TimeoutError:
        logger.warning("backtest timed out for %s/%s/%s", symbol, strategy, per)
        raise
    except ValueError:
        raise  # insufficient history / bad input — surfaced to the caller as 422
    except Exception:
        logger.exception("backtest failed for %s/%s/%s", symbol, strategy, per)
        raise
