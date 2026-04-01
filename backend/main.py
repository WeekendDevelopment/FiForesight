# backend/main.py
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from google import genai

from config import Config
from models import calculate_rsi, run_ensemble_forecast
from services import InfluxService, SerpService, YFinanceService, DataCleaner

# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="FiForesight API")

# Configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "WeekendDevelopment")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "FiForesightBucket")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
GOOGLE_GENAI_API_KEY = os.getenv("GOOGLE_GENAI_API_KEY")

app = FastAPI(title="FiForesight Quantum Engine")

# Services
influx_svc = InfluxService()
serp_svc = SerpService()


# ── Response schema ─────────────────────────────────────────────────────────

class PredictionResponse(BaseModel):
    symbol: str
    currentPrice: str
    rsi: str
    prediction: dict
    analystNote: str
    confidence: str
    history: List[dict]
    metrics: dict
    news: List[dict]
    trending: List[dict]
    lastUpdated: str

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

async def generate_ai_prediction(symbol: str, price_history: List[dict], rsi: float):
    if not ai_client:
        return {"predictedHigh": 0, "predictedLow": 0, "analystNote": "AI API Key missing.", "confidence": "low"}

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

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc)}


# ── Predict ──────────────────────────────────────────────────────────────────

@app.post("/predict", response_model=PredictionResponse)
async def predict(payload: dict = Body(...)):
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
        })
        if h_resp.status_code == 200:
            historical_data = h_resp.json()
        
        # 3. Fetch Earnings
        e_resp = await client.get(f"{base_url}/stock/earnings", params={"symbol": symbol, "token": FINNHUB_API_KEY})
        if e_resp.status_code == 200:
            earnings_data = e_resp.json()

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

    trending = []
    for category, items in data.get('markets', {}).items():
        if isinstance(items, list):
            for t in items[:3]:
                trending.append({
                    "symbol": t.get('symbol') or t.get('name', 'N/A'),
                    "name": t.get('name', ''),
                    "price": str(t.get('price', 'N/A')),
                    "change": str(t.get('price_change_percentage', '0%')),
                    "category": category
                })

    # 2. Historical Context via InfluxService
    historical_prices = await asyncio.to_thread(influx_svc.query_history, symbol)

    if len(historical_prices) < 20 and live_price > 0:
        prev_close_val = serp_svc.clean_price(metrics['prev_close']) or (live_price * 0.99)
        historical_prices = generate_synthetic_history(symbol, live_price, prev_close_val)

    if live_price > 0:
        historical_prices.append({"_time": datetime.now(timezone.utc), "close": live_price})

    # 3. Analytics & Models
    historical_prices.sort(key=lambda x: x['_time'])
    closes = [float(p['close']) for p in historical_prices]
    rsi = calculate_rsi(closes)
    forecast = run_ensemble_forecast(closes, symbol)

    history_formatted = [{"date": p['_time'].strftime('%m/%d') if isinstance(p['_time'], datetime) else str(p['_time'])[5:10], "price": p['close']} for p in historical_prices[-20:]]

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
        "symbol": symbol, "currentPrice": f"{live_price if live_price > 0 else closes[-1]:.2f}", "rsi": f"{rsi:.2f}",
        "prediction": {"highRange": str(ai_result.get('predictedHigh', 0)), "lowRange": str(ai_result.get('predictedLow', 0)), "trend": "Bullish" if rsi > 50 else "Bearish"},
        "analystNote": ai_result.get('analystNote', ""), "confidence": ai_result.get('confidence', "low"),
        "history": history_formatted, "lastUpdated": now.isoformat()
    }
  
    # 4. Background Ingestion
    if live_price > 0:
        asyncio.create_task(asyncio.to_thread(influx_svc.write_price, symbol, live_price))

    return {
        "symbol": symbol, "currentPrice": f"{live_price:.2f}", "rsi": f"{rsi:.2f}",
        "prediction": {"highRange": str(forecast['high']), "lowRange": str(forecast['low']),
                       "trend": "Bullish" if rsi > 50 else "Bearish"},
        "analystNote": forecast['note'], "confidence": forecast['conf'],
        "metrics": metrics, "news": news, "trending": trending,
        "history": [{"date": p['_time'].strftime('%m/%d'), "price": round(float(p['close']), 2)} for p in
                    historical_prices[-60:]],
        "lastUpdated": datetime.now(timezone.utc).isoformat()
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=Config.PORT)

