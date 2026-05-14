# backend/dependencies.py
"""
Shared service singletons — imported by all router modules.
Instantiated once at import time so there's a single instance across the app.
"""
from services import (
    InfluxService,
    ForecastStore,
    SerpService,
    YFinanceService,
    AnalystJuryService,
    SentimentService,
)

influx_svc       = InfluxService()
forecast_store   = ForecastStore(influx_svc)
serp_svc         = SerpService()
yf_svc           = YFinanceService()
analyst_jury_svc = AnalystJuryService()
sentiment_svc    = SentimentService()
