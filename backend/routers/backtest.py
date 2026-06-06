# backend/routers/backtest.py
"""
Walk-forward backtester for the ensemble forecast.

Rolling-window out-of-sample validation: train each model (Prophet, SARIMAX,
RandomForest) on a 252-day window, forecast the next 5 trading days, step
forward 21 days, and compare predictions against the realized closes.

Expensive (~30 train/predict cycles fitting 3 models each) so the result is
cached in Redis for 24h and the heavy compute runs in a worker thread under a
120s wall-clock budget.
"""
import asyncio
import logging
import math
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException

from models import (
    MODELS_AVAILABLE,
    _prophet_forecast,
    _sarima_forecast,
    _rf_forecast,
)
from services import DataCleaner
from dependencies import yf_svc
from redis_cache import cache_get, cache_set

router = APIRouter()
logger = logging.getLogger(__name__)

# Walk-forward parameters
TRAIN_WINDOW = 252   # ~1 trading year of history per fit
HORIZON      = 5     # forecast the next 5 trading days
STEP         = 21    # roll forward ~1 trading month between windows

CACHE_TTL_SECONDS = 86_400   # 24h — backtest is stable intraday & costly
COMPUTE_TIMEOUT   = 120.0    # wall-clock budget for the worker thread

_SYMBOL_RE = re.compile(r"[A-Za-z0-9.\-:]{1,15}")


def _sign(x: float) -> int:
    """Direction of a move: +1 up, -1 down, 0 flat."""
    return (x > 0) - (x < 0)


def _agg(errors: List[float], dirs: List[int]) -> Dict[str, Optional[float]]:
    """Aggregate per-window errors + directional hits into MAE + accuracy."""
    mae = round(sum(errors) / len(errors), 4) if errors else None
    acc = round(sum(dirs) / len(dirs), 4) if dirs else None
    return {"mae": mae, "directional_accuracy": acc}


def _run_backtest(symbol: str, closes: List[float], dates: List[str]) -> Optional[dict]:
    """
    Synchronous walk-forward loop — runs in a worker thread.

    For each rolling window, each model is re-fit on the train slice (closes
    only) and its 5-day mean path is scored against the realized closes:
      • MAE        — mean |predicted_close − actual_close| across all horizons
      • Direction  — did the day-5 prediction get the up/down move right?

    The ensemble path is the simple mean of the available model paths; its
    day-5 direction drives a long/short equity curve (one trade per window).
    Returns None when there is not enough history for a single window.
    """
    n = len(closes)
    if n < TRAIN_WINDOW + HORIZON:
        return None

    model_errors: Dict[str, List[float]] = {"prophet": [], "sarimax": [], "random_forest": []}
    model_dirs:   Dict[str, List[int]]   = {"prophet": [], "sarimax": [], "random_forest": []}
    ens_errors:   List[float] = []
    ens_dirs:     List[int]   = []

    equity_curve: List[dict] = []
    cumulative_return_pct = 0.0
    windows_tested = 0

    fitters = {
        "prophet":       lambda tr: _prophet_forecast(tr, HORIZON),
        "sarimax":       lambda tr: _sarima_forecast(tr, HORIZON),
        "random_forest": lambda tr: _rf_forecast(tr, HORIZON),
    }

    start = 0
    while start + TRAIN_WINDOW + HORIZON <= n:
        train  = closes[start: start + TRAIN_WINDOW]
        actual = closes[start + TRAIN_WINDOW: start + TRAIN_WINDOW + HORIZON]
        train_last = train[-1]
        actual_dir = _sign(actual[-1] - train_last)
        pred_date  = dates[start + TRAIN_WINDOW - 1]

        window_model_paths: List[List[float]] = []
        for name, fit in fitters.items():
            try:
                result = fit(train)                       # shape (HORIZON, 3)
                pred_path = [float(result[i][0]) for i in range(HORIZON)]
            except Exception as exc:
                logger.warning(
                    "[BACKTEST] %s fit failed for %s window @%s: %s",
                    name, symbol, pred_date, exc,
                )
                continue
            model_errors[name].extend(abs(p - a) for p, a in zip(pred_path, actual))
            model_dirs[name].append(1 if _sign(pred_path[-1] - train_last) == actual_dir else 0)
            window_model_paths.append(pred_path)

        if not window_model_paths:
            start += STEP
            continue

        # Ensemble = simple mean of the model paths that succeeded this window.
        ens_path = [
            sum(p[i] for p in window_model_paths) / len(window_model_paths)
            for i in range(HORIZON)
        ]
        ens_errors.extend(abs(p - a) for p, a in zip(ens_path, actual))
        ens_dir = _sign(ens_path[-1] - train_last)
        ens_dirs.append(1 if ens_dir == actual_dir else 0)

        # Equity curve: take the position implied by the ensemble's day-5 call
        # (long if it predicts up, short if down). A flat prediction is treated
        # as a no-trade rather than defaulting long, so an undecided model
        # doesn't introduce a systematic long bias. One trade per window,
        # compounded additively.
        if ens_dir == 0:
            window_return_pct = 0.0
        else:
            position = 1 if ens_dir > 0 else -1
            window_return_pct = position * (actual[-1] - train_last) / train_last * 100.0
        cumulative_return_pct += window_return_pct
        equity_curve.append({
            "date": pred_date,
            "cumulative_return_pct": round(cumulative_return_pct, 2),
        })

        windows_tested += 1
        start += STEP

    if windows_tested == 0:
        return None

    return {
        "symbol":         symbol,
        "windows_tested": windows_tested,
        "ensemble":       _agg(ens_errors, ens_dirs),
        "models": {
            "prophet":       _agg(model_errors["prophet"],       model_dirs["prophet"]),
            "sarimax":       _agg(model_errors["sarimax"],       model_dirs["sarimax"]),
            "random_forest": _agg(model_errors["random_forest"], model_dirs["random_forest"]),
        },
        "equity_curve": equity_curve,
        "computed_at":  datetime.now(timezone.utc).isoformat(),
    }


@router.get("/backtest/{symbol}")
async def backtest(symbol: str) -> dict:
    """
    Walk-forward validation of the ensemble forecast over ~2y of daily history.

    Cached in Redis for 24h. The compute runs in a worker thread under a 120s
    budget since it fits Prophet + SARIMAX + RF once per rolling window.
    """
    sym = (symbol or "").strip().upper()
    if not sym or not _SYMBOL_RE.fullmatch(sym):
        raise HTTPException(status_code=400, detail="Invalid symbol.")

    if not MODELS_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Forecasting models unavailable — backtest cannot run.",
        )

    cache_key = f"backtest:{sym}"
    cached = await cache_get(cache_key)
    if cached:
        logger.info("[BACKTEST] cache HIT for %s", sym)
        return cached

    logger.info("[BACKTEST] cache MISS for %s — fetching 2y history", sym)
    try:
        df = await asyncio.wait_for(
            asyncio.to_thread(yf_svc.fetch_history, sym, "2y"),
            timeout=12.0,
        )
    except asyncio.TimeoutError:
        logger.warning("[BACKTEST] yfinance fetch timed out for %s", sym)
        raise HTTPException(status_code=504, detail=f"Data fetch for {sym} timed out.")
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No data found for {sym}.")

    try:
        df = DataCleaner.clean(df)
    except Exception as exc:
        logger.warning("[BACKTEST] DataCleaner.clean failed for %s: %s — using raw df", sym, exc)

    hist = DataCleaner.to_history_list(df)
    hist.sort(key=lambda x: x["_time"])
    # Keep only finite, positive closes — a stray NaN/inf would silently poison
    # the Prophet/SARIMAX paths and surface as null MAE in the response.
    closes: List[float] = []
    dates:  List[str]   = []
    for p in hist:
        c = float(p["close"])
        if math.isfinite(c) and c > 0:
            closes.append(c)
            dates.append(str(p["_time"])[:10])

    if len(closes) < TRAIN_WINDOW + HORIZON:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Insufficient history for {sym} — need ≥ {TRAIN_WINDOW + HORIZON} "
                f"trading days, have {len(closes)}."
            ),
        )

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_backtest, sym, closes, dates),
            timeout=COMPUTE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("[BACKTEST] %s timed out after %ss", sym, COMPUTE_TIMEOUT)
        raise HTTPException(status_code=504, detail="Backtest timed out — please try again.")

    if result is None:
        raise HTTPException(status_code=422, detail=f"Not enough data to backtest {sym}.")

    logger.info(
        "[BACKTEST] ✓ %s — %d windows | ensemble MAE=%s dir_acc=%s",
        sym, result["windows_tested"],
        result["ensemble"]["mae"], result["ensemble"]["directional_accuracy"],
    )
    await cache_set(cache_key, result, ttl_seconds=CACHE_TTL_SECONDS)
    return result
