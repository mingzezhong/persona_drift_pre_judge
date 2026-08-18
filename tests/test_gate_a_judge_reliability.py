import pytest

from scripts.analyze_gate_a_judge_reliability import (
    reviewer_analysis,
    score_agreement,
)


def test_score_agreement_reports_scale_offset_and_pairs() -> None:
    report = score_agreement([[3, 4], [3, 4], [4, 4], [2, 0]])
    assert report["examples"] == 4
    assert report["exact_agreement"] == pytest.approx(0.25)
    assert report["mean_absolute_difference"] == pytest.approx(1.0)
    assert report["score_pair_counts"] == {"2|0": 1, "3|4": 2, "4|4": 1}


def test_score_agreement_rejects_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        score_agreement([])
    with pytest.raises(ValueError, match="finite"):
        score_agreement([[3, float("nan")]])


def test_reviewer_analysis_uses_preregistered_fixed_threshold() -> None:
    rows = []
    for axis in ["cautious_risk_seeking", "independent_sycophantic"]:
        for condition in ["neutral", "gradual_pressure"]:
            for checkpoint, score in [(0, 4.0), (5, 3.0), (10, 3.0)]:
                rows.append(
                    {
                        "trajectory_id": f"{axis}-{condition}",
                        "axis": axis,
                        "condition": condition,
                        "split": "confirmation",
                        "checkpoint_turn": checkpoint,
                        "reviewer_a_trait_alignment": score,
                    }
                )
    config = {
        "data": {
            "axes": ["cautious_risk_seeking", "independent_sycophantic"],
            "conditions": ["neutral", "gradual_pressure"],
        },
        "analysis": {
            "confirmation_split": "confirmation",
            "pressure_conditions": ["gradual_pressure"],
            "control_conditions": ["neutral"],
            "fixed_threshold": 3.5,
            "fixed_threshold_source": "frozen.json",
            "fixed_threshold_source_sha256": "a" * 64,
            "sustain_checkpoints": 2,
        },
    }
    report = reviewer_analysis(rows, config, "reviewer_a_trait_alignment")
    assert report["threshold"] == 3.5
    assert report["threshold_metadata"]["source"] == (
        "fixed_external_preregistered"
    )
    assert report["threshold_metadata"]["calibration_observations"] == 0
