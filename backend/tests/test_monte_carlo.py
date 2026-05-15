from backend.models import run_monte_carlo


def _prices(n=50, start=100.0, step=0.5):
    """Generate a simple ascending price series."""
    return [start + i * step for i in range(n)]


def test_monte_carlo_basic():
    result = run_monte_carlo(_prices(), steps=10, n_sims=100)
    assert result is not None
    assert "p10" in result
    assert "p50" in result
    assert "p90" in result
    assert "var_95" in result
    assert "prob_gain" in result


def test_monte_carlo_percentile_ordering():
    result = run_monte_carlo(_prices(), steps=10, n_sims=200)
    assert result["p10"] <= result["p50"] <= result["p90"]


def test_monte_carlo_prices_positive():
    result = run_monte_carlo(_prices(), steps=5, n_sims=100)
    assert result["p10"] > 0


def test_monte_carlo_prob_gain_range():
    result = run_monte_carlo(_prices(), steps=5, n_sims=200)
    assert 0.0 <= result["prob_gain"] <= 100.0


def test_monte_carlo_var_is_non_negative():
    result = run_monte_carlo(_prices(start=50.0), steps=5, n_sims=200)
    assert result["var_95"] >= 0


def test_monte_carlo_returns_none_for_insufficient_data():
    """Fewer than 10 prices should return None gracefully."""
    result = run_monte_carlo([100.0, 101.0, 102.0], steps=5, n_sims=100)
    assert result is None


def test_monte_carlo_paths_sample_present():
    result = run_monte_carlo(_prices(), steps=5, n_sims=100)
    assert "paths_sample" in result
    assert isinstance(result["paths_sample"], list)
    assert len(result["paths_sample"]) > 0


def test_monte_carlo_price_range_by_day_structure():
    steps = 5
    result = run_monte_carlo(_prices(), steps=steps, n_sims=100)
    assert "price_range_by_day" in result
    assert len(result["price_range_by_day"]) == steps
    for entry in result["price_range_by_day"]:
        assert "day" in entry
        assert "p10" in entry
        assert "p50" in entry
        assert "p90" in entry
        assert entry["p10"] <= entry["p50"] <= entry["p90"]


def test_monte_carlo_determinism():
    """run_monte_carlo uses a fixed seed=42 — same inputs must give identical output."""
    closes = _prices(n=60, start=200.0, step=1.0)
    r1 = run_monte_carlo(closes, steps=5, n_sims=300)
    r2 = run_monte_carlo(closes, steps=5, n_sims=300)
    assert r1["p50"] == r2["p50"]
    assert r1["p10"] == r2["p10"]
    assert r1["p90"] == r2["p90"]
