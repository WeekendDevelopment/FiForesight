# backend/supabase_rest.py
"""
Thin async client for the Supabase `holdings` table via PostgREST.

Auth model — the backend never uses a service-role key. It forwards the signed-in
user's own JWT as the Bearer token and the project's anon key as `apikey`, so
Supabase Row-Level Security scopes every read/write to `auth.uid() = user_id`.
This keeps ownership enforcement in the database (defence in depth alongside the
`require_user` gate) and stays within the free tier.

All functions raise SupabaseConfigError when SUPABASE_URL / SUPABASE_ANON_KEY are
unset, and SupabaseRestError on a non-2xx PostgREST response. Routers translate
these into clean HTTP errors — tracebacks never reach the client.
"""
import logging
from typing import Any, Dict, List

import httpx

from config import Config

logger = logging.getLogger(__name__)

_TABLE = "holdings"
_TIMEOUT = 8.0


class SupabaseConfigError(RuntimeError):
    """Raised when Supabase REST is called but the project URL/key is not set."""


class SupabaseRestError(RuntimeError):
    """Raised on a non-2xx PostgREST response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def _base_url() -> str:
    if not Config.SUPABASE_URL or not Config.SUPABASE_ANON_KEY:
        raise SupabaseConfigError(
            "Supabase is not configured (SUPABASE_URL / SUPABASE_ANON_KEY). "
            "Portfolio holdings require a Supabase project."
        )
    return f"{Config.SUPABASE_URL.rstrip('/')}/rest/v1/{_TABLE}"


def _headers(user_jwt: str, *, prefer: str | None = None) -> Dict[str, str]:
    headers = {
        "apikey": Config.SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {user_jwt}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


async def list_holdings(user_jwt: str) -> List[Dict[str, Any]]:
    """Return the authenticated user's holdings (RLS-scoped), newest first."""
    url = _base_url()
    params = {
        "select": "id,symbol,shares,cost_basis,currency,opened_at",
        "order": "opened_at.desc",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=_headers(user_jwt), params=params)
    except httpx.HTTPError as exc:
        logger.error("[PORTFOLIO] list_holdings: network error contacting %s: %s", url, exc)
        raise SupabaseRestError(0, f"Network error: {exc}") from exc
    if resp.status_code != 200:
        logger.error(
            "[PORTFOLIO] list_holdings: PostgREST returned HTTP %s from %s — "
            "body: %s — check migration 0001/0002 applied and SUPABASE_URL/SUPABASE_ANON_KEY are correct.",
            resp.status_code, url, _safe_body(resp),
        )
        raise SupabaseRestError(resp.status_code, _safe_body(resp))
    data = resp.json()
    return data if isinstance(data, list) else []


async def upsert_holding(
    user_jwt: str, symbol: str, shares: float, cost_basis: float, currency: str = "USD"
) -> Dict[str, Any]:
    """Insert a holding, or replace shares/cost_basis/currency if the user already holds it.

    Relies on the `holdings_user_symbol_unique` constraint + PostgREST
    merge-duplicates upsert. RLS check (auth.uid() = user_id) enforces ownership.
    """
    url = _base_url()
    payload = {"symbol": symbol, "shares": shares, "cost_basis": cost_basis, "currency": currency}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                url,
                headers=_headers(user_jwt, prefer="resolution=merge-duplicates,return=representation"),
                params={"on_conflict": "user_id,symbol"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        logger.error("[PORTFOLIO] upsert_holding(%s): network error: %s", symbol, exc)
        raise SupabaseRestError(0, f"Network error: {exc}") from exc
    if resp.status_code not in (200, 201):
        logger.error(
            "[PORTFOLIO] upsert_holding(%s): PostgREST returned HTTP %s — body: %s",
            symbol, resp.status_code, _safe_body(resp),
        )
        raise SupabaseRestError(resp.status_code, _safe_body(resp))
    rows = resp.json()
    return rows[0] if isinstance(rows, list) and rows else (rows if isinstance(rows, dict) else {})


async def delete_holding(user_jwt: str, holding_id: str) -> bool:
    """Delete a holding by id. RLS guarantees a user can only delete their own row.

    Returns True when a row was actually removed, False when nothing matched
    (wrong id, or another user's row that RLS hid).
    """
    url = _base_url()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.delete(
                url,
                headers=_headers(user_jwt, prefer="return=representation"),
                params={"id": f"eq.{holding_id}"},
            )
    except httpx.HTTPError as exc:
        logger.error("[PORTFOLIO] delete_holding(%s): network error: %s", holding_id, exc)
        raise SupabaseRestError(0, f"Network error: {exc}") from exc
    if resp.status_code not in (200, 204):
        logger.error(
            "[PORTFOLIO] delete_holding(%s): PostgREST returned HTTP %s — body: %s",
            holding_id, resp.status_code, _safe_body(resp),
        )
        raise SupabaseRestError(resp.status_code, _safe_body(resp))
    try:
        rows = resp.json()
        return bool(rows)
    except Exception:
        return resp.status_code == 204


def _safe_body(resp: httpx.Response) -> str:
    """Truncated response body for logging — never surfaced to clients."""
    try:
        return resp.text[:300]
    except Exception:
        return f"HTTP {resp.status_code}"
