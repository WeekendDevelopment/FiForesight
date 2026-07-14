"""
Symbol search endpoint tests (F33) — GET /symbols/search.
The Yahoo search HTTP call is mocked; no network.
"""
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from backend.routers import market

_FAKE_QUOTES = [
    # NYSE ADR + LSE listing of the same name — the multi-exchange case the
    # palette surfaces (BP NYSE vs BP.L London).
    {"symbol": "BP",    "shortname": "BP p.l.c.", "quoteType": "EQUITY",
     "exchDisp": "NYSE", "exchange": "NYQ"},
    {"symbol": "BP.L",  "shortname": "BP PLC",    "quoteType": "EQUITY",
     "exchDisp": "London", "exchange": "LSE"},
    # Caret index — passes Yahoo but must be filtered (backend /predict rejects ^).
    {"symbol": "^GSPC", "shortname": "S&P 500",   "quoteType": "INDEX",
     "exchDisp": "SNP", "exchange": "SNP"},
    # Unsupported quote type.
    {"symbol": "BPOPT", "shortname": "BP Option", "quoteType": "OPTION",
     "exchDisp": "OPR", "exchange": "OPR"},
    # longname-only fallback.
    {"symbol": "BPCL.NS", "longname": "Bharat Petroleum Corporation Limited",
     "quoteType": "EQUITY", "exchDisp": "NSE", "exchange": "NSI"},
]


@pytest.fixture(autouse=True)
def _no_cache() -> Generator[None, None, None]:
    """Inert Redis so symsearch:* cache entries can't leak between tests."""
    with patch("redis_cache.get_redis", return_value=None):
        yield


def _build_app() -> TestClient:
    app = FastAPI()
    app.state.limiter = market.limiter

    async def _handler(req: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": "rate limited"})

    app.add_exception_handler(RateLimitExceeded, _handler)
    app.include_router(market.router)
    return TestClient(app)


client = _build_app()


def _mock_client(get_kwargs: dict) -> MagicMock:
    """An httpx.AsyncClient async-context-manager whose .get is configured
    with ``get_kwargs`` (return_value= or side_effect=)."""
    mock = MagicMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    mock.get = AsyncMock(**get_kwargs)
    return mock


def _response(quotes: list) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"quotes": quotes}
    return resp


def _get(q: str, get_kwargs: dict):
    with patch("backend.routers.market.httpx.AsyncClient",
               return_value=_mock_client(get_kwargs)):
        return client.get("/symbols/search", params={"q": q})


def test_maps_and_filters_quotes() -> None:
    resp = _get("BP", {"return_value": _response(_FAKE_QUOTES)})
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    symbols = [r["symbol"] for r in rows]
    assert symbols == ["BP", "BP.L", "BPCL.NS"]  # order preserved, junk dropped
    assert "^GSPC" not in symbols       # caret filtered
    assert "BPOPT" not in symbols       # OPTION type filtered
    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["BP"]["exchange"] == "NYSE"
    assert by_symbol["BP.L"]["exchange"] == "London"
    assert by_symbol["BPCL.NS"]["name"].startswith("Bharat")  # longname fallback
    for row in rows:
        assert set(row) == {"symbol", "name", "exchange", "type"}


def test_upstream_failure_returns_empty_list() -> None:
    resp = _get("BP", {"side_effect": RuntimeError("yahoo down")})
    assert resp.status_code == 200
    assert resp.json() == []


def test_empty_query_422() -> None:
    resp = _get("  ", {"return_value": _response([])})
    assert resp.status_code == 422


def test_overlong_query_422() -> None:
    resp = _get("X" * 21, {"return_value": _response([])})
    assert resp.status_code == 422
