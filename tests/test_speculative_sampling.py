import pytest

from scripts.check_speculative_sampling import check, corrected_distribution


def test_rejection_restores_target_when_draft_has_disjoint_support():
    assert corrected_distribution([1.0, 0.0], [0.0, 1.0]) == [1.0, 0.0]


def test_equal_distributions_do_not_divide_by_zero():
    assert corrected_distribution([0.5, 0.5], [0.5, 0.5]) == [0.5, 0.5]


def test_correction_preserves_distribution_in_all_smoke_cases():
    result = check()
    assert result["decision"] == "mechanism_check_passed"
    assert len(result["cases"]) >= 20
    assert result["gpu_speedup_measured"] is False


@pytest.mark.parametrize("target,draft", [([], []), ([1], [0.5, 0.5]),
    ([0.4, 0.4], [0.5, 0.5]), ([float("nan"), 0], [1, 0]), ([-1, 2], [1, 0])])
def test_invalid_distributions_rejected(target, draft):
    with pytest.raises(ValueError):
        corrected_distribution(target, draft)
