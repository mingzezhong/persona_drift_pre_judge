import pytest

from persona_drift.gate_c_v2 import (
    fit_clean_axis_calibration,
    transform_axis_calibrated_rows,
)


def row(axis, split, condition, projection, norm, eligible=True):
    return {
        "axis": axis,
        "development_split": split,
        "condition": condition,
        "eligible_h5": eligible,
        "activation_features": {
            "projection_layer20": projection,
            "projection_delta_turn1": projection - 1.0,
            "projection_slope_last3": 0.25,
            "norm_layer20": norm,
            "turn": 2.0,
        },
    }


def test_clean_axis_calibration_excludes_pressure_and_held_out_rows() -> None:
    rows = [
        row("a", "train", "neutral", 1.0, 10.0),
        row("a", "train", "topic_shift", 3.0, 14.0),
        row("a", "train", "gradual_pressure", 999.0, 999.0),
        row("a", "validation", "neutral", 999.0, 999.0),
        row("b", "train", "neutral", -3.0, 20.0),
        row("b", "train", "topic_shift", -1.0, 24.0),
    ]
    calibration = fit_clean_axis_calibration(
        rows,
        axes=["a", "b"],
        split="train",
        clean_conditions=["neutral", "topic_shift"],
        eligibility_key="eligible_h5",
    )
    assert calibration["a"]["projection_mean"] == pytest.approx(2.0)
    assert calibration["a"]["projection_scale"] == pytest.approx(1.0)
    assert calibration["a"]["norm_mean"] == pytest.approx(12.0)
    assert calibration["b"]["projection_mean"] == pytest.approx(-2.0)


def test_transform_uses_matching_axis_and_does_not_mutate_source() -> None:
    source = [row("a", "development_test", "neutral", 3.0, 14.0)]
    calibration = {
        "a": {
            "projection_mean": 2.0,
            "projection_scale": 0.5,
            "norm_mean": 10.0,
            "norm_scale": 2.0,
        }
    }
    transformed = transform_axis_calibrated_rows(source, calibration)
    assert transformed[0]["activation_features"] == {
        "projection_clean_axis_z": 2.0,
        "projection_delta_turn1": 2.0,
        "projection_slope_last3": 0.25,
        "norm_clean_axis_z": 2.0,
        "turn": 2.0,
    }
    assert "projection_layer20" in source[0]["activation_features"]


def test_degenerate_calibration_is_rejected() -> None:
    rows = [
        row("a", "train", "neutral", 1.0, 10.0),
        row("a", "train", "topic_shift", 1.0, 10.0),
    ]
    with pytest.raises(ValueError):
        fit_clean_axis_calibration(
            rows,
            axes=["a"],
            split="train",
            clean_conditions=["neutral", "topic_shift"],
            eligibility_key="eligible_h5",
        )
