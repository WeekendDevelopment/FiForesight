# backend/simulation_service.py
import asyncio
import json
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Callable, Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# ── Rate-limit guard ──────────────────────────────────────────────────────────
# Caps concurrent yfinance HTTP calls. Prevents Yahoo Finance 429s when many
# tickers or ETFs are fetched in parallel during simulation setup.
_YF_SEM: Optional[asyncio.Semaphore] = None


def _yf_sem() -> asyncio.Semaphore:
    """Lazy singleton — must be called inside a running event loop."""
    global _YF_SEM
    if _YF_SEM is None:
        _YF_SEM = asyncio.Semaphore(5)
    return _YF_SEM


# ── Dynamic universe: sector ETFs by risk level ───────────────────────────────
# ETF compositions reflect real market state at query time — top holdings
# change as constituents are added/removed, so this stays current without
# manual curation.  Conservative = large-cap stable; Aggressive = thematic/growth.
SECTOR_ETF_MAP: Dict[str, Dict[str, List[str]]] = {
    "Technology": {
        "conservative": ["XLK"],
        "moderate":     ["XLK", "VGT"],
        "aggressive":   ["ARKW", "WCLD"],
    },
    "Healthcare": {
        "conservative": ["XLV"],
        "moderate":     ["XLV", "VHT"],
        "aggressive":   ["ARKG"],
    },
    "Finance": {
        "conservative": ["XLF"],
        "moderate":     ["XLF", "KBE"],
        "aggressive":   ["KBWB", "FINX"],
    },
    "Energy": {
        "conservative": ["XLE"],
        "moderate":     ["XLE", "ICLN"],
        "aggressive":   ["XOP", "TAN"],
    },
    "Consumer": {
        "conservative": ["XLP"],
        "moderate":     ["XLY", "VCR"],
        "aggressive":   ["FDIS", "IBUY"],
    },
    "Industrial": {
        "conservative": ["XLI"],
        "moderate":     ["XLI", "VIS"],
        "aggressive":   ["ROKT", "DRIV"],
    },
}

# ── Static fallback pool ──────────────────────────────────────────────────────
# Used only when all ETF holdings fetches fail (network down, API change, etc.)
SECTOR_POOL: Dict[str, Dict[str, List[str]]] = {
    "Technology": {
        "conservative": ["MSFT", "AAPL", "GOOGL"],
        "moderate":     ["MSFT", "AAPL", "NVDA", "META", "GOOGL"],
        "aggressive":   ["NVDA", "AMD", "META", "PLTR", "SMCI"],
    },
    "Healthcare": {
        "conservative": ["JNJ", "UNH", "ABT"],
        "moderate":     ["UNH", "ABBV", "LLY", "PFE", "JNJ"],
        "aggressive":   ["MRNA", "CRSP", "DXCM", "RXRX", "NVAX"],
    },
    "Finance": {
        "conservative": ["JPM", "BRK-B", "V"],
        "moderate":     ["JPM", "GS", "V", "MA", "BAC"],
        "aggressive":   ["COIN", "HOOD", "SOFI", "SQ", "UPST"],
    },
    "Energy": {
        "conservative": ["XOM", "CVX", "NEE"],
        "moderate":     ["XOM", "CVX", "OXY", "FSLR", "NEE"],
        "aggressive":   ["ENPH", "PLUG", "AR", "CHPT", "BLNK"],
    },
    "Consumer": {
        "conservative": ["WMT", "PG", "KO"],
        "moderate":     ["AMZN", "COST", "SBUX", "WMT", "NKE"],
        "aggressive":   ["TSLA", "DKNG", "DASH", "LYFT", "ABNB"],
    },
    "Industrial": {
        "conservative": ["CAT", "DE", "HON"],
        "moderate":     ["GE", "CAT", "BA", "DE", "HON"],
        "aggressive":   ["RKLB", "JOBY", "ACHR", "IONQ", "SPCE"],
    },
}

BENCHMARK_SYMBOL = "SPY"

# 24-hour in-memory cache for ETF top-holdings.
# A single process restart clears it; that's fine — one cold fetch per day per ETF.
_ETF_HOLDINGS_CACHE: Dict[str, tuple] = {}  # etf_symbol -> ([tickers], fetched_unix_ts)
_ETF_CACHE_TTL = 86_400  # seconds


# ── ETF holdings fetcher ──────────────────────────────────────────────────────

async def _fetch_etf_holdings(etf_symbol: str) -> List[str]:
    """
    Return the top holding tickers for an ETF, cached 24 h.
    Tries two yfinance strategies before giving up gracefully.
    """
    cached = _ETF_HOLDINGS_CACHE.get(etf_symbol)
    if cached and (time.time() - cached[1]) < _ETF_CACHE_TTL:
        logger.debug("[SIM] ETF cache hit: %s (%d symbols)", etf_symbol, len(cached[0]))
        return cached[0]

    symbols: List[str] = []
    try:
        async with _yf_sem():
            ticker = yf.Ticker(etf_symbol)

            # Strategy 1: funds_data.top_holdings (yfinance >= 0.2.31)
            try:
                fd = await asyncio.to_thread(lambda: ticker.funds_data)
                if fd is not None:
                    df = await asyncio.to_thread(lambda: fd.top_holdings)
                    if df is not None and not df.empty:
                        col = next((c for c in ("Symbol", "symbol") if c in df.columns), None)
                        symbols = df[col].dropna().tolist() if col else df.index.tolist()
            except Exception as exc:
                logger.debug("[SIM] %s funds_data failed: %s", etf_symbol, exc)

            # Strategy 2: get_holdings()
            if not symbols:
                try:
                    df2 = await asyncio.to_thread(ticker.get_holdings)
                    if df2 is not None and not df2.empty:
                        col = next((c for c in ("Symbol", "symbol") if c in df2.columns), None)
                        symbols = df2[col].dropna().tolist() if col else df2.index.tolist()
                except Exception as exc:
                    logger.debug("[SIM] %s get_holdings failed: %s", etf_symbol, exc)

    except Exception as exc:
        logger.warning("[SIM] _fetch_etf_holdings(%s) outer error: %s", etf_symbol, exc)

    symbols = [
        str(s).upper().strip()
        for s in symbols
        if s and str(s).strip() not in ("", "nan")
    ][:20]

    if symbols:
        _ETF_HOLDINGS_CACHE[etf_symbol] = (symbols, time.time())
        logger.info("[SIM] ETF %s → %d holdings cached", etf_symbol, len(symbols))
    else:
        logger.warning("[SIM] ETF %s: no holdings resolved, will use static fallback", etf_symbol)

    return symbols


# ── Candidate pool builder ────────────────────────────────────────────────────

async def _build_candidate_pool(
    sectors: List[str],
    risk_level: str,
    max_candidates: int = 15,
) -> tuple[List[str], str]:
    """
    Tier-1 (dynamic): per-sector ETF top-holdings — time-appropriate, cache-backed.
    Tier-2 (static):  per-sector SECTOR_POOL fallback for sectors whose ETF
                      discovery returns nothing. This avoids silently dropping a
                      requested sector when only one sector's ETFs fail.
    Returns (candidates, source_label) where source_label is 'etf', 'static',
    or 'mixed' when some sectors resolved dynamically and others fell back.
    """
    # Collect per-sector ETF lists, deduped but order-preserving.
    sector_etfs: Dict[str, List[str]] = {}
    for sector in sectors:
        sector_map = SECTOR_ETF_MAP.get(sector, {})
        sector_etfs[sector] = list(sector_map.get(risk_level, sector_map.get("moderate", [])))

    # Fetch all unique ETFs once, then stitch back per-sector.
    unique_etfs: List[str] = []
    for etfs in sector_etfs.values():
        for etf in etfs:
            if etf not in unique_etfs:
                unique_etfs.append(etf)

    etf_holdings: Dict[str, List[str]] = {}
    if unique_etfs:
        results = await asyncio.gather(
            *[_fetch_etf_holdings(e) for e in unique_etfs], return_exceptions=True
        )
        for etf, result in zip(unique_etfs, results):
            etf_holdings[etf] = result if isinstance(result, list) else []

    candidates: List[str] = []
    etf_resolved_sectors = 0
    static_fallback_sectors = 0

    for sector in sectors:
        sector_candidates: List[str] = []
        for etf in sector_etfs.get(sector, []):
            for sym in etf_holdings.get(etf, []):
                if sym not in sector_candidates:
                    sector_candidates.append(sym)

        if sector_candidates:
            etf_resolved_sectors += 1
        else:
            # Per-sector static fallback — don't drop this sector on ETF failure.
            logger.warning(
                "[SIM] ETF discovery empty for sector %r — using static pool", sector,
            )
            static_fallback_sectors += 1
            pool = SECTOR_POOL.get(sector, {})
            sector_candidates = list(pool.get(risk_level, pool.get("moderate", [])))

        for sym in sector_candidates:
            if sym not in candidates:
                candidates.append(sym)

    if not candidates:
        candidates = list(SECTOR_POOL["Technology"]["moderate"])
        return candidates[:max_candidates], "static"

    if static_fallback_sectors == 0:
        source = "etf"
    elif etf_resolved_sectors == 0:
        source = "static"
    else:
        source = "mixed"

    logger.info(
        "[SIM] Candidate pool: %d symbols (etf_sectors=%d, static_sectors=%d, source=%s)",
        len(candidates), etf_resolved_sectors, static_fallback_sectors, source,
    )
    return candidates[:max_candidates], source


# ── RSI helper ────────────────────────────────────────────────────────────────

def _calc_rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    recent = deltas[-period:]
    gains  = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)


async def _analyze_ticker(
    symbol: str,
    yf_svc: Any,
    run_forecast_fn: Callable[..., Dict],
    influx_svc: Optional[Any],
) -> Optional[Dict]:
    """Fetch OHLCV data and run ensemble ML forecast for one ticker."""
    try:
        yf_sym = yf_svc._to_yf_symbol(symbol) if hasattr(yf_svc, "_to_yf_symbol") else symbol
        ticker_obj = yf.Ticker(yf_sym)
        async with _yf_sem():
            df = await asyncio.to_thread(
                ticker_obj.history, period="3mo", interval="1d", auto_adjust=True
            )
        if df is None or df.empty or len(df) < 20:
            logger.warning("[SIM] %s: insufficient data", symbol)
            return None

        ohlcv_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        df_clean   = df[ohlcv_cols].dropna()
        if len(df_clean) < 20:
            logger.warning("[SIM] %s: insufficient data after cleaning (%d rows)", symbol, len(df_clean))
            return None

        closes  = df_clean["Close"].tolist()
        opens   = df_clean["Open"].tolist()   if "Open"   in df_clean.columns else None
        highs   = df_clean["High"].tolist()   if "High"   in df_clean.columns else None
        lows    = df_clean["Low"].tolist()    if "Low"    in df_clean.columns else None
        volumes = df_clean["Volume"].tolist() if "Volume" in df_clean.columns else None

        async with _yf_sem():
            info = await asyncio.to_thread(yf_svc.fetch_info, symbol)

        hist_weights = None
        sample_count = 0
        if influx_svc:
            try:
                acc = await asyncio.to_thread(influx_svc.query_model_accuracy, symbol)
                if acc:
                    maes = [
                        acc.get("prophet", {}).get("mae", 1.0),
                        acc.get("sarima",  {}).get("mae", 1.0),
                        acc.get("rf",      {}).get("mae", 1.0),
                    ]
                    sample_count = min(
                        acc.get("prophet", {}).get("samples", 0),
                        acc.get("sarima",  {}).get("samples", 0),
                        acc.get("rf",      {}).get("samples", 0),
                    )
                    total_inv = sum(1.0 / m if m > 0 else 1.0 for m in maes)
                    hist_weights = [(1.0 / m if m > 0 else 1.0) / total_inv for m in maes]
            except Exception as exc:
                logger.warning("[SIM] %s: InfluxDB weight fetch failed: %s", symbol, exc)

        forecast = await asyncio.to_thread(
            run_forecast_fn,
            closes, symbol,
            opens, highs, lows, volumes,
            hist_weights, sample_count,
        )

        live_price = info.get("current_price") or float(closes[-1])
        mc         = forecast.get("monte_carlo") or {}
        return {
            "symbol":       symbol,
            "name":         info.get("short_name", symbol),
            "sector":       info.get("sector", "Unknown"),
            "currentPrice": float(live_price),
            "forecast":     forecast,
            "rsi":          _calc_rsi(closes),
            "var_95":       mc.get("var_95"),
            "prob_gain":    mc.get("prob_gain"),
        }
    except Exception as exc:
        logger.error("[SIM] _analyze_ticker(%s) failed: %s", symbol, exc)
        return None


def _score(stock: Dict, risk_level: str) -> float:
    forecast  = stock.get("forecast", {})
    days      = forecast.get("forecast_days", [])
    conf_avg  = sum(d.get("confidence_pct", 50) for d in days) / max(len(days), 1)
    current   = stock["currentPrice"]
    high_5d   = forecast.get("high", current)
    low_5d    = forecast.get("low",  current)
    mid       = (high_5d + low_5d) / 2
    upside    = ((mid - current) / current * 100) if current > 0 else 0
    rsi       = stock.get("rsi", 50)
    rsi_pen   = max(0, rsi - 70) + max(0, 30 - rsi)
    score     = conf_avg * 0.5 + upside * 0.3 - rsi_pen * 0.2
    if risk_level == "conservative":
        score += conf_avg * 0.2
    elif risk_level == "aggressive":
        score += upside * 0.3
    return score


async def _bulk_jury(
    stocks: List[Dict],
    risk_level: str,
    analyst_jury_svc: Optional[Any],
) -> Dict[str, Dict]:
    """Concurrent per-stock Groq calls so one failure never drops the whole batch."""
    if not stocks or not analyst_jury_svc:
        return {}

    async def _rate_one(s: Dict) -> tuple:
        sym    = s["symbol"]
        f      = s.get("forecast", {})
        cur    = s["currentPrice"]
        upside = ((f.get("high", cur) - cur) / cur * 100) if cur > 0 else 0
        prompt = (
            f"Rate for a {risk_level} investor.\n"
            f"{sym} ({s['sector']}): ${cur:.2f}, upside {upside:+.1f}%, "
            f"RSI {s.get('rsi', 50):.0f}, conf={f.get('conf', 'medium')}\n\n"
            f'Return exactly: {{"symbol":"{sym}",'
            '"rating":"Strong Buy|Buy|Hold|Sell|Strong Sell",'
            '"confidence":50,"note":"1 concise sentence"}'
        )
        try:
            raw  = await analyst_jury_svc.call_groq(
                "llama-3.3-70b-versatile",
                "You are a portfolio advisor. Output only valid JSON, nothing else.",
                prompt,
                max_tokens=120,
            )
            text = raw.strip()
            if "```" in text:
                text = text.split("```")[1].replace("json", "").strip()
            verdict = json.loads(text)
            verdict.setdefault("symbol", sym)
            return sym, verdict
        except Exception as exc:
            logger.warning("[SIM] _bulk_jury: %s rating failed: %s", sym, exc)
            return sym, {"symbol": sym, "rating": "Hold", "confidence": 50, "note": ""}

    results = await asyncio.gather(*[_rate_one(s) for s in stocks], return_exceptions=True)
    verdicts: Dict[str, Dict] = {}
    for item in results:
        if isinstance(item, Exception):
            logger.error("[SIM] _bulk_jury: unexpected gather error: %s", item)
        else:
            sym, verdict = item
            verdicts[sym] = verdict
    return verdicts


async def suggest_portfolio(
    sectors: List[str],
    risk_level: str,
    budget: float,
    yf_svc: Any,
    run_forecast_fn: Callable[..., Dict],
    influx_svc: Optional[Any],
    analyst_jury_svc: Optional[Any],
) -> Dict[str, Any]:
    """Analyze sector candidates → rank → return portfolio suggestions."""
    candidates, source = await _build_candidate_pool(sectors, risk_level)
    logger.info(
        "[SIM] source=%s  risk=%s  sectors=%s  candidates(%d)=%s",
        source, risk_level, sectors, len(candidates), candidates,
    )

    results = await asyncio.gather(
        *[_analyze_ticker(t, yf_svc, run_forecast_fn, influx_svc) for t in candidates]
    )
    valid = [r for r in results if r is not None]

    if not valid:
        return {"error": "Could not analyze any candidates", "suggestions": [], "candidateSource": source}

    top = sorted(valid, key=lambda s: _score(s, risk_level), reverse=True)[:6]
    verdicts = await _bulk_jury(top, risk_level, analyst_jury_svc)

    spy_price = 0.0
    try:
        spy_price = await asyncio.to_thread(yf_svc.get_live_price, BENCHMARK_SYMBOL)
    except Exception as exc:
        logger.warning("[SIM] get_live_price(SPY) failed: %s — trying fetch_history fallback", exc)
    if spy_price <= 0:
        try:
            spy_df = await asyncio.to_thread(yf_svc.fetch_history, BENCHMARK_SYMBOL, "5d")
            if not spy_df.empty:
                spy_price = float(spy_df["Close"].iloc[-1])
        except Exception as exc:
            logger.warning("[SIM] SPY fetch_history fallback also failed: %s", exc)

    n = len(top)
    alloc_per = budget / n if n else 0

    suggestions = []
    for stock in top:
        sym     = stock["symbol"]
        price   = stock["currentPrice"]
        f       = stock["forecast"]
        verdict = verdicts.get(sym, {})
        shares  = int(alloc_per / price) if price > 0 else 0
        mc      = f.get("monte_carlo") or {}

        suggestions.append({
            "symbol":         sym,
            "name":           stock["name"],
            "sector":         stock["sector"],
            "currentPrice":   round(price, 4),
            "forecastHigh":   round(f.get("high", price), 4),
            "forecastLow":    round(f.get("low",  price), 4),
            "forecastConf":   f.get("conf", "medium"),
            "forecastDays":   f.get("forecast_days", []),
            "direction":      "Bullish" if f.get("high", price) > price else "Bearish",
            "rsi":            stock.get("rsi", 50),
            "juryRating":     verdict.get("rating", "Hold"),
            "juryNote":       verdict.get("note", ""),
            "juryConfidence": verdict.get("confidence", 50),
            "allocationPct":  round(100 / n, 1) if n else 0,
            "allocationUsd":  round(shares * price, 2),
            "shares":         shares,
            "var_95":         mc.get("var_95"),
            "prob_gain":      mc.get("prob_gain"),
        })

    # Weighted portfolio VaR: sum of (per-share VaR × shares) across all positions
    portfolio_var_95 = round(
        sum(
            (s.get("var_95") or 0.0) * s.get("shares", 0)
            for s in suggestions
        ),
        2,
    )

    spy_shares = int(budget / spy_price) if spy_price > 0 else 0

    return {
        "suggestions":     suggestions,
        "benchmark": {
            "symbol":        BENCHMARK_SYMBOL,
            "name":          "S&P 500 ETF (SPY)",
            "currentPrice":  round(spy_price, 4),
            "allocationUsd": round(spy_shares * spy_price, 2),
            "shares":        spy_shares,
        },
        "riskLevel":        risk_level,
        "sectors":          sectors,
        "budget":           budget,
        "candidateSource":  source,
        "portfolioVaR95":   portfolio_var_95,
    }


async def get_portfolio_performance(
    holdings: List[Dict],
    start_date: str,
    spy_buy_price: float,
    budget: float,
    yf_svc: Any,
    interval: str = "1d",
) -> Dict[str, Any]:
    """
    Fetch price history from start_date → now for all holdings + SPY.
    interval: yfinance interval string — '1m','5m','15m','1h','1d' etc.
    Returns timestamped cumulative return % for portfolio and SPY benchmark.
    """
    try:
        try:
            dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            if interval == "1d":
                start_str = dt.strftime("%Y-%m-%d")
            else:
                # Scope: NASDAQ-listed stocks only, benchmarked against SPY (S&P 500).
                # ET (America/New_York) is correct for all supported symbols.
                # If global exchange support is added later, compute tz per-symbol
                # using the ticker suffix (.NS → Asia/Kolkata, .L → Europe/London, etc.)
                start_str = dt.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
        except Exception:
            start_str = start_date[:10]

        all_symbols = list({h["symbol"] for h in holdings} | {BENCHMARK_SYMBOL})
        price_data: Dict[str, Dict[str, float]] = {}

        def _fmt_key(idx: Any) -> str:
            if interval == "1d":
                return str(idx.date())
            return idx.strftime("%Y-%m-%d %H:%M")

        async def _fetch(symbol: str) -> None:
            try:
                yf_sym = yf_svc._to_yf_symbol(symbol) if hasattr(yf_svc, '_to_yf_symbol') else symbol
                ticker = yf.Ticker(yf_sym)
                async with _yf_sem():
                    hist = await asyncio.to_thread(
                        ticker.history, start=start_str, interval=interval, auto_adjust=True
                    )
                if not hist.empty:
                    price_data[symbol] = {
                        _fmt_key(idx): round(float(row["Close"]), 4)
                        for idx, row in hist.iterrows()
                    }
            except Exception as exc:
                logger.warning("[SIM] history fetch %s (%s): %s", symbol, interval, exc)

        await asyncio.gather(*[_fetch(s) for s in all_symbols])

        spy_prices = price_data.get(BENCHMARK_SYMBOL, {})
        all_dates  = sorted(set().union(*[set(p.keys()) for p in price_data.values()]))

        # For intraday intervals yfinance only accepts a date (not datetime) as
        # start, so it returns data from market open even if the simulation was
        # started mid-session.  Trim to the actual simulation start timestamp so
        # the chart always begins at the moment the user clicked "Start Race".
        sim_start_hm: Optional[str] = None
        if interval != "1d":
            try:
                sim_start_hm = dt.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M")
            except Exception as exc:
                logger.debug(
                    "[SIM] intraday start conversion failed; keeping full series: %s",
                    exc,
                )
                sim_start_hm = None

        # Carry-forward seed: the most recent pre-start bar (if any) becomes the
        # initial last-known price, so the first plotted point uses a real quote
        # rather than snapping back to buyPrice / spy_buy_price on the left edge.
        last_prices: Dict[str, float] = {}
        last_spy_price = spy_buy_price
        if sim_start_hm is not None:
            for h in holdings:
                sym = h["symbol"]
                pre_start = [d for d in price_data.get(sym, {}) if d < sim_start_hm]
                if pre_start:
                    last_prices[sym] = price_data[sym][max(pre_start)]
            spy_pre_start = [d for d in spy_prices if d < sim_start_hm]
            if spy_pre_start:
                last_spy_price = spy_prices[max(spy_pre_start)]
            all_dates = [d for d in all_dates if d >= sim_start_hm]

        if not all_dates:
            return _empty_perf(budget)

        initial_cost = sum(h["shares"] * h["buyPrice"] for h in holdings)
        if initial_cost <= 0:
            initial_cost = max(budget, 1e-6)

        spy_ref_shares = initial_cost / spy_buy_price if spy_buy_price > 0 else 0

        port_values: List[float] = []
        spy_values:  List[float] = []
        port_returns: List[float] = []
        spy_returns:  List[float] = []

        for date in all_dates:
            for h in holdings:
                sym = h["symbol"]
                px = price_data.get(sym, {}).get(date)
                if px is not None:
                    last_prices[sym] = px
            spy_px = spy_prices.get(date)
            if spy_px is not None:
                last_spy_price = spy_px

            port_val = sum(
                h["shares"] * last_prices.get(h["symbol"], h["buyPrice"])
                for h in holdings
            )
            spy_val  = spy_ref_shares * last_spy_price

            port_values.append(round(port_val, 2))
            spy_values.append(round(spy_val, 2))
            port_returns.append(round((port_val / initial_cost - 1) * 100, 3))
            spy_returns.append(round((spy_val  / initial_cost - 1) * 100, 3))

        holdings_pnl = []
        for h in holdings:
            sym_px    = price_data.get(h["symbol"], {})
            cur_price = float(list(sym_px.values())[-1]) if sym_px else h["buyPrice"]
            cost      = h["shares"] * h["buyPrice"]
            value     = h["shares"] * cur_price
            pnl       = value - cost
            holdings_pnl.append({
                "symbol":       h["symbol"],
                "name":         h.get("name", h["symbol"]),
                "shares":       h["shares"],
                "buyPrice":     round(h["buyPrice"], 4),
                "currentPrice": round(cur_price, 4),
                "value":        round(value, 2),
                "pnl":          round(pnl, 2),
                "pnlPct":       round(pnl / cost * 100, 2) if cost > 0 else 0.0,
            })

        return {
            "dates":                 all_dates,
            "portfolioValues":       port_values,
            "spyValues":             spy_values,
            "portfolioReturns":      port_returns,
            "spyReturns":            spy_returns,
            "currentPortfolioValue": port_values[-1] if port_values else budget,
            "currentSpyValue":       spy_values[-1]  if spy_values  else budget,
            "portfolioReturn":       port_returns[-1] if port_returns else 0.0,
            "spyReturn":             spy_returns[-1]  if spy_returns  else 0.0,
            "holdings":              holdings_pnl,
            "interval":              interval,
        }
    except Exception as exc:
        logger.error("[SIM] get_portfolio_performance failed: %s", exc)
        return _empty_perf(budget)


def _empty_perf(budget: float) -> Dict[str, Any]:
    return {
        "dates": [], "portfolioValues": [], "spyValues": [],
        "portfolioReturns": [], "spyReturns": [],
        "currentPortfolioValue": budget, "currentSpyValue": budget,
        "portfolioReturn": 0.0, "spyReturn": 0.0, "holdings": [],
    }
