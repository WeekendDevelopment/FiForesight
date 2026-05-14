import pytest
from backend.services import SentimentService


@pytest.fixture
def svc():
    return SentimentService()


def test_score_headlines_empty(svc):
    result = svc.score_headlines([])
    assert result["compound"] == 0.0
    assert result["label"] == "Neutral"
    assert result["headline_count"] == 0


def test_score_headlines_positive(svc):
    headlines = ["Stocks surge to record highs on strong earnings beat"]
    result = svc.score_headlines(headlines)
    assert result["compound"] > 0
    assert result["label"] in {"Bullish", "Neutral", "Bearish"}
    assert result["headline_count"] == 1


def test_score_headlines_negative(svc):
    headlines = ["Market crashes amid panic selling and recession fears"]
    result = svc.score_headlines(headlines)
    assert result["compound"] < 0.5  # not strongly positive
    assert result["label"] in {"Bearish", "Neutral"}


def test_score_headlines_multiple(svc):
    headlines = [
        "Tech giant reports record profits",
        "Inflation hits 40-year high, Fed raises rates",
        "New product launch excites investors",
    ]
    result = svc.score_headlines(headlines)
    assert isinstance(result["compound"], float)
    assert -1.0 <= result["compound"] <= 1.0
    assert result["headline_count"] == 3


def test_score_headlines_returns_scores_list(svc):
    headlines = ["Strong buy signal as earnings beat expectations"]
    result = svc.score_headlines(headlines)
    assert isinstance(result["scores"], list)
    assert len(result["scores"]) == 1
    assert "compound" in result["scores"][0]
    assert "text" in result["scores"][0]


def test_score_headlines_label_thresholds(svc):
    """Verify label assignment: >= 0.05 Bullish, <= -0.05 Bearish, else Neutral."""
    # A clearly bullish headline
    bullish = svc.score_headlines(["Excellent outstanding amazing profit boom surge rally"])
    assert bullish["label"] == "Bullish"

    # A clearly bearish headline
    bearish = svc.score_headlines(["Terrible loss crash collapse bankruptcy failure disaster"])
    assert bearish["label"] == "Bearish"
