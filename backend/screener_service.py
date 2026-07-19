# backend/screener_service.py
"""Equity Screener (F24) — on-demand snapshot builder for the curated universe.

Fetches one fundamentals/technical row per ticker via yfinance, concurrently but
bounded (semaphore + per-call timeout). A single bad symbol is logged and skipped
(returns ``None``) so it never aborts the batch. Callers cache the full snapshot
in Redis (1h TTL) and apply filters in-memory.
"""
import asyncio
import logging

import yfinance as yf

from universe import SCREENER_UNIVERSE

logger = logging.getLogger(__name__)

_SEM = asyncio.Semaphore(8)   # cap concurrent yfinance calls
_TIMEOUT = 12.0               # match the backend external-fetch standard


async def _fetch_row(symbol: str) -> dict | None:
    """Build one screener row for ``symbol``; ``None`` on any failure/timeout."""
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

            return {
                "symbol": symbol,
                "name": info.get("shortName", symbol),
                "sector": info.get("sector", "—"),
                "marketCap": info.get("marketCap"),
                "peRatio": info.get("trailingPE"),
                "forwardPE": info.get("forwardPE"),
                "beta": info.get("beta"),
                "dividendYield": round(info["dividendYield"] * 100, 2)
                    if info.get("dividendYield") is not None else None,
                "revenueGrowth": round(info["revenueGrowth"] * 100, 1)
                    if info.get("revenueGrowth") is not None else None,
                "rsi": rsi,
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "currency": info.get("currency"),
            }

        try:
            return await asyncio.wait_for(asyncio.to_thread(_get), timeout=_TIMEOUT)
        except Exception as e:
            logger.warning(f"screener {symbol}: {e}")
            return None


async def build_universe_snapshot() -> list[dict]:
    """Fetch a row for every ticker in the universe; skip the ones that fail."""
    tasks = [_fetch_row(s) for s in SCREENER_UNIVERSE]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]
