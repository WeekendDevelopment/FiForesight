"""
Unit tests for _skill_to_weights — ensemble weighting helper.
Pure logic, no I/O, no mocks needed.
"""
from backend.models import _skill_to_weights


def test_proportional_to_skill() -> None:
    """Weights are proportional to skill when all models beat naive."""
    # naive=4.0 → skills: [1-2/4, 1-3/4, 1-1/4] = [0.5, 0.25, 0.75]
    w = _skill_to_weights([2.0, 3.0, 1.0], naive_mae=4.0)
    assert abs(sum(w) - 1.0) < 1e-9
    assert w[2] > w[0] > w[1]   # rf > prophet > sarima


def test_below_naive_zeroed() -> None:
    """A model worse than naive persistence receives weight 0."""
    # naive=3.0 → skills: [1-1/3≈0.667, max(0,1-5/3)=0, 1-2/3≈0.333]
    w = _skill_to_weights([1.0, 5.0, 2.0], naive_mae=3.0)
    assert w[1] == 0.0
    assert w[0] > 0.0 and w[2] > 0.0
    assert abs(sum(w) - 1.0) < 1e-9


def test_all_below_naive_equal_fallback() -> None:
    """When all models are ≤ naive, equal weights are returned."""
    w = _skill_to_weights([5.0, 6.0, 7.0], naive_mae=1.0)
    assert w == [1 / 3, 1 / 3, 1 / 3]


def test_no_naive_mae_inv_mae_fallback() -> None:
    """Without a naive baseline, fall back to inverse-MAE weighting."""
    w = _skill_to_weights([2.0, 4.0, 1.0], naive_mae=None)
    # inv-MAE: rf (1.0) gets highest weight, sarima (4.0) lowest
    assert w[2] > w[0] > w[1]
    assert abs(sum(w) - 1.0) < 1e-9


def test_zero_naive_mae_inv_mae_fallback() -> None:
    """naive_mae=0 is treated the same as None (no division by zero)."""
    w = _skill_to_weights([2.0, 3.0, 1.0], naive_mae=0.0)
    assert abs(sum(w) - 1.0) < 1e-9
    assert w[2] > w[0] > w[1]


def test_weights_always_sum_to_one() -> None:
    """Invariant: weights sum to 1.0 for all inputs."""
    cases = [
        ([1.0, 2.0, 3.0], 2.5),
        ([0.5, 0.5, 0.5], 1.0),
        ([999.0, 999.0, 999.0], None),
        ([1.0, 1.0, 1.0], 0.0),
    ]
    for maes, naive in cases:
        w = _skill_to_weights(maes, naive_mae=naive)
        assert abs(sum(w) - 1.0) < 1e-9, f"Failed for maes={maes} naive={naive}"


def test_equal_skill_equal_weights() -> None:
    """Models with identical skill scores get equal weights."""
    w = _skill_to_weights([1.0, 1.0, 1.0], naive_mae=2.0)
    assert abs(w[0] - 1 / 3) < 1e-9
    assert abs(w[1] - 1 / 3) < 1e-9
    assert abs(w[2] - 1 / 3) < 1e-9
