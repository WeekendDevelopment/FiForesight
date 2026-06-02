# backend/routers/market.py
import asyncio
import logging
import math
from typing import Any, Dict, List, Optional

import httpx
import yfinance as yf
from fastapi import APIRouter, HTTPException

from config import Config
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
    from redis_cache import cache_get, cache_set

    def _missing(v: Any) -> bool:
        return v in (None, "N/A", "")

    async def _fetch_info_bounded() -> dict:
        """fetch_info wrapped in a 12s timeout (matches sibling endpoints) so a
        hung yfinance call can't stall the /dcf response. Always returns a dict."""
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(yf_svc.fetch_info, symbol), timeout=12.0
            )
            return result or {}
        except asyncio.TimeoutError:
            logger.warning("[DCF] fetch_info timed out for %s", symbol)
            return {}

    # Reuse the shared fundamentals cache (populated by /predict, 1h TTL) so the
    # DCF reads the SAME beta/revenue_growth as the rest of the dashboard. Under
    # the dashboard's concurrent request burst yfinance sometimes returns partial
    # `info`; caching plus a single retry when the key growth/risk inputs are
    # missing stops the intrinsic value from silently flipping to the default
    # beta=1.0 / growth=5% (which produced wildly different valuations per load).
    info_cache_key = f"info:{symbol.upper()}"
    info = await cache_get(info_cache_key)
    if not info:
        info = await _fetch_info_bounded()
        if info:
            await cache_set(info_cache_key, info, ttl_seconds=3600)
    info = info or {}

    if _missing(info.get("beta")) or _missing(info.get("revenue_growth")):
        retry = await _fetch_info_bounded()
        # Accept the retry only when it makes BOTH inputs present (symmetric with
        # the trigger above) so we never overwrite the cache with still-partial data.
        if retry and not (_missing(retry.get("beta")) or _missing(retry.get("revenue_growth"))):
            info = retry
            await cache_set(info_cache_key, info, ttl_seconds=3600)

    fundamentals_complete = not (
        _missing(info.get("beta")) or _missing(info.get("revenue_growth"))
    )

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
        # False when yfinance returned partial fundamentals and beta/growth fell
        # back to defaults — lets the frontend flag a lower-confidence valuation.
        "fundamentals_complete": fundamentals_complete,
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


# ---------------------------------------------------------------------------
# Sector Heatmap
# ---------------------------------------------------------------------------

SECTOR_ETFS = [
    ("XLK",  "Technology"),
    ("XLF",  "Financials"),
    ("XLE",  "Energy"),
    ("XLV",  "Health Care"),
    ("XLY",  "Cons. Discret."),
    ("XLP",  "Cons. Staples"),
    ("XLI",  "Industrials"),
    ("XLB",  "Materials"),
    ("XLRE", "Real Estate"),
    ("XLU",  "Utilities"),
    ("XLC",  "Comm. Services"),
]


@router.get("/sectors")
async def sector_heatmap():
    """Returns 1-day % change for 11 SPDR sector ETFs. Cached 15 min."""
    from redis_cache import cache_get, cache_set
    CACHE_KEY = "sectors:heatmap"
    cached = await cache_get(CACHE_KEY)
    if cached:
        return cached

    def _fetch_sectors():
        results = []
        for ticker, label in SECTOR_ETFS:
            try:
                hist = yf.Ticker(ticker).history(period="5d", interval="1d")
                if hist is None or len(hist) < 2:
                    results.append({"ticker": ticker, "label": label, "change_pct": None, "price": None})
                    continue
                prev_close = float(hist["Close"].iloc[-2])
                last_close = float(hist["Close"].iloc[-1])
                change_pct = round((last_close - prev_close) / prev_close * 100, 2) if prev_close else None
                results.append({"ticker": ticker, "label": label, "change_pct": change_pct, "price": round(last_close, 2)})
            except Exception:
                results.append({"ticker": ticker, "label": label, "change_pct": None, "price": None})
        return results

    try:
        data = await asyncio.wait_for(asyncio.to_thread(_fetch_sectors), timeout=12.0)
    except asyncio.TimeoutError:
        logger.warning("[SECTORS] upstream fetch timed out")
        raise HTTPException(status_code=504, detail="Market data temporarily unavailable")
    payload = {"sectors": data}
    await cache_set(CACHE_KEY, payload, ttl_seconds=900)
    return payload


# ---------------------------------------------------------------------------
# Morning Briefing
# ---------------------------------------------------------------------------

MARKET_OVERVIEW_TICKERS = [
    ("SPY",  "S&P 500"),
    ("QQQ",  "NASDAQ"),
    ("DIA",  "Dow Jones"),
    ("IWM",  "Russell 2000"),
    ("^VIX", "VIX"),
    ("^TNX", "10Y Yield"),
    ("GLD",  "Gold"),
    ("USO",  "Oil"),
]


@router.get("/briefing")
async def morning_briefing():
    """Market overview: % change for key indices + ETFs. Cached 15 min."""
    from redis_cache import cache_get, cache_set
    CACHE_KEY = "briefing:market"
    cached = await cache_get(CACHE_KEY)
    if cached:
        return cached

    def _fetch_overview():
        results = []
        for ticker, label in MARKET_OVERVIEW_TICKERS:
            try:
                hist = yf.Ticker(ticker).history(period="5d", interval="1d")
                if hist is None or len(hist) < 2:
                    results.append({"ticker": ticker, "label": label, "change_pct": None, "price": None})
                    continue
                prev_close = float(hist["Close"].iloc[-2])
                last_close = float(hist["Close"].iloc[-1])
                change_pct = round((last_close - prev_close) / prev_close * 100, 2) if prev_close else None
                results.append({"ticker": ticker, "label": label, "change_pct": change_pct, "price": round(last_close, 2)})
            except Exception:
                results.append({"ticker": ticker, "label": label, "change_pct": None, "price": None})
        return results

    try:
        data = await asyncio.wait_for(asyncio.to_thread(_fetch_overview), timeout=12.0)
    except asyncio.TimeoutError:
        logger.warning("[BRIEFING] upstream fetch timed out")
        raise HTTPException(status_code=504, detail="Market data temporarily unavailable")
    payload = {"indices": data}
    await cache_set(CACHE_KEY, payload, ttl_seconds=900)
    return payload


# ---------------------------------------------------------------------------
# Order Book / Market Depth
#
# Real, free multi-level depth only exists for crypto, so the source is
# chosen per symbol:
#   • Crypto pairs (e.g. BTC-USD) → Coinbase free public book (level=2),
#     genuine Level-2 depth ladder, no API key required.
#   • Stocks (e.g. NVDA)          → Alpaca free IEX feed, top-of-book (L1).
#
# Both paths emit the same response shape (multi-level bids/asks arrays) so
# the frontend renders either without branching.
# ---------------------------------------------------------------------------

ALPACA_DATA_URL = "https://data.alpaca.markets/v2"
COINBASE_API_URL = "https://api.exchange.coinbase.com"
ORDERBOOK_TTL_SECONDS = 10
ORDERBOOK_DEPTH = 12  # levels per side to return for crypto books

# Quote currencies that mark a "<BASE>-<QUOTE>" symbol as a crypto pair.
_CRYPTO_QUOTES = {"USD", "USDT", "USDC", "USDD", "DAI", "EUR", "GBP", "BTC", "ETH"}


def _is_crypto_symbol(symbol: str) -> bool:
    """True for Coinbase-style crypto pairs like ``BTC-USD`` / ``ETH-USDT``."""
    parts = symbol.upper().split("-")
    return (
        len(parts) == 2
        and parts[0].isalnum()
        and parts[1] in _CRYPTO_QUOTES
    )


def _build_orderbook(symbol: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Shape an Alpaca latest-quote payload into the order-book response.

    The free IEX feed exposes top-of-book (one bid + one ask level). The
    response keeps the multi-level ``bids``/``asks`` array shape so richer
    feeds (SIP subscription) can drop in extra levels without an API change.
    """
    quote = payload.get("quote") or {}
    bid_price = float(quote.get("bp") or 0.0)
    ask_price = float(quote.get("ap") or 0.0)
    bid_size = _safe_int(quote.get("bs"))
    ask_size = _safe_int(quote.get("as"))
    timestamp = quote.get("t") or ""

    if bid_price <= 0 and ask_price <= 0:
        return None

    bids: List[Dict[str, Any]] = (
        [{"price": round(bid_price, 2), "size": bid_size}] if bid_price > 0 else []
    )
    asks: List[Dict[str, Any]] = (
        [{"price": round(ask_price, 2), "size": ask_size}] if ask_price > 0 else []
    )

    if bid_price > 0 and ask_price > 0:
        spread = round(ask_price - bid_price, 4)
        mid = (ask_price + bid_price) / 2
    else:
        spread = 0.0
        mid = ask_price or bid_price

    spread_pct = round(spread / mid * 100, 4) if mid else 0.0

    total_size = bid_size + ask_size
    imbalance = round(bid_size / total_size, 4) if total_size else 0.5

    return {
        "symbol": symbol,
        "timestamp": timestamp,
        "mid_price": round(mid, 2) if mid else 0.0,
        "bids": bids,
        "asks": asks,
        "spread": spread,
        "spread_pct": spread_pct,
        "bid_ask_imbalance": imbalance,
        "source": "Alpaca · IEX (L1)",
    }


def _build_coinbase_book(
    symbol: str, payload: Dict[str, Any], depth: int = ORDERBOOK_DEPTH
) -> Optional[Dict[str, Any]]:
    """Shape a Coinbase ``/book?level=2`` payload into the order-book response.

    Coinbase returns ``[[price, size, num_orders], ...]`` with bids sorted
    best-first (descending price) and asks best-first (ascending price).
    """
    def _levels(rows: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for row in (rows or [])[:depth]:
            try:
                price = float(row[0])
                size = float(row[1])
            except (TypeError, ValueError, IndexError):
                continue
            if price <= 0:
                continue
            # Crypto prices span many magnitudes (sub-cent tokens up to BTC,
            # plus BTC/ETH-quoted pairs) — keep 8dp so low-priced books aren't
            # rounded to zero.
            out.append({"price": round(price, 8), "size": round(size, 8)})
        return out

    bids = _levels(payload.get("bids"))
    asks = _levels(payload.get("asks"))
    if not bids and not asks:
        return None

    best_bid = bids[0]["price"] if bids else 0.0
    best_ask = asks[0]["price"] if asks else 0.0

    if best_bid > 0 and best_ask > 0:
        spread = round(best_ask - best_bid, 8)
        mid = (best_ask + best_bid) / 2
    else:
        spread = 0.0
        mid = best_ask or best_bid

    spread_pct = round(spread / mid * 100, 4) if mid else 0.0

    # Depth imbalance: aggregate resting size across all returned levels.
    bid_vol = sum(b["size"] for b in bids)
    ask_vol = sum(a["size"] for a in asks)
    total_vol = bid_vol + ask_vol
    imbalance = round(bid_vol / total_vol, 4) if total_vol else 0.5

    return {
        "symbol": symbol,
        "timestamp": payload.get("time") or "",
        "mid_price": round(mid, 8) if mid else 0.0,
        "bids": bids,
        "asks": asks,
        "spread": spread,
        "spread_pct": spread_pct,
        "bid_ask_imbalance": imbalance,
        "source": "Coinbase (L2)",
    }


async def _fetch_alpaca_book(sym: str) -> Dict[str, Any]:
    """Top-of-book for a stock symbol via the Alpaca free IEX feed."""
    if not Config.ALPACA_API_KEY or not Config.ALPACA_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "Order book unavailable — Alpaca API key not configured. "
                "Free live depth is available for crypto pairs (e.g. BTC-USD)."
            ),
        )

    headers = {
        "APCA-API-KEY-ID": Config.ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": Config.ALPACA_SECRET_KEY,
    }
    url = f"{ALPACA_DATA_URL}/stocks/{sym}/quotes/latest"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await asyncio.wait_for(
                client.get(url, headers=headers, params={"feed": "iex"}),
                timeout=12.0,
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            raise HTTPException(
                status_code=503,
                detail="Order book unavailable — Alpaca authentication failed",
            )
        if status == 404:
            raise HTTPException(status_code=404, detail=f"No order book data for {sym}")
        logger.warning("[ORDERBOOK] Alpaca returned %s for %s", status, sym)
        raise HTTPException(status_code=502, detail="Order book provider error")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[ORDERBOOK] Alpaca fetch failed for %s: %s", sym, exc)
        raise HTTPException(status_code=502, detail="Order book provider error")

    result = _build_orderbook(sym, payload)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No order book data for {sym}")
    return result


async def _fetch_coinbase_book(sym: str) -> Dict[str, Any]:
    """Free multi-level depth for a crypto pair via Coinbase's public API."""
    url = f"{COINBASE_API_URL}/products/{sym}/book"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await asyncio.wait_for(
                client.get(
                    url,
                    params={"level": 2},
                    headers={"User-Agent": "FiForesight/1.0"},
                ),
                timeout=12.0,
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            raise HTTPException(status_code=404, detail=f"No order book data for {sym}")
        logger.warning("[ORDERBOOK] Coinbase returned %s for %s", status, sym)
        raise HTTPException(status_code=502, detail="Order book provider error")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[ORDERBOOK] Coinbase fetch failed for %s: %s", sym, exc)
        raise HTTPException(status_code=502, detail="Order book provider error")

    result = _build_coinbase_book(sym, payload)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No order book data for {sym}")
    return result


@router.get("/orderbook/{symbol}")
async def order_book(symbol: str) -> Dict[str, Any]:
    """Order book snapshot with spread + bid/ask imbalance metrics.

    Crypto pairs (``BTC-USD``) return genuine free Level-2 depth from
    Coinbase; stocks return Alpaca's free IEX top-of-book. Cached in Redis
    for 10s.
    """
    sym = symbol.upper()

    from redis_cache import cache_get, cache_set
    cache_key = f"orderbook:{sym}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    if _is_crypto_symbol(sym):
        result = await _fetch_coinbase_book(sym)
    else:
        result = await _fetch_alpaca_book(sym)

    await cache_set(cache_key, result, ttl_seconds=ORDERBOOK_TTL_SECONDS)
    return result
