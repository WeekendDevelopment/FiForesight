import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel

from config import Config
from models import calculate_rsi, run_ensemble_forecast, generate_synthetic_history
from services import InfluxService, SerpService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FiForesight Quantum Engine")

# Services
influx_svc = InfluxService()
serp_svc = SerpService()

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

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc)}

@app.post("/predict", response_model=PredictionResponse)
async def predict(payload: dict = Body(...)):
    symbol = payload.get('data', 'NVDA').upper()
    
    if not re.match(r"^[A-Z0-9.-:]+$", symbol):
        raise HTTPException(status_code=400, detail="Invalid ticker symbol format.")

    if not Config.SERP_API_KEY:
        raise HTTPException(status_code=500, detail="SERP_API_KEY not configured")

    # 1. Fetch Data via SerpService
    data = await serp_svc.fetch_data(symbol)
    
    # Fallback to NASDAQ if no initial result
    if not data or not data.get('summary', {}).get('price'):
        if ":" not in symbol:
            logger.info(f"Retrying with NASDAQ fallback for {symbol}")
            data = await serp_svc.fetch_data(f"{symbol}:NASDAQ")
            if data and data.get('summary', {}).get('price'):
                symbol = f"{symbol}:NASDAQ"

    if not data: raise HTTPException(status_code=404, detail="Ticker not found on Google Finance")

    summary = data.get('summary', {})
    live_price = serp_svc.clean_price(summary.get('price')) or serp_svc.clean_price(data.get('price'))

    metrics = {
        "market_cap": str(summary.get('market_cap') or data.get('market_cap', 'N/A')),
        "pe_ratio": str(summary.get('pe_ratio') or data.get('pe_ratio', 'N/A')),
        "yield": str(summary.get('dividend_yield') or data.get('dividend_yield', 'N/A')),
        "prev_close": str(summary.get('previous_close') or data.get('previous_close', 'N/A')),
        "range_52w": str(summary.get('52_week_high_low') or data.get('52_week_high_low', 'N/A'))
    }
    
    news = []
    for item in (data.get('news') or data.get('news_results') or [])[:5]:
        news.append({
            "title": item.get('title', 'Market Update'),
            "link": item.get('link', '#'),
            "source": item.get('source', 'Financial News'),
            "thumbnail": item.get('thumbnail'),
            "date": item.get('date', 'Today')
        })
    
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

    # 4. Background Ingestion
    if live_price > 0:
        asyncio.create_task(asyncio.to_thread(influx_svc.write_price, symbol, live_price))

    return {
        "symbol": symbol, "currentPrice": f"{live_price:.2f}", "rsi": f"{rsi:.2f}",
        "prediction": {"highRange": str(forecast['high']), "lowRange": str(forecast['low']), "trend": "Bullish" if rsi > 50 else "Bearish"},
        "analystNote": forecast['note'], "confidence": forecast['conf'],
        "metrics": metrics, "news": news, "trending": trending,
        "history": [{"date": p['_time'].strftime('%m/%d'), "price": round(float(p['close']), 2)} for p in historical_prices[-60:]],
        "lastUpdated": datetime.now(timezone.utc).isoformat()
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=Config.PORT)
