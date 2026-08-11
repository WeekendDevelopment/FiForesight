# backend/dependencies.py
"""
Shared service singletons — imported by all router modules.
Instantiated once at import time so there's a single instance across the app.
"""

import logging

import jwt
from config import Config
from fastapi import Header, HTTPException, Request
from jwt import PyJWKClient
from services import (
    AnalystJuryService,
    FinnhubService,
    ForecastStore,
    FREDService,
    InfluxService,
    InsiderService,
    RegimeService,
    SentimentService,
    SerpService,
    ShortInterestService,
    StockTwitsService,
    YahooRSSService,
    YFinanceService,
)
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

if not Config.SUPABASE_JWT_SECRET and not Config.SUPABASE_JWKS_URL:
    if Config.ALLOW_INSECURE_JWT:
        logger.warning(
            "[AUTH] Neither SUPABASE_JWT_SECRET nor SUPABASE_JWKS_URL is set and "
            "ALLOW_INSECURE_JWT=true — JWT signature verification is DISABLED. This is "
            "only safe in dev/test environments. Set SUPABASE_JWT_SECRET (HS256) or "
            "SUPABASE_URL/SUPABASE_JWKS_URL (ES256/RS256) in production."
        )
    else:
        logger.info(
            "[AUTH] Neither SUPABASE_JWT_SECRET nor SUPABASE_JWKS_URL is set. "
            "Requests without a verifiable JWT will be treated as anonymous. "
            "To enable dev-mode unsigned JWT decoding, set ALLOW_INSECURE_JWT=true."
        )

# JWKS client for asymmetric (ES256/RS256) Supabase tokens. PyJWKClient caches
# fetched keys internally, so this single instance is reused across requests and
# only hits the network on a cache miss (e.g. first request or key rotation).
_jwks_client: "PyJWKClient | None" = (
    PyJWKClient(Config.SUPABASE_JWKS_URL) if Config.SUPABASE_JWKS_URL else None
)
# Asymmetric algorithms whose tokens must be verified via the JWKS public key,
# not the HS256 shared secret.
_ASYMMETRIC_ALGS = {"ES256", "RS256", "ES384", "RS384", "ES512", "RS512", "EdDSA"}

influx_svc = InfluxService()
forecast_store = ForecastStore(influx_svc)
serp_svc = SerpService()
yf_svc = YFinanceService()
analyst_jury_svc = AnalystJuryService()
sentiment_svc = SentimentService()
finnhub_svc = FinnhubService()
stocktwits_svc = StockTwitsService()
yahoo_rss_svc = YahooRSSService()
# Alternative data sources (Feature 15)
fred_svc = FREDService()
insider_svc = InsiderService()
short_interest_svc = ShortInterestService()
# Market regime intelligence (Feature 16)
regime_svc = RegimeService()


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
        elif Config.ALLOW_INSECURE_JWT:
            # Dev/test only — skip signature verification when explicitly opted in
            p = jwt.decode(token, options={"verify_signature": False})
        else:
            # No secret and no insecure flag → fail closed; treat as anonymous
            return ""
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

    Verification is chosen by the token's `alg` header so both Supabase signing
    schemes work:
      - ES256/RS256 (asymmetric, the default for projects with JWT signing keys)
        → verified against the project's JWKS public keys (SUPABASE_JWKS_URL).
      - HS256 (legacy shared secret) → verified with SUPABASE_JWT_SECRET.
    When ALLOW_INSECURE_JWT=true and no verifier is configured, decodes without
    verification (dev/test only). Otherwise fails closed → "".
    """
    if not authorization.startswith("Bearer "):
        return ""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return ""
    try:
        alg = (jwt.get_unverified_header(token) or {}).get("alg", "")
        if alg in _ASYMMETRIC_ALGS:
            # Asymmetric (e.g. Supabase ES256) — verify via JWKS public key.
            if _jwks_client is not None:
                signing_key = _jwks_client.get_signing_key_from_jwt(token).key
                payload = jwt.decode(
                    token,
                    signing_key,
                    algorithms=list(_ASYMMETRIC_ALGS),
                    options={"verify_aud": False},
                )
            elif Config.ALLOW_INSECURE_JWT:
                payload = jwt.decode(token, options={"verify_signature": False})
            else:
                # Asymmetric token but no JWKS configured → can't verify.
                return ""
        elif Config.SUPABASE_JWT_SECRET:
            # Legacy HS256 shared-secret token.
            payload = jwt.decode(
                token,
                Config.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        elif Config.ALLOW_INSECURE_JWT:
            # Dev/test only — skip signature verification when explicitly opted in
            payload = jwt.decode(token, options={"verify_signature": False})
        else:
            # No verifier configured → fail closed; treat as anonymous
            return ""
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
