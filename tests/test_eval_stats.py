import pytest

from verdict.evals.stats import percentile, wilson_interval


def test_wilson_interval_is_bounded_and_contains_observed_rate():
    low, high = wilson_interval(57, 60)
    assert 0 <= low < 0.95 < high <= 1
    assert low == pytest.approx(0.8629, abs=0.001)


def test_wilson_interval_handles_empty_and_perfect_slices():
    assert wilson_interval(0, 0) == (0.0, 0.0)
    low, high = wilson_interval(5, 5)
    assert low < 1
    assert high == 1


def test_wilson_interval_rejects_invalid_counts():
    with pytest.raises(ValueError):
        wilson_interval(6, 5)


def test_percentile_interpolates_sorted_values():
    values = [100, 10, 40, 20]
    assert percentile(values, 0.5) == 30
    assert percentile(values, 0.95) == 91
    assert percentile([], 0.95) is None
