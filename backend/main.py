from fastapi import FastAPI, HTTPException, Query
import httpx
import os

app = FastAPI(title="FiForesight API")

async def get_alpha_vantage_data(function: str, symbol: str):
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol parameter is required")

    url = "https://www.alphavantage.co/query"
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    
    if not api_key:
        raise HTTPException(status_code=500, detail="ALPHA_VANTAGE_API_KEY environment variable not set")

    async with httpx.AsyncClient() as client:
        try:
            params = {
                "function": function,
                "symbol": symbol,
                "apikey": api_key
            }
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail="External API error")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/global-quote")
async def get_global_quote(symbol: str | None = Query(default=None)):
    return await get_alpha_vantage_data("GLOBAL_QUOTE", symbol)

@app.get("/earnings")
async def get_earnings(symbol: str | None = Query(default=None)):
    return await get_alpha_vantage_data("EARNINGS", symbol)

@app.get("/time-series/monthly")
async def get_monthly_series(symbol: str | None = Query(default=None)):
    return await get_alpha_vantage_data("TIME_SERIES_MONTHLY_ADJUSTED", symbol)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
