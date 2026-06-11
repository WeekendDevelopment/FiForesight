# backend/routers/analytics.py
"""
Forecast-accuracy & sentiment analytics — read-only views built almost entirely
from data already accumulated in InfluxDB by /predict (forecast_record,
price_outcome, model_accuracy) and the new sentiment_score measurement.

Endpoints (read-only tier rate limit, 15-min Redis cache):
  GET /analytics/accuracy/{symbol}   — model MAE, directional accuracy, forecast-vs-actual
  GET /analytics/sentiment/{symbol}  — 30-day VADER compound trend
"""
import asyncio
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from slowapi.util import get_remote_address

from config import Config
from dependencies import forecast_store, influx_svc, limiter

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-:]{1,15}$")

router = APIRouter()
logger = logging.getLogger(__name__)

# Stored sentinel for a missing per-model day-1 prediction (see write_forecast_record).
_MISSING = 0.0

# Map InfluxDB per-model accuracy keys → public API names.
_MODEL_NAME_MAP = {"prophet": "prophet", "sarima": "sarima", "rf": "random_forest"}


def _sign(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def _compute_accuracy(
    model_acc: dict,
    ensemble_mae: dict,
    records: list,
    outcomes: dict,
) -> dict:
    """Pure transform of the four InfluxDB query results into the API payload.

    Kept side-effect-free (no I/O) so it is trivially unit-testable.
    """
    # ── Per-model MAE (filter out the 999.0 "no data" sentinel) ──────────────
    model_mae: dict = {}
    for src_key, out_key in _MODEL_NAME_MAP.items():
        rec = model_acc.get(src_key)
        if rec and rec.get("mae") is not None and rec["mae"] < 999.0:
            model_mae[out_key] = round(float(rec["mae"]), 2)

    best_model = min(model_mae, key=model_mae.get) if model_mae else None

    # ── Ensemble MAE by horizon d1..d5 ───────────────────────────────────────
    ensemble_mae_by_horizon = []
    for i in range(1, 6):
        rec = ensemble_mae.get(f"ensemble_d{i}")
        if rec and rec.get("mae") is not None and rec["mae"] < 999.0:
            ensemble_mae_by_horizon.append({"horizon": f"d{i}", "mae": round(float(rec["mae"]), 2)})

    # ── Join forecast records → next-day actual close ────────────────────────
    # price_outcome entries are written one-per-record at the d1 target date, so
    # the matching actual is the earliest outcome strictly after the record date.
    outcomes_sorted = sorted(outcomes.items())  # [(date, close), ...]
    # One forecast-vs-actual point per resolved date (latest record wins) so the
    # chart stays clean when several /predict calls landed on the same day.
    fva_by_date: dict = {}
    # {model: [correct, total]}
    dir_counts = {k: [0, 0] for k in ("prophet", "sarima", "random_forest", "ensemble")}
    field_map = {"prophet": "p_d1", "sarima": "s_d1", "random_forest": "r_d1", "ensemble": "e_d1"}
    matched = 0
    naive_errors: list[float] = []

    for rec in records:
        pred_time = rec.get("_time")
        if pred_time is None:
            continue
        try:
            pred_date = pred_time.date()
        except AttributeError:
            continue
        last_price = rec.get("last_price")
        if last_price is None or last_price <= 0:
            continue

        actual = None
        actual_date = None
        for d, close in outcomes_sorted:
            if d > pred_date and close > 0:
                actual, actual_date = close, d
                break
        if actual is None:
            continue
        matched += 1
        naive_errors.append(abs(actual - last_price))

        e_d1 = rec.get("e_d1")
        if e_d1 is not None and e_d1 > _MISSING:
            # records are ascending by _time → later same-date entry overwrites
            fva_by_date[actual_date] = {
                "date":     actual_date.isoformat(),
                "forecast": round(float(e_d1), 2),
                "actual":   round(float(actual), 2),
            }

        actual_dir = _sign(actual - last_price)
        for model, field in field_map.items():
            pred = rec.get(field)
            if pred is None or pred <= _MISSING:
                continue  # sentinel / missing prediction
            dir_counts[model][1] += 1
            if _sign(pred - last_price) == actual_dir:
                dir_counts[model][0] += 1

    directional_accuracy = {
        model: round(c / t, 2) if t else None
        for model, (c, t) in dir_counts.items()
    }
    forecast_vs_actual = [fva_by_date[d] for d in sorted(fva_by_date)]

    # ── Naive-persistence baseline & per-model skill ──────────────────────────
    # Naive baseline: always predict last_price (yesterday's close).
    # skill = 1 − model_mae/naive_mae; >0 beats persistence, <0 is worse.
    naive_mae: float | None = round(sum(naive_errors) / len(naive_errors), 2) if naive_errors else None
    model_skill: dict = {}
    if naive_mae and naive_mae > 0:
        for model, mae in model_mae.items():
            model_skill[model] = round(1.0 - mae / naive_mae, 3)

    return {
        "model_mae":               model_mae,
        "best_model":              best_model,
        "ensemble_mae_by_horizon": ensemble_mae_by_horizon,
        "directional_accuracy":    directional_accuracy,
        "forecast_vs_actual":      forecast_vs_actual,
        "samples":                 matched,
        "naive_mae":               naive_mae,
        "model_skill":             model_skill,
    }


@router.get("/analytics/accuracy/{symbol}")
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def accuracy_analytics(request: Request, symbol: str):
    from redis_cache import cache_get, cache_set

    symbol = symbol.strip().upper()
    if not _SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=422, detail="Invalid symbol.")

    cache_key = f"analytics:accuracy:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    async def _gather() -> dict:
        # Read all four InfluxDB sources concurrently (each is a blocking query).
        model_acc, ensemble_mae, records, outcomes = await asyncio.gather(
            asyncio.to_thread(forecast_store.query_model_accuracy, symbol),
            asyncio.to_thread(forecast_store.query_ensemble_mae, symbol),
            asyncio.to_thread(forecast_store.query_forecast_records, symbol, 30),
            asyncio.to_thread(forecast_store.query_price_outcomes, symbol, 35),
        )
        return _compute_accuracy(model_acc, ensemble_mae, records, outcomes)

    try:
        result = await asyncio.wait_for(_gather(), timeout=12.0)
    except asyncio.TimeoutError:
        logger.warning("[ANALYTICS] accuracy query timed out for %s", symbol)
        result = {
            "model_mae": {}, "best_model": None, "ensemble_mae_by_horizon": [],
            "directional_accuracy": {}, "forecast_vs_actual": [], "samples": 0,
            "naive_mae": None, "model_skill": {},
        }

    payload = {
        "symbol":       symbol,
        **result,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    await cache_set(cache_key, payload, ttl_seconds=900)
    return payload


@router.get("/analytics/sentiment/{symbol}")
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def sentiment_analytics(request: Request, symbol: str):
    from redis_cache import cache_get, cache_set

    symbol = symbol.strip().upper()
    if not _SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=422, detail="Invalid symbol.")

    cache_key = f"analytics:sentiment:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    try:
        history = await asyncio.wait_for(
            asyncio.to_thread(influx_svc.query_sentiment_history, symbol, 30),
            timeout=12.0,
        )
    except asyncio.TimeoutError:
        logger.warning("[ANALYTICS] sentiment query timed out for %s", symbol)
        history = []

    current = history[-1] if history else None
    payload = {
        "symbol":       symbol,
        "history":      history,
        "current":      current,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    await cache_set(cache_key, payload, ttl_seconds=900)
    return payload
