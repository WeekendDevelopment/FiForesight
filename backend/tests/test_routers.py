"""
Router tests — trade setup, DCF valuation, options chain.
All external calls are mocked; no network required.
"""
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

def _trade_payload(**overrides):
    base = {
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


def _mock_jury():
    mock = MagicMock()
    mock._call_groq = AsyncMock(return_value="Strong entry on oversold reversal.")
    return mock


# ---------------------------------------------------------------------------
# Trade-setup tests
# ---------------------------------------------------------------------------

def test_trade_setup_bullish_oversold():
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=_trade_payload(rsi=32.0, trend="Bullish"))
    assert resp.status_code == 200
    d = resp.json()
    assert d["setup_type"] == "Oversold Reversal"
    assert d["entry_low"] < d["entry_high"]
    assert d["stop_loss"] < d["entry_low"]
    assert d["target_1"] < d["target_2"] < d["target_3"]


def test_trade_setup_bullish_momentum():
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=_trade_payload(rsi=68.0, trend="Bullish"))
    assert resp.status_code == 200
    assert resp.json()["setup_type"] == "Momentum Continuation"


def test_trade_setup_bullish_support_bounce():
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=_trade_payload(rsi=50.0, trend="Bullish"))
    assert resp.status_code == 200
    assert resp.json()["setup_type"] == "Support Bounce"


def test_trade_setup_bearish_overbought():
    payload = _trade_payload(rsi=75.0, trend="Bearish", high_range=180.0, low_range=135.0)
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    d = resp.json()
    assert d["setup_type"] == "Overbought Fade"
    # Bearish: stop is above entry, targets descend
    assert d["stop_loss"] > d["entry_high"]
    assert d["target_1"] > d["target_2"]


def test_trade_setup_bearish_breakdown():
    payload = _trade_payload(rsi=32.0, trend="Bearish", high_range=180.0, low_range=135.0)
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=payload)
    assert resp.status_code == 200
    assert resp.json()["setup_type"] == "Breakdown Play"


def test_trade_setup_position_sizing():
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=_trade_payload())
    assert resp.status_code == 200
    d = resp.json()
    assert d["risk_per_share"] > 0
    assert 0 < d["risk_pct"] < 100
    assert 0 < d["suggested_position_pct"] <= 500   # capped at 5× = 500%


def test_trade_setup_risk_reward_format():
    with patch("backend.routers.trade.analyst_jury_svc", _mock_jury()):
        resp = client.post("/trade-setup", json=_trade_payload())
    assert resp.status_code == 200
    rr = resp.json()["risk_reward"]
    assert rr.startswith("1:")
    assert float(rr.split(":")[1]) > 0


def test_trade_setup_groq_failure_uses_fallback_rationale():
    mock = MagicMock()
    mock._call_groq = AsyncMock(side_effect=Exception("Groq down"))
    with patch("backend.routers.trade.analyst_jury_svc", mock):
        resp = client.post("/trade-setup", json=_trade_payload())
    assert resp.status_code == 200
    assert len(resp.json()["rationale"]) > 0


def test_trade_setup_invalid_price():
    resp = client.post("/trade-setup", json=_trade_payload(current_price=-5.0))
    assert resp.status_code == 422


def test_trade_setup_invalid_rsi():
    resp = client.post("/trade-setup", json=_trade_payload(rsi=110.0))
    assert resp.status_code == 422


def test_trade_setup_high_below_low():
    resp = client.post("/trade-setup", json=_trade_payload(high_range=130.0, low_range=140.0))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DCF tests
# ---------------------------------------------------------------------------

def _mock_dcf_deps(fcf=50_000_000_000, beta=1.2, revenue_growth=0.08,
                   current_price=150.0, shares=15_000_000_000):
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


def test_dcf_returns_three_scenarios():
    yf_svc, yf_ticker = _mock_dcf_deps()
    with patch("backend.routers.market.yf_svc", yf_svc), \
         patch("backend.routers.market.yf.Ticker", yf_ticker):
        resp = client.get("/dcf/AAPL")
    assert resp.status_code == 200
    d = resp.json()
    for key in ("bear", "base", "bull", "current_price", "symbol"):
        assert key in d, f"missing key: {key}"


def test_dcf_bull_higher_than_bear():
    yf_svc, yf_ticker = _mock_dcf_deps()
    with patch("backend.routers.market.yf_svc", yf_svc), \
         patch("backend.routers.market.yf.Ticker", yf_ticker):
        resp = client.get("/dcf/AAPL")
    d = resp.json()
    assert d["bear"]["intrinsic_value"] < d["base"]["intrinsic_value"] < d["bull"]["intrinsic_value"]


def test_dcf_wacc_base_positive():
    yf_svc, yf_ticker = _mock_dcf_deps(beta=1.5)
    with patch("backend.routers.market.yf_svc", yf_svc), \
         patch("backend.routers.market.yf.Ticker", yf_ticker):
        resp = client.get("/dcf/AAPL")
    assert resp.json()["wacc_base"] > 0


def test_dcf_missing_fcf_returns_422():
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


def test_dcf_negative_fcf_returns_422():
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


def test_dcf_symbol_uppercased():
    yf_svc, yf_ticker = _mock_dcf_deps()
    with patch("backend.routers.market.yf_svc", yf_svc), \
         patch("backend.routers.market.yf.Ticker", yf_ticker):
        resp = client.get("/dcf/aapl")
    assert resp.json()["symbol"] == "AAPL"


# ---------------------------------------------------------------------------
# Options chain tests
# ---------------------------------------------------------------------------

def _make_options_df(strikes, price, is_call):
    import pandas as pd
    rows = []
    for strike in strikes:
        rows.append({
            "strike":           strike,
            "lastPrice":        1.5,
            "bid":              1.4,
            "ask":              1.6,
            "change":           0.05,
            "percentChange":    3.4,
            "volume":           500,
            "openInterest":     1200,
            "impliedVolatility": 0.28,
            "inTheMoney":       strike < price if is_call else strike > price,
        })
    return pd.DataFrame(rows)


def _mock_options_ticker(price=150.0):
    strikes = [130, 140, 145, 150, 155, 160, 170]
    calls_df = _make_options_df(strikes, price, is_call=True)
    puts_df  = _make_options_df(strikes, price, is_call=False)

    chain = MagicMock()
    chain.calls = calls_df
    chain.puts  = puts_df

    ticker = MagicMock()
    ticker.options = ["2026-06-20", "2026-07-18"]
    ticker.option_chain.return_value = chain
    ticker.info = {"currentPrice": price}
    return MagicMock(return_value=ticker)


def test_options_chain_basic():
    with patch("backend.routers.market.yf.Ticker", _mock_options_ticker()):
        resp = client.get("/options/AAPL")
    assert resp.status_code == 200
    d = resp.json()
    assert d["symbol"] == "AAPL"
    assert "calls" in d and "puts" in d
    assert len(d["calls"]) > 0 and len(d["puts"]) > 0


def test_options_chain_filters_far_strikes():
    """Strikes beyond ±25% of current price should be excluded."""
    with patch("backend.routers.market.yf.Ticker", _mock_options_ticker(price=150.0)):
        resp = client.get("/options/AAPL")
    d = resp.json()
    price = d["current_price"]
    for option in d["calls"] + d["puts"]:
        assert abs(option["strike"] - price) / price <= 0.25


def test_options_chain_no_expirations_returns_404():
    ticker = MagicMock()
    ticker.options = []
    ticker.info    = {"currentPrice": 150.0}
    with patch("backend.routers.market.yf.Ticker", MagicMock(return_value=ticker)):
        resp = client.get("/options/AAPL")
    assert resp.status_code == 404


def test_options_chain_itm_field_present():
    with patch("backend.routers.market.yf.Ticker", _mock_options_ticker()):
        resp = client.get("/options/AAPL")
    call = resp.json()["calls"][0]
    assert "in_the_money" in call
    assert isinstance(call["in_the_money"], bool)


def test_options_chain_expiry_list_capped():
    """expirations list should contain at most 8 entries."""
    with patch("backend.routers.market.yf.Ticker", _mock_options_ticker()):
        resp = client.get("/options/AAPL")
    assert len(resp.json()["expirations"]) <= 8
