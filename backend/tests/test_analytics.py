"""
Analytics router tests — forecast accuracy + sentiment trend.
All InfluxDB / ForecastStore queries are mocked; no network required.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
import importlib as _il

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from backend.routers import analytics

_deps = _il.import_module("dependencies")
limiter = _deps.limiter

_test_app = FastAPI()
_test_app.state.limiter = limiter


async def _rl_handler(req, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Too many requests — please slow down."})


_test_app.add_exception_handler(RateLimitExceeded, _rl_handler)
_test_app.include_router(analytics.router)
client = TestClient(_test_app)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _ts(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _forecast_record(days_ago: int, last_price: float, p, s, r, e_d1) -> dict:
    """Mirror the row shape returned by ForecastStore.query_forecast_records."""
    return {
        "_time":      _ts(days_ago),
        "last_price": last_price,
        "p_d1":       p,
        "s_d1":       s,
        "r_d1":       r,
        "e_d1":       e_d1,
    }


def _patch_store(model_acc=None, ensemble_mae=None, records=None, outcomes=None):
    """Patch the four ForecastStore queries used by /analytics/accuracy."""
    mock = MagicMock()
    mock.query_model_accuracy.return_value = model_acc or {}
    mock.query_ensemble_mae.return_value = ensemble_mae or {}
    mock.query_forecast_records.return_value = records or []
    mock.query_price_outcomes.return_value = outcomes or {}
    return patch("backend.routers.analytics.forecast_store", mock)


# ---------------------------------------------------------------------------
# Accuracy — populated path
# ---------------------------------------------------------------------------

def test_accuracy_full_shape() -> None:
    model_acc = {
        "prophet": {"mae": 4.1, "samples": 12},
        "sarima":  {"mae": 4.8, "samples": 12},
        "rf":      {"mae": 3.6, "samples": 12},
    }
    ensemble_mae = {f"ensemble_d{i}": {"mae": 2.0 + i * 0.5, "samples": 10} for i in range(1, 6)}
    # Forecast at d-3, last_price 100, all models predict up; actual close 105 (d-2) = up.
    records = [_forecast_record(3, 100.0, 102.0, 101.5, 103.0, 102.5)]
    outcomes = {_ts(2).date(): 105.0}

    with _patch_store(model_acc, ensemble_mae, records, outcomes):
        resp = client.get("/analytics/accuracy/NVDA")
    assert resp.status_code == 200
    d = resp.json()
    for key in (
        "symbol", "model_mae", "best_model", "ensemble_mae_by_horizon",
        "directional_accuracy", "forecast_vs_actual", "samples", "generated_at",
    ):
        assert key in d, f"missing key: {key}"
    assert d["symbol"] == "NVDA"
    assert d["model_mae"] == {"prophet": 4.1, "sarima": 4.8, "random_forest": 3.6}
    assert d["best_model"] == "random_forest"          # lowest MAE
    assert len(d["ensemble_mae_by_horizon"]) == 5
    assert d["ensemble_mae_by_horizon"][0] == {"horizon": "d1", "mae": 2.5}
    assert d["samples"] == 1
    assert d["forecast_vs_actual"] == [
        {"date": _ts(2).date().isoformat(), "forecast": 102.5, "actual": 105.0}
    ]


def test_accuracy_directional_correctness() -> None:
    # Prophet predicts UP (correct), SARIMA predicts DOWN (wrong); actual UP.
    records = [_forecast_record(3, 100.0, 105.0, 95.0, 104.0, 103.0)]
    outcomes = {_ts(2).date(): 110.0}  # actual up
    with _patch_store(records=records, outcomes=outcomes):
        resp = client.get("/analytics/accuracy/NVDA")
    da = resp.json()["directional_accuracy"]
    assert da["prophet"] == 1.0
    assert da["sarima"] == 0.0
    assert da["random_forest"] == 1.0
    assert da["ensemble"] == 1.0


def test_accuracy_skips_missing_model_prediction() -> None:
    # SARIMA missing (0.0 sentinel) → excluded from directional accuracy entirely.
    records = [_forecast_record(3, 100.0, 105.0, 0.0, 104.0, 103.0)]
    outcomes = {_ts(2).date(): 110.0}
    with _patch_store(records=records, outcomes=outcomes):
        resp = client.get("/analytics/accuracy/NVDA")
    da = resp.json()["directional_accuracy"]
    assert da["sarima"] is None          # no valid samples
    assert da["prophet"] == 1.0


def test_accuracy_filters_999_sentinel() -> None:
    model_acc = {"prophet": {"mae": 999.0, "samples": 0}, "rf": {"mae": 3.0, "samples": 5}}
    with _patch_store(model_acc=model_acc):
        resp = client.get("/analytics/accuracy/NVDA")
    d = resp.json()
    assert "prophet" not in d["model_mae"]    # 999 sentinel dropped
    assert d["model_mae"] == {"random_forest": 3.0}
    assert d["best_model"] == "random_forest"


# ---------------------------------------------------------------------------
# Accuracy — empty path
# ---------------------------------------------------------------------------

def test_accuracy_empty_returns_200_samples_zero() -> None:
    with _patch_store():  # everything empty
        resp = client.get("/analytics/accuracy/ZZZZ")
    assert resp.status_code == 200
    d = resp.json()
    assert d["samples"] == 0
    assert d["model_mae"] == {}
    assert d["best_model"] is None
    assert d["ensemble_mae_by_horizon"] == []
    assert d["forecast_vs_actual"] == []


def test_accuracy_invalid_symbol_422() -> None:
    resp = client.get("/analytics/accuracy/this-symbol-is-way-too-long")
    assert resp.status_code == 422


def test_accuracy_symbol_uppercased() -> None:
    with _patch_store():
        resp = client.get("/analytics/accuracy/nvda")
    assert resp.json()["symbol"] == "NVDA"


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------

def test_sentiment_history_shape() -> None:
    history = [
        {"date": "2026-06-01", "compound": 0.42, "label": "Bullish"},
        {"date": "2026-06-02", "compound": -0.10, "label": "Bearish"},
    ]
    mock = MagicMock()
    mock.query_sentiment_history.return_value = history
    with patch("backend.routers.analytics.influx_svc", mock):
        resp = client.get("/analytics/sentiment/NVDA")
    assert resp.status_code == 200
    d = resp.json()
    assert d["symbol"] == "NVDA"
    assert d["history"] == history
    assert d["current"] == history[-1]    # latest point


def test_sentiment_empty_returns_200_null_current() -> None:
    mock = MagicMock()
    mock.query_sentiment_history.return_value = []
    with patch("backend.routers.analytics.influx_svc", mock):
        resp = client.get("/analytics/sentiment/ZZZZ")
    assert resp.status_code == 200
    d = resp.json()
    assert d["history"] == []
    assert d["current"] is None


def test_sentiment_invalid_symbol_422() -> None:
    resp = client.get("/analytics/sentiment/!!bad!!")
    assert resp.status_code == 422
