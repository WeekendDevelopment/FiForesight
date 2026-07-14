# backend/watchlist_metrics_service.py
"""Smart Watchlist Columns (F-watchlist-metrics) — per-symbol fundamentals/technicals.

Mirrors screener_service.py's on-demand yfinance fan-out: one row per symbol,
bounded concurrency + timeout, a bad symbol is logged and skipped (returns
``None``) so it never aborts the batch. Callers (routers/watchlist.py) cache
each row in Redis independently.
"""
import asyncio
import logging

import yfinance as yf

logger = logging.getLogger(__name__)

_SEM = asyncio.Semaphore(8)   # cap concurrent yfinance calls
_TIMEOUT = 8.0


async def _fetch_metrics(symbol: str) -> dict | None:
    """Build one watchlist metrics row for ``symbol``; ``None`` on failure/timeout."""
    async with _SEM:
        def _get() -> dict:
            t = yf.Ticker(symbol)
            info = t.info or {}
            hist = t.history(period="1mo", auto_adjust=True)

            rsi = None
            if hist is not None and len(hist) >= 14:
                delta = hist["Close"].diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss.replace(0, float("nan"))
                rsi_series = 100 - 100 / (1 + rs)
                rsi = round(float(rsi_series.iloc[-1]), 1) if not rsi_series.empty else None

            price = info.get("currentPrice") or info.get("regularMarketPrice")
            hi = info.get("fiftyTwoWeekHigh")
            pct_from_high = round((price / hi - 1) * 100, 2) if (price and hi) else None

            next_earnings = None
            try:
                cal = t.calendar
                if isinstance(cal, dict):
                    ed = cal.get("Earnings Date")
                    if isinstance(ed, list) and ed:
                        next_earnings = str(ed[0])[:10]
            except Exception:
                next_earnings = None

            return {
                "symbol": symbol,
                "price": price,
                "changePct": info.get("regularMarketChangePercent"),
                "peRatio": info.get("trailingPE"),
                "rsi": rsi,
                "pctFrom52wHigh": pct_from_high,
                "marketCap": info.get("marketCap"),
                "nextEarnings": next_earnings,
            }

        try:
            return await asyncio.wait_for(asyncio.to_thread(_get), timeout=_TIMEOUT)
        except Exception as e:
            logger.warning(f"watchlist metrics {symbol}: {e}")
            return None


async def fetch_watchlist_metrics(symbols: list[str]) -> list[dict]:
    """Fetch a metrics row for each symbol; skip the ones that fail."""
    rows = await asyncio.gather(*[_fetch_metrics(s) for s in symbols])
    return [r for r in rows if r is not None]
