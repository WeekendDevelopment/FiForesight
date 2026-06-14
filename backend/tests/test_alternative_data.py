"""
Tests for the Alternative Data sources (Feature 15):
  - FREDService          (macro snapshot CSV parsing)
  - InsiderService       (SEC EDGAR Form 4 mapping)
  - ShortInterestService (FINRA short-volume parsing + days-to-cover)
  - GET /macro/snapshot  (response shape)
  - GET /insider/{symbol} (symbol validation)

All HTTP/yfinance calls are mocked — no network required.
"""
import asyncio
import importlib as _il
from typing import Any, Coroutine
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from backend.services import (
    FREDService, InsiderService, ShortInterestService, _parse_fred_csv,
)


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


def _async_client(get_mock: AsyncMock) -> MagicMock:
    """Build a mock httpx.AsyncClient whose .get is `get_mock`."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = get_mock
    return mock_client


# ---------------------------------------------------------------------------
# FREDService
# ---------------------------------------------------------------------------

def _fred_csv(values: list) -> str:
    """Build a fredgraph.csv body with one row per value."""
    lines = ["observation_date,SERIES"]
    for i, v in enumerate(values, 1):
        lines.append(f"2026-05-{i:02d},{v}")
    return "\n".join(lines)


class TestParseFredCsv:
    def test_value_and_delta_inputs(self):
        # 31 points 4.00 .. 4.30 — last value 4.30, first 4.00
        vals = [round(4.0 + i * 0.01, 2) for i in range(31)]
        rows = _parse_fred_csv(_fred_csv(vals))
        assert len(rows) == 31
        assert rows[-1][1] == 4.30
        assert rows[0][1] == 4.00

    def test_skips_missing_dot_markers(self):
        body = "observation_date,SERIES\n2026-05-01,.\n2026-05-02,4.25\n"
        rows = _parse_fred_csv(body)
        assert rows == [("2026-05-02", 4.25)]

    def test_caps_to_last_31(self):
        vals = list(range(40))
        rows = _parse_fred_csv(_fred_csv(vals))
        assert len(rows) == 31
        assert rows[-1][1] == 39.0

    def test_empty_on_garbage(self):
        assert _parse_fred_csv("") == []
        assert _parse_fred_csv("header_only") == []


class TestFREDService:
    def setup_method(self):
        self.svc = FREDService()

    def test_snapshot_value_and_delta(self):
        # First=4.00, last=4.50 → delta +0.50; t10y2y negative would invert, so
        # use a positive curve here and assert delta math.
        vals = [round(4.0 + i * (0.5 / 30), 4) for i in range(31)]
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.text = _fred_csv(vals)
        with patch("backend.services.httpx.AsyncClient",
                   return_value=_async_client(AsyncMock(return_value=resp))), \
             patch("backend.services.Config") as cfg:
            cfg.FRED_API_KEY = ""
            snap = run(self.svc.get_macro_snapshot())
        assert "dgs10" in snap
        assert snap["dgs10"]["value"] == 4.5
        assert snap["dgs10"]["delta_30d"] == 0.5
        assert snap["inverted"] is False
        assert len(snap["t10y2y_trend"]) == 31
        assert "fetched_at" in snap

    def test_inverted_flag_when_curve_negative(self):
        vals = [-0.42] * 31
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.text = _fred_csv(vals)
        with patch("backend.services.httpx.AsyncClient",
                   return_value=_async_client(AsyncMock(return_value=resp))), \
             patch("backend.services.Config") as cfg:
            cfg.FRED_API_KEY = ""
            snap = run(self.svc.get_macro_snapshot())
        assert snap["inverted"] is True
        assert snap["t10y2y"]["value"] == -0.42

    def test_returns_empty_on_http_error(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock(side_effect=Exception("500"))
        with patch("backend.services.httpx.AsyncClient",
                   return_value=_async_client(AsyncMock(return_value=resp))), \
             patch("backend.services.Config") as cfg:
            cfg.FRED_API_KEY = ""
            snap = run(self.svc.get_macro_snapshot())
        assert snap == {}


# ---------------------------------------------------------------------------
# InsiderService
# ---------------------------------------------------------------------------

class TestInsiderService:
    def setup_method(self):
        self.svc = InsiderService()

    def _hit(self, **src: Any) -> dict:
        base = {
            "display_names": ["Apple Inc. (CIK 0000320193)", "John Smith (CIK 0001234567)"],
            "file_date": "2026-05-01",
            "ciks": ["0001234567"],
            "transaction_code": "P",
            "shares": 5000,
            "price": 132.0,
        }
        base.update(src)
        return {"_id": "0001234567-26-000001:wf-form4.xml", "_source": base}

    def test_maps_filing(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"hits": {"hits": [self._hit()]}}
        with patch("backend.services.httpx.AsyncClient",
                   return_value=_async_client(AsyncMock(return_value=resp))):
            result = run(self.svc.get_insider_transactions("AAPL"))
        assert len(result) == 1
        f = result[0]
        assert f["filer"] == "John Smith"
        assert f["type"] == "Purchase"
        assert f["shares"] == 5000
        assert f["price"] == 132.0
        assert f["date"] == "2026-05-01"
        assert f["sec_link"].startswith("https://www.sec.gov/")

    def test_type_code_mapping(self):
        assert self.svc._map_type("P") == "Purchase"
        assert self.svc._map_type("S") == "Sale"
        assert self.svc._map_type("A") == "Award"
        assert self.svc._map_type("Purchase") == "Purchase"
        assert self.svc._map_type("") == "Filing"
        assert self.svc._map_type(None) == "Filing"

    def test_caps_to_10_filings(self):
        hits = [self._hit() for _ in range(15)]
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"hits": {"hits": hits}}
        with patch("backend.services.httpx.AsyncClient",
                   return_value=_async_client(AsyncMock(return_value=resp))):
            result = run(self.svc.get_insider_transactions("AAPL"))
        assert len(result) == 10

    def test_returns_empty_on_parse_failure(self):
        with patch("backend.services.httpx.AsyncClient",
                   return_value=_async_client(AsyncMock(side_effect=Exception("network")))):
            result = run(self.svc.get_insider_transactions("AAPL"))
        assert result == []

    def test_empty_hits_returns_empty(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"hits": {"hits": []}}
        with patch("backend.services.httpx.AsyncClient",
                   return_value=_async_client(AsyncMock(return_value=resp))):
            result = run(self.svc.get_insider_transactions("CRYPTO"))
        assert result == []


# ---------------------------------------------------------------------------
# ShortInterestService
# ---------------------------------------------------------------------------

_FINRA_SAMPLE = (
    "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
    "20260605|AAPL|1000000|5000|2000000|Q\n"
    "20260605|MSFT|500000|1000|2500000|Q\n"
)


class TestShortInterestService:
    def setup_method(self):
        self.svc = ShortInterestService()

    def test_parse_finra(self):
        parsed = self.svc._parse_finra(_FINRA_SAMPLE, "20260605")
        assert parsed["report_date"] == "2026-06-05"
        assert parsed["symbols"]["AAPL"]["short_volume"] == 1000000.0
        assert parsed["symbols"]["AAPL"]["total_volume"] == 2000000.0
        assert "MSFT" in parsed["symbols"]

    def test_days_to_cover_formula(self):
        parsed = self.svc._parse_finra(_FINRA_SAMPLE, "20260605")
        with patch.object(self.svc, "_load_map", AsyncMock(return_value=parsed)), \
             patch.object(self.svc, "_avg_daily_volume", MagicMock(return_value=200000.0)):
            result = run(self.svc.get_short_interest("AAPL"))
        # days_to_cover = short_volume / avg_daily_volume = 1_000_000 / 200_000 = 5.0
        assert result["days_to_cover"] == 5.0
        assert result["short_ratio"] == 0.5  # 1_000_000 / 2_000_000
        assert result["short_volume"] == 1000000
        assert result["report_date"] == "2026-06-05"

    def test_none_for_missing_symbol(self):
        parsed = self.svc._parse_finra(_FINRA_SAMPLE, "20260605")
        with patch.object(self.svc, "_load_map", AsyncMock(return_value=parsed)):
            result = run(self.svc.get_short_interest("NONEXIST"))
        assert result is None

    def test_days_to_cover_none_when_no_volume(self):
        parsed = self.svc._parse_finra(_FINRA_SAMPLE, "20260605")
        with patch.object(self.svc, "_load_map", AsyncMock(return_value=parsed)), \
             patch.object(self.svc, "_avg_daily_volume", MagicMock(return_value=None)):
            result = run(self.svc.get_short_interest("AAPL"))
        assert result["days_to_cover"] is None


# ---------------------------------------------------------------------------
# Endpoints — /macro/snapshot shape + /insider/{symbol} validation
# ---------------------------------------------------------------------------

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


class TestMacroEndpoint:
    def test_snapshot_shape(self):
        sample = {
            "dgs10": {"value": 4.35, "delta_30d": -0.12},
            "t10y2y": {"value": -0.42, "delta_30d": 0.05},
            "inverted": True,
            "t10y2y_trend": [{"date": "2026-05-01", "value": -0.42}],
            "fetched_at": "2026-06-14T00:00:00+00:00",
        }
        with patch.object(market.fred_svc, "get_macro_snapshot",
                          AsyncMock(return_value=sample)):
            resp = client.get("/macro/snapshot")
        assert resp.status_code == 200
        body = resp.json()
        assert body["inverted"] is True
        assert body["dgs10"]["value"] == 4.35
        assert "t10y2y_trend" in body

    def test_empty_when_unavailable(self):
        with patch.object(market.fred_svc, "get_macro_snapshot",
                          AsyncMock(return_value={})):
            resp = client.get("/macro/snapshot")
        assert resp.status_code == 200
        assert resp.json() == {}


class TestInsiderEndpoint:
    def test_valid_symbol(self):
        with patch.object(market.insider_svc, "get_insider_transactions",
                          AsyncMock(return_value=[])):
            resp = client.get("/insider/AAPL")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_rejects_bad_symbol(self):
        resp = client.get("/insider/!!bad!!")
        assert resp.status_code == 422

    def test_rejects_overlong_symbol(self):
        resp = client.get("/insider/ABCDEFGHIJKLMNOPQRST")
        assert resp.status_code == 422
