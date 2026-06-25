"""
Router tests — trade setup, DCF valuation, options chain.
All external calls are mocked; no network required.
"""
from typing import Any, Dict, List, Tuple
from unittest.mock import patch, AsyncMock, MagicMock
import importlib as _il
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

# Build a lightweight test app that includes only the routers under test.
# This avoids the Redis lifespan in main.py while still exercising the real
# router logic (validation, calculations, response models).
from backend.routers import trade, market
# Import from the bare module path so the object identity matches what the
# routers use (they do `from dependencies import ...`, not `from backend.dependencies`).
# Dependency overrides use object identity as the key, so paths must match.
_deps = _il.import_module("dependencies")
require_user = _deps.require_user
limiter = _deps.limiter

_test_app = FastAPI()
# Register the limiter (same instance as used by router decorators) so
# slowapi can find it on request.app.state.
_test_app.state.limiter = limiter


async def _test_rate_limit_handler(req, exc: RateLimitExceeded) -> JSONResponse:
    """Mirror the production 429 payload and Retry-After header."""
    retry_after = getattr(exc, "retry_after", None)
    headers = {"Retry-After": str(int(retry_after)) if retry_after else "60"}
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests — please slow down."},
        headers=headers,
    )


_test_app.add_exception_handler(RateLimitExceeded, _test_rate_limit_handler)
_test_app.include_router(trade.router)
_test_app.include_router(market.router)

# Bypass auth so existing trade-setup tests keep passing without real JWTs.
# Security tests in test_security.py use a fresh app without this override.
_test_app.dependency_overrides[require_user] = lambda: "test-user-uuid"

client = TestClient(_test_app)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset the shared in-memory limiter before each test.

    The suite fires many /trade-setup + /market calls in well under a minute;
    without this they accumulate against the per-IP limit and later tests get a
    spurious 429. (Dedicated rate-limit behaviour is covered in test_security.py.)
    """
    try:
        limiter.reset()
    except Exception:
        pass
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _mock_jury() -> MagicMock:
    mock = MagicMock()
    mock._call_groq = AsyncMock(return_value="Strong entry on oversold reversal.")
    return mock


# ---------------------------------------------------------------------------
# Trade-setup tests
# ---------------------------------------------------------------------------

def test_trade_setup_bullish_oversold() -> None:
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=_trade_payload(rsi=32.0, trend="Bullish"))
    assert resp.status_code == 200
    d = resp.json()
    assert d["setup_type"] == "Oversold Reversal"
    assert d["direction"] == "Long"
    assert d["entry_low"] < d["entry_high"]
    assert d["stop_loss"] < d["entry_low"]
    assert d["target_1"] < d["target_2"] < d["target_3"]


def test_trade_setup_bullish_momentum() -> None:
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=_trade_payload(rsi=68.0, trend="Bullish"))
    assert resp.status_code == 200
    assert resp.json()["setup_type"] == "Momentum Continuation"


def test_trade_setup_bullish_support_bounce() -> None:
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=_trade_payload(rsi=50.0, trend="Bullish"))
    assert resp.status_code == 200
    assert resp.json()["setup_type"] == "Support Bounce"


def test_trade_setup_bearish_overbought() -> None:
    payload = _trade_payload(rsi=75.0, trend="Bearish", high_range=180.0, low_range=135.0)
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    d = resp.json()
    assert d["setup_type"] == "Overbought Fade"
    assert d["direction"] == "Short"
    # Bearish: stop is above entry, targets descend
    assert d["stop_loss"] > d["entry_high"]
    assert d["target_1"] > d["target_2"]


def test_trade_setup_bearish_breakdown() -> None:
    payload = _trade_payload(rsi=32.0, trend="Bearish", high_range=180.0, low_range=135.0)
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    assert resp.json()["setup_type"] == "Breakdown Play"


def test_trade_setup_position_sizing() -> None:
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=_trade_payload())
    assert resp.status_code == 200
    d = resp.json()
    assert d["risk_per_share"] > 0
    assert 0 < d["risk_pct"] < 100
    assert 0 < d["suggested_position_pct"] <= 500   # capped at 5× = 500%


def test_trade_setup_risk_reward_format() -> None:
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=_trade_payload())
    assert resp.status_code == 200
    rr = resp.json()["risk_reward"]
    assert rr.startswith("1:")
    assert float(rr.split(":")[1]) > 0


def test_trade_setup_groq_failure_uses_fallback_rationale() -> None:
    mock = MagicMock()
    mock._call_groq = AsyncMock(side_effect=Exception("Groq down"))
    with patch("backend.routers.trade.analyst_jury_svc", mock):
        resp = client.post("/trade-setup", json=_trade_payload())
    assert resp.status_code == 200
    assert len(resp.json()["rationale"]) > 0


def test_trade_setup_atr_stop_widens_with_volatility() -> None:
    """A larger ATR should place the long stop further from entry (volatility-adaptive)."""
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        low_vol = client.post(
            "/trade-setup",
            json=_trade_payload(rsi=50.0, trend="Bullish", atr_14=0.5),
        ).json()
        high_vol = client.post(
            "/trade-setup",
            json=_trade_payload(rsi=50.0, trend="Bullish", atr_14=4.0),
        ).json()
    assert low_vol["atr_14"] == 0.5 and low_vol["atr_multiplier"] == 2.0
    assert high_vol["atr_14"] == 4.0
    entry_low_lv  = (low_vol["entry_low"] + low_vol["entry_high"]) / 2 - low_vol["stop_loss"]
    entry_low_hv  = (high_vol["entry_low"] + high_vol["entry_high"]) / 2 - high_vol["stop_loss"]
    # Higher ATR → wider stop distance.
    assert entry_low_hv > entry_low_lv


def test_trade_setup_atr_stop_8pct_hard_cap() -> None:
    """An enormous ATR must still keep the stop within 8% of entry."""
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        d = client.post(
            "/trade-setup",
            json=_trade_payload(rsi=50.0, trend="Bullish", current_price=150.0, atr_14=50.0),
        ).json()
    entry_mid = (d["entry_low"] + d["entry_high"]) / 2
    # Stop is below entry but capped at 8% away.
    assert d["stop_loss"] < entry_mid
    assert d["stop_loss"] >= entry_mid * 0.92 - 0.01


def test_trade_setup_conservative_uses_2_5_multiplier() -> None:
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        d = client.post(
            "/trade-setup",
            json=_trade_payload(rsi=50.0, trend="Bullish", atr_14=1.0, conservative=True),
        ).json()
    assert d["atr_multiplier"] == 2.5


def test_trade_setup_no_atr_falls_back() -> None:
    """Without ATR, the response carries null ATR fields (legacy % stop path)."""
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        d = client.post("/trade-setup", json=_trade_payload(rsi=50.0, trend="Bullish")).json()
    assert d["atr_14"] is None
    assert d["atr_multiplier"] is None


def test_trade_setup_negative_atr_rejected() -> None:
    """A negative atr_14 must be rejected by the validator (422)."""
    resp = client.post(
        "/trade-setup",
        json=_trade_payload(rsi=50.0, trend="Bullish", atr_14=-1.0),
    )
    assert resp.status_code == 422


def test_trade_setup_invalid_symbol_rejected() -> None:
    """A symbol outside the allowlist must be rejected (422)."""
    resp = client.post("/trade-setup", json=_trade_payload(symbol="AAPL; DROP TABLE"))
    assert resp.status_code == 422


def test_trade_setup_invalid_price() -> None:
    resp = client.post("/trade-setup", json=_trade_payload(current_price=-5.0))
    assert resp.status_code == 422


def test_trade_setup_invalid_rsi() -> None:
    resp = client.post("/trade-setup", json=_trade_payload(rsi=110.0))
    assert resp.status_code == 422


def test_trade_setup_high_below_low() -> None:
    resp = client.post("/trade-setup", json=_trade_payload(high_range=130.0, low_range=140.0))
    assert resp.status_code == 422


# ── Coherence gate: forecast-aware, honesty-gated setups ──────────────────────

def test_trade_setup_conflict_short_vs_rising_forecast() -> None:
    """The GOOGL case: a bearish trend would build a short, but the 5-day forecast
    projects HIGHER — the setup must be flagged non-actionable, not a fake short."""
    payload = _trade_payload(
        rsi=35.0, trend="Bearish", current_price=150.0,
        high_range=160.0, low_range=140.0,
        forecast_close=156.0,   # +4% over 5 days → forecast up, contradicts short
    )
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    d = resp.json()
    assert d["actionable"] is False
    assert d["direction"] == "Neutral"
    assert d["setup_type"] == "Conflicting Signals"
    assert d["conflict_note"]
    assert d["suggested_position_pct"] == 0.0


def test_trade_setup_conflict_long_vs_falling_forecast() -> None:
    payload = _trade_payload(
        rsi=55.0, trend="Bullish", current_price=150.0,
        high_range=160.0, low_range=140.0,
        forecast_close=144.0,   # −4% → forecast down, contradicts long
    )
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    d = resp.json()
    assert d["actionable"] is False
    assert d["direction"] == "Neutral"
    assert d["setup_type"] == "Conflicting Signals"


def test_trade_setup_aligned_forecast_is_actionable() -> None:
    """Bullish trend + rising forecast agree → a real, actionable long."""
    payload = _trade_payload(
        rsi=55.0, trend="Bullish", current_price=150.0,
        high_range=165.0, low_range=140.0,
        forecast_close=158.0,   # +5% → forecast up, agrees with long
    )
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    d = resp.json()
    assert d["actionable"] is True
    assert d["direction"] == "Long"
    assert d["suggested_position_pct"] > 0


def test_trade_setup_neutral_trend_no_clean_setup() -> None:
    """A mixed (Neutral) trend yields an honest 'No Clean Setup', not a forced long."""
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=_trade_payload(rsi=50.0, trend="Neutral"))
    assert resp.status_code == 200
    d = resp.json()
    assert d["actionable"] is False
    assert d["direction"] == "Neutral"
    assert d["setup_type"] == "No Clean Setup"
    assert d["suggested_position_pct"] == 0.0


def test_trade_setup_unfavorable_rr_flagged() -> None:
    """A setup whose reward is smaller than its risk is flagged, not presented as an edge."""
    payload = _trade_payload(
        rsi=50.0, trend="Bearish", current_price=150.0,
        high_range=152.0, low_range=149.0,   # tiny downside reward
        atr_14=10.0,                         # huge ATR → wide stop = large risk
    )
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    d = resp.json()
    assert d["actionable"] is False
    assert d["setup_type"] == "Unfavorable R:R"
    assert d["suggested_position_pct"] == 0.0


def test_trade_setup_no_forecast_is_backward_compatible() -> None:
    """Without forecast_close, behaviour is unchanged (no spurious conflict)."""
    payload = _trade_payload(rsi=32.0, trend="Bearish", high_range=180.0, low_range=135.0)
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    d = resp.json()
    assert d["direction"] == "Short"
    assert d["setup_type"] == "Breakdown Play"
    assert d["actionable"] is True


# ── Swing entry trigger: daily candle confirmation ────────────────────────────

def test_trade_setup_entry_confirmed_by_matching_candle() -> None:
    """An actionable long with a bullish candle already printed → confirmed trigger."""
    payload = _trade_payload(
        rsi=55.0, trend="Bullish", current_price=150.0,
        high_range=165.0, low_range=140.0, forecast_close=158.0,
        candle_pattern="Bullish Engulfing", candle_pattern_dir="bullish",
    )
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    d = resp.json()
    assert d["actionable"] is True
    assert d["confirmation"] == "confirmed"
    assert "Bullish Engulfing" in d["entry_trigger"]


def test_trade_setup_entry_pending_without_candle() -> None:
    """Actionable long, no candle → pending trigger ('wait for ...')."""
    payload = _trade_payload(
        rsi=55.0, trend="Bullish", current_price=150.0,
        high_range=165.0, low_range=140.0, forecast_close=158.0,
    )
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    d = resp.json()
    assert d["confirmation"] == "pending"
    assert "Wait for" in d["entry_trigger"]


def test_trade_setup_entry_pending_when_candle_dir_mismatches() -> None:
    """A bearish candle does not confirm a long → still pending."""
    payload = _trade_payload(
        rsi=55.0, trend="Bullish", current_price=150.0,
        high_range=165.0, low_range=140.0, forecast_close=158.0,
        candle_pattern="Shooting Star", candle_pattern_dir="bearish",
    )
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    assert resp.json()["confirmation"] == "pending"


def test_trade_setup_no_trigger_when_not_actionable() -> None:
    """A conflicted (non-actionable) setup carries no entry trigger."""
    payload = _trade_payload(
        rsi=35.0, trend="Bearish", current_price=150.0,
        high_range=160.0, low_range=140.0, forecast_close=156.0,
        candle_pattern="Bullish Engulfing", candle_pattern_dir="bullish",
    )
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    d = resp.json()
    assert d["actionable"] is False
    assert d["confirmation"] is None
    assert d["entry_trigger"] is None


def test_trade_setup_invalid_candle_dir_rejected() -> None:
    resp = client.post("/trade-setup", json=_trade_payload(candle_pattern_dir="sideways"))
    assert resp.status_code == 422


# ── CFD-ready framing ─────────────────────────────────────────────────────────

def test_trade_setup_cfd_framing_on_actionable_long() -> None:
    payload = _trade_payload(
        rsi=55.0, trend="Bullish", current_price=150.0,
        high_range=165.0, low_range=140.0, forecast_close=158.0,
    )
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    d = resp.json()
    assert d["cfd_side"] == "Buy"
    assert d["cfd_margin_pct"] == 20.0          # 5:1 leverage → 20% margin
    assert "CFD" in d["cfd_note"] and "financing" in d["cfd_note"]


def test_trade_setup_cfd_side_sell_on_short() -> None:
    payload = _trade_payload(
        rsi=32.0, trend="Bearish", current_price=150.0,
        high_range=180.0, low_range=135.0,   # aligned short (no forecast_close)
    )
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    assert resp.json()["cfd_side"] == "Sell"


def test_trade_setup_no_cfd_framing_when_not_actionable() -> None:
    payload = _trade_payload(rsi=50.0, trend="Neutral")
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    d = resp.json()
    assert d["cfd_side"] is None
    assert d["cfd_note"] is None


# ---------------------------------------------------------------------------
# DCF tests
# ---------------------------------------------------------------------------

def _mock_dcf_deps(
    fcf: float = 50_000_000_000,
    beta: float = 1.2,
    revenue_growth: float = 0.08,
    current_price: float = 150.0,
    shares: int = 15_000_000_000,
) -> Tuple[MagicMock, MagicMock]:
    mock_yf_svc = MagicMock()
    mock_yf_svc.fetch_info.return_value = {
        "free_cash_flow":  fcf,
        "beta":            beta,
        "revenue_growth":  revenue_growth,
        "current_price":   current_price,
    }
    mock_ticker_inst         = MagicMock()
    mock_ticker_inst.info    = {"sharesOutstanding": shares}
    mock_yf_ticker           = MagicMock(return_value=mock_ticker_inst)
    return mock_yf_svc, mock_yf_ticker


def test_dcf_returns_three_scenarios() -> None:
    yf_svc, yf_ticker = _mock_dcf_deps()
    with patch("backend.routers.market.yf_svc", yf_svc), \
         patch("backend.routers.market.yf.Ticker", yf_ticker):
        resp = client.get("/dcf/AAPL")
    assert resp.status_code == 200
    d = resp.json()
    for key in ("bear", "base", "bull", "current_price", "symbol"):
        assert key in d, f"missing key: {key}"


def test_dcf_bull_higher_than_bear() -> None:
    yf_svc, yf_ticker = _mock_dcf_deps()
    with patch("backend.routers.market.yf_svc", yf_svc), \
         patch("backend.routers.market.yf.Ticker", yf_ticker):
        resp = client.get("/dcf/AAPL")
    d = resp.json()
    assert d["bear"]["intrinsic_value"] < d["base"]["intrinsic_value"] < d["bull"]["intrinsic_value"]


def test_dcf_wacc_base_positive() -> None:
    yf_svc, yf_ticker = _mock_dcf_deps(beta=1.5)
    with patch("backend.routers.market.yf_svc", yf_svc), \
         patch("backend.routers.market.yf.Ticker", yf_ticker):
        resp = client.get("/dcf/AAPL")
    assert resp.json()["wacc_base"] > 0


def test_dcf_missing_fcf_returns_422() -> None:
    yf_svc_mock = MagicMock()
    yf_svc_mock.fetch_info.return_value = {
        "free_cash_flow": None,
        "beta": 1.0,
        "revenue_growth": 0.05,
        "current_price": 100.0,
    }
    ticker_inst = MagicMock()
    ticker_inst.info = {"sharesOutstanding": 1_000_000_000}
    with patch("backend.routers.market.yf_svc", yf_svc_mock), \
         patch("backend.routers.market.yf.Ticker", MagicMock(return_value=ticker_inst)):
        resp = client.get("/dcf/AAPL")
    assert resp.status_code == 422


def test_dcf_negative_fcf_returns_422() -> None:
    yf_svc_mock = MagicMock()
    yf_svc_mock.fetch_info.return_value = {
        "free_cash_flow": -1_000_000,
        "beta": 1.0,
        "revenue_growth": 0.05,
        "current_price": 100.0,
    }
    ticker_inst = MagicMock()
    ticker_inst.info = {"sharesOutstanding": 1_000_000_000}
    with patch("backend.routers.market.yf_svc", yf_svc_mock), \
         patch("backend.routers.market.yf.Ticker", MagicMock(return_value=ticker_inst)):
        resp = client.get("/dcf/AAPL")
    assert resp.status_code == 422


def test_dcf_symbol_uppercased() -> None:
    yf_svc, yf_ticker = _mock_dcf_deps()
    with patch("backend.routers.market.yf_svc", yf_svc), \
         patch("backend.routers.market.yf.Ticker", yf_ticker):
        resp = client.get("/dcf/aapl")
    assert resp.json()["symbol"] == "AAPL"


# ---------------------------------------------------------------------------
# Options chain tests
# ---------------------------------------------------------------------------

def _make_options_df(strikes: List[int], price: float, is_call: bool) -> Any:
    import pandas as pd
    rows = []
    for strike in strikes:
        rows.append({
            "strike":            strike,
            "lastPrice":         1.5,
            "bid":               1.4,
            "ask":               1.6,
            "change":            0.05,
            "percentChange":     3.4,
            "volume":            500,
            "openInterest":      1200,
            "impliedVolatility": 0.28,
            "inTheMoney":        strike < price if is_call else strike > price,
        })
    return pd.DataFrame(rows)


def _mock_options_ticker(
    price: float = 150.0,
    expirations: List[str] | None = None,
) -> MagicMock:
    strikes  = [130, 140, 145, 150, 155, 160, 170]
    calls_df = _make_options_df(strikes, price, is_call=True)
    puts_df  = _make_options_df(strikes, price, is_call=False)

    chain       = MagicMock()
    chain.calls = calls_df
    chain.puts  = puts_df

    ticker              = MagicMock()
    ticker.options      = expirations or ["2026-06-20", "2026-07-18"]
    ticker.option_chain.return_value = chain
    ticker.info         = {"currentPrice": price}
    return MagicMock(return_value=ticker)


def test_options_chain_basic() -> None:
    with patch("backend.routers.market.yf.Ticker", _mock_options_ticker()):
        resp = client.get("/options/AAPL")
    assert resp.status_code == 200
    d = resp.json()
    assert d["symbol"] == "AAPL"
    assert "calls" in d and "puts" in d
    assert len(d["calls"]) > 0 and len(d["puts"]) > 0


def test_options_chain_filters_far_strikes() -> None:
    """Strikes beyond ±25% of current price should be excluded."""
    with patch("backend.routers.market.yf.Ticker", _mock_options_ticker(price=150.0)):
        resp = client.get("/options/AAPL")
    d = resp.json()
    price = d["current_price"]
    for option in d["calls"] + d["puts"]:
        assert abs(option["strike"] - price) / price <= 0.25


def test_options_chain_no_expirations_returns_404() -> None:
    ticker        = MagicMock()
    ticker.options = []
    ticker.info    = {"currentPrice": 150.0}
    with patch("backend.routers.market.yf.Ticker", MagicMock(return_value=ticker)):
        resp = client.get("/options/AAPL")
    assert resp.status_code == 404


def test_options_chain_itm_field_present() -> None:
    with patch("backend.routers.market.yf.Ticker", _mock_options_ticker()):
        resp = client.get("/options/AAPL")
    call = resp.json()["calls"][0]
    assert "in_the_money" in call
    assert isinstance(call["in_the_money"], bool)


def test_options_chain_expiry_list_capped() -> None:
    """12 expirations in the mock; the router caps the response to 8."""
    many_expirations = [f"2026-{m:02d}-20" for m in range(1, 13)]
    with patch("backend.routers.market.yf.Ticker", _mock_options_ticker(expirations=many_expirations)):
        resp = client.get("/options/AAPL")
    assert len(resp.json()["expirations"]) == 8


def test_options_chain_includes_greeks() -> None:
    """Each contract carries Black-Scholes delta + theta."""
    with patch("backend.routers.market.yf.Ticker", _mock_options_ticker()):
        resp = client.get("/options/AAPL")
    call = resp.json()["calls"][0]
    put  = resp.json()["puts"][0]
    assert "delta" in call and "theta" in call
    # Call delta in [0, 1]; put delta in [-1, 0].
    assert 0.0 <= call["delta"] <= 1.0
    assert -1.0 <= put["delta"] <= 0.0


def test_options_chain_includes_stats() -> None:
    """Response carries aggregate stats (put/call ratio, ATM IV, skew)."""
    with patch("backend.routers.market.yf.Ticker", _mock_options_ticker()):
        resp = client.get("/options/AAPL")
    stats = resp.json()["stats"]
    for key in ("put_call_ratio", "iv_avg_calls", "iv_avg_puts", "iv_skew"):
        assert key in stats
    assert stats["put_call_ratio"] >= 0


def test_options_chain_handles_nan_iv() -> None:
    """A NaN impliedVolatility must not produce non-finite (invalid-JSON) Greeks."""
    import math as _math

    strikes = [145, 150, 155]
    calls_df = _make_options_df(strikes, 150.0, is_call=True)
    puts_df  = _make_options_df(strikes, 150.0, is_call=False)
    calls_df.loc[:, "impliedVolatility"] = _math.nan  # poison the IV column

    chain = MagicMock()
    chain.calls = calls_df
    chain.puts  = puts_df
    ticker = MagicMock()
    ticker.options = ["2026-06-20"]
    ticker.option_chain.return_value = chain
    ticker.info = {"currentPrice": 150.0}

    with patch("backend.routers.market.yf.Ticker", MagicMock(return_value=ticker)):
        resp = client.get("/options/AAPL")
    assert resp.status_code == 200
    for c in resp.json()["calls"]:
        assert _math.isfinite(c["delta"]) and _math.isfinite(c["theta"])
        assert _math.isfinite(c["implied_vol"])
        assert c["delta"] == 0.0 and c["theta"] == 0.0  # guarded → neutral


def test_options_chain_expiry_param_selects_expiry() -> None:
    """A valid ?expiry= picks that expiry; an unknown one falls back to nearest."""
    exps = ["2026-06-20", "2026-07-18"]
    with patch("backend.routers.market.yf.Ticker", _mock_options_ticker(expirations=exps)):
        chosen = client.get("/options/AAPL?expiry=2026-07-18")
    assert chosen.json()["expiry"] == "2026-07-18"

    with patch("backend.routers.market.yf.Ticker", _mock_options_ticker(expirations=exps)):
        fallback = client.get("/options/AAPL?expiry=1999-01-01")
    assert fallback.json()["expiry"] == "2026-06-20"  # nearest default


# ---------------------------------------------------------------------------
# Earnings calendar tests
# ---------------------------------------------------------------------------

def _mock_earnings_ticker(date_str: str = "2026-06-20", market_cap: float = 3e12) -> MagicMock:
    fast_info = MagicMock()
    fast_info.display_name = "Mock Corp"
    fast_info.market_cap   = market_cap

    ticker = MagicMock()
    ticker.calendar  = {"Earnings Date": [date_str]}
    ticker.fast_info = fast_info
    return MagicMock(return_value=ticker)


def test_earnings_calendar_groups_and_caps() -> None:
    with patch("backend.routers.market.yf.Ticker", _mock_earnings_ticker()):
        resp = client.get("/earnings/calendar")
    assert resp.status_code == 200
    payload = resp.json()
    assert "calendar" in payload and "generated_at" in payload
    cal = payload["calendar"]
    assert "2026-06-20" in cal
    # All watchlist tickers share one date → capped to 8 per day.
    assert len(cal["2026-06-20"]) <= 8
    entry = cal["2026-06-20"][0]
    for key in ("symbol", "name", "market_cap", "date"):
        assert key in entry


def test_earnings_calendar_skips_missing_dates() -> None:
    ticker = MagicMock()
    ticker.calendar = None
    with patch("backend.routers.market.yf.Ticker", MagicMock(return_value=ticker)):
        resp = client.get("/earnings/calendar")
    assert resp.status_code == 200
    assert resp.json()["calendar"] == {}


# ---------------------------------------------------------------------------
# IPO calendar tests
# ---------------------------------------------------------------------------

def _mock_httpx_client(json_payload: Any) -> MagicMock:
    """Build a drop-in for ``httpx.AsyncClient`` usable as an async context
    manager, whose ``.get()`` resolves to a response carrying ``json_payload``."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_payload)

    http = MagicMock()
    http.get = AsyncMock(return_value=resp)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=http)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


# A minimal Nasdaq IPO-calendar payload (one upcoming + one priced row).
_NASDAQ_SAMPLE = {
    "data": {
        "upcoming": {"upcomingTable": {"rows": [
            {
                "dealID": "1", "proposedTickerSymbol": "SPCX",
                "companyName": "Space Exploration Technologies Corp",
                "proposedExchange": "NASDAQ", "proposedSharePrice": "135.00",
                "sharesOffered": "555,555,555", "expectedPriceDate": "6/12/2026",
                "dollarValueOfSharesOffered": "$86,249,999,880",
            },
        ]}},
        "priced": {"rows": [
            {
                "dealID": "2", "proposedTickerSymbol": "ACME",
                "companyName": "Acme Inc", "proposedExchange": "NYSE",
                "proposedSharePrice": "15.00-17.00", "sharesOffered": "3,000,000",
                "pricedDate": "5/20/2026", "dollarValueOfSharesOffered": "$48,000,000",
            },
        ]},
        "filed": None,
        "withdrawn": None,
    }
}


def test_ipo_calendar_nasdaq_free_source() -> None:
    # The free Nasdaq calendar is the primary source (no API key). The same
    # payload is returned for every month query; rows de-dupe by deal id.
    with patch("backend.routers.market.httpx.AsyncClient", _mock_httpx_client(_NASDAQ_SAMPLE)):
        resp = client.get("/ipo/calendar")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["source"] == "nasdaq"
    assert len(payload["upcoming"]) == 1
    assert len(payload["recent"]) == 1

    up = payload["upcoming"][0]
    assert up["symbol"] == "SPCX" and up["status"] == "upcoming"
    assert up["date"] == "2026-06-12"              # "6/12/2026" -> ISO
    assert up["price_low"] == 135.0 and up["price_high"] == 135.0
    assert up["shares"] == 555_555_555             # commas stripped
    assert up["market_cap"] == 86_249_999_880      # "$..." stripped

    rec = payload["recent"][0]
    assert rec["symbol"] == "ACME" and rec["actions"] == "Priced"
    assert rec["price_low"] == 15.0 and rec["price_high"] == 17.0  # range parsed


def test_ipo_calendar_nasdaq_upcoming_wins_dedup() -> None:
    # The same deal id appears in BOTH the upcoming table and a later month's
    # priced table; it must be classified "upcoming", not duplicated into recent.
    payload = {
        "data": {
            "upcoming": {"upcomingTable": {"rows": [
                {"dealID": "DUP", "proposedTickerSymbol": "DUP", "companyName": "Dup Co",
                 "proposedExchange": "NASDAQ", "proposedSharePrice": "10.00",
                 "expectedPriceDate": "7/01/2026"},
            ]}},
            "priced": {"rows": [
                {"dealID": "DUP", "proposedTickerSymbol": "DUP", "companyName": "Dup Co",
                 "proposedExchange": "NASDAQ", "proposedSharePrice": "10.00",
                 "pricedDate": "6/01/2026"},
            ]},
        }
    }
    with patch("backend.routers.market.httpx.AsyncClient", _mock_httpx_client(payload)):
        resp = client.get("/ipo/calendar")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "nasdaq"
    assert len(body["upcoming"]) == 1 and body["upcoming"][0]["symbol"] == "DUP"
    assert len(body["recent"]) == 0          # not double-counted as recent


def test_ipo_calendar_edgar_fallback_when_nasdaq_unavailable() -> None:
    # When Nasdaq returns nothing usable, the chain degrades to the keyless
    # SEC EDGAR S-1 feed rather than failing. The mock serves this EDGAR-shaped
    # payload for every URL; Nasdaq finds no rows in it and raises, so the
    # endpoint falls through to EDGAR parsing.
    edgar_payload = {
        "hits": {
            "hits": [
                {"_source": {"display_names": ["Newco Inc."], "file_date": "2026-05-20"}},
                {"_source": {"display_names": [], "file_date": "2026-05-18"}},
            ]
        }
    }
    with patch("backend.routers.market.httpx.AsyncClient", _mock_httpx_client(edgar_payload)):
        resp = client.get("/ipo/calendar")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["source"] == "edgar"
    # EDGAR rows are all classified as recent S-1 filings.
    assert len(payload["recent"]) == 2
    assert payload["recent"][0]["actions"] == "S-1 Filed"
    assert payload["recent"][0]["company"] == "Newco Inc."
    assert payload["recent"][1]["company"] == "Unknown"
