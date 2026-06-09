"""
Security hardening tests — auth enforcement, input validation, rate limiting.
Uses a fresh FastAPI app (no dependency overrides) to verify actual security behaviour.
"""
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import importlib as _il

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.routers import predict, trade, market
# Use bare module path to match the identity used by router imports.
_deps = _il.import_module("dependencies")
limiter = _deps.limiter


# ---------------------------------------------------------------------------
# App WITHOUT dependency overrides — auth is enforced for real
# ---------------------------------------------------------------------------

def _make_rate_handler(app):
    async def _handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse({"detail": "rate limited"}, status_code=429,
                            headers={"Retry-After": "60"})
    return _handler


_sec_app = FastAPI()
_sec_app.state.limiter = limiter
_sec_app.add_exception_handler(RateLimitExceeded, _make_rate_handler(_sec_app))
_sec_app.include_router(predict.router)
_sec_app.include_router(trade.router)
_sec_app.include_router(market.router)

_sec_client = TestClient(_sec_app, raise_server_exceptions=False)


def _trade_payload(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "symbol":          "AAPL",
        "current_price":   150.0,
        "high_range":      165.0,
        "low_range":       135.0,
        "rsi":             35.0,
        "support":         [148.0, 144.0],
        "resistance":      [155.0, 162.0],
        "trend":           "Bullish",
        "sentiment_label": "Bullish",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------

def test_trade_setup_requires_auth() -> None:
    """POST /trade-setup without a Bearer token must return 401."""
    resp = _sec_client.post("/trade-setup", json=_trade_payload())
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


def test_jury_reanalyze_requires_auth() -> None:
    """POST /jury/reanalyze without a Bearer token must return 401."""
    resp = _sec_client.post("/jury/reanalyze", json={"symbol": "AAPL"})
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# Symbol validation
# ---------------------------------------------------------------------------

def test_predict_rejects_invalid_symbol() -> None:
    """POST /predict with a shell-injection-style symbol must return 422."""
    resp = _sec_client.post("/predict", json={"data": "; DROP TABLE stocks--"})
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_predict_rejects_symbol_too_long() -> None:
    """Symbol longer than 15 chars should be rejected."""
    resp = _sec_client.post("/predict", json={"data": "AVERYLONGSYMBOL99"})
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_predict_accepts_valid_symbols() -> None:
    """Common valid symbol formats must pass validation (even if fetch fails)."""
    # We don't expect 422 — any other error (500, 404) means validation passed.
    valid_symbols = ["AAPL", "BRK.B", "BTC-USD", "AAPL:NASDAQ"]
    for sym in valid_symbols:
        with patch("backend.routers.predict._predict_inner", new=AsyncMock(side_effect=Exception("mocked"))):
            resp = _sec_client.post("/predict", json={"data": sym})
        assert resp.status_code != 422, f"Symbol {sym!r} was incorrectly rejected with 422"


def test_dcf_rejects_invalid_symbol() -> None:
    resp = _sec_client.get("/dcf/; DROP TABLE--")
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


def test_options_rejects_invalid_symbol() -> None:
    # Use a symbol with invalid characters but no `/` so the path still matches
    resp = _sec_client.get("/options/INVALID_SYMBOL!")
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Chat input validation
# ---------------------------------------------------------------------------

def test_chat_rejects_oversized_message() -> None:
    """POST /chat with message > 500 chars must return 422."""
    resp = _sec_client.post("/chat", json={
        "message": "x" * 501,
        "context": {},
        "history": [],
    })
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_chat_accepts_500_char_message() -> None:
    """Exactly 500 chars should be accepted (boundary condition).

    Mock the outbound Groq stream so the test stays fully offline and we only
    verify Pydantic validation, not network reachability.
    """
    with patch("httpx.AsyncClient.stream") as mock_stream:
        # Return a minimal context manager that yields no chunks
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock(__aiter__=lambda s: iter([])))
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_stream.return_value = mock_cm

        resp = _sec_client.post("/chat", json={
            "message": "x" * 500,
            "context": {"symbol": "AAPL"},
            "history": [],
        })
    # Not 422 means validation passed
    assert resp.status_code != 422, "500-char message was incorrectly rejected"


# ---------------------------------------------------------------------------
# Rate limiting infrastructure
# ---------------------------------------------------------------------------

def test_rate_limit_returns_429_and_retry_after() -> None:
    """The rate limit infrastructure must return 429 + Retry-After."""
    # Use a dedicated minimal app with a very tight limit so we can hit it easily.
    _rl_limiter = Limiter(key_func=get_remote_address)
    _rl_app = FastAPI()
    _rl_app.state.limiter = _rl_limiter

    async def _rl_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        retry = getattr(exc, "retry_after", None)
        headers = {"Retry-After": str(int(retry))} if retry else {"Retry-After": "60"}
        return JSONResponse({"detail": "Too many requests — please slow down."},
                            status_code=429, headers=headers)

    _rl_app.add_exception_handler(RateLimitExceeded, _rl_handler)

    @_rl_app.get("/test-rl")
    @_rl_limiter.limit("1/minute")
    async def _limited_route(request: Request):
        return {"ok": True}

    with TestClient(_rl_app) as c:
        r1 = c.get("/test-rl")
        assert r1.status_code == 200, f"First request should succeed, got {r1.status_code}"
        r2 = c.get("/test-rl")
        assert r2.status_code == 429, f"Second request should be rate-limited, got {r2.status_code}"
        assert "Retry-After" in r2.headers, "429 response must include Retry-After header"
        assert r2.json()["detail"] == "Too many requests — please slow down."
