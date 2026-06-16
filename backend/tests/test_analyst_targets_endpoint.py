"""
Tests for the Analyst Price Targets endpoint (Feature 21):
  - GET /analyst-targets/{symbol}

yfinance is mocked — no network required.
"""
import importlib as _il
from unittest.mock import MagicMock, patch

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from backend.routers import market  # noqa: E402

_deps = _il.import_module("dependencies")
limiter = _deps.limiter

_app = FastAPI()
_app.state.limiter = limiter


async def _rl_handler(req: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Too many requests."})


_app.add_exception_handler(RateLimitExceeded, _rl_handler)
_app.include_router(market.router)
client = TestClient(_app)


def _mock_ticker(targets=None, recs_df=None, info=None):
    t = MagicMock()
    t.analyst_price_targets = targets
    t.recommendations_summary = recs_df
    t.info = info if info is not None else {}
    return t


class TestAnalystTargetsEndpoint:
    def test_analyst_targets_returns_expected_keys(self):
        targets = {
            "current": 226.5, "low": 200.0, "mean": 255.0,
            "median": 250.0, "high": 310.0,
        }
        recs_df = pd.DataFrame([
            {"period": "0m", "strongBuy": 12, "buy": 20, "hold": 8, "sell": 2, "strongSell": 1},
        ])
        info = {"numberOfAnalystOpinions": 43}
        with patch.object(market.yf, "Ticker",
                          MagicMock(return_value=_mock_ticker(targets, recs_df, info))):
            resp = client.get("/analyst-targets/AAPL")
        assert resp.status_code == 200
        body = resp.json()
        for key in (
            "symbol", "currentPrice", "targetLow", "targetMean", "targetMedian",
            "targetHigh", "numberOfAnalysts",
            "strongBuy", "buy", "hold", "sell", "strongSell",
        ):
            assert key in body
        assert body["symbol"] == "AAPL"
        assert body["currentPrice"] == 226.5
        assert body["targetLow"] == 200.0
        assert body["targetMean"] == 255.0
        assert body["targetHigh"] == 310.0
        # numberOfAnalysts is absent from analyst_price_targets → filled from .info
        assert body["numberOfAnalysts"] == 43
        assert body["strongBuy"] == 12
        assert body["hold"] == 8
        assert body["strongSell"] == 1

    def test_analyst_targets_handles_empty_data(self):
        # yfinance hands back nothing: no targets, no recommendations, empty info.
        # The endpoint degrades to a 200 with null targets + zero rating counts
        # (graceful fallback — the frontend renders its empty state).
        with patch.object(market.yf, "Ticker",
                          MagicMock(return_value=_mock_ticker(None, None, {}))):
            resp = client.get("/analyst-targets/ZZZZ")
        assert resp.status_code == 200
        body = resp.json()
        assert body["symbol"] == "ZZZZ"
        assert body["targetMean"] is None
        assert body["targetLow"] is None
        assert body["numberOfAnalysts"] is None
        assert body["strongBuy"] == 0
        assert body["hold"] == 0

    def test_analyst_targets_returns_502_on_fetch_error(self):
        # A hard yfinance failure surfaces as a 502, never a 500 / traceback.
        with patch.object(market.yf, "Ticker",
                          MagicMock(side_effect=RuntimeError("network down"))):
            resp = client.get("/analyst-targets/AAPL")
        assert resp.status_code == 502

    def test_analyst_targets_sanitizes_non_finite(self):
        # yfinance can return NaN/inf — these must become null (Starlette serializes
        # with allow_nan=False, so an unsanitized NaN would 500 the response).
        targets = {
            "current": float("nan"), "low": float("inf"), "mean": 255.0,
            "median": 250.0, "high": float("-inf"),
        }
        with patch.object(market.yf, "Ticker",
                          MagicMock(return_value=_mock_ticker(targets, None, {}))):
            resp = client.get("/analyst-targets/AAPL")
        assert resp.status_code == 200
        body = resp.json()
        assert body["currentPrice"] is None
        assert body["targetLow"] is None
        assert body["targetHigh"] is None
        assert body["targetMean"] == 255.0

    def test_analyst_targets_rejects_bad_symbol(self):
        resp = client.get("/analyst-targets/!!bad!!")
        assert resp.status_code == 422
