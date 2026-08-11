# backend/main.py
import logging
import os
import traceback
from contextlib import asynccontextmanager

import uvicorn
from config import Config, SanitizeHttpxFilter
from dependencies import limiter
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis_cache import close_redis, init_redis
from routers import (
    alerts,
    analytics,
    backtest,
    history,
    market,
    portfolio,
    predict,
    simulation,
    trade,
    watchlist,
)
from slowapi.errors import RateLimitExceeded

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

    # Warm the FRED macro snapshot (Feature 15) so the first /macro and /predict
    # requests hit a warm 1h cache. Non-blocking and non-fatal.
    import asyncio as _asyncio

    from dependencies import fred_svc

    async def _warm_fred() -> None:
        try:
            await fred_svc.get_macro_snapshot()
            logger.info("[STARTUP] FRED macro snapshot warmed")
        except Exception as exc:
            logger.warning("[STARTUP] FRED warm failed (non-fatal): %s", exc)

    _asyncio.create_task(_warm_fred())

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
_origins = [o.strip() for o in Config.ALLOWED_ORIGINS.split(",") if o.strip() and o.strip() != "*"]
if not _origins:
    logger.error(
        "[CORS] ALLOWED_ORIGINS resolved to an empty list — no cross-origin requests will be permitted."
    )
elif len(_origins) != len([o.strip() for o in Config.ALLOWED_ORIGINS.split(",") if o.strip()]):
    logger.error(
        "[CORS] ALLOWED_ORIGINS contained a wildcard '*' entry — it was removed. Set explicit origins only."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
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
app.include_router(analytics.router)
app.include_router(portfolio.router)
app.include_router(alerts.router)
app.include_router(watchlist.router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=Config.PORT)
