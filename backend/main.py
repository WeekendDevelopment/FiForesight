import os
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List

import httpx
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Body
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from pydantic import BaseModel
<<<<<<< HEAD
from google import genai
=======

from config import Config
from models import calculate_rsi, run_ensemble_forecast
from services import InfluxService, SerpService, YFinanceService, DataCleaner
>>>>>>> 3af7434 ((feat): yfinance data pipeline, cross-platform launcher, 5-day ensemble forecast)

# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

<<<<<<< HEAD
app = FastAPI(title="FiForesight API")
=======
# Services (instantiated once at startup)
influx_svc = InfluxService()
serp_svc   = SerpService()
yf_svc     = YFinanceService()
cleaner    = DataCleaner()
# ---------------------------------------------------------------------------
>>>>>>> 3af7434 ((feat): yfinance data pipeline, cross-platform launcher, 5-day ensemble forecast)

# Configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "WeekendDevelopment")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "FiForesightBucket")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
GOOGLE_GENAI_API_KEY = os.getenv("GOOGLE_GENAI_API_KEY")

# Clients
try:
    influx_client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)
    query_api = influx_client.query_api()
except Exception as e:
    logger.error(f"Failed to connect to InfluxDB: {e}")

ai_client = None
if GOOGLE_GENAI_API_KEY:
    ai_client = genai.Client(api_key=GOOGLE_GENAI_API_KEY)

# ── Response schema ─────────────────────────────────────────────────────────

class PredictionResponse(BaseModel):
<<<<<<< HEAD
    symbol: str
    currentPrice: str
    rsi: str
    prediction: dict
    analystNote: str
    confidence: str
    history: List[dict]
    lastUpdated: str
=======
    symbol:        str
    currentPrice:  str
    rsi:           str
    prediction:    dict          # includes forecast_days, high, low, trend
    analystNote:   str
    confidence:    str
    history:       List[dict]
    forecastDays:  List[dict]    # 5-day per-day forecast for chart
    modelStats:    dict          # ann_volatility_pct, trend_slope, sma_20, etc.
    metrics:       dict
    news:          List[dict]
    trending:      List[dict]
    lastUpdated:   str
>>>>>>> 3af7434 ((feat): yfinance data pipeline, cross-platform launcher, 5-day ensemble forecast)

def calculate_rsi(prices: List[float], periods: int = 14) -> float:
    if len(prices) < periods + 1:
        return 50.0
    series = pd.Series(prices)
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    loss = loss.replace(0, 1e-9)
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    last_rsi = rsi.iloc[-1]
    return float(last_rsi) if not np.isnan(last_rsi) else 50.0

<<<<<<< HEAD
async def generate_ai_prediction(symbol: str, price_history: List[dict], rsi: float):
    if not ai_client:
        return {"predictedHigh": 0, "predictedLow": 0, "analystNote": "AI API Key missing.", "confidence": "low"}
=======
# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean_symbol(symbol: str) -> str:
    return symbol.strip().upper()


async def _get_news_and_trending(symbol: str) -> tuple:
    """
    Calls SerpAPI for live price, news, trending markets, and raw fundamentals.
    Returns (news, trending, serp_metrics, serp_live_price).
    Falls back gracefully if SerpAPI is unavailable or key is missing.
    """
    news, trending, serp_metrics, serp_price = [], [], {}, 0.0

    if not Config.SERP_API_KEY:
        return news, trending, serp_metrics, serp_price

    try:
        data = await serp_svc.fetch_data(symbol)

        # NASDAQ fallback
        if not data or not data.get("summary", {}).get("price"):
            if ":" not in symbol:
                data = await serp_svc.fetch_data(f"{symbol}:NASDAQ")

        if data:
            summary    = data.get("summary", {})
            serp_price = (
                serp_svc.clean_price(summary.get("price"))
                or serp_svc.clean_price(data.get("price"))
            )
            serp_metrics = {
                "market_cap": str(summary.get("market_cap")       or data.get("market_cap",       "N/A")),
                "pe_ratio":   str(summary.get("pe_ratio")         or data.get("pe_ratio",         "N/A")),
                "yield":      str(summary.get("dividend_yield")   or data.get("dividend_yield",   "N/A")),
                "prev_close": str(summary.get("previous_close")   or data.get("previous_close",   "N/A")),
                "range_52w":  str(summary.get("52_week_high_low") or data.get("52_week_high_low", "N/A")),
            }

            for item in (data.get("news") or data.get("news_results") or [])[:5]:
                news.append({
                    "title":     item.get("title",     "Market Update"),
                    "link":      item.get("link",      "#"),
                    "source":    item.get("source",    "Financial News"),
                    "thumbnail": item.get("thumbnail"),
                    "date":      item.get("date",      "Today"),
                })

            for category, items in data.get("markets", {}).items():
                if isinstance(items, list):
                    for t in items[:3]:
                        trending.append({
                            "symbol":   t.get("symbol") or t.get("name", "N/A"),
                            "name":     t.get("name",                    ""),
                            "price":    str(t.get("price",               "N/A")),
                            "change":   str(t.get("price_change_percentage", "0%")),
                            "category": category,
                        })
    except Exception as e:
        logger.warning(f"SerpAPI fetch failed for {symbol}: {e}")

    return news, trending, serp_metrics, serp_price


async def _build_history(symbol: str) -> list:
    """
    History priority:
      1. InfluxDB — if we already have fresh data, skip the yfinance call
      2. yfinance — fetch 2 years of OHLCV, clean, write to InfluxDB
      3. Stale InfluxDB rows as a last resort
    Returns list of dicts: _time, open, high, low, close, volume
    """
    # 1. Try InfluxDB first (fresh = data written within last 20h)
    if influx_svc.has_recent_data(symbol):
        stored = influx_svc.query_history(symbol, days=365)
        if len(stored) >= 20:
            logger.info(f"Using {len(stored)} rows from InfluxDB for {symbol}")
            return stored

    # 2. Fetch from yfinance
    logger.info(f"Fetching history from yfinance for {symbol}")
    raw_df = await asyncio.to_thread(yf_svc.fetch_history, symbol, "2y")

    if not raw_df.empty:
        clean_df = cleaner.clean(raw_df)
        history  = cleaner.to_history_list(clean_df)
        # Persist to InfluxDB in background
        asyncio.create_task(
            asyncio.to_thread(influx_svc.write_ohlcv_batch, symbol, clean_df)
        )
        return history

    # 3. Last resort — stale InfluxDB
    stored = influx_svc.query_history(symbol, days=365)
    if stored:
        logger.warning(f"Using stale InfluxDB data for {symbol}")
        return stored

    logger.warning(f"No history available for {symbol}")
    return []


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc)}
>>>>>>> 3af7434 ((feat): yfinance data pipeline, cross-platform launcher, 5-day ensemble forecast)

    price_str = "\n".join([f"Date: {p['_time']}, Close: {p['close']}" for p in price_history[-20:]])
    
    prompt = f"Analyze {symbol} (Current RSI: {rsi:.2f}). Recent history:\n{price_str}\nProvide 48h forecast and analyst note in JSON: {{'predictedHigh': float, 'predictedLow': float, 'analystNote': string, 'confidence': 'low|medium|high'}}"

    # Model priority list based on user's available models
    models_to_try = ["gemini-2.5-flash"]
    
    for model_name in models_to_try:
        try:
            logger.info(f"Attempting AI prediction with {model_name}")
            response = await asyncio.to_thread(
                ai_client.models.generate_content, 
                model=model_name, 
                contents=prompt
            )
            text = response.text.strip()
            start, end = text.find('{'), text.rfind('}') + 1
            if start != -1 and end != 0:
                return json.loads(text[start:end])
        except Exception as e:
            logger.warning(f"Model {model_name} failed: {e}")
            continue

    last_price = price_history[-1]['close'] if price_history else 100.0
    return {
        "predictedHigh": round(last_price * 1.02, 2),
        "predictedLow": round(last_price * 0.98, 2),
        "analystNote": f"Technical trend suggests {'bullish' if rsi > 50 else 'bearish'} momentum.",
        "confidence": "medium"
    }

async def ingest_to_influx(symbol: str, historical_data: dict, earnings_data: list):
    points = []
    if 'c' in historical_data and 't' in historical_data:
        for i in range(len(historical_data['c'])):
            try:
                point = Point("market_data").tag("symbol", symbol)
                point.field("close", float(historical_data['c'][i]))
                point.time(datetime.fromtimestamp(historical_data['t'][i], tz=timezone.utc), WritePrecision.NS)
                points.append(point)
            except (ValueError, KeyError, TypeError):
                continue
    
    for earning in earnings_data:
        try:
            point = Point("earnings_data").tag("symbol", symbol)
            surprise = earning.get('surprisePercent') or 0
            point.field("surprise_percentage", float(surprise))
            date_str = earning.get('period') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
            point.time(datetime.strptime(date_str, '%Y-%m-%d'), WritePrecision.NS)
            points.append(point)
        except (ValueError, KeyError, TypeError):
            continue

    if points:
        try:
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=points)
        except Exception as e:
            logger.error(f"InfluxDB Write Error: {e}")

# ── Predict ──────────────────────────────────────────────────────────────────

@app.post("/predict", response_model=PredictionResponse)
async def predict(payload: dict = Body(...)):
<<<<<<< HEAD
    symbol = payload.get('data', 'SPY').upper()
    base_url = "https://finnhub.io/api/v1"
    
    live_price, prev_close, historical_data, earnings_data = 0.0, 0.0, {}, []

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Fetch Quote
        q_resp = await client.get(f"{base_url}/quote", params={"symbol": symbol, "token": FINNHUB_API_KEY})
        if q_resp.status_code == 200:
            q_json = q_resp.json()
            live_price = float(q_json.get('c', 0))
            prev_close = float(q_json.get('pc', 0))

        # 2. Fetch History
        now = datetime.now(timezone.utc)
        end = int(now.timestamp())
        start = int((now - timedelta(days=150)).timestamp())
        h_resp = await client.get(f"{base_url}/stock/candle", params={
            "symbol": symbol, "resolution": "D", "from": start, "to": end, "token": FINNHUB_API_KEY
=======
    symbol = _clean_symbol(payload.get("data", "NVDA"))

    if not re.match(r"^[A-Z0-9.\-:]+$", symbol):
        raise HTTPException(status_code=400, detail="Invalid ticker symbol format.")

    # Run all fetches concurrently
    history_task = asyncio.create_task(_build_history(symbol))
    yf_info_task = asyncio.create_task(asyncio.to_thread(yf_svc.fetch_info, symbol))
    serp_task    = asyncio.create_task(_get_news_and_trending(symbol))

    history                                  = await history_task
    yf_info                                  = await yf_info_task
    news, trending, serp_metrics, serp_price = await serp_task

    # ── Live price: prefer SerpAPI (intraday), fall back to yfinance ──────────
    live_price = (
        serp_price
        or yf_info.get("current_price", 0.0)
        or (history[-1]["close"] if history else 0.0)
    )

    # Append live snapshot as the most recent point
    if live_price > 0:
        history.append({
            "_time":  datetime.now(timezone.utc),
            "open":   live_price,
            "high":   live_price,
            "low":    live_price,
            "close":  live_price,
            "volume": 0.0,
>>>>>>> 3af7434 ((feat): yfinance data pipeline, cross-platform launcher, 5-day ensemble forecast)
        })
        if h_resp.status_code == 200:
            historical_data = h_resp.json()
        
        # 3. Fetch Earnings
        e_resp = await client.get(f"{base_url}/stock/earnings", params={"symbol": symbol, "token": FINNHUB_API_KEY})
        if e_resp.status_code == 200:
            earnings_data = e_resp.json()

<<<<<<< HEAD
        if historical_data and historical_data.get('s') == 'ok':
            await ingest_to_influx(symbol, historical_data, earnings_data)

    # Database Query
    query_market = f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: -100d) |> filter(fn: (r) => r["_measurement"] == "market_data" and r["symbol"] == "{symbol}") |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value") |> sort(columns: ["_time"], desc: false)'
    
    historical_prices = []
    try:
        historical_prices = [r.values for t in query_api.query(query_market) for r in t.records]
    except Exception as e:
        logger.error(f"InfluxDB query error: {e}")

    # API Fallback if DB empty
    if not historical_prices:
        if historical_data and historical_data.get('s') == 'ok':
            for i in range(len(historical_data['c'])):
                historical_prices.append({"_time": datetime.fromtimestamp(historical_data['t'][i], tz=timezone.utc), "close": float(historical_data['c'][i])})
        elif live_price > 0:
            for i in range(10, 0, -1):
                historical_prices.append({"_time": now - timedelta(days=i), "close": prev_close if i > 1 else live_price})
    
    if live_price > 0 and (not historical_prices or historical_prices[-1]['close'] != live_price):
        historical_prices.append({"_time": now, "close": live_price})
    
    if not historical_prices:
        raise HTTPException(status_code=404, detail=f"No data available for {symbol}.")

    historical_prices.sort(key=lambda x: x['_time'])
    closes = [float(p['close']) for p in historical_prices]
    rsi = calculate_rsi(closes)
    ai_result = await generate_ai_prediction(symbol, historical_prices, rsi)

    history_formatted = [{"date": p['_time'].strftime('%m/%d') if isinstance(p['_time'], datetime) else str(p['_time'])[5:10], "price": p['close']} for p in historical_prices[-20:]]
=======
    history.sort(key=lambda x: x["_time"])

    # ── Metrics: yfinance fills gaps left by SerpAPI ──────────────────────────
    def _fmt(val):
        if val is None or val == "N/A":
            return "N/A"
        if isinstance(val, float):
            return f"{val:,.2f}" if val < 1_000_000 else f"{val:,.0f}"
        return str(val)

    mc = yf_info.get("market_cap", "N/A")
    metrics = {
        "market_cap": serp_metrics.get("market_cap") or (f"${mc:,}" if isinstance(mc, (int, float)) else "N/A"),
        "pe_ratio":   serp_metrics.get("pe_ratio")   or _fmt(yf_info.get("pe_ratio")),
        "yield":      serp_metrics.get("yield")       or _fmt(yf_info.get("dividend_yield")),
        "prev_close": serp_metrics.get("prev_close")  or _fmt(yf_info.get("prev_close")),
        "range_52w":  serp_metrics.get("range_52w")   or yf_info.get("range_52w", "N/A"),
        "sector":     yf_info.get("sector",           "N/A"),
        "currency":   yf_info.get("currency",         "USD"),
    }

    # ── Analytics ─────────────────────────────────────────────────────────────
    closes   = [float(p["close"]) for p in history]
    rsi      = calculate_rsi(closes)
    forecast = run_ensemble_forecast(closes, symbol)

    # ── Background: persist latest live price ─────────────────────────────────
    if live_price > 0:
        asyncio.create_task(asyncio.to_thread(influx_svc.write_price, symbol, live_price))
>>>>>>> 3af7434 ((feat): yfinance data pipeline, cross-platform launcher, 5-day ensemble forecast)

    # ── Build chart history (last 90 trading days, with full OHLCV) ───────────
    chart_history = [
        {
            "date":   (
                p["_time"].strftime("%m/%d")
                if hasattr(p["_time"], "strftime")
                else str(p["_time"])[:10]
            ),
            "price":  round(float(p["close"]),              2),
            "open":   round(float(p.get("open",  p["close"])), 2),
            "high":   round(float(p.get("high",  p["close"])), 2),
            "low":    round(float(p.get("low",   p["close"])), 2),
            "volume": round(float(p.get("volume", 0)),         0),
        }
        for p in history[-90:]
    ]

    return {
<<<<<<< HEAD
        "symbol": symbol, "currentPrice": f"{live_price if live_price > 0 else closes[-1]:.2f}", "rsi": f"{rsi:.2f}",
        "prediction": {"highRange": str(ai_result.get('predictedHigh', 0)), "lowRange": str(ai_result.get('predictedLow', 0)), "trend": "Bullish" if rsi > 50 else "Bearish"},
        "analystNote": ai_result.get('analystNote', ""), "confidence": ai_result.get('confidence', "low"),
        "history": history_formatted, "lastUpdated": now.isoformat()
    }
=======
        "symbol":       symbol,
        "currentPrice": f"{live_price:.2f}",
        "rsi":          f"{rsi:.2f}",
        "prediction": {
            "highRange":    str(forecast["high"]),
            "lowRange":     str(forecast["low"]),
            "trend":        "Bullish" if rsi > 50 else "Bearish",
            "forecast_days": forecast.get("forecast_days", []),
        },
        "analystNote":  forecast["note"],
        "confidence":   forecast["conf"],
        "forecastDays": forecast.get("forecast_days", []),
        "modelStats":   forecast.get("stats", {}),
        "metrics":      metrics,
        "news":         news,
        "trending":     trending,
        "history":      chart_history,
        "lastUpdated":  datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=Config.PORT)
>>>>>>> 3af7434 ((feat): yfinance data pipeline, cross-platform launcher, 5-day ensemble forecast)
