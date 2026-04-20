# backend/mcp_server.py
"""
FiForesight MCP Server — exposes the forecasting engine as MCP tools.

Usage (dev):
    fastmcp dev backend/mcp_server.py

Usage (Claude Code):
    Add to .claude/settings.json mcpServers:
    {
      "fiforesight": {
        "command": "python",
        "args": ["backend/mcp_server.py"],
        "cwd": "<repo-root>"
      }
    }

The server proxies to the running FastAPI backend (BACKEND_URL env var,
default http://localhost:8000).  This lets Claude Code call the full
forecasting pipeline as a tool during development sessions — no browser
required to test predictions.
"""

import os
import httpx
from fastmcp import FastMCP

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

mcp = FastMCP(
    name="FiForesight",
    instructions=(
        "FiForesight financial forecasting engine. "
        "Use predict() to get 48-hour price forecasts, technical indicators, "
        "analyst jury verdicts, and news sentiment for any stock ticker. "
        "Use sparklines() to get 5-day mini price series for watchlist views. "
        "Use health() to check if the backend is reachable."
    ),
)


@mcp.tool()
async def predict(symbol: str) -> dict:
    """
    Run the full FiForesight forecast pipeline for a stock ticker.

    Returns:
      - currentPrice: latest price
      - prediction: 5-day high/low range and trend
      - forecastDays: per-day predicted price, high, low, confidence
      - indicators: RSI series, support/resistance levels
      - juryAnalysts: 3-analyst LLM jury verdicts (rating, note, confidence)
      - sentiment: VADER news sentiment (compound score, label)
      - news: recent headlines
      - modelWeights: Prophet/SARIMAX/RF ensemble weights
      - confidence: overall forecast confidence label (high/medium/low)

    Args:
      symbol: Stock ticker, e.g. 'AAPL', 'NVDA', 'SPY'
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/predict",
            json={"data": symbol.upper()},
        )
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def sparklines(tickers: str) -> dict:
    """
    Get the last 5 closing prices for a comma-separated list of tickers.
    Useful for building quick watchlist views without running a full forecast.

    Args:
      tickers: Comma-separated symbols, e.g. 'AAPL,MSFT,NVDA'

    Returns:
      Dict mapping each symbol to a list of up to 5 recent close prices.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{BACKEND_URL}/sparklines",
            params={"tickers": tickers},
        )
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def health() -> dict:
    """
    Check the health of the FiForesight backend and all its dependencies.

    Returns a dict with:
      - status: 'ok' if the backend is reachable
      - yfinance_installed, ml_models_available, influxdb_reachable, groq_key_set, etc.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{BACKEND_URL}/health")
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    mcp.run()
