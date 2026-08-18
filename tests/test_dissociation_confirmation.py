import pytest

from scripts.analyze_dissociation_confirmation import (
    binary_rate_summary,
    stratified_gap_bootstrap,
    wilson_interval,
)


def test_wilson_precision_for_frozen_sample_size() -> None:
    assert wilson_interval(0, 60)[1] == pytest.approx(0.06017185214208986)
    assert wilson_interval(60, 60)[0] == pytest.approx(0.93982814785791)


def test_binary_rate_summary_uses_trajectory_denominator() -> None:
    summary = binary_rate_summary([True, False, True, False])
    assert summary["successes"] == 2
    assert summary["total"] == 4
    assert summary["rate"] == 0.5


def test_stratified_gap_bootstrap_preserves_condition_cells() -> None:
    rows = [
        {"condition": "gradual_pressure", "alarm": True, "drifted": False},
        {"condition": "gradual_pressure", "alarm": True, "drifted": False},
        {"condition": "abrupt_pressure", "alarm": True, "drifted": False},
        {"condition": "abrupt_pressure", "alarm": True, "drifted": False},
    ]
    result = stratified_gap_bootstrap(rows, samples=20, seed=7)
    assert result["point"] == 1.0
    assert result["95ci"] == [1.0, 1.0]
