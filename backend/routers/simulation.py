# backend/routers/simulation.py
import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from models import run_ensemble_forecast
from simulation_service import suggest_portfolio, get_portfolio_performance
from dependencies import influx_svc, yf_svc, analyst_jury_svc

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Simulation endpoints
# ---------------------------------------------------------------------------

class SimSuggestRequest(BaseModel):
    sectors:    List[str]
    risk_level: str   = "moderate"
    budget:     float = Field(default=100_000.0, gt=0)

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, v: str) -> str:
        allowed = {"conservative", "moderate", "aggressive"}
        if v not in allowed:
            raise ValueError(f"risk_level must be one of {allowed}, got {v!r}")
        return v


class SimHolding(BaseModel):
    symbol:        str
    name:          Optional[str] = None
    shares:        int   = Field(ge=0)
    buyPrice:      float = Field(gt=0)
    allocationUsd: float = 0.0


class SimPerfRequest(BaseModel):
    holdings:      List[SimHolding]
    start_date:    str
    spy_buy_price: float = Field(gt=0)
    budget:        float = Field(default=100_000.0, gt=0)
    interval:      str   = "1d"

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, v: str) -> str:
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"start_date must be a valid ISO date string, got: {v!r}") from exc
        # Normalize naive datetimes (e.g. "2026-04-20" has no tzinfo) to UTC
        # before comparing — mixing naive and aware raises TypeError in Python.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt > datetime.now(timezone.utc):
            raise ValueError("start_date must not be in the future")
        return v

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, v: str) -> str:
        allowed = {"1m", "2m", "5m", "15m", "30m", "60m", "1h", "1d"}
        if v not in allowed:
            raise ValueError(f"interval must be one of {allowed}, got {v!r}")
        return v


@router.post("/simulation/suggest")
async def simulation_suggest(req: SimSuggestRequest):
    result = await suggest_portfolio(
        sectors=req.sectors,
        risk_level=req.risk_level,
        budget=req.budget,
        yf_svc=yf_svc,
        run_forecast_fn=run_ensemble_forecast,
        influx_svc=influx_svc,
        analyst_jury_svc=analyst_jury_svc,
    )
    if "error" in result and not result.get("suggestions"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/simulation/performance")
async def simulation_performance(req: SimPerfRequest):
    return await get_portfolio_performance(
        holdings=[h.model_dump() for h in req.holdings],
        start_date=req.start_date,
        spy_buy_price=req.spy_buy_price,
        budget=req.budget,
        yf_svc=yf_svc,
        interval=req.interval,
    )


# ---------------------------------------------------------------------------
# Simulation state endpoints  (env-scoped, InfluxDB-backed)
# ---------------------------------------------------------------------------

class SimStateSaveRequest(BaseModel):
    sim_id: str
    env:    str
    state:  dict


@router.post("/simulation/state")
async def simulation_state_save(req: SimStateSaveRequest):
    # Validate env / sim_id at the route boundary so bad input → 400 (not 500).
    try:
        influx_svc._validate_sim_env(req.env)
        influx_svc._validate_sim_id(req.sim_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Canonicalize the state payload id — the record is keyed by sim_id, so the
    # embedded state.id must agree (otherwise the UI will resume/delete a
    # different id than the one persisted).
    state = dict(req.state)
    state_id = state.get("id")
    if state_id not in (None, req.sim_id):
        raise HTTPException(
            status_code=400,
            detail=f"state.id ({state_id!r}) must match sim_id ({req.sim_id!r})",
        )
    state["id"] = req.sim_id

    ok = await asyncio.to_thread(
        influx_svc.write_simulation_state, req.sim_id, req.env, state
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to persist simulation state")
    return {"saved": True}


@router.get("/simulation/state")
async def simulation_state_list(env: str = Query(...)):
    try:
        influx_svc._validate_sim_env_read(env)  # accepts "all" for cross-env reads
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    sims = await asyncio.to_thread(influx_svc.query_simulation_states, env)
    return {"simulations": sims}


@router.delete("/simulation/state/{sim_id}")
async def simulation_state_delete(sim_id: str, env: str = Query(...)):
    try:
        influx_svc._validate_sim_env(env)
        influx_svc._validate_sim_id(sim_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    ok = await asyncio.to_thread(influx_svc.delete_simulation_state, sim_id, env)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to delete simulation state")
    return {"deleted": True}
