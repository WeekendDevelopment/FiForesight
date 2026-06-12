# backend/routers/alerts.py
"""
Alerts & Notifications (Feature 9).

User-facing CRUD is auth-gated via `require_user` (401 when unauthenticated) and
reads/writes Supabase through the caller's own forwarded JWT, so Row-Level
Security scopes everything to `auth.uid() = user_id` (same model as holdings).

The scheduled evaluator + daily digest are exposed as internal endpoints guarded
by a shared `X-Cron-Secret` header (env CRON_SECRET) — NOT a user JWT. A cron job
or Supabase scheduled Edge Function hits them every 15 min (evaluate) / once a
day (digest). They run the cross-user evaluator, which uses the service-role key
to read all active rules and deliver notifications. There is no sleep loop.

Endpoints
  GET    /alerts/rules                 — list the user's rules
  POST   /alerts/rules                 — create a rule (validated per type)
  PATCH  /alerts/rules/{id}            — toggle active / update threshold
  DELETE /alerts/rules/{id}            — delete a rule (ownership via RLS)
  GET    /alerts/fires                 — recent fire history
  GET    /alerts/vapid-public-key      — VAPID public key for browser subscribe
  POST   /alerts/subscribe             — store a Web-Push subscription
  POST   /alerts/unsubscribe           — remove a Web-Push subscription
  POST   /alerts/evaluate              — [cron] run the evaluator
  POST   /alerts/digest                — [cron] send the daily briefing digest
"""
import hmac
import logging
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, field_validator

import alerts_evaluator
import alerts_store
import supabase_rest
from config import Config
from dependencies import limiter, require_user, yf_svc, forecast_store, _user_rate_key
from notifications import web_push_configured

router = APIRouter()
logger = logging.getLogger(__name__)

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-:]{1,15}$")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

_VALID_TYPES = {"price_cross", "rsi_threshold", "pct_move", "earnings_soon", "forecast_breakout"}
_VALID_OPERATORS = {"above", "below"}
# Types that REQUIRE an operator + threshold.
_OPERATOR_TYPES = {"price_cross", "rsi_threshold"}


def _bearer(authorization: str) -> str:
    """Extract the raw JWT. require_user already guarantees it's present+valid."""
    return authorization.removeprefix("Bearer ").strip()


def _handle_store_error(exc: Exception) -> HTTPException:
    """Map Supabase helper errors to clean HTTP errors (no traceback leakage)."""
    if isinstance(exc, supabase_rest.SupabaseConfigError):
        logger.error("[ALERTS] Supabase not configured: %s", exc)
        return HTTPException(status_code=503, detail="Alerts storage is not configured.")
    if isinstance(exc, supabase_rest.SupabaseRestError):
        logger.error(
            "[ALERTS] Supabase REST error (HTTP %s): %s — "
            "if 404/42P01, the 0003_alerts / 0004_push_subscriptions migration may not be applied.",
            exc.status_code, exc,
        )
        return HTTPException(status_code=502, detail="Could not reach the alerts store.")
    logger.error("[ALERTS] unexpected store error: %s", exc)
    return HTTPException(status_code=500, detail="An internal server error occurred.")


# ---------------------------------------------------------------------------
# Schemas + validation
# ---------------------------------------------------------------------------

class RuleCreate(BaseModel):
    symbol: str
    type: str
    operator: Optional[str] = None
    threshold: Optional[float] = None
    active: bool = True

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not _SYMBOL_RE.match(v):
            raise ValueError("Invalid symbol.")
        return v

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in _VALID_TYPES:
            raise ValueError(f"Invalid type. Allowed: {', '.join(sorted(_VALID_TYPES))}")
        return v

    @field_validator("operator")
    @classmethod
    def _validate_operator(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        v = v.strip().lower()
        if v not in _VALID_OPERATORS:
            raise ValueError("operator must be 'above' or 'below'.")
        return v


def _validate_combo(rule: RuleCreate) -> None:
    """Enforce type ⇄ operator ⇄ threshold consistency. Raises HTTP 422."""
    t, op, thr = rule.type, rule.operator, rule.threshold

    if t in _OPERATOR_TYPES:
        if op is None:
            raise HTTPException(422, f"{t} requires operator 'above' or 'below'.")
        if thr is None:
            raise HTTPException(422, f"{t} requires a numeric threshold.")
        if t == "rsi_threshold" and not (0 <= thr <= 100):
            raise HTTPException(422, "rsi_threshold must be between 0 and 100.")
        if t == "price_cross" and thr <= 0:
            raise HTTPException(422, "price_cross threshold must be > 0.")

    elif t == "pct_move":
        if thr is None or thr <= 0:
            raise HTTPException(422, "pct_move requires a positive threshold (percent).")
        # operator optional: above (up only) / below (down only) / none (abs)

    elif t == "earnings_soon":
        if rule.operator is not None:
            raise HTTPException(422, "earnings_soon does not take an operator.")
        if thr is not None and not (1 <= thr <= 30):
            raise HTTPException(422, "earnings_soon window (days) must be between 1 and 30.")

    elif t == "forecast_breakout":
        if rule.operator is not None or thr is not None:
            raise HTTPException(422, "forecast_breakout does not take an operator or threshold.")


class RuleUpdate(BaseModel):
    active: Optional[bool] = None
    threshold: Optional[float] = None


class PushSubscription(BaseModel):
    endpoint: str
    keys: Dict[str, str]

    @field_validator("endpoint")
    @classmethod
    def _validate_endpoint(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.startswith("https://") or len(v) > 2000:
            raise ValueError("Invalid push endpoint.")
        return v


class Unsubscribe(BaseModel):
    endpoint: str


# ---------------------------------------------------------------------------
# Rules CRUD
# ---------------------------------------------------------------------------

@router.get("/alerts/rules")
@limiter.limit(lambda: Config.RATE_LIMIT_ALERTS, key_func=_user_rate_key)
async def list_rules(
    request: Request,
    user_id: str = Depends(require_user),
    authorization: str = Header(default=""),
):
    try:
        rules = await alerts_store.list_rules(_bearer(authorization))
    except Exception as exc:
        raise _handle_store_error(exc)
    return {"rules": rules}


@router.post("/alerts/rules")
@limiter.limit(lambda: Config.RATE_LIMIT_ALERTS, key_func=_user_rate_key)
async def create_rule(
    request: Request,
    body: RuleCreate,
    user_id: str = Depends(require_user),
    authorization: str = Header(default=""),
):
    _validate_combo(body)
    try:
        rule = await alerts_store.create_rule(
            _bearer(authorization), body.symbol, body.type, body.operator, body.threshold, body.active
        )
    except Exception as exc:
        raise _handle_store_error(exc)
    return {"rule": rule}


@router.patch("/alerts/rules/{rule_id}")
@limiter.limit(lambda: Config.RATE_LIMIT_ALERTS, key_func=_user_rate_key)
async def update_rule(
    request: Request,
    rule_id: str,
    body: RuleUpdate,
    user_id: str = Depends(require_user),
    authorization: str = Header(default=""),
):
    if not _UUID_RE.match(rule_id):
        raise HTTPException(status_code=422, detail="Invalid rule id.")
    fields: Dict[str, Any] = {}
    if body.active is not None:
        fields["active"] = body.active
    if body.threshold is not None:
        fields["threshold"] = body.threshold
    if not fields:
        raise HTTPException(status_code=422, detail="No updatable fields provided.")
    try:
        rule = await alerts_store.update_rule(_bearer(authorization), rule_id, fields)
    except Exception as exc:
        raise _handle_store_error(exc)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")
    return {"rule": rule}


@router.delete("/alerts/rules/{rule_id}")
@limiter.limit(lambda: Config.RATE_LIMIT_ALERTS, key_func=_user_rate_key)
async def delete_rule(
    request: Request,
    rule_id: str,
    user_id: str = Depends(require_user),
    authorization: str = Header(default=""),
):
    if not _UUID_RE.match(rule_id):
        raise HTTPException(status_code=422, detail="Invalid rule id.")
    try:
        removed = await alerts_store.delete_rule(_bearer(authorization), rule_id)
    except Exception as exc:
        raise _handle_store_error(exc)
    if not removed:
        raise HTTPException(status_code=404, detail="Rule not found.")
    return {"deleted": True, "id": rule_id}


@router.get("/alerts/fires")
@limiter.limit(lambda: Config.RATE_LIMIT_ALERTS, key_func=_user_rate_key)
async def list_fires(
    request: Request,
    user_id: str = Depends(require_user),
    authorization: str = Header(default=""),
):
    try:
        fires = await alerts_store.list_fires(_bearer(authorization))
    except Exception as exc:
        raise _handle_store_error(exc)
    return {"fires": fires}


# ---------------------------------------------------------------------------
# Web Push subscription
# ---------------------------------------------------------------------------

@router.get("/alerts/vapid-public-key")
@limiter.limit(lambda: Config.RATE_LIMIT_ALERTS, key_func=_user_rate_key)
async def vapid_public_key(
    request: Request,
    user_id: str = Depends(require_user),
):
    return {
        "public_key": Config.VAPID_PUBLIC_KEY or "",
        "configured": web_push_configured(),
    }


@router.post("/alerts/subscribe")
@limiter.limit(lambda: Config.RATE_LIMIT_ALERTS, key_func=_user_rate_key)
async def subscribe(
    request: Request,
    body: PushSubscription,
    user_id: str = Depends(require_user),
    authorization: str = Header(default=""),
):
    p256dh = body.keys.get("p256dh", "")
    auth_key = body.keys.get("auth", "")
    if not p256dh or not auth_key:
        raise HTTPException(status_code=422, detail="Subscription missing p256dh/auth keys.")
    try:
        row = await alerts_store.upsert_push_subscription(
            _bearer(authorization), body.endpoint, p256dh, auth_key
        )
    except Exception as exc:
        raise _handle_store_error(exc)
    return {"subscribed": True, "id": row.get("id")}


@router.post("/alerts/unsubscribe")
@limiter.limit(lambda: Config.RATE_LIMIT_ALERTS, key_func=_user_rate_key)
async def unsubscribe(
    request: Request,
    body: Unsubscribe,
    user_id: str = Depends(require_user),
    authorization: str = Header(default=""),
):
    try:
        await alerts_store.delete_push_subscription(_bearer(authorization), body.endpoint)
    except Exception as exc:
        raise _handle_store_error(exc)
    return {"unsubscribed": True}


# ---------------------------------------------------------------------------
# Internal scheduled endpoints — X-Cron-Secret gated (NOT user JWT)
# ---------------------------------------------------------------------------

def require_cron(x_cron_secret: str = Header(default="", alias="X-Cron-Secret")) -> bool:
    """Guard the evaluator/digest endpoints with a shared secret.

    Fails closed: 503 when CRON_SECRET is unset (evaluator disabled), 403 on a
    missing/incorrect header. Constant-time comparison avoids timing leaks.
    """
    if not Config.CRON_SECRET:
        raise HTTPException(status_code=503, detail="Evaluator is not configured.")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, Config.CRON_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden.")
    return True


@router.post("/alerts/evaluate")
async def run_evaluator(request: Request, _ok: bool = Depends(require_cron)):
    if not Config.SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Evaluator requires SUPABASE_SERVICE_ROLE_KEY.")
    try:
        summary = await alerts_evaluator.evaluate_alerts(yf_svc, forecast_store)
    except Exception as exc:
        raise _handle_store_error(exc)
    return {"ok": True, "summary": summary}


@router.post("/alerts/digest")
async def run_digest(request: Request, _ok: bool = Depends(require_cron)):
    if not Config.SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Digest requires SUPABASE_SERVICE_ROLE_KEY.")
    try:
        summary = await alerts_evaluator.build_and_send_digest(yf_svc)
    except Exception as exc:
        raise _handle_store_error(exc)
    return {"ok": True, "summary": summary}
