# backend/simulation_service.py
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Curated ticker pool by sector and risk level
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


def _calc_rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    recent = deltas[-period:]
    gains  = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)


async def _analyze_ticker(
    symbol: str,
    yf_svc,
    run_forecast_fn,
    influx_svc,
) -> Optional[Dict]:
    """Fetch OHLCV data and run ensemble ML forecast for one ticker."""
    try:
        df = await asyncio.to_thread(yf_svc.fetch_history, symbol, "3mo")
        if df is None or df.empty or len(df) < 20:
            logger.warning("[SIM] %s: insufficient data", symbol)
            return None

        closes  = df["Close"].dropna().tolist()
        opens   = df["Open"].dropna().tolist()   if "Open"   in df.columns else None
        highs   = df["High"].dropna().tolist()   if "High"   in df.columns else None
        lows    = df["Low"].dropna().tolist()    if "Low"    in df.columns else None
        volumes = df["Volume"].dropna().tolist() if "Volume" in df.columns else None

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
            except Exception:
                pass

        forecast = await asyncio.to_thread(
            run_forecast_fn,
            closes, symbol,
            opens, highs, lows, volumes,
            hist_weights, sample_count,
        )

        live_price = info.get("current_price") or float(closes[-1])
        return {
            "symbol":       symbol,
            "name":         info.get("short_name", symbol),
            "sector":       info.get("sector", "Unknown"),
            "currentPrice": float(live_price),
            "forecast":     forecast,
            "rsi":          _calc_rsi(closes),
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
    analyst_jury_svc,
) -> Dict[str, Dict]:
    """Single Groq call that rates all top stocks at once."""
    if not stocks or not analyst_jury_svc:
        return {}

    lines = []
    for s in stocks:
        f      = s.get("forecast", {})
        cur    = s["currentPrice"]
        upside = ((f.get("high", cur) - cur) / cur * 100) if cur > 0 else 0
        lines.append(
            f"{s['symbol']} ({s['sector']}): ${cur:.2f}, "
            f"5d upside +{upside:.1f}%, RSI {s.get('rsi', 50):.0f}, "
            f"conf={f.get('conf', 'medium')}"
        )

    prompt = (
        f"Portfolio advisor evaluating for a {risk_level} investor.\n\n"
        + "\n".join(lines)
        + '\n\nReturn a JSON array only. Each item: '
          '{"symbol":"XXX","rating":"Strong Buy|Buy|Hold|Sell|Strong Sell",'
          '"confidence":50,"note":"1 concise sentence"}'
    )
    try:
        raw = await analyst_jury_svc._call_groq(
            "llama-3.3-70b-versatile",
            "You are a portfolio advisor. Output only a valid JSON array, nothing else.",
            prompt,
        )
        text = raw.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        verdicts = json.loads(text)
        return {v["symbol"]: v for v in verdicts if "symbol" in v}
    except Exception as exc:
        logger.error("[SIM] _bulk_jury failed: %s", exc)
        return {}


async def suggest_portfolio(
    sectors: List[str],
    risk_level: str,
    budget: float,
    yf_svc,
    run_forecast_fn,
    influx_svc,
    analyst_jury_svc,
) -> Dict[str, Any]:
    """Analyze sector candidates → rank → return portfolio suggestions."""
    candidates: List[str] = []
    for sector in sectors:
        pool = SECTOR_POOL.get(sector, {})
        for t in pool.get(risk_level, pool.get("moderate", [])):
            if t not in candidates:
                candidates.append(t)
    candidates = candidates[:12] or SECTOR_POOL["Technology"]["moderate"]

    logger.info("[SIM] Analyzing %d candidates: %s", len(candidates), candidates)

    results = await asyncio.gather(
        *[_analyze_ticker(t, yf_svc, run_forecast_fn, influx_svc) for t in candidates]
    )
    valid = [r for r in results if r is not None]

    if not valid:
        return {"error": "Could not analyze any candidates", "suggestions": []}

    top = sorted(valid, key=lambda s: _score(s, risk_level), reverse=True)[:6]
    verdicts = await _bulk_jury(top, risk_level, analyst_jury_svc)

    spy_price = 0.0
    try:
        spy_price = await asyncio.to_thread(yf_svc.get_live_price, BENCHMARK_SYMBOL)
    except Exception:
        pass

    n = len(top)
    alloc_per = budget / n if n else 0

    suggestions = []
    for stock in top:
        sym     = stock["symbol"]
        price   = stock["currentPrice"]
        f       = stock["forecast"]
        verdict = verdicts.get(sym, {})
        shares  = int(alloc_per / price) if price > 0 else 0

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
        })

    spy_shares = int(budget / spy_price) if spy_price > 0 else 0

    return {
        "suggestions": suggestions,
        "benchmark": {
            "symbol":        BENCHMARK_SYMBOL,
            "name":          "S&P 500 ETF (SPY)",
            "currentPrice":  round(spy_price, 4),
            "allocationUsd": round(spy_shares * spy_price, 2),
            "shares":        spy_shares,
        },
        "riskLevel": risk_level,
        "sectors":   sectors,
        "budget":    budget,
    }


async def get_portfolio_performance(
    holdings: List[Dict],   # [{symbol, shares, buyPrice, name?}]
    start_date: str,
    spy_buy_price: float,
    budget: float,
    yf_svc,
) -> Dict[str, Any]:
    """
    Fetch price history from start_date → today for all holdings + SPY.
    Returns daily cumulative return % for the portfolio and the SPY benchmark.
    """
    try:
        import yfinance as yf
        from datetime import datetime, timezone

        try:
            dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            start_str = dt.strftime("%Y-%m-%d")
        except Exception:
            start_str = start_date[:10]

        all_symbols = list({h["symbol"] for h in holdings} | {BENCHMARK_SYMBOL})
        price_data: Dict[str, Dict[str, float]] = {}

        async def _fetch(symbol: str) -> None:
            try:
                ticker = yf.Ticker(symbol)
                hist = await asyncio.to_thread(
                    ticker.history, start=start_str, auto_adjust=True
                )
                if not hist.empty:
                    price_data[symbol] = {
                        str(idx.date()): round(float(row["Close"]), 4)
                        for idx, row in hist.iterrows()
                    }
            except Exception as exc:
                logger.warning("[SIM] history fetch %s: %s", symbol, exc)

        await asyncio.gather(*[_fetch(s) for s in all_symbols])

        spy_prices = price_data.get(BENCHMARK_SYMBOL, {})
        all_dates  = sorted(set().union(*[set(p.keys()) for p in price_data.values()]))

        if not all_dates:
            return _empty_perf(budget)

        # Actual invested cost (shares × buyPrice, summed across holdings)
        initial_cost = sum(h["shares"] * h["buyPrice"] for h in holdings)
        if initial_cost <= 0:
            initial_cost = budget

        # SPY benchmark: same dollars invested in SPY at spy_buy_price
        spy_ref_shares = initial_cost / spy_buy_price if spy_buy_price > 0 else 0

        port_values: List[float] = []
        spy_values:  List[float] = []
        port_returns: List[float] = []
        spy_returns:  List[float] = []

        for date in all_dates:
            port_val = sum(
                h["shares"] * price_data.get(h["symbol"], {}).get(date, h["buyPrice"])
                for h in holdings
            )
            spy_px  = spy_prices.get(date, spy_buy_price)
            spy_val = spy_ref_shares * spy_px

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
