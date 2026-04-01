# backend/main.py
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from google import genai

from config import Config
from models import calculate_rsi, run_ensemble_forecast
from services import DataCleaner, InfluxService, SerpService, YFinanceService

# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FiForesight Quantum Engine")

# AI client (optional - graceful fallback if key missing)
ai_client: Optional[genai.Client] = None
if Config.GOOGLE_GENAI_API_KEY:
    try:
        ai_client = genai.Client(api_key=Config.GOOGLE_GENAI_API_KEY)
    except Exception as _e:
        logger.warning(f"Gemini client init failed: {_e}")

# Services
influx_svc = InfluxService()
serp_svc   = SerpService()
yf_svc     = YFinanceService()


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class PredictionResponse(BaseModel):
    symbol:       str
    currentPrice: str
    rsi:          str
    prediction:   dict
    analystNote:  str
    confidence:   str
    history:      List[dict]
    forecastDays: List[dict]
    modelStats:   dict
    metrics:      dict
    news:         List[dict]
    trending:     List[dict]
    lastUpdated:  str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_market_cap(cap) -> str:
    try:
        v = float(cap)
        if v >= 1e12: return f"${v/1e12:.2f}T"
        if v >= 1e9:  return f"${v/1e9:.2f}B"
        if v >= 1e6:  return f"${v/1e6:.2f}M"
        return f"${v:,.0f}"
    except Exception:
        return str(cap) if cap else "N/A"


def _fmt_pct(val) -> str:
    try:
        return f"{float(val)*100:.2f}%"
    except Exception:
        return "N/A"


async def _ai_note(symbol: str, closes: List[float], rsi: float, forecast: dict) -> str:
    """Return a Gemini analyst note, falling back to the model's own note."""
    if not ai_client:
        return forecast["note"]
    recent    = closes[-20:]
    price_str = "\n".join(f"  {i+1}. {p:.2f}" for i, p in enumerate(recent))
    prompt = (
        f"You are a quantitative analyst. Symbol: {symbol}\n"
        f"RSI: {rsi:.1f}\n"
        f"Recent 20-day closes:\n{price_str}\n"
        f"5-day ensemble forecast: high=${forecast['high']:.2f}, low=${forecast['low']:.2f}\n"
        f"Write a concise 2-sentence analyst note with the outlook and key risk. "
        f"Plain text only, no markdown."
    )
    try:
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        logger.warning(f"Gemini note failed: {e}")
        return forecast["note"]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/predict", response_model=PredictionResponse)
async def predict(payload: dict = Body(...)):
    symbol = payload.get("data", "SPY").upper()
    now    = datetime.now(timezone.utc)

    # 1. Fetch OHLCV history
    # Populate InfluxDB from yfinance if we don't have fresh data
    if not influx_svc.has_recent_data(symbol):
        df = await asyncio.to_thread(yf_svc.fetch_history, symbol, "2y")
        if not df.empty:
            df = DataCleaner.clean(df)
            await asyncio.to_thread(influx_svc.write_ohlcv_batch, symbol, df)

    historical_prices: list = await asyncio.to_thread(influx_svc.query_history, symbol)

    # Fallback: use yfinance directly if InfluxDB is unavailable
    if not historical_prices:
        df = await asyncio.to_thread(yf_svc.fetch_history, symbol, "2y")
        if not df.empty:
            df = DataCleaner.clean(df)
            historical_prices = DataCleaner.to_history_list(df)

    if not historical_prices:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}.")

    historical_prices.sort(key=lambda x: x["_time"])

    # 2. Live price
    live_price = await asyncio.to_thread(yf_svc.get_live_price, symbol)
    if live_price > 0:
        historical_prices.append({
            "_time": now, "close": live_price,
            "open": live_price, "high": live_price,
            "low":  live_price, "volume": 0.0,
        })
    else:
        live_price = float(historical_prices[-1]["close"])

    # 3. Fundamentals
    info = await asyncio.to_thread(yf_svc.fetch_info, symbol)
    metrics = {
        "market_cap": _fmt_market_cap(info.get("market_cap")),
        "pe_ratio":   str(info.get("pe_ratio", "N/A")),
        "yield":      _fmt_pct(info.get("dividend_yield")) if info.get("dividend_yield") not in (None, "N/A") else "N/A",
        "prev_close": str(info.get("prev_close", "N/A")),
        "range_52w":  info.get("range_52w", "N/A"),
        "sector":     info.get("sector",   "N/A"),
        "currency":   info.get("currency", "USD"),
    }

    # 4. Analytics & ensemble forecast
    closes   = [float(p["close"]) for p in historical_prices]
    rsi      = calculate_rsi(closes)
    forecast = run_ensemble_forecast(closes, symbol)

    # 5. AI analyst note
    note = await _ai_note(symbol, closes, rsi, forecast)

    # 6. News + trending via SerpAPI
    news: list     = []
    trending: list = []
    try:
        serp_data = await serp_svc.fetch_data(symbol)
        news = [
            {
                "title":     n.get("title",  ""),
                "link":      n.get("link",   ""),
                "source":    n.get("source", {}).get("name", "") if isinstance(n.get("source"), dict) else str(n.get("source", "")),
                "thumbnail": n.get("thumbnail", ""),
                "date":      n.get("date",   ""),
            }
            for n in serp_data.get("news_results", [])[:8]
        ]
        for category, items in serp_data.get("markets", {}).items():
            if isinstance(items, list):
                for t in items[:3]:
                    trending.append({
                        "symbol":   t.get("symbol") or t.get("name", "N/A"),
                        "name":     t.get("name",  ""),
                        "price":    str(t.get("price", "N/A")),
                        "change":   str(t.get("price_change_percentage", "0%")),
                        "category": category,
                    })
    except Exception as e:
        logger.warning(f"SerpAPI fetch failed: {e}")

    # 7. Background price snapshot
    asyncio.create_task(asyncio.to_thread(influx_svc.write_price, symbol, live_price))

    # 8. Chart history (last 90 trading days)
    history = [
        {
            "date":   p["_time"].strftime("%m/%d") if hasattr(p["_time"], "strftime") else str(p["_time"])[:10],
            "price":  round(float(p["close"]),                 2),
            "open":   round(float(p.get("open",  p["close"])), 2),
            "high":   round(float(p.get("high",  p["close"])), 2),
            "low":    round(float(p.get("low",   p["close"])), 2),
            "volume": round(float(p.get("volume", 0)),         0),
        }
        for p in historical_prices[-90:]
    ]

    return PredictionResponse(
        symbol       = symbol,
        currentPrice = f"{live_price:.2f}",
        rsi          = f"{rsi:.2f}",
        prediction   = {
            "highRange": f"{forecast['high']:.2f}",
            "lowRange":  f"{forecast['low']:.2f}",
            "trend":     "Bullish" if rsi > 50 else "Bearish",
        },
        analystNote  = note,
        confidence   = forecast["conf"],
        history      = history,
        forecastDays = forecast["forecast_days"],
        modelStats   = forecast.get("stats", {}),
        metrics      = metrics,
        news         = news,
        trending     = trending,
        lastUpdated  = now.isoformat(),
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=Config.PORT)