import pytest

from scripts.analyze_gate_a import resolve_consistency_threshold


def test_fixed_threshold_ignores_new_confirmation_scores() -> None:
    rows = [
        {
            "split": "confirmation",
            "condition": "neutral",
            "consistency_score": 0.0,
        },
        {
            "split": "confirmation",
            "condition": "gradual_pressure",
            "consistency_score": 4.0,
        },
    ]
    analysis = {
        "fixed_threshold": 3.5,
        "fixed_threshold_source": (
            "outputs/gate_a/pilot_v1/analysis/summary.json"
        ),
        "fixed_threshold_source_sha256": "a" * 64,
    }
    threshold, metadata = resolve_consistency_threshold(rows, analysis)
    assert threshold == 3.5
    assert metadata["source"] == "fixed_external_preregistered"
    assert metadata["calibration_observations"] == 0


def test_fixed_threshold_requires_auditable_source() -> None:
    with pytest.raises(ValueError):
        resolve_consistency_threshold([], {"fixed_threshold": 3.5})


def test_legacy_threshold_metadata_remains_unchanged() -> None:
    rows = [
        {
            "split": "calibration",
            "condition": "neutral",
            "consistency_score": 3.5,
        },
        {
            "split": "calibration",
            "condition": "topic_shift",
            "consistency_score": 3.5,
        },
    ]
    analysis = {
        "calibration_split": "calibration",
        "clean_calibration_conditions": ["neutral", "topic_shift"],
        "threshold_quantile": 0.10,
        "rubric_alignment_floor": 3.0,
    }
    threshold, metadata = resolve_consistency_threshold(rows, analysis)
    assert threshold == 3.5
    assert metadata == {
        "value": 3.5,
        "calibration_split": "calibration",
        "clean_conditions": ["neutral", "topic_shift"],
        "quantile": 0.10,
        "rubric_floor": 3.0,
        "calibration_observations": 2,
    }
