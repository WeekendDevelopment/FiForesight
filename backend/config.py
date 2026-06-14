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
    # FRED macro data (Feature 15). OPTIONAL — the public fredgraph.csv endpoint
    # works without a key; a key only raises the request rate limit.
    FRED_API_KEY = os.getenv("FRED_API_KEY", "")
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
    SUPABASE_URL = os.getenv("SUPABASE_URL", "") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
    # JWKS endpoint. Defaults to the standard Supabase path under SUPABASE_URL;
    # can be overridden directly.
    SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL", "") or (
        f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else ""
    )
    # Supabase anon (public) API key. Used as the `apikey` header when the backend
    # reads the user's `holdings` rows through Supabase PostgREST. The user's own
    # JWT is forwarded as the Bearer token, so Row-Level Security scopes every
    # query to that user — no service-role key is needed (free-tier safe).
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    # Supabase service-role key. Bypasses Row-Level Security. Used ONLY by the
    # scheduled alert evaluator (Feature 9), which must read active rules across
    # ALL users and write fires on their behalf — work that no single user's JWT
    # could authorise. NEVER forwarded from a user request; never sent to the
    # client. When unset, the evaluator endpoints return 503 (alerts CRUD still
    # works via the user JWT + RLS, like holdings).
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # --- Alerts & Notifications (Feature 9) -------------------------------------
    # Shared secret guarding the internal POST /alerts/evaluate and
    # /alerts/digest endpoints. The scheduler (cron / Supabase Edge Function)
    # sends it as the `X-Cron-Secret` header. When unset, those endpoints return
    # 503 — the evaluator is effectively disabled (fail closed).
    CRON_SECRET = os.getenv("CRON_SECRET", "")
    # Cooldown (hours) after a rule fires before it can fire again. Prevents a
    # persistently-true condition (e.g. price stays above a threshold) from
    # notifying on every 15-min evaluator run.
    ALERT_COOLDOWN_HOURS = float(os.getenv("ALERT_COOLDOWN_HOURS", "6"))

    # Web Push (VAPID). Generate a key pair once with `vapid --gen` (py-vapid,
    # bundled with pywebpush) or the helper in docs. The public key is exposed to
    # the browser (GET /alerts/vapid-public-key) to create the subscription; the
    # private key signs outgoing pushes server-side. When the pair is unset, push
    # delivery is skipped (logged) and alerts still record fires + email.
    VAPID_PUBLIC_KEY  = os.getenv("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
    # mailto: or https: subject claim required by the Web Push spec.
    VAPID_SUBJECT     = os.getenv("VAPID_SUBJECT", "mailto:alerts@fiforesight.duckdns.org")

    # Email fallback (optional). Off unless ALERT_EMAIL_ENABLED=true AND a Resend
    # API key is configured. Resend's free tier (100 emails/day) keeps this within
    # the project's free-only constraint. Web push works independently of email.
    ALERT_EMAIL_ENABLED = os.getenv("ALERT_EMAIL_ENABLED", "false").lower() in ("1", "true", "yes")
    RESEND_API_KEY      = os.getenv("RESEND_API_KEY", "")
    ALERT_EMAIL_FROM    = os.getenv("ALERT_EMAIL_FROM", "FiForesight Alerts <alerts@fiforesight.duckdns.org>")
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
    # Alternative data (Feature 15) — SEC EDGAR insider lookup (per IP).
    RATE_LIMIT_INSIDER:      str = os.getenv("RATE_LIMIT_INSIDER",      "30/minute")
    # Portfolio Manager (Feature 10) — holdings CRUD is cheap (Supabase only);
    # the summary fans out to yfinance per holding, so it gets a tighter limit.
    RATE_LIMIT_PORTFOLIO:         str = os.getenv("RATE_LIMIT_PORTFOLIO",         "30/minute")
    RATE_LIMIT_PORTFOLIO_SUMMARY: str = os.getenv("RATE_LIMIT_PORTFOLIO_SUMMARY", "15/minute")
    # Alerts & Notifications (Feature 9) — rule CRUD + push subscribe are cheap
    # (Supabase only), keyed per authenticated user.
    RATE_LIMIT_ALERTS:            str = os.getenv("RATE_LIMIT_ALERTS",            "30/minute")

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
