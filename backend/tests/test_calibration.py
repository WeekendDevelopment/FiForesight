"""
Forecast calibration audit (Feature 30) tests.

The math lives in pure helpers in calibration_service, so these feed synthetic
forecast+outcome records straight to the transform — no network, no InfluxDB.
A few endpoint smoke tests exercise the router with the store mocked.
"""
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import importlib as _il

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

import calibration_service
from calibration_service import _compute_calibration, MIN_CALIBRATION_SAMPLES
from backend.routers import analytics

_deps = _il.import_module("dependencies")
limiter = _deps.limiter

_test_app = FastAPI()
_test_app.state.limiter = limiter


async def _rl_handler(req: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "slow down"})


_test_app.add_exception_handler(RateLimitExceeded, _rl_handler)
_test_app.include_router(analytics.router)
client = TestClient(_test_app)


# ---------------------------------------------------------------------------
# Helpers — build synthetic forecast_record rows + price_outcome map
# ---------------------------------------------------------------------------

def _ts(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _build(samples: list[dict]) -> tuple[list, dict]:
    """Turn a list of {last, e_d1, actual, [low, high, p10, p90, prev]} into
    (records, outcomes). Records are spaced 2 days apart, ascending by time;
    each resolves to its actual one day later (the earliest later outcome)."""
    records, outcomes = [], {}
    n = len(samples)
    for i, s in enumerate(samples):
        days_ago = (n - i) * 2 + 1  # i↑ ⇒ days_ago↓ ⇒ time ascending
        rec = {"_time": _ts(days_ago), "last_price": s["last"], "e_d1": s["e_d1"]}
        for src, dst in (("low", "e_d1_low"), ("high", "e_d1_high"),
                         ("p10", "p10"), ("p90", "p90"), ("prev", "prev_price")):
            if src in s:
                rec[dst] = s[src]
        records.append(rec)
        outcomes[_ts(days_ago - 1).date()] = s["actual"]
    return records, outcomes


# ---------------------------------------------------------------------------
# Pure-transform tests
# ---------------------------------------------------------------------------

def test_perfect_coverage() -> None:
    """~80% of realized prices land inside the band → well_calibrated."""
    # 10 samples, band [95, 105]; 8 land inside (100), 2 escape (130).
    samples = [{"last": 100.0, "e_d1": 100.0, "low": 95.0, "high": 105.0,
                "actual": 100.0 if i < 8 else 130.0} for i in range(10)]
    records, outcomes = _build(samples)
    r = _compute_calibration(records, outcomes)

    assert r["samples"] == 10
    assert r["p10_p90_coverage_pct"] == 80.0       # p10/p90 default to the range
    assert r["range_coverage_pct"] == 80.0
    assert r["calibration_verdict"] == "well_calibrated"


def test_overconfident() -> None:
    """Bands too tight → few realized prices inside → overconfident."""
    # 10 samples, band [99.5, 100.5]; only 1 lands inside, rest escape high.
    samples = [{"last": 100.0, "e_d1": 100.0, "low": 99.5, "high": 100.5,
                "actual": 100.0 if i == 0 else 115.0} for i in range(10)]
    records, outcomes = _build(samples)
    r = _compute_calibration(records, outcomes)

    assert r["samples"] == 10
    assert r["range_coverage_pct"] == 10.0
    assert r["calibration_verdict"] == "overconfident"


def test_edge_vs_naive() -> None:
    """Ensemble calls the reversal; naive persistence is wrong → edge > 0."""
    # Prior move was DOWN (prev>last) but price reverses UP; ensemble predicts up.
    samples = [{"prev": 105.0, "last": 100.0, "e_d1": 103.0, "actual": 104.0}
               for _ in range(6)]
    records, outcomes = _build(samples)
    r = _compute_calibration(records, outcomes)

    assert r["directional_accuracy_pct"] == 100.0
    assert r["naive_accuracy_pct"] == 0.0
    assert r["edge_pct"] > 0


def test_bias_detection() -> None:
    """Every forecast sits above the actual → mean_signed_error > 0 (high bias)."""
    samples = [{"last": 100.0, "e_d1": 110.0, "actual": 100.0} for _ in range(6)]
    records, outcomes = _build(samples)
    r = _compute_calibration(records, outcomes)

    assert r["mean_signed_error"] is not None
    assert r["mean_signed_error"] > 0
    assert r["mean_signed_error"] == 10.0


def test_insufficient_history() -> None:
    """Below MIN_CALIBRATION_SAMPLES matched samples → samples + nulls, no error."""
    n = MIN_CALIBRATION_SAMPLES - 1
    samples = [{"last": 100.0, "e_d1": 101.0, "low": 95.0, "high": 105.0, "actual": 100.0}
               for _ in range(n)]
    records, outcomes = _build(samples)
    r = _compute_calibration(records, outcomes)

    assert r["samples"] == n
    assert r["p10_p90_coverage_pct"] is None
    assert r["range_coverage_pct"] is None
    assert r["directional_accuracy_pct"] is None
    assert r["edge_pct"] is None
    assert r["mean_signed_error"] is None
    assert r["calibration_verdict"] is None


# ---------------------------------------------------------------------------
# Endpoint smoke tests (store mocked)
# ---------------------------------------------------------------------------

def _patch_store(
    records: list | None = None,
    outcomes: dict | None = None,
    symbols: list | None = None,
) -> AbstractContextManager[MagicMock]:
    mock = MagicMock()
    mock.query_forecast_records.return_value = records or []
    mock.query_price_outcomes.return_value = outcomes or {}
    mock.query_forecast_symbols.return_value = symbols or []
    return patch.object(calibration_service, "forecast_store", mock)


@contextmanager
def _no_redis():
    """Stub the Redis cache so endpoint tests exercise the mocked store, never a
    live/stale analytics:calibration:* key. Bare module path (tests run from backend/)."""
    with patch("redis_cache.cache_get", AsyncMock(return_value=None)), \
         patch("redis_cache.cache_set", AsyncMock(return_value=None)):
        yield


def test_calibration_endpoint_empty_200() -> None:
    with _no_redis(), _patch_store():  # no history
        resp = client.get("/analytics/calibration/NVDA")
    assert resp.status_code == 200
    d = resp.json()
    assert d["symbol"] == "NVDA"
    assert d["samples"] == 0
    assert d["calibration_verdict"] is None


def test_calibration_endpoint_all_aggregate() -> None:
    samples = [{"last": 100.0, "e_d1": 100.0, "low": 95.0, "high": 105.0, "actual": 100.0}
               for _ in range(6)]
    records, outcomes = _build(samples)
    mock = MagicMock()
    mock.query_forecast_symbols.return_value = ["AAA", "BBB"]
    mock.query_forecast_records.return_value = records
    mock.query_price_outcomes.return_value = outcomes
    with _no_redis(), patch.object(calibration_service, "forecast_store", mock):
        resp = client.get("/analytics/calibration/ALL")
    assert resp.status_code == 200
    d = resp.json()
    assert d["symbol"] == "ALL"
    # 6 records × 2 symbols = 12 matched samples, all in-band.
    assert d["samples"] == 12
    assert d["range_coverage_pct"] == 100.0


def test_calibration_invalid_symbol_422() -> None:
    resp = client.get("/analytics/calibration/this-is-way-too-long-a-symbol")
    assert resp.status_code == 422
