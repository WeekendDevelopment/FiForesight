"""
Router tests — trade setup, DCF valuation, options chain.
All external calls are mocked; no network required.
"""
import os
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Build a lightweight test app that includes only the routers under test.
# This avoids the Redis lifespan in main.py while still exercising the real
# router logic (validation, calculations, response models).
from backend.routers import trade, market

_test_app = FastAPI()
_test_app.include_router(trade.router)
_test_app.include_router(market.router)

client = TestClient(_test_app)


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


def test_trade_setup_invalid_price() -> None:
    resp = client.post("/trade-setup", json=_trade_payload(current_price=-5.0))
    assert resp.status_code == 422


def test_trade_setup_invalid_rsi() -> None:
    resp = client.post("/trade-setup", json=_trade_payload(rsi=110.0))
    assert resp.status_code == 422


def test_trade_setup_high_below_low() -> None:
    resp = client.post("/trade-setup", json=_trade_payload(high_range=130.0, low_range=140.0))
    assert resp.status_code == 422


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


def test_ipo_calendar_fmp_split_and_shapes() -> None:
    today = date.today()
    upcoming_date = (today + timedelta(days=10)).isoformat()
    recent_date = (today - timedelta(days=5)).isoformat()
    raw = [
        {
            "date": upcoming_date, "company": "Upcoming Co", "symbol": "UPCO",
            "exchange": "NASDAQ", "actions": "expected", "shares": 5_200_000,
            "marketCap": 1_200_000_000, "priceRange": "$18-$22",
        },
        {
            "date": recent_date, "company": "Recent Co", "symbol": "RECO",
            "exchange": "NYSE", "actions": "priced", "shares": 3_000_000,
            "marketCap": 800_000_000, "priceLow": 20, "priceHigh": 24,
        },
    ]
    with patch.dict(os.environ, {"FMP_API_KEY": "test-key"}), \
            patch("backend.routers.market.httpx.AsyncClient", _mock_httpx_client(raw)):
        resp = client.get("/ipo/calendar")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["source"] == "fmp"
    assert "generated_at" in payload

    # Upcoming / recent split is driven by date vs. today.
    assert len(payload["upcoming"]) == 1
    assert len(payload["recent"]) == 1

    up = payload["upcoming"][0]
    assert up["symbol"] == "UPCO" and up["status"] == "upcoming"
    assert up["price_low"] == 18 and up["price_high"] == 22  # parsed from "$18-$22"

    rec = payload["recent"][0]
    assert rec["symbol"] == "RECO" and rec["status"] == "recent"
    assert rec["price_low"] == 20 and rec["price_high"] == 24

    # Every card carries the full, stable shape the frontend renders.
    for key in (
        "symbol", "company", "exchange", "date", "price_low",
        "price_high", "shares", "market_cap", "actions", "status",
    ):
        assert key in up


def test_ipo_calendar_edgar_fallback_without_key() -> None:
    edgar_payload = {
        "hits": {
            "hits": [
                {"_source": {"display_names": ["Newco Inc."], "file_date": "2026-05-20"}},
                {"_source": {"display_names": [], "file_date": "2026-05-18"}},
            ]
        }
    }
    # Empty key (after strip) forces the EDGAR fallback branch.
    with patch.dict(os.environ, {"FMP_API_KEY": ""}), \
            patch("backend.routers.market.httpx.AsyncClient", _mock_httpx_client(edgar_payload)):
        resp = client.get("/ipo/calendar")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["source"] == "edgar"
    # EDGAR rows are all classified as recent S-1 filings.
    assert len(payload["recent"]) == 2
    assert payload["recent"][0]["actions"] == "S-1 Filed"
    assert payload["recent"][0]["company"] == "Newco Inc."
    assert payload["recent"][1]["company"] == "Unknown"
