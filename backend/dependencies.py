# backend/dependencies.py
"""
Shared service singletons — imported by all router modules.
Instantiated once at import time so there's a single instance across the app.
"""
import logging

import jwt
from fastapi import Header
from services import (
    InfluxService,
    ForecastStore,
    SerpService,
    YFinanceService,
    AnalystJuryService,
    SentimentService,
    FinnhubService,
    StockTwitsService,
)
from config import Config

logger = logging.getLogger(__name__)

influx_svc       = InfluxService()
forecast_store   = ForecastStore(influx_svc)
serp_svc         = SerpService()
yf_svc           = YFinanceService()
analyst_jury_svc = AnalystJuryService()
sentiment_svc    = SentimentService()
finnhub_svc      = FinnhubService()
stocktwits_svc   = StockTwitsService()


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
