import os
from pathlib import Path
from dotenv import load_dotenv
import logging

# Always load .env from the backend/ directory, regardless of where uvicorn is launched from
load_dotenv(Path(__file__).parent / ".env")

class Config:
    INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
    INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
    INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "WeekendDevelopment")
    INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "FiForesightBucket")
    SERP_API_KEY = os.getenv("SERP_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
    ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
    ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
    PORT = int(os.getenv("PORT", 8000))
    # Deployment environment tag — stamped onto time-series writes (e.g. sentiment_score)
    # so preview and prod data can be distinguished in InfluxDB. local | preview | live.
    APP_ENV = os.getenv("APP_ENV", "local")
    SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
    # Supabase project URL (e.g. https://xxxx.supabase.co). Used to locate the
    # JWKS endpoint for verifying asymmetric (ES256/RS256) access tokens — the
    # default signing scheme for Supabase projects with JWT signing keys. The
    # legacy HS256 SUPABASE_JWT_SECRET cannot verify these.
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    # JWKS endpoint. Defaults to the standard Supabase path under SUPABASE_URL;
    # can be overridden directly.
    SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL", "") or (
        f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else ""
    )
    # When True, allows JWT decoding without signature verification (dev/test only).
    # NEVER set this in production — always set SUPABASE_JWT_SECRET (HS256) or
    # SUPABASE_URL/SUPABASE_JWKS_URL (ES256/RS256) instead.
    ALLOW_INSECURE_JWT: bool = os.getenv("ALLOW_INSECURE_JWT", "false").lower() in ("1", "true", "yes")
    # StockTwits public API now returns 403 without auth — disabled by default so
    # we don't fire a guaranteed-failing request on every prediction.
    STOCKTWITS_ENABLED = os.getenv("STOCKTWITS_ENABLED", "false").lower() in ("1", "true", "yes")

    # When True, /predict runs the 3-analyst LLM jury automatically (legacy
    # behaviour). Default False: the jury is on-demand only via POST
    # /jury/reanalyze, which saves Groq free-tier quota (each auto-run could
    # fire up to ~9 requests) and avoids 429-driven fallback verdicts inside
    # the prediction response.
    JURY_AUTO_RUN: bool = os.getenv("JURY_AUTO_RUN", "false").lower() in ("1", "true", "yes")

    # CORS — comma-separated list of allowed origins.
    # Defaults to prod + preview + local dev.
    ALLOWED_ORIGINS: str = os.getenv(
        "ALLOWED_ORIGINS",
        "https://fiforesight.duckdns.org,https://fiforesight-preview.duckdns.org,http://localhost:3000",
    )

    # Per-endpoint rate limits (slowapi format: "N/period").
    # Separate anon (IP-keyed) and authed (user-keyed) limits for compute endpoints.
    RATE_LIMIT_PREDICT_ANON: str = os.getenv("RATE_LIMIT_PREDICT_ANON", "3/minute")
    RATE_LIMIT_PREDICT_AUTH: str = os.getenv("RATE_LIMIT_PREDICT_AUTH", "10/minute")
    RATE_LIMIT_CHAT:         str = os.getenv("RATE_LIMIT_CHAT",         "20/minute")
    RATE_LIMIT_JURY:         str = os.getenv("RATE_LIMIT_JURY",         "10/minute")
    RATE_LIMIT_TRADE:        str = os.getenv("RATE_LIMIT_TRADE",        "15/minute")
    RATE_LIMIT_BACKTEST:     str = os.getenv("RATE_LIMIT_BACKTEST",     "5/minute")
    RATE_LIMIT_READONLY:     str = os.getenv("RATE_LIMIT_READONLY",     "60/minute")

class SanitizeHttpxFilter(logging.Filter):
    SENSITIVE_PARAMS = {"api_key", "token", "secret", "password", "key"}

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith("httpx"):
            msg = record.getMessage()
            for param in self.SENSITIVE_PARAMS:
                # crude but effective — mask value after param name
                import re
                msg = re.sub(
                    rf"({param}=)[^&\s\"']+",
                    r"\1***",
                    msg,
                    flags=re.IGNORECASE,
                )
            record.msg = msg
            record.args = ()
        return True
