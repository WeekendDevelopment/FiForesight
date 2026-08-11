# backend/universe.py
"""Curated equity universe for the Light Edition screener (F24).

A fixed ~50-name list spanning the major sectors plus a few sector-proxy ETFs.
Kept deliberately small so the screener can build its snapshot on-demand
(no background cron) and cache it in Redis for an hour.
"""

SCREENER_UNIVERSE: list[str] = [
    # Magnificent 7
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "AMZN",
    "META",
    "TSLA",
    # Semiconductors
    "AMD",
    "INTC",
    "AVGO",
    "QCOM",
    "MU",
    "ARM",
    # Financials
    "JPM",
    "BAC",
    "GS",
    "MS",
    "BRK-B",
    "V",
    "MA",
    # Healthcare
    "JNJ",
    "UNH",
    "PFE",
    "ABBV",
    "LLY",
    "MRK",
    # Energy
    "XOM",
    "CVX",
    "COP",
    # Consumer
    "WMT",
    "COST",
    "HD",
    "NKE",
    "MCD",
    # Industrials
    "CAT",
    "BA",
    "GE",
    "HON",
    # Telecom / Media
    "NFLX",
    "DIS",
    "CMCSA",
    "T",
    # ETFs (sector proxies)
    "SPY",
    "QQQ",
    "IWM",
]
