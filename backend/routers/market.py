# backend/routers/market.py
import asyncio
import logging
import math
from typing import Any, Dict, List, Optional

import yfinance as yf
from fastapi import APIRouter, HTTPException

from dependencies import yf_svc

router = APIRouter()
logger = logging.getLogger(__name__)


def _safe_int(v: Any) -> int:
    """Convert v to int, treating None and NaN as 0."""
    try:
        f = float(v if v is not None else 0)
        return 0 if math.isnan(f) else int(f)
    except (TypeError, ValueError):
        return 0

# ---------------------------------------------------------------------------
# DCF Intrinsic Value
# ---------------------------------------------------------------------------
RISK_FREE_RATE      = 0.045   # ~10Y Treasury yield
EQUITY_RISK_PREMIUM = 0.055   # Damodaran


def _run_dcf(
    fcf: float,
    growth: float,
    wacc: float,
    terminal_growth: float = 0.025,
    years: int = 5,
) -> float:
    """Returns equity value (total PV of FCF stream + terminal value)."""
    pv = 0.0
    cf = fcf
    for yr in range(1, years + 1):
        cf *= (1 + growth)
        pv += cf / ((1 + wacc) ** yr)
    # Gordon Growth terminal value
    tv = cf * (1 + terminal_growth) / max(wacc - terminal_growth, 0.001)
    pv += tv / ((1 + wacc) ** years)
    return pv


@router.get("/dcf/{symbol}")
async def dcf_valuation(symbol: str):
    import yfinance as yf

    info = await asyncio.to_thread(yf_svc.fetch_info, symbol)

    # Raw data
    fcf           = info.get("free_cash_flow")
    beta          = info.get("beta")
    revenue_growth = info.get("revenue_growth")
    current_price = info.get("current_price", 0)

    # Shares outstanding + cashflow fallback — single yfinance Ticker call
    ticker_obj = await asyncio.to_thread(lambda: yf.Ticker(symbol.upper()))
    ticker_info = await asyncio.to_thread(lambda: ticker_obj.info)
    shares = (
        ticker_info.get("sharesOutstanding")
        or ticker_info.get("impliedSharesOutstanding")
        or 1
    )

    # FCF fallback: info may not carry freeCashflow in newer yfinance builds.
    # Try the cashflow statement before giving up.
    def _is_valid_fcf(v: Any) -> bool:
        try:
            return isinstance(v, (int, float)) and not math.isnan(float(v)) and float(v) > 0
        except (TypeError, ValueError):
            return False

    if not _is_valid_fcf(fcf):
        # Attempt 1: raw freeCashflow from ticker.info (may differ from fetch_info)
        raw_fcf = ticker_info.get("freeCashflow") or ticker_info.get("freeCashFlow")
        if _is_valid_fcf(raw_fcf):
            fcf = raw_fcf
            logger.info(f"[DCF] {symbol.upper()} — freeCashflow from ticker.info: {fcf:.0f}")
        else:
            # Attempt 2: cashflow statement (Free Cash Flow row)
            try:
                cf_stmt = await asyncio.to_thread(lambda: ticker_obj.cashflow)
                if cf_stmt is not None and not cf_stmt.empty:
                    for row_label in ("Free Cash Flow", "FreeCashFlow"):
                        if row_label in cf_stmt.index:
                            val = float(cf_stmt.loc[row_label].iloc[0])
                            if _is_valid_fcf(val):
                                fcf = val
                                logger.info(
                                    f"[DCF] {symbol.upper()} — FCF from cashflow statement "
                                    f"({row_label}): {fcf:.0f}"
                                )
                                break
            except Exception as cf_err:
                logger.debug(f"[DCF] cashflow statement fallback failed: {cf_err}")

    # Validate: need positive FCF and shares
    if not _is_valid_fcf(fcf) or not shares or shares <= 0:
        raise HTTPException(
            status_code=422,
            detail="Insufficient data for DCF (negative/zero FCF or missing shares)",
        )

    # WACC
    b = float(beta) if beta and beta != "N/A" else 1.0
    b = max(0.1, min(b, 3.0))
    wacc_base = RISK_FREE_RATE + b * EQUITY_RISK_PREMIUM

    # Growth rate
    g = float(revenue_growth) if revenue_growth and revenue_growth != "N/A" else 0.05
    g = max(-0.20, min(g, 0.40))   # clamp to ±20-40%

    TERMINAL_GROWTH = 0.025

    def scenario(wacc_delta: float, growth_mult: float) -> dict:
        w  = max(wacc_base + wacc_delta, TERMINAL_GROWTH + 0.001)
        gr = g * growth_mult
        total_pv  = _run_dcf(float(fcf), gr, w, TERMINAL_GROWTH)
        per_share = round(total_pv / shares, 2)
        upside    = (
            round((per_share - float(current_price)) / float(current_price) * 100, 1)
            if current_price else 0
        )
        return {
            "wacc":            round(w  * 100, 2),
            "growth_rate":     round(gr * 100, 2),
            "intrinsic_value": per_share,
            "upside_pct":      upside,
        }

    logger.info(f"[DCF] {symbol.upper()} — FCF={fcf:.0f} beta={b:.2f} wacc_base={wacc_base:.3f} g={g:.3f}")
    return {
        "symbol":             symbol.upper(),
        "current_price":      round(float(current_price), 2),
        "bear":               scenario(+0.02, 0.7),
        "base":               scenario(0.0,   1.0),
        "bull":               scenario(-0.02, 1.3),
        "shares_outstanding": int(shares),
        "fcf_billions":       round(float(fcf) / 1e9, 2),
        "wacc_base":          round(wacc_base * 100, 2),
        "growth_rate_base":   round(g * 100, 2),
        "method":             "FCF",
    }


# ---------------------------------------------------------------------------
# Options Chain
# ---------------------------------------------------------------------------

@router.get("/options/{symbol}")
async def options_chain(symbol: str) -> Dict[str, Any]:
    """
    Returns the nearest-expiry options chain (calls + puts) for the given symbol.
    Filters to strikes within ±25% of current price to keep payload small.
    """

    def _fetch() -> Optional[Dict[str, Any]]:
        ticker = yf.Ticker(symbol.upper())
        expirations = ticker.options
        if not expirations:
            return None
        expiry = expirations[0]
        chain  = ticker.option_chain(expiry)
        price  = (
            ticker.info.get("currentPrice")
            or ticker.info.get("regularMarketPrice")
            or ticker.info.get("previousClose")
            or 0.0
        )
        price = float(price)
        if price <= 0:
            logger.warning("[OPTIONS] Unable to retrieve price for %s", symbol)
            return None

        def _clean(df: Any, is_call: bool) -> List[Dict[str, Any]]:
            rows = []
            for _, r in df.iterrows():
                strike = float(r.get("strike", 0))
                if abs(strike - price) / price > 0.25:
                    continue
                rows.append({
                    "strike":        round(strike, 2),
                    "last":          round(float(r.get("lastPrice",        0)), 2),
                    "bid":           round(float(r.get("bid",              0)), 2),
                    "ask":           round(float(r.get("ask",              0)), 2),
                    "change":        round(float(r.get("change",           0)), 2),
                    "change_pct":    round(float(r.get("percentChange",    0)), 2),
                    "volume":        _safe_int(r.get("volume",       0)),
                    "open_interest": _safe_int(r.get("openInterest", 0)),
                    "implied_vol":   round(float(r.get("impliedVolatility", 0)) * 100, 1),
                    "in_the_money":  bool(r.get("inTheMoney", False)),
                    "type":          "call" if is_call else "put",
                })
            return rows

        return {
            "symbol":        symbol.upper(),
            "expiry":        expiry,
            "expirations":   list(expirations[:8]),
            "current_price": round(price, 2),
            "calls":         _clean(chain.calls, True),
            "puts":          _clean(chain.puts,  False),
        }

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=12.0)
    except asyncio.TimeoutError:
        logger.warning("[OPTIONS] timeout fetching chain for %s", symbol)
        raise HTTPException(status_code=504, detail=f"Options fetch timed out for {symbol}")
    except Exception as exc:
        logger.warning("[OPTIONS] fetch failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Options provider error for {symbol}")
    if result is None:
        raise HTTPException(status_code=404, detail=f"No options data for {symbol}")
    return result
