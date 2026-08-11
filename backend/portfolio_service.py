# backend/portfolio_service.py
"""
Portfolio Manager (Feature 10) — live P&L, sector allocation, diversification
score, and a lightweight portfolio-level forecast over a user's real holdings.

This is intentionally CHEAPER than the /simulation "race" engine: it does NOT run
the full Prophet+SARIMAX+RF ensemble or the LLM jury per holding (that would be
far too slow/expensive for an interactive summary over many positions). Instead
each holding gets a fast, deterministic trend signal derived from recent closes,
and the portfolio outlook is the market-value-weighted aggregate of those signals.
The whole summary is Redis-cached (15 min) by the router.

Failure isolation: a holding whose price/history can't be fetched is skipped and
reported in `skipped`, never failing the whole summary.
"""

import asyncio
import logging
import math
from statistics import fmean
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

# Cap concurrent yfinance calls to avoid Yahoo 429s on larger portfolios.
_YF_SEM: asyncio.Semaphore | None = None

# Bound work so a pathologically large holdings list can't hang the request.
_MAX_HOLDINGS = 50
_PER_HOLDING_TIMEOUT = 8.0

# Portfolio-outlook thresholds on the weighted trend score (range [-1, 1]).
_BULLISH_AT = 0.15
_BEARISH_AT = -0.15


def _yf_sem() -> asyncio.Semaphore:
    """Lazy singleton — must be created inside a running event loop."""
    global _YF_SEM
    if _YF_SEM is None:
        _YF_SEM = asyncio.Semaphore(6)
    return _YF_SEM


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _label_for(score: float) -> str:
    if score > _BULLISH_AT:
        return "Bullish"
    if score < _BEARISH_AT:
        return "Bearish"
    return "Neutral"


def _trend_signal(closes: list[float]) -> tuple[str, float]:
    """Lightweight directional signal from recent daily closes.

    Blends three classic momentum reads into a score in [-1, 1]:
      • price vs 20-day SMA (above = bullish)
      • 20-day SMA vs 50-day SMA (golden/death-cross proxy)
      • ~1-month price momentum (scaled)
    Returns (label, score). Neutral/0.0 when there isn't enough history.
    """
    closes = [v for c in closes if not math.isnan(v := float(c))]  # drop NaN
    if len(closes) < 20:
        return "Neutral", 0.0
    last = closes[-1]
    sma20 = fmean(closes[-20:])
    sma50 = fmean(closes[-50:]) if len(closes) >= 50 else fmean(closes)
    mom = (last / closes[-21] - 1.0) if len(closes) >= 21 else 0.0

    signals = [
        1.0 if last > sma20 else -1.0,
        1.0 if sma20 > sma50 else -1.0,
        _clamp(mom * 5.0),  # ±20% monthly move saturates the signal
    ]
    score = round(_clamp(fmean(signals)), 3)
    return _label_for(score), score


async def _analyze_holding(holding: dict[str, Any], yf_svc: Any) -> dict[str, Any] | None:
    """Resolve live price, sector, and trend for one holding. None on failure."""
    symbol = str(holding.get("symbol", "")).upper()
    try:
        shares = float(holding.get("shares", 0) or 0)
        cost_basis = float(holding.get("cost_basis", 0) or 0)
        currency = str(holding.get("currency") or "USD")
    except (TypeError, ValueError):
        logger.warning("[PORTFOLIO] %s: non-numeric shares/cost_basis — skipped", symbol)
        return None

    try:
        async with _yf_sem():
            info = await asyncio.to_thread(yf_svc.fetch_info, symbol)
        price = float(info.get("current_price") or 0.0)
        sector = info.get("sector") or "Unknown"
        name = info.get("short_name") or symbol

        if price <= 0:  # fetch_info missed — fall back to the fast price path
            async with _yf_sem():
                price = float(await asyncio.to_thread(yf_svc.get_live_price, symbol))
        if price <= 0:
            logger.warning("[PORTFOLIO] %s: no live price resolved — skipped", symbol)
            return None

        direction, direction_score = "Neutral", 0.0
        try:
            yf_sym = yf_svc._to_yf_symbol(symbol) if hasattr(yf_svc, "_to_yf_symbol") else symbol
            async with _yf_sem():
                df = await asyncio.to_thread(
                    yf.Ticker(yf_sym).history, period="3mo", interval="1d", auto_adjust=True
                )
            if df is not None and not df.empty and "Close" in df.columns:
                direction, direction_score = _trend_signal(df["Close"].tolist())
        except Exception as exc:
            logger.debug("[PORTFOLIO] %s: trend signal failed (neutral): %s", symbol, exc)

        market_value = shares * price
        cost_value = shares * cost_basis
        pnl = market_value - cost_value
        pnl_pct = (pnl / cost_value * 100.0) if cost_value > 0 else 0.0

        return {
            "id": holding.get("id"),
            "symbol": symbol,
            "name": name,
            "sector": sector if sector and sector != "N/A" else "Unknown",
            "currency": currency,
            "shares": round(shares, 6),
            "costBasis": round(cost_basis, 4),
            "price": round(price, 4),
            "marketValue": round(market_value, 2),
            "costValue": round(cost_value, 2),
            "pnl": round(pnl, 2),
            "pnlPct": round(pnl_pct, 2),
            "direction": direction,
            "directionScore": direction_score,
        }
    except Exception as exc:
        logger.error("[PORTFOLIO] _analyze_holding(%s) failed: %s", symbol, exc)
        return None


def _empty_summary(skipped: list[str] | None = None) -> dict[str, Any]:
    return {
        "holdings": [],
        "totalMarketValue": 0.0,
        "totalCost": 0.0,
        "totalPnl": 0.0,
        "totalPnlPct": 0.0,
        "sectorAllocation": [],
        "diversificationScore": 0,
        "forecast": {"label": "Neutral", "score": 0.0},
        "skipped": skipped or [],
    }


async def build_summary(holdings: list[dict[str, Any]], yf_svc: Any) -> dict[str, Any]:
    """Compute the full portfolio summary. Holdings that error are skipped, not fatal."""
    if not holdings:
        return _empty_summary()

    capped = holdings[:_MAX_HOLDINGS]

    async def _guarded(h: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return await asyncio.wait_for(_analyze_holding(h, yf_svc), timeout=_PER_HOLDING_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("[PORTFOLIO] %s: analysis timed out — skipped", h.get("symbol"))
            return None

    results = await asyncio.gather(*[_guarded(h) for h in capped], return_exceptions=True)

    rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    for h, res in zip(capped, results):
        if isinstance(res, dict):
            rows.append(res)
        else:
            skipped.append(str(h.get("symbol", "")).upper())
            if isinstance(res, Exception):
                logger.error("[PORTFOLIO] unexpected gather error for %s: %s", h.get("symbol"), res)

    if not rows:
        return _empty_summary(skipped=skipped)

    total_market_value = sum(r["marketValue"] for r in rows)
    total_cost = sum(r["costValue"] for r in rows)
    total_pnl = total_market_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100.0) if total_cost > 0 else 0.0

    # Per-holding weight by market value.
    for r in rows:
        r["weightPct"] = (
            round((r["marketValue"] / total_market_value * 100.0), 2)
            if total_market_value > 0
            else 0.0
        )

    # Sector allocation — aggregate weight (and value) by sector, largest first.
    sector_map: dict[str, dict[str, float]] = {}
    for r in rows:
        bucket = sector_map.setdefault(r["sector"], {"weightPct": 0.0, "value": 0.0})
        bucket["weightPct"] += r["weightPct"]
        bucket["value"] += r["marketValue"]
    sector_allocation = sorted(
        [
            {"sector": s, "weightPct": round(v["weightPct"], 2), "value": round(v["value"], 2)}
            for s, v in sector_map.items()
        ],
        key=lambda x: x["weightPct"],
        reverse=True,
    )

    # Diversification score: 0–100 from the Herfindahl–Hirschman Index of weights.
    # HHI = Σ wᵢ² (weights as fractions). Score = (1 − HHI) × 100, so a single
    # position → 0 and N equal positions → (1 − 1/N) × 100 (approaches 100).
    hhi = sum((r["weightPct"] / 100.0) ** 2 for r in rows)
    diversification_score = round((1.0 - hhi) * 100.0)

    # Portfolio forecast: market-value-weighted mean of per-holding trend scores.
    weighted_score = round(
        _clamp(sum(r["directionScore"] * (r["weightPct"] / 100.0) for r in rows)), 3
    )

    return {
        "holdings": rows,
        "totalMarketValue": round(total_market_value, 2),
        "totalCost": round(total_cost, 2),
        "totalPnl": round(total_pnl, 2),
        "totalPnlPct": round(total_pnl_pct, 2),
        "sectorAllocation": sector_allocation,
        "diversificationScore": diversification_score,
        "forecast": {"label": _label_for(weighted_score), "score": weighted_score},
        "skipped": skipped,
    }
