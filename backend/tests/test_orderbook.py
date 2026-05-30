"""Tests for the Alpaca Level-2 order book endpoint (GET /orderbook/{symbol})."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

import main
from routers import market


@pytest.fixture
def client():
    # raise_server_exceptions=False so the global 500 handler is exercised
    # instead of the exception propagating into the test.
    return TestClient(main.app, raise_server_exceptions=False)


def _mock_async_client(json_payload):
    """Build a mock httpx.AsyncClient context manager returning json_payload."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = json_payload

    inner = MagicMock()
    inner.get = AsyncMock(return_value=mock_resp)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=inner)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class TestOrderBookEndpoint:
    def test_returns_503_when_key_missing(self, client):
        with patch.object(market.Config, "ALPACA_API_KEY", ""), \
             patch.object(market.Config, "ALPACA_SECRET_KEY", ""):
            resp = client.get("/orderbook/NVDA")
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]

    def test_success_shape_and_metrics(self, client):
        payload = {
            "symbol": "NVDA",
            "quote": {
                "t": "2025-05-22T14:32:11Z",
                "bp": 135.20, "bs": 5,
                "ap": 135.25, "as": 3,
            },
        }
        with patch.object(market.Config, "ALPACA_API_KEY", "key"), \
             patch.object(market.Config, "ALPACA_SECRET_KEY", "secret"), \
             patch("routers.market.httpx.AsyncClient", return_value=_mock_async_client(payload)):
            resp = client.get("/orderbook/nvda")

        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "NVDA"
        assert data["bids"] == [{"price": 135.20, "size": 5}]
        assert data["asks"] == [{"price": 135.25, "size": 3}]
        assert data["spread"] == 0.05
        assert data["mid_price"] == 135.22
        # imbalance = bid_size / (bid_size + ask_size) = 5 / 8
        assert data["bid_ask_imbalance"] == 0.625

    def test_empty_quote_returns_404(self, client):
        payload = {"symbol": "ZZZZ", "quote": {}}
        with patch.object(market.Config, "ALPACA_API_KEY", "key"), \
             patch.object(market.Config, "ALPACA_SECRET_KEY", "secret"), \
             patch("routers.market.httpx.AsyncClient", return_value=_mock_async_client(payload)):
            resp = client.get("/orderbook/ZZZZ")
        assert resp.status_code == 404


class TestBuildOrderBook:
    def test_one_sided_book_imbalance(self):
        # Only a bid present → imbalance should be 1.0, spread 0.
        result = market._build_orderbook("AAPL", {"quote": {"bp": 100.0, "bs": 10, "ap": 0, "as": 0}})
        assert result is not None
        assert result["bids"] == [{"price": 100.0, "size": 10}]
        assert result["asks"] == []
        assert result["spread"] == 0.0
        assert result["bid_ask_imbalance"] == 1.0

    def test_no_prices_returns_none(self):
        assert market._build_orderbook("AAPL", {"quote": {}}) is None
