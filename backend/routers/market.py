# backend/routers/market.py
import asyncio
import logging
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slowapi.util import get_remote_address
from scipy.stats import norm

from config import Config
from dependencies import yf_svc, limiter, fred_svc, insider_svc
from redis_cache import cache_get, cache_set
from screener_service import build_universe_snapshot

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-:]{1,15}$")

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


def _bs_greeks(S: float, K: float, T: float, r: float, sigma: float, is_call: bool):
    """Returns (delta, theta) for a European option (Black-Scholes)."""
    # yfinance can hand back NaN/inf implied vol; non-finite inputs would
    # otherwise slip past the `<= 0` checks (NaN comparisons are False) and
    # yield non-finite Greeks (invalid JSON).
    if not all(math.isfinite(x) for x in (S, K, T, sigma)):
        return (0.0, 0.0)
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return (0.0, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if is_call:
        delta = norm.cdf(d1)
        theta = (-(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T))
                 - r * K * math.exp(-r * T) * norm.cdf(d2)) / 365
    else:
        delta = norm.cdf(d1) - 1
        theta = (-(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T))
                 + r * K * math.exp(-r * T) * norm.cdf(-d2)) / 365
    return (round(delta, 3), round(theta, 4))


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
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def dcf_valuation(request: Request, symbol: str):
    import yfinance as yf
    from redis_cache import cache_get, cache_set

    symbol = symbol.strip().upper()
    if not _SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=422, detail="Invalid symbol.")

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
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def options_chain(request: Request, symbol: str, expiry: Optional[str] = None) -> Dict[str, Any]:
    """Returns an options chain (calls + puts) for the given symbol.

    Filters to strikes within ±25% of current price to keep payload small.
    Each contract carries Black-Scholes `delta` and `theta`. Aggregate `stats`
    (put/call ratio, ATM IV, IV skew) are included. An optional `?expiry=`
    query param selects a specific expiry; defaults to the nearest one.
    """
    symbol = symbol.strip().upper()
    if not _SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=422, detail="Invalid symbol.")

    def _fetch() -> Optional[Dict[str, Any]]:
        ticker = yf.Ticker(symbol.upper())
        expirations = ticker.options
        if not expirations:
            return None
        # Honour the requested expiry only when it's a real one; else nearest.
        selected_expiry = expiry if (expiry and expiry in expirations) else expirations[0]
        chain  = ticker.option_chain(selected_expiry)
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

        # Time to expiry in years for the Greeks (floor at 1 day).
        try:
            exp_date = datetime.strptime(selected_expiry, "%Y-%m-%d").date()
            days_to_expiry = (exp_date - date.today()).days
        except ValueError:
            days_to_expiry = 30
        T = max(days_to_expiry, 1) / 365

        def _clean(df: Any, is_call: bool) -> List[Dict[str, Any]]:
            rows = []
            for _, r in df.iterrows():
                strike = float(r.get("strike", 0))
                if abs(strike - price) / price > 0.25:
                    continue
                raw_iv = float(r.get("impliedVolatility", 0) or 0)
                if not math.isfinite(raw_iv) or raw_iv < 0:
                    raw_iv = 0.0
                delta, theta = _bs_greeks(price, strike, T, RISK_FREE_RATE, raw_iv, is_call)
                rows.append({
                    "strike":        round(strike, 2),
                    "last":          round(float(r.get("lastPrice",        0)), 2),
                    "bid":           round(float(r.get("bid",              0)), 2),
                    "ask":           round(float(r.get("ask",              0)), 2),
                    "change":        round(float(r.get("change",           0)), 2),
                    "change_pct":    round(float(r.get("percentChange",    0)), 2),
                    "volume":        _safe_int(r.get("volume",       0)),
                    "open_interest": _safe_int(r.get("openInterest", 0)),
                    "implied_vol":   round(raw_iv * 100, 1),
                    "delta":         delta,
                    "theta":         theta,
                    "in_the_money":  bool(r.get("inTheMoney", False)),
                    "type":          "call" if is_call else "put",
                })
            return rows

        calls = _clean(chain.calls, True)
        puts  = _clean(chain.puts,  False)

        def _atm_iv(rows: List[Dict[str, Any]]) -> float:
            """Mean implied vol of contracts within 5% of spot (ATM)."""
            atm = [r["implied_vol"] for r in rows if abs(r["strike"] - price) / price <= 0.05]
            return round(sum(atm) / len(atm), 1) if atm else 0.0

        iv_avg_calls = _atm_iv(calls)
        iv_avg_puts  = _atm_iv(puts)
        stats = {
            "put_call_ratio": round(
                sum(p["open_interest"] for p in puts)
                / max(sum(c["open_interest"] for c in calls), 1),
                2,
            ),
            "iv_avg_calls": iv_avg_calls,
            "iv_avg_puts":  iv_avg_puts,
            "iv_skew":      round(iv_avg_puts - iv_avg_calls, 1),
        }

        return {
            "symbol":        symbol.upper(),
            "expiry":        selected_expiry,
            "expirations":   list(expirations[:8]),
            "current_price": round(price, 2),
            "calls":         calls,
            "puts":          puts,
            "stats":         stats,
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
# Earnings Calendar
# ---------------------------------------------------------------------------

# Top ~60 S&P 500 constituents by market cap (hardcoded — avoids an index API
# call). Used only as the watchlist for the earnings calendar.
# symbol -> company name. yfinance's FastInfo carries no display_name, and
# calling .info for every ticker would blow the 45s budget — so names for the
# (hardcoded) watchlist are resolved from this static map, no API cost.
EARNINGS_NAMES: Dict[str, str] = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "AMZN": "Amazon",
    "GOOGL": "Alphabet", "META": "Meta Platforms", "TSLA": "Tesla", "AVGO": "Broadcom",
    "BRK-B": "Berkshire Hathaway", "JPM": "JPMorgan Chase", "LLY": "Eli Lilly",
    "V": "Visa", "UNH": "UnitedHealth", "XOM": "Exxon Mobil", "MA": "Mastercard",
    "JNJ": "Johnson & Johnson", "PG": "Procter & Gamble", "HD": "Home Depot",
    "COST": "Costco", "ABBV": "AbbVie", "MRK": "Merck", "CVX": "Chevron",
    "CRM": "Salesforce", "WMT": "Walmart", "BAC": "Bank of America", "NFLX": "Netflix",
    "AMD": "Advanced Micro Devices", "KO": "Coca-Cola", "PEP": "PepsiCo",
    "TMO": "Thermo Fisher", "ACN": "Accenture", "LIN": "Linde", "MCD": "McDonald's",
    "ABT": "Abbott Laboratories", "CSCO": "Cisco", "ORCL": "Oracle", "GE": "GE Aerospace",
    "TXN": "Texas Instruments", "ADBE": "Adobe", "PM": "Philip Morris", "DHR": "Danaher",
    "INTC": "Intel", "QCOM": "Qualcomm", "NEE": "NextEra Energy", "RTX": "RTX Corp",
    "UPS": "United Parcel Service", "AMGN": "Amgen", "INTU": "Intuit",
    "IBM": "IBM", "SBUX": "Starbucks", "CAT": "Caterpillar", "GS": "Goldman Sachs",
    "BLK": "BlackRock", "SPGI": "S&P Global", "AXP": "American Express",
    "NOW": "ServiceNow", "ISRG": "Intuitive Surgical",
}

EARNINGS_WATCHLIST = list(EARNINGS_NAMES.keys())


@router.get("/earnings/calendar")
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def earnings_calendar(request: Request):
    """Returns upcoming earnings dates for S&P 500 top constituents. Cached 6h."""
    from redis_cache import cache_get, cache_set
    CACHE_KEY = "earnings:calendar"
    cached = await cache_get(CACHE_KEY)
    if cached:
        return cached

    def _fetch_earnings():
        results: Dict[str, List[Dict[str, Any]]] = {}
        for ticker in EARNINGS_WATCHLIST:
            try:
                t = yf.Ticker(ticker)
                cal = t.calendar  # dict or DataFrame depending on yfinance version
                if cal is None:
                    continue
                if hasattr(cal, "loc"):  # DataFrame
                    if "Earnings Date" in cal.index:
                        dates = cal.loc["Earnings Date"]
                        date_val = (
                            str(dates.iloc[0])[:10]
                            if hasattr(dates, "iloc") else str(dates)[:10]
                        )
                    else:
                        continue
                elif isinstance(cal, dict):
                    date_val = cal.get("Earnings Date", [None])
                    if isinstance(date_val, list):
                        date_val = str(date_val[0])[:10] if date_val else None
                    else:
                        date_val = str(date_val)[:10]
                else:
                    continue
                if not date_val or date_val == "None":
                    continue

                # fast_info is cheaper than .info for market cap; names come
                # from the static map (FastInfo has no display_name).
                info = t.fast_info
                short_name = EARNINGS_NAMES.get(ticker) or getattr(info, "display_name", ticker) or ticker
                market_cap = getattr(info, "market_cap", 0) or 0

                results.setdefault(date_val, []).append({
                    "symbol": ticker,
                    "name": short_name,
                    "market_cap": market_cap,
                    "date": date_val,
                })
            except Exception as _exc:
                logger.debug("[EARNINGS] skipping ticker %s: %s", ticker, _exc)
                continue

        # Sort each day's entries by market cap desc, keep top 8.
        calendar: Dict[str, List[Dict[str, Any]]] = {}
        for date_str, entries in results.items():
            entries.sort(key=lambda x: x["market_cap"], reverse=True)
            calendar[date_str] = entries[:8]
        return calendar

    try:
        # Intentional exception to the 12s per-fetch guideline: this batches ~57
        # sequential yfinance calls and runs at most once per 6h (Redis cache),
        # never on a hot path. 12s cannot complete the full watchlist sweep.
        data = await asyncio.wait_for(asyncio.to_thread(_fetch_earnings), timeout=45.0)
    except asyncio.TimeoutError:
        logger.warning("[EARNINGS] calendar fetch timed out")
        raise HTTPException(status_code=504, detail="Earnings calendar temporarily unavailable")

    payload = {"calendar": data, "generated_at": datetime.now(timezone.utc).isoformat()}
    await cache_set(CACHE_KEY, payload, ttl_seconds=21600)  # 6h TTL
    return payload


# ---------------------------------------------------------------------------
# IPO Calendar
# ---------------------------------------------------------------------------

# --- Nasdaq IPO calendar (free, no key) parsing helpers ---------------------

def _nasdaq_date_to_iso(s: Any) -> str:
    """Convert Nasdaq's ``M/D/YYYY`` date to ISO ``YYYY-MM-DD`` ('' if invalid)."""
    if not isinstance(s, str):
        return ""
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", s)
    if not m:
        return ""
    mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return ""


def _parse_price_string(s: Any) -> Tuple[Optional[float], Optional[float]]:
    """``"135.00"`` -> (135.0, 135.0); ``"15.00-17.00"`` -> (15.0, 17.0)."""
    if not isinstance(s, str) or not s.strip():
        return None, None

    def _n(x: str) -> Optional[float]:
        try:
            return float(x.strip())
        except (TypeError, ValueError):
            return None

    parts = [p for p in s.replace("$", "").replace(",", "").split("-") if p.strip()]
    if len(parts) >= 2:
        return _n(parts[0]), _n(parts[-1])
    if len(parts) == 1:
        v = _n(parts[0])
        return v, v
    return None, None


def _parse_loose_int(s: Any) -> Optional[int]:
    """Parse ``"555,555,555"`` / ``"$86,000,000"`` -> int (None if unparseable)."""
    if s is None:
        return None
    try:
        return int(float(str(s).replace(",", "").replace("$", "").strip()))
    except (TypeError, ValueError):
        return None


def _normalize_nasdaq_row(
    row: Dict[str, Any], status: str, action: str
) -> Optional[Dict[str, Any]]:
    """Map a Nasdaq IPO-calendar row onto the shared IPO card shape."""
    symbol = str(row.get("proposedTickerSymbol") or row.get("symbol") or "").strip()
    company = str(row.get("companyName") or "").strip()
    if not symbol and not company:
        return None
    low, high = _parse_price_string(row.get("proposedSharePrice"))
    iso = _nasdaq_date_to_iso(
        row.get("expectedPriceDate") or row.get("pricedDate")
        or row.get("priceDate") or row.get("filedDate") or row.get("dealDate")
    )
    return {
        "symbol":     symbol,
        "company":    company or "Unknown",
        "exchange":   str(row.get("proposedExchange") or row.get("exchange") or "").strip(),
        "date":       iso,
        "price_low":  low,
        "price_high": high,
        "shares":     _parse_loose_int(row.get("sharesOffered")),
        "market_cap": _parse_loose_int(row.get("dollarValueOfSharesOffered")),
        "actions":    action,
        "status":     status,
    }


@router.get("/ipo/calendar")
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def ipo_calendar(request: Request, refresh: bool = False) -> Dict[str, Any]:
    """Upcoming (next 90d) + recent (last 30d) public offerings.

    Source chain (degrades on failure):
      1. Nasdaq IPO calendar — free, no key; the default upcoming + recent feed.
      2. SEC EDGAR S-1 filings — keyless last resort (recent filings only).
    Cached 4h in Redis; pass ``?refresh=true`` to force a live re-fetch.
    """
    from redis_cache import cache_get, cache_set
    CACHE_KEY = "ipo:calendar"
    if not refresh:
        cached = await cache_get(CACHE_KEY)
        if cached:
            return cached

    today = date.today()

    async def _fetch_nasdaq() -> List[Dict[str, Any]]:
        """Free Nasdaq IPO calendar — upcoming + priced/filed/withdrawn, no key.

        The endpoint is queried per calendar month, so we sweep the months that
        cover the last ~30 and next ~90 days and de-dupe by deal id.
        """
        months: List[str] = []
        base = today.year * 12 + (today.month - 1)
        for delta in range(-1, 4):  # previous month .. +3 months
            total = base + delta
            months.append(f"{total // 12:04d}-{total % 12 + 1:02d}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            async def _month(mo: str) -> Optional[Dict[str, Any]]:
                try:
                    r = await client.get(
                        f"https://api.nasdaq.com/api/ipo/calendar?date={mo}"
                    )
                    r.raise_for_status()
                    return r.json()
                except Exception as exc:
                    logger.info(f"[IPO] Nasdaq month {mo} failed: {exc}")
                    return None

            payloads = await asyncio.gather(*[_month(mo) for mo in months])

        datas = [
            d for d in ((p or {}).get("data") for p in payloads) if isinstance(d, dict)
        ]

        def _rows(data: Dict[str, Any], table: str) -> List[Dict[str, Any]]:
            tbl = data.get(table) or {}
            if table == "upcoming":
                tbl = tbl.get("upcomingTable") or {}
            return tbl.get("rows") or []

        results: List[Dict[str, Any]] = []
        seen: set = set()

        def _ingest(rows: List[Dict[str, Any]], status: str, action: str) -> None:
            for row in rows:
                norm = _normalize_nasdaq_row(row, status, action)
                if norm is None:
                    continue
                key = row.get("dealID") or f"{norm['symbol']}|{norm['company']}|{norm['date']}"
                if key in seen:
                    continue
                seen.add(key)
                results.append(norm)

        # Pass 1 — upcoming first so a scheduled deal wins dedup over any later
        # "recent" duplicate of itself (the same IPO often also appears in the
        # priced/withdrawn tables of an adjacent month).
        for data in datas:
            _ingest(_rows(data, "upcoming"), "upcoming", "Expected")
        # Pass 2 — recently actioned IPOs. The "filed" table (raw S-1 filings) is
        # intentionally skipped: it's huge, undated, and overlaps EDGAR's role.
        for data in datas:
            _ingest(_rows(data, "priced"), "recent", "Priced")
            _ingest(_rows(data, "withdrawn"), "recent", "Withdrawn")

        if not results:
            raise RuntimeError("Nasdaq returned no IPO rows")
        return results

    async def _fetch_edgar_fallback() -> List[Dict[str, Any]]:
        """Lightweight fallback: recent S-1 filings from EDGAR full-text search."""
        from_date = (today - timedelta(days=30)).isoformat()
        url = (
            "https://efts.sec.gov/LATEST/search-index"
            f"?forms=S-1&dateRange=custom&startdt={from_date}"
            "&_source=file_date,display_names,period_of_report"
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url, headers={"User-Agent": "FiForesight research@fiforesight.dev"}
            )
            resp.raise_for_status()
            raw = resp.json()

        results: List[Dict[str, Any]] = []
        hits = ((raw or {}).get("hits", {}) or {}).get("hits", []) or []
        for hit in hits[:20]:
            src = hit.get("_source", {}) or {}
            names = src.get("display_names") or []
            results.append({
                "symbol":     "",
                "company":    names[0] if names else "Unknown",
                "exchange":   "US",
                "date":       src.get("file_date", "") or "",
                "price_low":  None,
                "price_high": None,
                "shares":     None,
                "market_cap": None,
                "actions":    "S-1 Filed",
                "status":     "recent",
            })
        return results

    data: Optional[List[Dict[str, Any]]] = None
    source = "edgar"

    # 1) Free Nasdaq IPO calendar — the default upcoming + recent source.
    try:
        data = await asyncio.wait_for(_fetch_nasdaq(), timeout=12.0)
        source = "nasdaq"
    except Exception as e:
        logger.warning(f"[IPO] Nasdaq fetch failed ({e!r}); falling back to SEC EDGAR")
        data = None

    # 2) SEC EDGAR S-1 filings — keyless last resort (recent only).
    if data is None:
        try:
            data = await asyncio.wait_for(_fetch_edgar_fallback(), timeout=12.0)
            source = "edgar"
        except asyncio.TimeoutError:
            logger.warning("[IPO] EDGAR fallback timed out")
            raise HTTPException(status_code=504, detail="IPO calendar temporarily unavailable")
        except Exception as e:
            logger.warning(f"[IPO] EDGAR fallback failed: {e}")
            raise HTTPException(status_code=502, detail="IPO data provider error")

    # Upcoming first (ascending by date), then recent (most recent first).
    upcoming = sorted(
        [x for x in data if x["status"] == "upcoming"], key=lambda x: x["date"]
    )
    recent = sorted(
        [x for x in data if x["status"] == "recent"], key=lambda x: x["date"], reverse=True
    )[:60]  # cap the recent list so a busy filing window can't bloat the payload

    payload = {
        "upcoming":     upcoming,
        "recent":       recent,
        "source":       source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    await cache_set(CACHE_KEY, payload, ttl_seconds=14400)  # 4h TTL
    return payload


# ---------------------------------------------------------------------------
# Sector Heatmap (F23)
# ---------------------------------------------------------------------------
# Single source of truth for sector data: per-ETF 1D + 5D return with full GICS
# names. Feeds both the dedicated "Sectors" tab and the compact landing overview.

SECTOR_ETF_MAP = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Energy": "XLE",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}


@router.get("/sectors/heatmap")
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def get_sector_heatmap(request: Request) -> List[Dict[str, Any]]:
    """11 GICS sector ETFs with 1D + 5D % returns. Cached 15 min."""
    from redis_cache import cache_get, cache_set
    CACHE_KEY = "sectors:heatmap:f23"
    cached = await cache_get(CACHE_KEY)
    if cached:
        return cached

    def _closes_for(raw, etf):
        """Close series for one ETF from a yf.download frame. Handles the grouped
        (multi-ticker) and flat (single-ticker retry) column layouts; raises
        KeyError when the ticker was dropped from a grouped batch."""
        try:
            return raw[etf]["Close"].dropna()
        except KeyError:
            # A single-ticker download isn't grouped by ticker.
            return raw["Close"].dropna()

    def _download_rows(etfs: List[str]) -> Dict[str, Dict[str, Any]]:
        raw = yf.download(
            " ".join(etfs), period="6d", auto_adjust=True,
            progress=False, group_by="ticker",
        )
        out: Dict[str, Dict[str, Any]] = {}
        # iterate the canonical map so each row keeps its full sector name
        for sector, etf in SECTOR_ETF_MAP.items():
            if etf not in etfs:
                continue
            try:
                closes = _closes_for(raw, etf)
                if len(closes) < 2:
                    continue
                ret_1d = (closes.iloc[-1] / closes.iloc[-2] - 1) * 100
                ret_5d = (closes.iloc[-1] / closes.iloc[0] - 1) * 100 if len(closes) >= 5 else None
                out[etf] = {
                    "sector": sector,
                    "etf": etf,
                    "price": round(float(closes.iloc[-1]), 2),
                    "return1d": round(float(ret_1d), 2),
                    "return5d": round(float(ret_5d), 2) if ret_5d is not None else None,
                    "source": "yfinance",
                }
            except Exception as e:
                logger.warning(f"sector heatmap {etf}: {e}")
        return out

    def _fetch() -> List[Dict[str, Any]]:
        all_etfs = list(SECTOR_ETF_MAP.values())
        rows = _download_rows(all_etfs)
        # yfinance intermittently drops a ticker from a grouped batch (transient).
        # Retry just the missing ones once so a sector doesn't silently vanish.
        missing = [etf for etf in all_etfs if etf not in rows]
        if missing:
            logger.info("sector heatmap retrying %d missing ETFs: %s", len(missing), missing)
            rows.update(_download_rows(missing))
        # Emit in canonical sector order.
        return [rows[etf] for etf in all_etfs if etf in rows]

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=12.0)
    except Exception as e:
        logger.error(f"sector heatmap: {e}")
        raise HTTPException(status_code=502, detail="Could not fetch sector data")

    # No usable rows for any ETF => treat as an upstream failure (provider outage),
    # not an empty-but-OK response, so the UI can show its error state.
    if not result:
        logger.warning("sector heatmap returned no usable ETF rows")
        raise HTTPException(status_code=502, detail="Could not fetch sector data")

    await cache_set(CACHE_KEY, result, ttl_seconds=900)
    return result


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
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def morning_briefing(request: Request):
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
            except Exception as _exc:
                logger.debug("[BRIEFING] fetch failed for %s: %s", ticker, _exc)
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
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def order_book(request: Request, symbol: str) -> Dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Alternative Data (Feature 15) — FRED macro snapshot + SEC EDGAR insider flow
# ---------------------------------------------------------------------------

@router.get("/macro/snapshot")
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def macro_snapshot(request: Request) -> Dict[str, Any]:
    """FRED macro snapshot — 10Y yield, CPI, unemployment, fed funds, yield curve.

    Each series carries ``{value, delta_30d}``; the payload also flags yield-curve
    ``inverted`` and includes the T10Y2Y 31-point trend. Redis-cached 1h inside
    the service; returns ``{}`` when FRED is unreachable (frontend shows an
    empty state). 60/min.
    """
    return await fred_svc.get_macro_snapshot()


@router.get("/insider/{symbol}")
@limiter.limit(lambda: Config.RATE_LIMIT_INSIDER, key_func=get_remote_address)
async def insider_transactions(request: Request, symbol: str) -> List[Dict[str, Any]]:
    """Recent (last 30d) SEC EDGAR Form 4 insider filings for ``symbol``.

    Returns a list of ``{filer, type, shares, price, date, sec_link}``. Empty
    list for tickers with no recent filings (crypto/foreign) or on any failure.
    Redis-cached 6h in the service. 30/min via the read-only limiter.
    """
    symbol = symbol.strip().upper()
    if not _SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=422, detail="Invalid symbol.")
    return await insider_svc.get_insider_transactions(symbol)


@router.get("/analyst-targets/{symbol}")
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def analyst_targets(request: Request, symbol: str) -> Dict[str, Any]:
    """Wall Street analyst price targets + rating breakdown for ``symbol``.

    Returns target low/mean/median/high, the current price, the number of
    covering analysts, and the strongBuy/buy/hold/sell/strongSell recommendation
    counts. yfinance's ``analyst_price_targets`` carries the price band but not
    the analyst count, so ``.info`` fills the gaps. Redis-cached 6h; 502 when the
    upstream fetch fails so the frontend can fall back to its empty state. 60/min.
    """
    from redis_cache import cache_get, cache_set

    sym = symbol.strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=422, detail="Invalid symbol.")

    cache_key = f"analyst_targets:{sym}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    def _fetch() -> Dict[str, Any]:
        t = yf.Ticker(sym)
        targets = t.analyst_price_targets or {}

        # numberOfAnalysts / current price aren't part of analyst_price_targets in
        # current yfinance builds — read .info as a fallback so the card has the
        # full picture on real data (info uses targetMeanPrice-style key names).
        info: Dict[str, Any] = {}
        try:
            info = t.info or {}
        except Exception:
            info = {}

        def _pick(*vals: Any) -> Any:
            for v in vals:
                if v is not None:
                    return v
            return None

        def _num_or_none(v: Any) -> Optional[float]:
            """Coerce to a finite number, mapping None/NaN/inf/garbage to None.

            yfinance can hand back NaN/inf; Starlette's JSONResponse serializes
            with ``allow_nan=False``, so an unsanitized NaN would 500 the whole
            response instead of degrading to a null field."""
            try:
                if v is None:
                    return None
                n = float(v)
                if not math.isfinite(n):
                    return None
                return int(n) if n.is_integer() else n
            except (TypeError, ValueError):
                return None

        recs = {"strongBuy": 0, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}
        rec_df = t.recommendations_summary
        if rec_df is not None and not rec_df.empty:
            row = rec_df.iloc[0]
            for k in recs:
                recs[k] = _safe_int(row.get(k, 0))

        return {
            "symbol": sym,
            "currentPrice": _num_or_none(_pick(targets.get("currentPrice"),
                                               targets.get("current"), info.get("currentPrice"))),
            "targetLow": _num_or_none(_pick(targets.get("low"), info.get("targetLowPrice"))),
            "targetMean": _num_or_none(_pick(targets.get("mean"), info.get("targetMeanPrice"))),
            "targetMedian": _num_or_none(_pick(targets.get("median"), info.get("targetMedianPrice"))),
            "targetHigh": _num_or_none(_pick(targets.get("high"), info.get("targetHighPrice"))),
            "numberOfAnalysts": _num_or_none(_pick(targets.get("numberOfAnalysts"),
                                                   info.get("numberOfAnalystOpinions"))),
            **recs,
        }

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=12.0)
    except Exception as e:
        logger.error(f"analyst_targets {sym}: {e}")
        raise HTTPException(status_code=502, detail="Could not fetch analyst targets")

    await cache_set(cache_key, result, ttl_seconds=21600)  # 6h TTL
    return result


@router.get("/dividends/{symbol}")
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def dividends(request: Request, symbol: str) -> Dict[str, Any]:
    """Dividend / income profile for ``symbol``. Redis-cached 6h; 502 on fetch
    failure. Non-payers return {"symbol", "paysDividend": False}. 60/min."""
    from redis_cache import cache_get, cache_set

    sym = symbol.strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=422, detail="Invalid symbol.")

    cache_key = f"dividends:{sym}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    def _fetch() -> Dict[str, Any]:
        t = yf.Ticker(sym)
        info = {}
        try:
            info = t.info or {}
        except Exception:
            info = {}

        def _num(v):  # reuse the NaN-safe coercion style from analyst_targets
            try:
                if v is None:
                    return None
                n = float(v)
                return None if not math.isfinite(n) else (int(n) if n.is_integer() else n)
            except (TypeError, ValueError):
                return None

        # Sanitize through _num first so a NaN/inf from yfinance becomes None and
        # never reaches JSON serialization (allow_nan=False would 500 the response).
        div_yield = _num(info.get("dividendYield"))
        rate = info.get("dividendRate")
        pays = bool(rate) or bool(div_yield)

        # dividend growth: compare trailing-12mo dividends vs the prior 12mo
        growth_pct = None
        try:
            divs = t.dividends  # pandas Series indexed by date
            if divs is not None and len(divs) >= 2:
                cutoff = divs.index.max()
                last_12 = divs[divs.index > (cutoff - pd.Timedelta(days=365))].sum()
                prev_12 = divs[(divs.index <= (cutoff - pd.Timedelta(days=365))) &
                               (divs.index > (cutoff - pd.Timedelta(days=730)))].sum()
                if prev_12 > 0:
                    growth_pct = round((last_12 / prev_12 - 1) * 100, 1)
        except Exception:
            growth_pct = None

        ex_date = info.get("exDividendDate")
        ex_iso = None
        if ex_date:
            try:
                ex_iso = datetime.utcfromtimestamp(int(ex_date)).strftime("%Y-%m-%d")
            except Exception:
                ex_iso = None

        return {
            "symbol": sym,
            "paysDividend": pays,
            "dividendYield": round(div_yield * 100, 2) if div_yield is not None else None,
            "dividendRate": _num(rate),
            "payoutRatio": round(_num(info.get("payoutRatio")) * 100, 1)
                if _num(info.get("payoutRatio")) is not None else None,
            "fiveYearAvgYield": _num(info.get("fiveYearAvgDividendYield")),
            "exDividendDate": ex_iso,
            "dividendGrowthPct": growth_pct,
        }

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=12.0)
    except Exception as e:
        logger.error(f"dividends {sym}: {e}")
        raise HTTPException(status_code=502, detail="Could not fetch dividend data")

    await cache_set(cache_key, result, ttl_seconds=21600)  # 6h TTL
    return result


# ---------------------------------------------------------------------------
# Equity Screener (Light Edition, F24)
# ---------------------------------------------------------------------------
class ScreenerFilter(BaseModel):
    """Filter/sort criteria for the curated-universe screener. All bounds optional."""
    sector: Optional[str] = None          # e.g. "Technology"
    minPE: Optional[float] = None
    maxPE: Optional[float] = None
    minRSI: Optional[float] = None
    maxRSI: Optional[float] = None
    minBeta: Optional[float] = None
    maxBeta: Optional[float] = None
    minDividendYield: Optional[float] = None
    sortBy: str = "marketCap"             # marketCap | peRatio | rsi | dividendYield
    sortDir: str = "desc"                 # asc | desc
    limit: int = 25


_SCREENER_SORT_KEYS = {"marketCap", "peRatio", "forwardPE", "beta", "rsi", "dividendYield", "revenueGrowth"}


@router.post("/screener")
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def run_screener(request: Request, filters: ScreenerFilter) -> Dict[str, Any]:
    """Filter & sort the curated ~50-stock universe (F24).

    Builds the universe snapshot on-demand (one yfinance row per ticker), caches
    it in Redis for 1h, then applies the requested numeric/sector filters and sort
    in-memory. Returns ``{results, total}`` where ``total`` is the post-filter count
    and ``results`` is capped at ``limit``. 60/min via the read-only limiter.
    """
    cache_key = "screener:universe"
    snapshot = await cache_get(cache_key)
    if not isinstance(snapshot, list) or not snapshot:
        snapshot = await build_universe_snapshot()
        if snapshot:
            await cache_set(cache_key, snapshot, ttl_seconds=3600)  # 1h TTL

    rows = snapshot or []
    if filters.sector:
        rows = [r for r in rows if r.get("sector") == filters.sector]
    if filters.minPE is not None:
        rows = [r for r in rows if r.get("peRatio") is not None and r["peRatio"] >= filters.minPE]
    if filters.maxPE is not None:
        rows = [r for r in rows if r.get("peRatio") is not None and r["peRatio"] <= filters.maxPE]
    if filters.minRSI is not None:
        rows = [r for r in rows if r.get("rsi") is not None and r["rsi"] >= filters.minRSI]
    if filters.maxRSI is not None:
        rows = [r for r in rows if r.get("rsi") is not None and r["rsi"] <= filters.maxRSI]
    if filters.minBeta is not None:
        rows = [r for r in rows if r.get("beta") is not None and r["beta"] >= filters.minBeta]
    if filters.maxBeta is not None:
        rows = [r for r in rows if r.get("beta") is not None and r["beta"] <= filters.maxBeta]
    if filters.minDividendYield is not None:
        rows = [r for r in rows
                if r.get("dividendYield") is not None and r["dividendYield"] >= filters.minDividendYield]

    sort_key = filters.sortBy if filters.sortBy in _SCREENER_SORT_KEYS else "marketCap"
    reverse = filters.sortDir == "desc"
    rows = sorted(rows, key=lambda x: (x.get(sort_key) or 0), reverse=reverse)

    limit = max(1, min(filters.limit, 50))
    return {"results": rows[:limit], "total": len(rows)}
