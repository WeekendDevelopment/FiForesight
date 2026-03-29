from fastapi import FastAPI, HTTPException, Query
import httpx
import os

app = FastAPI(title="FiForesight API")

@app.get("/global-quote")
async def get_global_quote(symbol: str | None = Query(default=None)):
    url = "https://www.alphavantage.co/query"

    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol parameter is required")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=[("function", "GLOBAL_QUOTE"), ("symbol", symbol), ("apikey", os.environ["ALPHA_VANTAGE_API_KEY"])])
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail="External API error")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
