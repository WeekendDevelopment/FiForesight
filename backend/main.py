import os
import json
import asyncio
import logging
import re
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
from google import genai

# Setup logging
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

# Clients initialization
write_api = None
query_api = None
try:
    influx_client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)
    query_api = influx_client.query_api()
except Exception as e:
    logger.error(f"Failed to connect to InfluxDB: {e}")

ai_client = None
if GOOGLE_GENAI_API_KEY:
    ai_client = genai.Client(api_key=GOOGLE_GENAI_API_KEY)

class PredictionResponse(BaseModel):
    symbol: str
    currentPrice: str
    rsi: str
    prediction: dict
    analystNote: str
    confidence: str
    history: List[dict]
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

    # Using only 2.5 flash as requested
    model_name = "gemini-2.5-flash"
    try:
        logger.info(f"Attempting AI prediction with {model_name}")
        response = await asyncio.to_thread(
            ai_client.models.generate_content, 
            model=model_name, 
            contents=prompt
        )
        text = response.text.strip()
        match = re.search(r"\{.*}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        logger.warning(f"Model {model_name} failed: {e}")

    last_price = price_history[-1]['close'] if price_history else 100.0
    return {
        "predictedHigh": round(last_price * 1.02, 2),
        "predictedLow": round(last_price * 0.98, 2),
        "analystNote": f"AI analysis temporarily unavailable. Technical trend suggests {'bullish' if rsi > 50 else 'bearish'} momentum.",
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

    if points and write_api:
        try:
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=points)
        except Exception as e:
            logger.error(f"InfluxDB Write Error: {e}")

@app.get("/health")
async def health():
    return {"status": "ok"}

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
        if query_api:
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

    return {
        "symbol": symbol, "currentPrice": f"{live_price if live_price > 0 else closes[-1]:.2f}", "rsi": f"{rsi:.2f}",
        "prediction": {"highRange": str(ai_result.get('predictedHigh', 0)), "lowRange": str(ai_result.get('predictedLow', 0)), "trend": "Bullish" if rsi > 50 else "Bearish"},
        "analystNote": ai_result.get('analystNote', ""), "confidence": ai_result.get('confidence', "low"),
        "history": history_formatted, "lastUpdated": now.isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
