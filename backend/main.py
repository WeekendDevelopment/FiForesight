# backend/main.py
import logging
import os
import traceback
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import Config, SanitizeHttpxFilter
from redis_cache import init_redis, close_redis
from routers import predict, simulation, trade, market

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").addFilter(SanitizeHttpxFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    url = os.getenv("UPSTASH_REDIS_URL")
    if url:
        init_redis(url)
    else:
        logger.warning("[REDIS] UPSTASH_REDIS_URL not set — caching disabled")
    yield
    await close_redis()


app = FastAPI(title="FiForesight Quantum Engine", lifespan=lifespan)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error(f"Unhandled exception on {request.method} {request.url}:\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )


app.include_router(predict.router)
app.include_router(simulation.router)
app.include_router(trade.router)
app.include_router(market.router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=Config.PORT)
