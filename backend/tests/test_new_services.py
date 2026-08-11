"""
Tests for FinnhubService, StockTwitsService, and the _dedup_news helper.
All HTTP calls are mocked — no network required.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.routers.predict import _dedup_news
from backend.services import FinnhubService, StockTwitsService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(coro):
    # asyncio.run creates and manages a fresh loop per call. The old
    # get_event_loop().run_until_complete pattern raises "no current event loop"
    # on Python 3.12+/3.14 when no loop is set on the main thread.
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# FinnhubService
# ---------------------------------------------------------------------------


class TestFinnhubService:
    def setup_method(self):
        self.svc = FinnhubService()

    def test_returns_empty_when_no_key(self):
        with patch("backend.services.Config") as mock_cfg:
            mock_cfg.FINNHUB_API_KEY = ""
            result = run(self.svc.fetch_company_news("AAPL"))
        assert result == []

    def test_parses_articles(self):
        payload = [
            {
                "headline": "Apple hits $4T market cap",
                "source": "Reuters",
                "url": "https://example.com",
                "image": "",
                "datetime": 1234567890,
            },
            {
                "headline": "iPhone sales miss estimates",
                "source": "Bloomberg",
                "url": "",
                "image": "",
                "datetime": 1234567891,
            },
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = payload

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch("backend.services.Config") as mock_cfg,
            patch("backend.services.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_cfg.FINNHUB_API_KEY = "test-key"
            result = run(self.svc.fetch_company_news("AAPL"))

        assert len(result) == 2
        assert result[0]["title"] == "Apple hits $4T market cap"
        assert result[0]["source"] == "Reuters"
        assert result[0]["source_label"] == "Finnhub"
        assert result[1]["title"] == "iPhone sales miss estimates"

    def test_skips_empty_headlines(self):
        payload = [
            {"headline": "", "source": "Noise"},
            {"headline": "  ", "source": "Noise2"},
            {"headline": "Real news", "source": "AP"},
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = payload

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch("backend.services.Config") as mock_cfg,
            patch("backend.services.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_cfg.FINNHUB_API_KEY = "test-key"
            result = run(self.svc.fetch_company_news("AAPL"))

        assert len(result) == 1
        assert result[0]["title"] == "Real news"

    def test_returns_empty_on_http_error(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))

        with (
            patch("backend.services.Config") as mock_cfg,
            patch("backend.services.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_cfg.FINNHUB_API_KEY = "test-key"
            result = run(self.svc.fetch_company_news("AAPL"))

        assert result == []


# ---------------------------------------------------------------------------
# StockTwitsService
# ---------------------------------------------------------------------------


class TestStockTwitsService:
    def setup_method(self):
        self.svc = StockTwitsService()

    def _make_messages(self, sentiments: list) -> list:
        """Build mock StockTwits message list from list of 'Bullish'/'Bearish'/None."""
        msgs = []
        for s in sentiments:
            if s is None:
                msgs.append({"entities": {}})
            else:
                msgs.append({"entities": {"sentiment": {"basic": s}}})
        return msgs

    def _mock_response(self, messages: list):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"messages": messages}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        return mock_client

    def test_counts_bullish_bearish(self):
        msgs = self._make_messages(["Bullish", "Bullish", "Bearish", None, "Bullish"])
        with patch("backend.services.httpx.AsyncClient", return_value=self._mock_response(msgs)):
            result = run(self.svc.fetch_sentiment("AAPL"))
        assert result["bullish"] == 3
        assert result["bearish"] == 1
        assert result["sentiment"] == pytest.approx(0.5, abs=0.01)  # (3-1)/4

    def test_all_bullish_gives_plus_one(self):
        msgs = self._make_messages(["Bullish", "Bullish", "Bullish"])
        with patch("backend.services.httpx.AsyncClient", return_value=self._mock_response(msgs)):
            result = run(self.svc.fetch_sentiment("TSLA"))
        assert result["bullish"] == 3
        assert result["bearish"] == 0
        assert result["sentiment"] == pytest.approx(1.0)

    def test_all_bearish_gives_minus_one(self):
        msgs = self._make_messages(["Bearish", "Bearish"])
        with patch("backend.services.httpx.AsyncClient", return_value=self._mock_response(msgs)):
            result = run(self.svc.fetch_sentiment("NVDA"))
        assert result["bullish"] == 0
        assert result["bearish"] == 2
        assert result["sentiment"] == pytest.approx(-1.0)

    def test_no_tagged_messages_gives_zero(self):
        msgs = self._make_messages([None, None, None])
        with patch("backend.services.httpx.AsyncClient", return_value=self._mock_response(msgs)):
            result = run(self.svc.fetch_sentiment("GOOG"))
        assert result["bullish"] == 0
        assert result["bearish"] == 0
        assert result["sentiment"] == 0.0

    def test_returns_empty_on_error(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("network error"))
        with patch("backend.services.httpx.AsyncClient", return_value=mock_client):
            result = run(self.svc.fetch_sentiment("AAPL"))
        assert result == {"bullish": 0, "bearish": 0, "sentiment": 0.0}

    def test_strips_exchange_suffix_from_symbol(self):
        """Ensure AAPL:NASDAQ → AAPL in the URL."""
        msgs = self._make_messages(["Bullish"])
        mock_client = self._mock_response(msgs)
        with patch("backend.services.httpx.AsyncClient", return_value=mock_client):
            run(self.svc.fetch_sentiment("AAPL:NASDAQ"))
        call_url = mock_client.get.call_args[0][0]
        assert "AAPL" in call_url
        assert "NASDAQ" not in call_url


# ---------------------------------------------------------------------------
# _dedup_news helper (imported from predict router at module top)
# ---------------------------------------------------------------------------


class TestDedupNews:
    def test_removes_exact_duplicates(self):
        items = [
            {"title": "Apple soars", "source": "A"},
            {"title": "Apple soars", "source": "B"},
            {"title": "Market update", "source": "C"},
        ]
        result = _dedup_news(items)
        assert len(result) == 2
        assert result[0]["source"] == "A"  # first occurrence kept

    def test_case_insensitive_dedup(self):
        items = [
            {"title": "APPLE SOARS", "source": "A"},
            {"title": "apple soars", "source": "B"},
        ]
        result = _dedup_news(items)
        assert len(result) == 1
        assert result[0]["source"] == "A"

    def test_preserves_order(self):
        items = [
            {"title": "First", "source": "A"},
            {"title": "Second", "source": "B"},
            {"title": "Third", "source": "C"},
        ]
        result = _dedup_news(items)
        assert [r["title"] for r in result] == ["First", "Second", "Third"]

    def test_skips_items_with_empty_title(self):
        items = [
            {"title": "", "source": "A"},
            {"title": "Real news", "source": "B"},
        ]
        result = _dedup_news(items)
        assert len(result) == 1
        assert result[0]["title"] == "Real news"

    def test_empty_input_returns_empty(self):
        assert _dedup_news([]) == []
