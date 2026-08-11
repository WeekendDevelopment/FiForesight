# backend/fx.py
"""Currency → USD FX rates (Feature 35) — keyless, via yfinance "GBPUSD=X" pairs.

yfinance quotes some exchanges in *minor* units (LSE in GBp = pence, JSE in
ZAc = cents): those map to the major-unit FX pair with a /100 scale so the
returned multiplier converts one displayed unit straight into USD.
"""

import asyncio
import logging

import yfinance as yf

logger = logging.getLogger(__name__)

# yfinance 'currency' values → FX pair vs USD + scale. GBp/ZAc/ILA are minor
# units (1/100 of the major currency the pair quotes).
_MINOR_UNITS = {
    "GBp": ("GBPUSD=X", 0.01),
    "ZAc": ("ZARUSD=X", 0.01),
    "ILA": ("ILSUSD=X", 0.01),
}


async def get_usd_rate(currency: str | None) -> float | None:
    """Multiplier converting 1 unit of ``currency`` into USD (1.0 for USD/None).

    GBp (pence) → GBPUSD rate × 0.01. Redis-cached 1h per currency. ``None`` on
    failure — callers must degrade to native display, never guess a rate.
    """
    from redis_cache import cache_get, cache_set

    if not currency or currency == "USD":
        return 1.0

    pair, scale = _MINOR_UNITS.get(currency, (f"{currency}USD=X", 1.0))
    key = f"fx:usd:{currency}"
    cached = await cache_get(key)
    if isinstance(cached, dict) and cached.get("rate") is not None:
        return cached["rate"]

    def _fetch() -> float | None:
        h = yf.Ticker(pair).history(period="1d")
        return float(h["Close"].iloc[-1]) if h is not None and len(h) else None

    try:
        # Deliberately tighter than the 12s external-fetch standard: /predict
        # awaits this inline, and a single FX pair either answers fast or the
        # response ships with fxToUsd=null (native display) — no need to wait.
        raw = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=8.0)
    except Exception as e:
        logger.warning(f"fx {currency}: {e}")
        return None
    if raw is None:
        return None

    rate = raw * scale
    await cache_set(key, {"rate": rate}, ttl_seconds=3600)
    return rate
