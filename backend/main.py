# backend/main.py
import logging
import os
import traceback
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from config import Config, SanitizeHttpxFilter
from dependencies import limiter
from redis_cache import init_redis, close_redis
from routers import predict, simulation, trade, market, history, backtest

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

# --- Rate limiting -----------------------------------------------------------
app.state.limiter = limiter


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    retry_after = getattr(exc, "retry_after", None)
    headers = {"Retry-After": str(int(retry_after))} if retry_after else {"Retry-After": "60"}
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests — please slow down."},
        headers=headers,
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# --- CORS --------------------------------------------------------------------
_origins = [o.strip() for o in Config.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# --- Global exception handler ------------------------------------------------
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
app.include_router(history.router)
app.include_router(backtest.router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=Config.PORT)
