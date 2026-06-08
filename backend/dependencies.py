# backend/dependencies.py
"""
Shared service singletons — imported by all router modules.
Instantiated once at import time so there's a single instance across the app.
"""
import logging

import jwt
from fastapi import Header, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from services import (
    InfluxService,
    ForecastStore,
    SerpService,
    YFinanceService,
    AnalystJuryService,
    SentimentService,
    FinnhubService,
    StockTwitsService,
    YahooRSSService,
)
from config import Config

logger = logging.getLogger(__name__)

if not Config.SUPABASE_JWT_SECRET:
    logger.warning(
        "[AUTH] SUPABASE_JWT_SECRET is not set — JWT signature verification DISABLED. "
        "Set SUPABASE_JWT_SECRET in production to enforce token integrity."
    )

influx_svc       = InfluxService()
forecast_store   = ForecastStore(influx_svc)
serp_svc         = SerpService()
yf_svc           = YFinanceService()
analyst_jury_svc = AnalystJuryService()
sentiment_svc    = SentimentService()
finnhub_svc      = FinnhubService()
stocktwits_svc   = StockTwitsService()
yahoo_rss_svc    = YahooRSSService()


# ---------------------------------------------------------------------------
# Rate limiting — single Limiter instance shared across all routers
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)


def _extract_sub_fast(request: Request) -> str:
    """Extract JWT sub from the request without any DB calls.

    Returns the UUID string for authenticated requests, '' for anonymous/invalid.
    Mirrors the logic in get_user_id() — keep in sync if auth model changes.
    """
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return ""
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        return ""
    secret = Config.SUPABASE_JWT_SECRET
    try:
        if secret:
            p = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})
        else:
            p = jwt.decode(token, options={"verify_signature": False})
        return p.get("sub", "")
    except Exception:
        return ""


def _is_authed_request(request: Request) -> bool:
    """Return True when the request carries a valid (or dev-mode) Supabase JWT."""
    return bool(_extract_sub_fast(request))


def _user_rate_key(request: Request) -> str:
    """Rate-limit key: user UUID for authenticated requests, remote IP for anonymous."""
    sub = _extract_sub_fast(request)
    return f"user:{sub}" if sub else f"ip:{get_remote_address(request)}"


# ---------------------------------------------------------------------------
# Auth dependencies
# ---------------------------------------------------------------------------

def get_user_id(authorization: str = Header(default="")) -> str:
    """Extract and validate the Supabase user UUID from a Bearer JWT.

    Returns the UUID string if the token is valid, or "" for anonymous/invalid.
    When SUPABASE_JWT_SECRET is set the signature is verified; otherwise the
    token is decoded without verification so dev environments still work.
    """
    if not authorization.startswith("Bearer "):
        return ""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return ""
    secret = Config.SUPABASE_JWT_SECRET
    try:
        if secret:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        else:
            payload = jwt.decode(token, options={"verify_signature": False})
        sub = payload.get("sub", "")
        return InfluxService._validate_user_id(sub)
    except Exception:
        logger.debug("get_user_id: invalid or unverifiable JWT, treating as anonymous")
        return ""


def require_user(authorization: str = Header(default="")) -> str:
    """Require a valid authenticated user.

    Raises HTTP 401 when no valid Bearer token is present.
    Returns the user UUID on success.
    """
    user_id = get_user_id(authorization)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id
