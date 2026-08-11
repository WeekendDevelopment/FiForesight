# backend/routers/history.py
import asyncio
import logging
import re
from datetime import datetime
from datetime import time as dtime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from config import Config
from dependencies import influx_svc, limiter
from fastapi import APIRouter, HTTPException, Query, Request
from models import (
    calculate_bollinger_bands,
    calculate_macd,
    calculate_rsi_series,
    calculate_sma_series,
)
from redis_cache import cache_get, cache_set
from slowapi.util import get_remote_address

router = APIRouter()
logger = logging.getLogger(__name__)

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-:]{1,15}$")

# Valid period → required interval
VALID_COMBINATIONS: dict[str, str] = {
    "1d": "5m",
    "5d": "15m",
    "1mo": "1h",
    "3mo": "1d",
    "6mo": "1d",
    "1y": "1d",
    "2y": "1d",
}

# Approximate trading periods per year per interval (for annualised vol)
PERIODS_PER_YEAR: dict[str, int] = {
    "5m": 252 * 78,
    "15m": 252 * 26,
    "1h": 252 * 7,
    "1d": 252,
}

INTRADAY_INTERVALS = {"5m", "15m", "1h"}
# Intraday bars go stale fast while the market is open — a long cache TTL was
# leaving the 1d/5m chart frozen mid-session (#287c). Use a short TTL during US
# market hours so the latest minute bars surface, and a relaxed TTL after the
# close when no new bars are produced.
INTRADAY_TTL_OPEN = 120  # 2 min — regular trading hours (09:30–16:00 ET)
INTRADAY_TTL_CLOSED = 300  # 5 min — pre/post-market & weekends
DAILY_TTL = 900  # 15 min
_EASTERN = ZoneInfo("America/New_York")


def _intraday_ttl() -> int:
    """Short cache TTL during US market hours so intraday bars stay fresh."""
    now = datetime.now(_EASTERN)
    is_weekday = now.weekday() < 5  # Mon–Fri
    in_session = dtime(9, 30) <= now.time() <= dtime(16, 0)
    return INTRADAY_TTL_OPEN if (is_weekday and in_session) else INTRADAY_TTL_CLOSED


# Minimum bar count needed to accept InfluxDB data as "sufficient" for each period
_INFLUX_MIN_ROWS: dict[str, int] = {
    "3mo": 50,
    "6mo": 110,
    "1y": 220,
    "2y": 450,
}


def _compute_vwap(df: pd.DataFrame) -> list:
    """Per-bar VWAP that resets at each calendar-day boundary."""
    required = {"High", "Low", "Close", "Volume"}
    if not required.issubset(df.columns):
        return [None] * len(df)
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    vol = df["Volume"]
    result: list = []
    cum_tv, cum_v = 0.0, 0.0
    prev_date = None
    for i in range(len(df)):
        d = df.index[i].date()
        if d != prev_date:
            cum_tv = cum_v = 0.0
            prev_date = d
        cum_tv += float(typical.iloc[i]) * float(vol.iloc[i])
        cum_v += float(vol.iloc[i])
        result.append(round(cum_tv / cum_v, 4) if cum_v > 0 else None)
    return result


def _fetch_df(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """Blocking yfinance download — wrapped by asyncio.to_thread."""
    try:
        import yfinance as yf
    except ImportError:
        logger.error("[HISTORY] yfinance not installed")
        return pd.DataFrame()

    ticker = symbol.split(":")[0].upper()
    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
            timeout=20,
        )
    except Exception as exc:
        logger.error(f"[HISTORY] yf.download failed for {ticker}: {exc}")
        return pd.DataFrame()

    if df.empty:
        return df

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        df = df.loc[:, ~df.columns.duplicated(keep="first")]

    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    return df[keep].dropna(subset=["Close"])


@router.get("/history")
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def get_history(
    request: Request,
    symbol: str = Query(..., min_length=1, max_length=20),
    period: str = Query("2y"),
    interval: str = Query("1d"),
) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    if not _SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=422, detail="Invalid symbol.")
    period = period.strip().lower()
    interval = interval.strip().lower()

    if period not in VALID_COMBINATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period '{period}'. Must be one of: {sorted(VALID_COMBINATIONS)}",
        )
    expected = VALID_COMBINATIONS[period]
    if interval != expected:
        raise HTTPException(
            status_code=400,
            detail=f"For period='{period}', interval must be '{expected}' (got '{interval}').",
        )

    is_intraday = interval in INTRADAY_INTERVALS
    ttl = _intraday_ttl() if is_intraday else DAILY_TTL
    cache_key = f"history:{symbol}:{period}:{interval}"

    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info(f"[HISTORY] Cache HIT — {symbol} {period}/{interval}")
        return cached

    logger.info(f"[HISTORY] Cache MISS — fetching {symbol} {period}/{interval}")

    ticker = symbol.split(":")[0].upper()

    # InfluxDB-first for daily-interval requests (intraday bars not stored in Influx)
    df = pd.DataFrame()
    if not is_intraday:
        period_to_days = {"3mo": 93, "6mo": 183, "1y": 365, "2y": 730}
        days = period_to_days.get(period, 730)
        try:
            influx_rows = await asyncio.to_thread(influx_svc.query_history, ticker, days)
            min_rows = _INFLUX_MIN_ROWS.get(period, 0)
            if len(influx_rows) >= min_rows:
                tmp = pd.DataFrame(influx_rows)
                tmp["_time"] = pd.to_datetime(tmp["_time"])
                tmp = tmp.set_index("_time").rename(
                    columns={
                        "close": "Close",
                        "open": "Open",
                        "high": "High",
                        "low": "Low",
                        "volume": "Volume",
                    }
                )
                if tmp.index.tz is None:
                    tmp.index = tmp.index.tz_localize("UTC")
                df = tmp.dropna(subset=["Close"])
                logger.info(f"[HISTORY] InfluxDB HIT — {len(df)} rows for {symbol} ({period})")
            else:
                logger.info(
                    f"[HISTORY] InfluxDB insufficient ({len(influx_rows)} rows, "
                    f"need ≥{min_rows}) — falling back to yfinance"
                )
        except Exception as exc:
            logger.warning(
                f"[HISTORY] InfluxDB query failed for {ticker}: {exc} — falling back to yfinance"
            )

    # yfinance fallback — always used for intraday; fallback for daily when Influx data is sparse
    if df.empty:
        try:
            df = await asyncio.wait_for(
                asyncio.to_thread(_fetch_df, ticker, period, interval),
                timeout=12,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="History fetch timed out.")
        except Exception as exc:
            logger.error(f"[HISTORY] yfinance error for {ticker}: {exc}")
            raise HTTPException(status_code=502, detail="Failed to fetch historical data.")

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for symbol '{symbol}'.")

    closes = [float(v) for v in df["Close"].tolist()]
    highs = [float(v) for v in df["High"].tolist()] if "High" in df.columns else list(closes)
    lows = [float(v) for v in df["Low"].tolist()] if "Low" in df.columns else list(closes)
    opens = [float(v) for v in df["Open"].tolist()] if "Open" in df.columns else list(closes)
    volumes = (
        [int(v) for v in df["Volume"].tolist()] if "Volume" in df.columns else [0] * len(closes)
    )

    # InfluxDB stores intraday live-price snapshots (close-only) alongside daily
    # OHLC bars; those snapshot rows arrive with open/high/low == 0 and would
    # render as candlesticks spanning from $0. Coalesce any non-positive OHLC to
    # the close so every bar is a valid candle (a flat doji for snapshot rows).
    opens = [o if o > 0 else c for o, c in zip(opens, closes)]
    highs = [h if h > 0 else c for h, c in zip(highs, closes)]
    lows = [low if low > 0 else c for low, c in zip(lows, closes)]

    bb = calculate_bollinger_bands(closes)
    macd_d = calculate_macd(closes)
    rsi_s = calculate_rsi_series(closes)
    sma20_s = calculate_sma_series(closes, 20)

    vwap_s: list = []
    if is_intraday:
        vwap_s = _compute_vwap(df)

    # Date strings — intraday uses Eastern, daily stays UTC date
    if is_intraday:
        fmt = "%m/%d %H:%M" if period == "5d" else "%H:%M"
        try:
            eastern = df.index.tz_convert("America/New_York")
            dates = [ts.strftime(fmt) for ts in eastern]
        except Exception:
            dates = [ts.strftime(fmt) for ts in df.index]
    else:
        dates = [ts.strftime("%Y-%m-%d") for ts in df.index]

    # Real UNIX epoch (seconds, UTC) per bar — fed straight to the lightweight-
    # charts time scale so the zoom chart works on every range (incl. intraday),
    # without reconstructing a calendar date from the display string.
    times = [int(ts.timestamp()) for ts in df.index]

    history_bars: list[dict] = []
    for i, date in enumerate(dates):
        bar: dict[str, Any] = {
            "date": date,
            "time": times[i],
            "price": round(closes[i], 4),
            "open": round(opens[i], 4),
            "high": round(highs[i], 4),
            "low": round(lows[i], 4),
            "volume": volumes[i],
            "bb_upper": bb["upper"][i],
            "bb_middle": bb["middle"][i],
            "bb_lower": bb["lower"][i],
            "macd": macd_d["macd"][i],
            "macd_signal": macd_d["signal"][i],
            "macd_hist": macd_d["hist"][i],
            "rsi": rsi_s[i],
        }
        if vwap_s:
            bar["vwap"] = vwap_s[i]
        history_bars.append(bar)

    valid_highs = [v for v in highs if np.isfinite(v) and v > 0]
    valid_lows = [v for v in lows if np.isfinite(v) and v > 0]

    log_returns = [
        float(np.log(closes[i] / closes[i - 1]))
        for i in range(1, len(closes))
        if closes[i - 1] > 0 and closes[i] > 0
    ]
    ppy = PERIODS_PER_YEAR.get(interval, 252)
    ann_vol = float(np.std(log_returns) * np.sqrt(ppy) * 100) if len(log_returns) > 1 else 0.0
    first = closes[0] if closes else 0.0
    last = closes[-1] if closes else 0.0
    sma20_last = next((v for v in reversed(sma20_s) if v is not None), None)

    stats: dict[str, Any] = {
        "change_pct": round((last - first) / first * 100, 4) if first > 0 else 0.0,
        "period_high": round(max(valid_highs), 4) if valid_highs else None,
        "period_low": round(min(valid_lows), 4) if valid_lows else None,
        "sma20": round(sma20_last, 4) if sma20_last is not None else None,
        "ann_vol": round(ann_vol, 2),
    }

    payload: dict[str, Any] = {
        "symbol": symbol,
        "period": period,
        "interval": interval,
        "history": history_bars,
        "rsi_series": rsi_s,
        "stats": stats,
    }

    await cache_set(cache_key, payload, ttl_seconds=ttl)
    logger.info(
        f"[HISTORY] ✓ {symbol} {period}/{interval} — {len(history_bars)} bars, cached {ttl}s"
    )
    return payload
