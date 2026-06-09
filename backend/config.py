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
    SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
    # When True, allows JWT decoding without signature verification (dev/test only).
    # NEVER set this in production — always set SUPABASE_JWT_SECRET instead.
    ALLOW_INSECURE_JWT: bool = os.getenv("ALLOW_INSECURE_JWT", "false").lower() in ("1", "true", "yes")
    # StockTwits public API now returns 403 without auth — disabled by default so
    # we don't fire a guaranteed-failing request on every prediction.
    STOCKTWITS_ENABLED = os.getenv("STOCKTWITS_ENABLED", "false").lower() in ("1", "true", "yes")

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
