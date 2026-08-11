from unittest.mock import MagicMock, patch

import pytest

from backend.services import YFinanceService


@pytest.fixture
def svc():
    return YFinanceService()


def _mock_info(**overrides):
    defaults = {
        "currentPrice": 150.0,
        "marketCap": 2_000_000_000_000,
        "trailingPE": 28.5,
        "previousClose": 149.0,
        "fiftyTwoWeekHigh": 200.0,
        "fiftyTwoWeekLow": 100.0,
        "beta": 1.2,
        "forwardPE": 25.0,
        "pegRatio": 2.1,
        "priceToBook": 45.0,
        "enterpriseToEbitda": 22.0,
        "freeCashflow": 90_000_000_000,
        "revenueGrowth": 0.08,
        "totalDebt": 120_000_000_000,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "currency": "USD",
        "shortName": "Apple Inc.",
        "trailingAnnualDividendRate": 0.92,
    }
    defaults.update(overrides)
    return defaults


@patch("backend.services.yf.Ticker")
def test_fetch_info_returns_expected_keys(mock_ticker, svc):
    mock_ticker.return_value.info = _mock_info()
    result = svc.fetch_info("AAPL")
    for key in [
        "current_price",
        "market_cap",
        "pe_ratio",
        "beta",
        "forward_pe",
        "ev_to_ebitda",
        "free_cash_flow",
        "revenue_growth",
        "sector",
        "industry",
        "dividend_yield",
        "prev_close",
        "range_52w",
        "short_name",
        "currency",
    ]:
        assert key in result, f"Missing key: {key}"


@patch("backend.services.yf.Ticker")
def test_fetch_info_price_correct(mock_ticker, svc):
    mock_ticker.return_value.info = _mock_info(currentPrice=200.0)
    result = svc.fetch_info("AAPL")
    assert result["current_price"] == 200.0


@patch("backend.services.yf.Ticker")
def test_fetch_info_pe_ratio(mock_ticker, svc):
    mock_ticker.return_value.info = _mock_info(trailingPE=35.0)
    result = svc.fetch_info("AAPL")
    assert result["pe_ratio"] == 35.0


@patch("backend.services.yf.Ticker")
def test_fetch_info_sector(mock_ticker, svc):
    mock_ticker.return_value.info = _mock_info(sector="Healthcare")
    result = svc.fetch_info("AAPL")
    assert result["sector"] == "Healthcare"


@patch("backend.services.yf.Ticker")
def test_fetch_info_dividend_yield_computed(mock_ticker, svc):
    """dividend_yield is computed as trailingAnnualDividendRate / currentPrice."""
    mock_ticker.return_value.info = _mock_info(currentPrice=100.0, trailingAnnualDividendRate=2.0)
    result = svc.fetch_info("AAPL")
    assert isinstance(result["dividend_yield"], float)
    assert abs(result["dividend_yield"] - 0.02) < 1e-9


@patch("backend.services.yf.Ticker")
def test_fetch_info_range_52w_formatted(mock_ticker, svc):
    mock_ticker.return_value.info = _mock_info(fiftyTwoWeekLow=90.0, fiftyTwoWeekHigh=210.0)
    result = svc.fetch_info("AAPL")
    assert result["range_52w"] == "90.00 - 210.00"


@patch("backend.services.yf.Ticker")
def test_fetch_info_graceful_on_error(mock_ticker, svc):
    """fetch_info should return {} instead of raising on network/API errors."""
    mock_ticker.return_value.info = MagicMock(side_effect=Exception("Network error"))
    # Accessing .info as a property raises; patch as property instead
    type(mock_ticker.return_value).info = property(
        lambda self: (_ for _ in ()).throw(Exception("Network error"))
    )
    try:
        result = svc.fetch_info("BADSYMBOL")
        assert isinstance(result, dict)
    except Exception:
        pytest.fail("fetch_info raised instead of returning empty dict")
