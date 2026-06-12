"""
Alerts & Notifications (Feature 9) tests.

Covers:
  • auth enforcement — every user-facing /alerts endpoint returns 401 unauthenticated
  • cron-secret gate — /alerts/evaluate rejects missing/incorrect X-Cron-Secret,
    503s when CRON_SECRET is unset, 200s with the correct header
  • per-type firing logic in the pure evaluate_rule() (price/RSI/%move/earnings/forecast)
  • cooldown suppression
  • evaluator survives a bad symbol in the batch (logged, others still processed)

Supabase, yfinance, and web-push are fully mocked; no network is required.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import importlib as _il

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

import alerts_evaluator
from config import Config
from backend.routers import alerts

_deps = _il.import_module("dependencies")
limiter = _deps.limiter

_app = FastAPI()
_app.state.limiter = limiter


async def _rl_handler(req, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Too many requests — please slow down."})


_app.add_exception_handler(RateLimitExceeded, _rl_handler)
_app.include_router(alerts.router)
client = TestClient(_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Auth enforcement — no Bearer token → 401 on every user-facing endpoint
# ---------------------------------------------------------------------------

def test_list_rules_requires_auth() -> None:
    assert client.get("/alerts/rules").status_code == 401


def test_fires_requires_auth() -> None:
    assert client.get("/alerts/fires").status_code == 401


def test_create_rule_requires_auth() -> None:
    resp = client.post("/alerts/rules", json={
        "symbol": "AAPL", "type": "price_cross", "operator": "above", "threshold": 200,
    })
    assert resp.status_code == 401


def test_patch_rule_requires_auth() -> None:
    resp = client.patch(
        "/alerts/rules/00000000-0000-0000-0000-000000000000", json={"active": False}
    )
    assert resp.status_code == 401


def test_delete_rule_requires_auth() -> None:
    resp = client.delete("/alerts/rules/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401


def test_subscribe_requires_auth() -> None:
    resp = client.post("/alerts/subscribe", json={
        "endpoint": "https://push.example/x", "keys": {"p256dh": "a", "auth": "b"},
    })
    assert resp.status_code == 401


def test_vapid_public_key_requires_auth() -> None:
    assert client.get("/alerts/vapid-public-key").status_code == 401


# ---------------------------------------------------------------------------
# Cron-secret gate on /alerts/evaluate
# ---------------------------------------------------------------------------

def test_evaluate_503_when_cron_secret_unset() -> None:
    with patch.object(Config, "CRON_SECRET", ""):
        assert client.post("/alerts/evaluate").status_code == 503


def test_evaluate_403_without_header() -> None:
    with patch.object(Config, "CRON_SECRET", "topsecret"):
        assert client.post("/alerts/evaluate").status_code == 403


def test_evaluate_403_with_wrong_header() -> None:
    with patch.object(Config, "CRON_SECRET", "topsecret"):
        resp = client.post("/alerts/evaluate", headers={"X-Cron-Secret": "nope"})
        assert resp.status_code == 403


def test_evaluate_200_with_correct_header() -> None:
    summary = {"rules_checked": 0, "fired": 0, "symbols": 0, "errors": 0, "skipped_cooldown": 0}
    with patch.object(Config, "CRON_SECRET", "topsecret"), \
         patch.object(Config, "SUPABASE_SERVICE_ROLE_KEY", "svc-role"), \
         patch.object(alerts.alerts_evaluator, "evaluate_alerts", new=AsyncMock(return_value=summary)):
        resp = client.post("/alerts/evaluate", headers={"X-Cron-Secret": "topsecret"})
    assert resp.status_code == 200
    assert resp.json()["summary"] == summary


def test_evaluate_503_when_service_role_missing() -> None:
    with patch.object(Config, "CRON_SECRET", "topsecret"), \
         patch.object(Config, "SUPABASE_SERVICE_ROLE_KEY", ""):
        resp = client.post("/alerts/evaluate", headers={"X-Cron-Secret": "topsecret"})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Pure rule evaluation — per type
# ---------------------------------------------------------------------------

def _rule(**kw):
    base = {"id": "r1", "user_id": "u1", "symbol": "AAPL", "type": "price_cross",
            "operator": None, "threshold": None, "last_fired": None}
    base.update(kw)
    return base


def test_price_cross_above_fires() -> None:
    rule = _rule(type="price_cross", operator="above", threshold=150)
    fired, msg, val = alerts_evaluator.evaluate_rule(rule, {"price": 152.0})
    assert fired and val == 152.0 and "above" in msg


def test_price_cross_above_does_not_fire_below() -> None:
    rule = _rule(type="price_cross", operator="above", threshold=150)
    fired, _, _ = alerts_evaluator.evaluate_rule(rule, {"price": 149.0})
    assert not fired


def test_price_cross_below_fires() -> None:
    rule = _rule(type="price_cross", operator="below", threshold=150)
    fired, _, val = alerts_evaluator.evaluate_rule(rule, {"price": 140.0})
    assert fired and val == 140.0


def test_rsi_threshold_above_fires() -> None:
    rule = _rule(type="rsi_threshold", operator="above", threshold=70)
    fired, _, val = alerts_evaluator.evaluate_rule(rule, {"rsi": 75.0})
    assert fired and val == 75.0


def test_rsi_threshold_below_fires() -> None:
    rule = _rule(type="rsi_threshold", operator="below", threshold=30)
    fired, _, _ = alerts_evaluator.evaluate_rule(rule, {"rsi": 25.0})
    assert fired


def test_rsi_threshold_no_fire_when_between() -> None:
    rule = _rule(type="rsi_threshold", operator="above", threshold=70)
    fired, _, _ = alerts_evaluator.evaluate_rule(rule, {"rsi": 50.0})
    assert not fired


def test_pct_move_absolute_fires_either_direction() -> None:
    rule = _rule(type="pct_move", operator=None, threshold=3)
    assert alerts_evaluator.evaluate_rule(rule, {"pct_move": -4.0})[0]
    assert alerts_evaluator.evaluate_rule(rule, {"pct_move": 4.0})[0]
    assert not alerts_evaluator.evaluate_rule(rule, {"pct_move": 2.0})[0]


def test_pct_move_up_only() -> None:
    rule = _rule(type="pct_move", operator="above", threshold=3)
    assert alerts_evaluator.evaluate_rule(rule, {"pct_move": 4.0})[0]
    assert not alerts_evaluator.evaluate_rule(rule, {"pct_move": -4.0})[0]


def test_pct_move_down_only() -> None:
    rule = _rule(type="pct_move", operator="below", threshold=3)
    assert alerts_evaluator.evaluate_rule(rule, {"pct_move": -4.0})[0]
    assert not alerts_evaluator.evaluate_rule(rule, {"pct_move": 4.0})[0]


def test_earnings_soon_fires_within_window() -> None:
    rule = _rule(type="earnings_soon", operator=None, threshold=1)
    fired, msg, val = alerts_evaluator.evaluate_rule(rule, {"earnings_days": 1})
    assert fired and val == 1.0 and "tomorrow" in msg


def test_earnings_soon_today() -> None:
    rule = _rule(type="earnings_soon", operator=None, threshold=2)
    fired, msg, _ = alerts_evaluator.evaluate_rule(rule, {"earnings_days": 0})
    assert fired and "today" in msg


def test_earnings_soon_no_fire_outside_window() -> None:
    rule = _rule(type="earnings_soon", operator=None, threshold=1)
    fired, _, _ = alerts_evaluator.evaluate_rule(rule, {"earnings_days": 5})
    assert not fired


def test_earnings_soon_default_window_one_day() -> None:
    rule = _rule(type="earnings_soon", operator=None, threshold=None)
    assert alerts_evaluator.evaluate_rule(rule, {"earnings_days": 1})[0]
    assert not alerts_evaluator.evaluate_rule(rule, {"earnings_days": 2})[0]


def test_forecast_breakout_above_high() -> None:
    rule = _rule(type="forecast_breakout")
    fired, msg, _ = alerts_evaluator.evaluate_rule(
        rule, {"price": 160.0, "forecast_high": 155.0, "forecast_low": 145.0}
    )
    assert fired and "above" in msg


def test_forecast_breakout_below_low() -> None:
    rule = _rule(type="forecast_breakout")
    fired, msg, _ = alerts_evaluator.evaluate_rule(
        rule, {"price": 140.0, "forecast_high": 155.0, "forecast_low": 145.0}
    )
    assert fired and "below" in msg


def test_forecast_breakout_inside_band_no_fire() -> None:
    rule = _rule(type="forecast_breakout")
    fired, _, _ = alerts_evaluator.evaluate_rule(
        rule, {"price": 150.0, "forecast_high": 155.0, "forecast_low": 145.0}
    )
    assert not fired


def test_missing_signal_degrades_to_no_fire() -> None:
    # price_cross with no price available
    rule = _rule(type="price_cross", operator="above", threshold=150)
    assert alerts_evaluator.evaluate_rule(rule, {"price": None}) == (False, "", None)
    # rsi rule with no rsi
    rule = _rule(type="rsi_threshold", operator="above", threshold=70)
    assert alerts_evaluator.evaluate_rule(rule, {"rsi": None}) == (False, "", None)


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

def test_cooldown_active_within_window() -> None:
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    last = (now - timedelta(hours=2)).isoformat()
    assert alerts_evaluator._cooldown_active(last, now, timedelta(hours=6)) is True


def test_cooldown_expired() -> None:
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    last = (now - timedelta(hours=8)).isoformat()
    assert alerts_evaluator._cooldown_active(last, now, timedelta(hours=6)) is False


def test_cooldown_none_last_fired() -> None:
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    assert alerts_evaluator._cooldown_active(None, now, timedelta(hours=6)) is False


# ---------------------------------------------------------------------------
# Evaluator orchestration — firing, cooldown suppression, bad-symbol resilience
# ---------------------------------------------------------------------------

def test_evaluate_alerts_fires_and_records() -> None:
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    rules = [_rule(id="r1", symbol="AAPL", type="price_cross", operator="above", threshold=150)]
    record = AsyncMock()
    with patch.object(alerts_evaluator.alerts_store, "admin_list_active_rules",
                      new=AsyncMock(return_value=rules)), \
         patch.object(alerts_evaluator, "_fetch_symbol_signals",
                      return_value={"price": 160.0}), \
         patch.object(alerts_evaluator.alerts_store, "admin_record_fire", new=record), \
         patch.object(alerts_evaluator.alerts_store, "admin_update_last_fired", new=AsyncMock()), \
         patch.object(alerts_evaluator.alerts_store, "admin_list_push_subscriptions",
                      new=AsyncMock(return_value=[])), \
         patch.object(alerts_evaluator.notifications, "email_configured", return_value=False):
        summary = asyncio.run(alerts_evaluator.evaluate_alerts(object(), object(), now=now))
    assert summary["fired"] == 1
    assert summary["rules_checked"] == 1
    record.assert_awaited_once()


def test_evaluate_alerts_cooldown_suppresses() -> None:
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    recent = (now - timedelta(hours=1)).isoformat()
    rules = [_rule(id="r1", symbol="AAPL", type="price_cross", operator="above",
                   threshold=150, last_fired=recent)]
    record = AsyncMock()
    with patch.object(alerts_evaluator.alerts_store, "admin_list_active_rules",
                      new=AsyncMock(return_value=rules)), \
         patch.object(alerts_evaluator, "_fetch_symbol_signals",
                      return_value={"price": 160.0}), \
         patch.object(alerts_evaluator.alerts_store, "admin_record_fire", new=record):
        summary = asyncio.run(alerts_evaluator.evaluate_alerts(object(), object(), now=now))
    assert summary["fired"] == 0
    assert summary["skipped_cooldown"] == 1
    record.assert_not_awaited()


def test_evaluate_alerts_survives_bad_symbol() -> None:
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    rules = [
        _rule(id="r1", symbol="BADX", type="price_cross", operator="above", threshold=10),
        _rule(id="r2", symbol="AAPL", type="price_cross", operator="above", threshold=150),
    ]

    def _fetch(symbol, needed, yf_svc, fs):
        if symbol == "BADX":
            raise RuntimeError("yfinance exploded")
        return {"price": 160.0}

    record = AsyncMock()
    with patch.object(alerts_evaluator.alerts_store, "admin_list_active_rules",
                      new=AsyncMock(return_value=rules)), \
         patch.object(alerts_evaluator, "_fetch_symbol_signals", side_effect=_fetch), \
         patch.object(alerts_evaluator.alerts_store, "admin_record_fire", new=record), \
         patch.object(alerts_evaluator.alerts_store, "admin_update_last_fired", new=AsyncMock()), \
         patch.object(alerts_evaluator.alerts_store, "admin_list_push_subscriptions",
                      new=AsyncMock(return_value=[])), \
         patch.object(alerts_evaluator.notifications, "email_configured", return_value=False):
        summary = asyncio.run(alerts_evaluator.evaluate_alerts(object(), object(), now=now))
    # BADX raised → counted as an error, AAPL still fired.
    assert summary["errors"] == 1
    assert summary["fired"] == 1
    record.assert_awaited_once()


def test_evaluate_alerts_delivers_web_push() -> None:
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    rules = [_rule(id="r1", symbol="AAPL", type="price_cross", operator="above", threshold=150)]
    send = AsyncMock(return_value="sent")
    subs = [{"endpoint": "https://push.example/x", "p256dh": "a", "auth": "b"}]
    with patch.object(alerts_evaluator.alerts_store, "admin_list_active_rules",
                      new=AsyncMock(return_value=rules)), \
         patch.object(alerts_evaluator, "_fetch_symbol_signals",
                      return_value={"price": 160.0}), \
         patch.object(alerts_evaluator.alerts_store, "admin_record_fire", new=AsyncMock()), \
         patch.object(alerts_evaluator.alerts_store, "admin_update_last_fired", new=AsyncMock()), \
         patch.object(alerts_evaluator.alerts_store, "admin_list_push_subscriptions",
                      new=AsyncMock(return_value=subs)), \
         patch.object(alerts_evaluator.notifications, "send_web_push", new=send), \
         patch.object(alerts_evaluator.notifications, "email_configured", return_value=False):
        asyncio.run(alerts_evaluator.evaluate_alerts(object(), object(), now=now))
    send.assert_awaited_once()
