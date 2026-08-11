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
from collections.abc import Coroutine
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from backend.services import (
    FREDService,
    InsiderService,
    ShortInterestService,
    _parse_fred_csv,
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
        with (
            patch(
                "backend.services.httpx.AsyncClient",
                return_value=_async_client(AsyncMock(return_value=resp)),
            ),
            patch("backend.services.Config") as cfg,
        ):
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
        with (
            patch(
                "backend.services.httpx.AsyncClient",
                return_value=_async_client(AsyncMock(return_value=resp)),
            ),
            patch("backend.services.Config") as cfg,
        ):
            cfg.FRED_API_KEY = ""
            snap = run(self.svc.get_macro_snapshot())
        assert snap["inverted"] is True
        assert snap["t10y2y"]["value"] == -0.42

    def test_returns_empty_on_http_error(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock(side_effect=Exception("500"))
        with (
            patch(
                "backend.services.httpx.AsyncClient",
                return_value=_async_client(AsyncMock(return_value=resp)),
            ),
            patch("backend.services.Config") as cfg,
        ):
            cfg.FRED_API_KEY = ""
            snap = run(self.svc.get_macro_snapshot())
        assert snap == {}


# ---------------------------------------------------------------------------
# InsiderService
# ---------------------------------------------------------------------------

# A minimal but realistic Form 4 ownership XML (issuer files for the insider).
_FORM4_XML = b"""<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>John Smith</rptOwnerName></reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>5000</value></transactionShares>
        <transactionPricePerShare><value>132.00</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


class TestInsiderService:
    def setup_method(self):
        self.svc = InsiderService()

    def _hit(self, **src: Any) -> dict:
        # Real EDGAR FTS shape: display_names = [reporting owner, issuer], with an
        # aligned ciks array; the accession prefix is the issuer's CIK (0000320193).
        base = {
            "display_names": ["John Smith (CIK 0007654321)", "Apple Inc. (CIK 0000320193)"],
            "ciks": ["0007654321", "0000320193"],
            "file_date": "2026-05-01",
        }
        base.update(src)
        return {"_id": "0000320193-26-000001:wf-form4.xml", "_source": base}

    def _routed_get(self, fts_hits: list, xml_bytes: bytes = _FORM4_XML, xml_status: int = 200):
        """AsyncMock .get that routes FTS-search vs Form 4 XML requests by URL."""
        fts = MagicMock()
        fts.raise_for_status = MagicMock()
        fts.json.return_value = {"hits": {"hits": fts_hits}}

        def _get(url, **kwargs):
            if str(url).endswith(".xml"):
                xml = MagicMock()
                xml.status_code = xml_status
                xml.content = xml_bytes
                return xml
            return fts

        return AsyncMock(side_effect=_get)

    # ── Pure XML parser ────────────────────────────────────────────────────
    def test_parse_form4_extracts_txn(self):
        out = self.svc._parse_form4(_FORM4_XML)
        assert out["owner"] == "John Smith"
        assert out["type"] == "Purchase"
        assert out["shares"] == 5000
        assert out["price"] == 132.0

    def test_parse_form4_picks_largest_txn(self):
        xml = b"""<ownershipDocument><nonDerivativeTable>
          <nonDerivativeTransaction>
            <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
            <transactionAmounts><transactionShares><value>100</value></transactionShares>
              <transactionPricePerShare><value>10</value></transactionPricePerShare></transactionAmounts>
          </nonDerivativeTransaction>
          <nonDerivativeTransaction>
            <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
            <transactionAmounts><transactionShares><value>900</value></transactionShares>
              <transactionPricePerShare><value>50</value></transactionPricePerShare></transactionAmounts>
          </nonDerivativeTransaction>
        </nonDerivativeTable></ownershipDocument>"""
        out = self.svc._parse_form4(xml)
        assert out["type"] == "Sale"
        assert out["shares"] == 900
        assert out["price"] == 50.0

    def test_parse_form4_bad_xml(self):
        out = self.svc._parse_form4(b"not xml <<<")
        assert out == {"owner": None, "type": None, "shares": None, "price": None}

    def test_owner_from_names_skips_issuer(self):
        # issuer CIK 320193 → the owner is the other entry
        owner = self.svc._owner_from_names(
            ["John Smith (CIK 0007654321)", "Apple Inc. (CIK 0000320193)"],
            ["0007654321", "0000320193"],
            "320193",
        )
        assert owner == "John Smith"

    # ── Full path with enrichment ──────────────────────────────────────────
    def test_enriches_filing_from_xml(self):
        with patch(
            "backend.services.httpx.AsyncClient",
            return_value=_async_client(self._routed_get([self._hit()])),
        ):
            result = run(self.svc.get_insider_transactions("AAPL"))
        assert len(result) == 1
        f = result[0]
        assert f["filer"] == "John Smith"
        assert f["type"] == "Purchase"
        assert f["shares"] == 5000
        assert f["price"] == 132.0
        assert f["date"] == "2026-05-01"
        assert f["sec_link"].startswith("https://www.sec.gov/")
        # private enrichment keys must not leak into the response
        assert not any(k.startswith("_") for k in f)

    def test_metadata_only_when_xml_unavailable(self):
        # XML 404 → row keeps its metadata-only fallback, still renders.
        with patch(
            "backend.services.httpx.AsyncClient",
            return_value=_async_client(self._routed_get([self._hit()], xml_status=404)),
        ):
            result = run(self.svc.get_insider_transactions("AAPL"))
        assert len(result) == 1
        f = result[0]
        assert f["filer"] == "John Smith"  # from display_names (issuer skipped)
        assert f["type"] == "Filing"
        assert f["shares"] is None
        assert f["price"] is None

    def test_type_code_mapping(self):
        assert self.svc._map_type("P") == "Purchase"
        assert self.svc._map_type("S") == "Sale"
        assert self.svc._map_type("A") == "Award"
        assert self.svc._map_type("Purchase") == "Purchase"
        assert self.svc._map_type("") == "Filing"
        assert self.svc._map_type(None) == "Filing"

    def test_caps_to_10_filings(self):
        hits = [self._hit() for _ in range(15)]
        with patch(
            "backend.services.httpx.AsyncClient", return_value=_async_client(self._routed_get(hits))
        ):
            result = run(self.svc.get_insider_transactions("AAPL"))
        assert len(result) == 10

    def test_returns_empty_on_parse_failure(self):
        with patch(
            "backend.services.httpx.AsyncClient",
            return_value=_async_client(AsyncMock(side_effect=Exception("network"))),
        ):
            result = run(self.svc.get_insider_transactions("AAPL"))
        assert result == []

    def test_empty_hits_returns_empty(self):
        with patch(
            "backend.services.httpx.AsyncClient", return_value=_async_client(self._routed_get([]))
        ):
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
        with (
            patch.object(self.svc, "_load_map", AsyncMock(return_value=parsed)),
            patch.object(self.svc, "_avg_daily_volume", MagicMock(return_value=200000.0)),
        ):
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
        with (
            patch.object(self.svc, "_load_map", AsyncMock(return_value=parsed)),
            patch.object(self.svc, "_avg_daily_volume", MagicMock(return_value=None)),
        ):
            result = run(self.svc.get_short_interest("AAPL"))
        assert result["days_to_cover"] is None


# ---------------------------------------------------------------------------
# Endpoints — /macro/snapshot shape + /insider/{symbol} validation
# ---------------------------------------------------------------------------

from backend.routers import market

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
        with patch.object(market.fred_svc, "get_macro_snapshot", AsyncMock(return_value=sample)):
            resp = client.get("/macro/snapshot")
        assert resp.status_code == 200
        body = resp.json()
        assert body["inverted"] is True
        assert body["dgs10"]["value"] == 4.35
        assert "t10y2y_trend" in body

    def test_empty_when_unavailable(self):
        with patch.object(market.fred_svc, "get_macro_snapshot", AsyncMock(return_value={})):
            resp = client.get("/macro/snapshot")
        assert resp.status_code == 200
        assert resp.json() == {}


class TestInsiderEndpoint:
    def test_valid_symbol(self):
        with patch.object(
            market.insider_svc, "get_insider_transactions", AsyncMock(return_value=[])
        ):
            resp = client.get("/insider/AAPL")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_rejects_bad_symbol(self):
        resp = client.get("/insider/!!bad!!")
        assert resp.status_code == 422

    def test_rejects_overlong_symbol(self):
        resp = client.get("/insider/ABCDEFGHIJKLMNOPQRST")
        assert resp.status_code == 422
