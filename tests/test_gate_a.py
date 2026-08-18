import pytest

from persona_drift.gate_a import (
    calibrate_consistency_threshold,
    parse_forced_choice,
    stable_seed,
    stratified_risk_difference_bootstrap,
    sustained_drift_onset,
)
from scripts.analyze_gate_a import resolve_analysis_axes


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Choice: B. Run a pilot.", "B"),
        ("A: Move now.", "A"),
        ("  choice - a\nReason", "A"),
        ("The safer option is B.", None),
    ],
)
def test_parse_forced_choice_only_uses_leading_decision(
    text: str, expected: str | None
) -> None:
    assert parse_forced_choice(text) == expected


def test_stable_seed_is_deterministic_and_sensitive() -> None:
    assert stable_seed("axis", "topic", 1, 3) == stable_seed("axis", "topic", 1, 3)
    assert stable_seed("axis", "topic", 1, 3) != stable_seed("axis", "topic", 1, 4)


def test_calibration_uses_lower_quantile_and_rubric_floor() -> None:
    assert calibrate_consistency_threshold(
        [2.0, 3.0, 3.5, 4.0], quantile=0.25, rubric_floor=3.0
    ) == 3.0
    assert calibrate_consistency_threshold(
        [3.5, 4.0, 4.0, 4.0], quantile=0.25, rubric_floor=3.0
    ) == 3.5


def test_sustained_drift_requires_consecutive_checkpoints() -> None:
    assert sustained_drift_onset(
        [0, 3, 6, 9, 12],
        [4.0, 2.5, 3.5, 2.0, 2.0],
        threshold=3.0,
        sustain_checkpoints=2,
    ) == 9
    assert sustained_drift_onset(
        [0, 3, 6, 9],
        [4.0, 2.5, 3.5, 2.0],
        threshold=3.0,
        sustain_checkpoints=2,
    ) is None


def test_stratified_bootstrap_preserves_clear_risk_difference() -> None:
    cells = {
        (axis, condition): values
        for axis in ("a", "b")
        for condition, values in {
            "gradual_pressure": [True, True, True],
            "abrupt_pressure": [True, True, True],
            "neutral": [False, False, False],
            "topic_shift": [False, False, False],
        }.items()
    }
    interval = stratified_risk_difference_bootstrap(
        cells,
        pressure_conditions=["gradual_pressure", "abrupt_pressure"],
        control_conditions=["neutral", "topic_shift"],
        samples=50,
        seed=9,
    )
    assert interval == [1.0, 1.0]


def test_analysis_axes_default_to_legacy_all_axis_behavior() -> None:
    assert resolve_analysis_axes(["a", "b"], {}) == (["a", "b"], [])


def test_analysis_axes_support_prespecified_negative_control() -> None:
    analysis = {
        "positive_axes": ["cautious_risk_seeking"],
        "negative_control_axes": ["independent_sycophantic"],
    }
    assert resolve_analysis_axes(
        ["independent_sycophantic", "cautious_risk_seeking"], analysis
    ) == (["cautious_risk_seeking"], ["independent_sycophantic"])


@pytest.mark.parametrize(
    "analysis",
    [
        {"positive_axes": []},
        {"positive_axes": ["unknown"]},
        {"positive_axes": ["a"], "negative_control_axes": ["a"]},
        {"positive_axes": ["a", "a"]},
    ],
)
def test_analysis_axes_reject_invalid_scopes(
    analysis: dict[str, list[str]],
) -> None:
    with pytest.raises(ValueError):
        resolve_analysis_axes(["a", "b"], analysis)
