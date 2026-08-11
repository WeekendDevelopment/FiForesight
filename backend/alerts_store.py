# backend/alerts_store.py
"""
Supabase storage for Alerts & Notifications (Feature 9).

Two distinct access modes share one PostgREST client here:

  • User mode — the alerts router's CRUD endpoints forward the signed-in user's
    own JWT as the Bearer token + the anon key as `apikey`, so Row-Level Security
    scopes every read/write to `auth.uid() = user_id`. Identical to the holdings
    pattern in supabase_rest.py. No elevated privilege.

  • Service-role (admin) mode — the scheduled evaluator (alerts_evaluator.py) must
    read active rules across ALL users and write fires + read push subscriptions
    on their behalf. No single user's JWT can authorise that, so these functions
    use the Supabase service-role key, which bypasses RLS. They run ONLY behind
    the cron-secret-gated /alerts/evaluate and /alerts/digest endpoints and never
    touch a user-supplied token.

All functions raise SupabaseConfigError when the required URL/key is unset, and
SupabaseRestError on a non-2xx PostgREST response (reused from supabase_rest so
routers translate both into clean HTTP errors — tracebacks never reach clients).
"""

import logging
from typing import Any

import httpx
from config import Config
from supabase_rest import SupabaseConfigError, SupabaseRestError

logger = logging.getLogger(__name__)

_TIMEOUT = 8.0


# ---------------------------------------------------------------------------
# Low-level request helper (shared by user + service-role modes)
# ---------------------------------------------------------------------------


def _rest_url(table: str) -> str:
    if not Config.SUPABASE_URL:
        raise SupabaseConfigError(
            "Supabase is not configured (SUPABASE_URL missing). Alerts require a Supabase project."
        )
    return f"{Config.SUPABASE_URL.rstrip('/')}/rest/v1/{table}"


def _user_headers(user_jwt: str, *, prefer: str | None = None) -> dict[str, str]:
    if not Config.SUPABASE_ANON_KEY:
        raise SupabaseConfigError(
            "Supabase is not configured (SUPABASE_ANON_KEY missing). "
            "User-scoped alerts operations require the anon key."
        )
    headers = {
        "apikey": Config.SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {user_jwt}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _admin_headers(*, prefer: str | None = None) -> dict[str, str]:
    key = Config.SUPABASE_SERVICE_ROLE_KEY
    if not key or not Config.SUPABASE_URL:
        raise SupabaseConfigError(
            "Alert evaluator needs SUPABASE_SERVICE_ROLE_KEY + SUPABASE_URL — "
            "the cross-user evaluator cannot run with only the anon key."
        )
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _safe_body(resp: httpx.Response) -> str:
    """Truncated response body for logging — never surfaced to clients."""
    try:
        return resp.text[:300]
    except Exception:
        return f"HTTP {resp.status_code}"


async def _request(
    method: str,
    table: str,
    *,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
    json_body: Any = None,
    ok_codes: tuple = (200, 201, 204),
) -> Any:
    url = _rest_url(table)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.request(method, url, headers=headers, params=params, json=json_body)
    except httpx.HTTPError as exc:
        logger.error("[ALERTS] %s %s: network error: %s", method, table, exc)
        raise SupabaseRestError(0, f"Network error: {exc}") from exc
    if resp.status_code not in ok_codes:
        logger.error(
            "[ALERTS] %s %s: PostgREST returned HTTP %s — body: %s "
            "(check the 0003_alerts / 0004_push_subscriptions migrations are applied).",
            method,
            table,
            resp.status_code,
            _safe_body(resp),
        )
        raise SupabaseRestError(resp.status_code, _safe_body(resp))
    if resp.status_code == 204 or not resp.content:
        return None
    try:
        return resp.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# User mode (RLS) — alert_rules CRUD
# ---------------------------------------------------------------------------

_RULE_COLS = "id,symbol,type,operator,threshold,active,last_fired,created_at"


async def list_rules(user_jwt: str) -> list[dict[str, Any]]:
    """The authenticated user's alert rules, newest first (RLS-scoped)."""
    rows = await _request(
        "GET",
        "alert_rules",
        headers=_user_headers(user_jwt),
        params={"select": _RULE_COLS, "order": "created_at.desc"},
        ok_codes=(200,),
    )
    return rows if isinstance(rows, list) else []


async def create_rule(
    user_jwt: str,
    symbol: str,
    rule_type: str,
    operator: str | None,
    threshold: float | None,
    active: bool = True,
) -> dict[str, Any]:
    """Insert a new rule. user_id is filled by the column default auth.uid()."""
    payload = {
        "symbol": symbol,
        "type": rule_type,
        "operator": operator,
        "threshold": threshold,
        "active": active,
    }
    rows = await _request(
        "POST",
        "alert_rules",
        headers=_user_headers(user_jwt, prefer="return=representation"),
        json_body=payload,
        ok_codes=(200, 201),
    )
    if isinstance(rows, list) and rows:
        return rows[0]
    return rows if isinstance(rows, dict) else {}


async def update_rule(user_jwt: str, rule_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    """Patch a rule (e.g. toggle `active`). RLS guarantees ownership.

    Returns the updated row, or None when nothing matched (wrong id / RLS-hidden).
    """
    rows = await _request(
        "PATCH",
        "alert_rules",
        headers=_user_headers(user_jwt, prefer="return=representation"),
        params={"id": f"eq.{rule_id}"},
        json_body=fields,
        ok_codes=(200, 204),
    )
    if isinstance(rows, list) and rows:
        return rows[0]
    return None


async def delete_rule(user_jwt: str, rule_id: str) -> bool:
    """Delete a rule by id. RLS ensures a user can only delete their own row.

    Returns True when a row was removed, False when nothing matched.
    """
    rows = await _request(
        "DELETE",
        "alert_rules",
        headers=_user_headers(user_jwt, prefer="return=representation"),
        params={"id": f"eq.{rule_id}"},
        ok_codes=(200, 204),
    )
    return bool(rows)


async def list_fires(user_jwt: str, limit: int = 50) -> list[dict[str, Any]]:
    """The authenticated user's recent fire history (RLS-scoped)."""
    limit = max(1, min(int(limit), 200))
    rows = await _request(
        "GET",
        "alert_fires",
        headers=_user_headers(user_jwt),
        params={
            "select": "id,rule_id,symbol,type,message,value,fired_at",
            "order": "fired_at.desc",
            "limit": str(limit),
        },
        ok_codes=(200,),
    )
    return rows if isinstance(rows, list) else []


# ---------------------------------------------------------------------------
# User mode (RLS) — push_subscriptions
# ---------------------------------------------------------------------------


async def upsert_push_subscription(
    user_jwt: str, endpoint: str, p256dh: str, auth_key: str
) -> dict[str, Any]:
    """Store (or refresh) a browser Web-Push subscription, upserting on endpoint."""
    payload = {"endpoint": endpoint, "p256dh": p256dh, "auth": auth_key}
    rows = await _request(
        "POST",
        "push_subscriptions",
        headers=_user_headers(user_jwt, prefer="resolution=merge-duplicates,return=representation"),
        params={"on_conflict": "endpoint"},
        json_body=payload,
        ok_codes=(200, 201),
    )
    if isinstance(rows, list) and rows:
        return rows[0]
    return rows if isinstance(rows, dict) else {}


async def delete_push_subscription(user_jwt: str, endpoint: str) -> bool:
    """Remove a subscription by endpoint (RLS-scoped to the owner)."""
    rows = await _request(
        "DELETE",
        "push_subscriptions",
        headers=_user_headers(user_jwt, prefer="return=representation"),
        params={"endpoint": f"eq.{endpoint}"},
        ok_codes=(200, 204),
    )
    return bool(rows)


# ---------------------------------------------------------------------------
# Service-role (admin) mode — evaluator only. Bypasses RLS.
# ---------------------------------------------------------------------------


async def admin_list_active_rules() -> list[dict[str, Any]]:
    """All active rules across ALL users — the evaluator's input set."""
    rows = await _request(
        "GET",
        "alert_rules",
        headers=_admin_headers(),
        params={
            "select": "id,user_id,symbol,type,operator,threshold,last_fired",
            "active": "eq.true",
        },
        ok_codes=(200,),
    )
    return rows if isinstance(rows, list) else []


async def admin_record_fire(
    user_id: str,
    rule_id: str,
    symbol: str,
    rule_type: str,
    message: str,
    value: float | None,
) -> None:
    """Insert a fire row attributed to the rule's owner (service-role)."""
    payload = {
        "user_id": user_id,
        "rule_id": rule_id,
        "symbol": symbol,
        "type": rule_type,
        "message": message,
        "value": value,
    }
    await _request(
        "POST",
        "alert_fires",
        headers=_admin_headers(prefer="return=minimal"),
        json_body=payload,
        ok_codes=(200, 201, 204),
    )


async def admin_update_last_fired(rule_id: str, fired_at_iso: str) -> None:
    """Stamp last_fired so the cooldown window starts (service-role)."""
    await _request(
        "PATCH",
        "alert_rules",
        headers=_admin_headers(prefer="return=minimal"),
        params={"id": f"eq.{rule_id}"},
        json_body={"last_fired": fired_at_iso},
        ok_codes=(200, 204),
    )


async def admin_list_push_subscriptions(user_id: str) -> list[dict[str, Any]]:
    """A user's push subscriptions (service-role, for delivery)."""
    rows = await _request(
        "GET",
        "push_subscriptions",
        headers=_admin_headers(),
        params={"select": "id,endpoint,p256dh,auth", "user_id": f"eq.{user_id}"},
        ok_codes=(200,),
    )
    return rows if isinstance(rows, list) else []


async def admin_list_all_push_subscriptions() -> list[dict[str, Any]]:
    """Every push subscription across users (service-role, for the daily digest)."""
    rows = await _request(
        "GET",
        "push_subscriptions",
        headers=_admin_headers(),
        params={"select": "id,user_id,endpoint,p256dh,auth"},
        ok_codes=(200,),
    )
    return rows if isinstance(rows, list) else []


async def admin_delete_push_subscription(endpoint: str) -> None:
    """Remove a dead subscription (Push Service returned 404/410 Gone)."""
    await _request(
        "DELETE",
        "push_subscriptions",
        headers=_admin_headers(prefer="return=minimal"),
        params={"endpoint": f"eq.{endpoint}"},
        ok_codes=(200, 204),
    )


async def admin_list_holdings(user_id: str) -> list[dict[str, Any]]:
    """A user's holdings (service-role) — used to compute digest movers."""
    rows = await _request(
        "GET",
        "holdings",
        headers=_admin_headers(),
        params={"select": "symbol,shares,cost_basis,currency", "user_id": f"eq.{user_id}"},
        ok_codes=(200,),
    )
    return rows if isinstance(rows, list) else []


async def admin_get_user_email(user_id: str) -> str | None:
    """Look up a user's email via the Supabase Auth admin API (service-role).

    Only used by the optional email channel. Returns None on any failure so
    email delivery degrades silently to web-push-only.
    """
    if not Config.SUPABASE_SERVICE_ROLE_KEY or not Config.SUPABASE_URL:
        return None
    url = f"{Config.SUPABASE_URL.rstrip('/')}/auth/v1/admin/users/{user_id}"
    headers = {
        "apikey": Config.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {Config.SUPABASE_SERVICE_ROLE_KEY}",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            return None
        data = resp.json()
        email = data.get("email") if isinstance(data, dict) else None
        return email or None
    except Exception as exc:
        logger.debug("[ALERTS] admin_get_user_email(%s) failed: %s", user_id, exc)
        return None
