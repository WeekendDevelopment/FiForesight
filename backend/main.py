import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Body
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
FMP_API_KEY = os.getenv("FMP_API_KEY")
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

async def generate_ai_prediction(symbol: str, price_history: List[dict], earnings_history: List[dict], rsi: float):
    if not ai_client:
        return {"predictedHigh": 0, "predictedLow": 0, "analystNote": "AI API Key missing.", "confidence": "low"}

    price_str = "\n".join([f"Date: {p['_time']}, Close: {p['close']}" for p in price_history[-20:]])
    
    prompt = f"Analyze {symbol} (RSI: {rsi:.2f}). Recent history:\n{price_str}\nProvide 48h forecast and analyst note in JSON: {{'predictedHigh': float, 'predictedLow': float, 'analystNote': string, 'confidence': 'low|medium|high'}}"

    try:
        # Use 1.5-flash as it usually has a separate (or higher) quota than 2.0-flash
        response = await asyncio.to_thread(ai_client.models.generate_content, model="gemini-2.5-flash", contents=prompt)
        text = response.text.strip()
        start, end = text.find('{'), text.rfind('}') + 1
        return json.loads(text[start:end])
    except Exception as e:
        logger.warning(f"AI Quota/Error: {e}")
        last_price = price_history[-1]['close'] if price_history else 100.0
        return {
            "predictedHigh": round(last_price * 1.02, 2),
            "predictedLow": round(last_price * 0.98, 2),
            "analystNote": "Technical RSI analysis indicates neutral momentum. AI analysis currently cooling down.",
            "confidence": "low"
        }

async def ingest_to_influx(symbol: str, historical_data: list, earnings_data: list):
    points = []
    for day in historical_data:
        try:
            point = Point("market_data").tag("symbol", symbol)
            point.field("close", float(day['close']))
            point.time(datetime.strptime(day['date'], '%Y-%m-%d'), WritePrecision.NS)
            points.append(point)
        except: continue
    for earning in earnings_data:
        try:
            point = Point("earnings_data").tag("symbol", symbol)
            surprise = earning.get('surprisePercentage') or earning.get('surprise') or 0
            point.field("surprise_percentage", float(surprise))
            point.time(datetime.strptime(earning['date'], '%Y-%m-%d'), WritePrecision.NS)
            points.append(point)
        except: continue
    if points:
        try: write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=points)
        except Exception as e: logger.error(f"InfluxDB Write Error: {e}")

@app.post("/predict", response_model=PredictionResponse)
async def predict(payload: dict = Body(...)):
    symbol = payload.get('data', 'SPY').upper()
    api_url = "https://financialmodelingprep.com/api/v3"
    stable_url = "https://financialmodelingprep.com/stable"
    
    headers = {"User-Agent": "Mozilla/5.0"}
    live_price, historical_data, earnings_data = 0.0, [], []

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        # 1. Fetch Quote (Using /stable/quote which we know works)
        q_resp = await client.get(f"{stable_url}/quote", params={"symbol": symbol, "apikey": FMP_API_KEY})
        if q_resp.status_code == 200:
            q_data = q_resp.json()
            if isinstance(q_data, list) and len(q_data) > 0:
                live_price = float(q_data[0].get('price', 0))

        # 2. Fetch History (Using /v3 but with Query Parameter style to avoid Legacy 403)
        h_resp = await client.get(f"{api_url}/historical-price-full", params={"symbol": symbol, "timeseries": 100, "apikey": FMP_API_KEY})
        if h_resp.status_code == 200:
            historical_data = h_resp.json().get('historical', [])
        
        # 3. Fetch Earnings (Using Query Parameter style)
        e_resp = await client.get(f"{api_url}/earnings-surprises", params={"symbol": symbol, "apikey": FMP_API_KEY})
        if e_resp.status_code == 200:
            earnings_data = e_resp.json()

        if historical_data:
            await ingest_to_influx(symbol, historical_data, earnings_data)

    # Database Query
    query_market = f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: -100d) |> filter(fn: (r) => r["_measurement"] == "market_data" and r["symbol"] == "{symbol}") |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value") |> sort(columns: ["_time"], desc: false)'
    query_earnings = f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: -5y) |> filter(fn: (r) => r["_measurement"] == "earnings_data" and r["symbol"] == "{symbol}") |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value") |> sort(columns: ["_time"], desc: false)'
    
    historical_prices, earnings_history = [], []
    try:
        historical_prices = [r.values for t in query_api.query(query_market) for r in t.records]
        earnings_history = [r.values for t in query_api.query(query_earnings) for r in t.records]
    except: pass

    if not historical_prices and historical_data:
        historical_prices = [{"_time": datetime.strptime(d['date'], '%Y-%m-%d'), "close": float(d['close'])} for d in sorted(historical_data, key=lambda x: x['date'])]
    
    if live_price > 0:
        historical_prices.append({"_time": datetime.now(timezone.utc), "close": live_price})
    
    if not historical_prices:
        raise HTTPException(status_code=404, detail=f"No data available for {symbol}.")

    historical_prices.sort(key=lambda x: x['_time'])
    closes = [float(p['close']) for p in historical_prices]
    rsi = calculate_rsi(closes)
    ai_result = await generate_ai_prediction(symbol, historical_prices, earnings_history, rsi)

    history_formatted = [{"date": p['_time'].strftime('%m/%d') if isinstance(p['_time'], datetime) else str(p['_time'])[5:10], "price": p['close']} for p in historical_prices[-20:]]

    return {
        "symbol": symbol, "currentPrice": f"{live_price if live_price > 0 else closes[-1]:.2f}", "rsi": f"{rsi:.2f}",
        "prediction": {"highRange": str(ai_result.get('predictedHigh', 0)), "lowRange": str(ai_result.get('predictedLow', 0)), "trend": "Bullish" if rsi > 50 else "Bearish"},
        "analystNote": ai_result.get('analystNote', ""), "confidence": ai_result.get('confidence', "low"),
        "history": history_formatted, "lastUpdated": datetime.now(timezone.utc).isoformat()
    }
