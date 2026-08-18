import numpy as np
import pytest

from persona_drift.measurement import (
    anchored_posterior,
    balanced_accuracy,
    estimate_confusion_matrix,
    group_drift_rates,
    posterior_summary,
    sustained_posterior_drift_onset,
    validation_metrics,
)


def test_confusion_matrix_is_smoothed_and_row_normalized() -> None:
    matrix = estimate_confusion_matrix(
        [0, 0, 1, 1, 2, 2, 3, 3, 4, 4],
        [0, 1, 1, 1, 2, 3, 3, 4, 4, 4],
        alpha=0.5,
    )
    assert matrix.shape == (5, 5)
    assert np.all(matrix > 0)
    assert np.allclose(matrix.sum(axis=1), 1.0)


def test_anchored_posterior_recovers_agreeing_high_scores() -> None:
    matrix = estimate_confusion_matrix(
        list(range(5)) * 5, list(range(5)) * 5, alpha=0.5
    )
    posterior = anchored_posterior([4, 4, 4], [matrix, matrix, matrix])
    summary = posterior_summary(posterior, stable_min_score=3)
    assert summary["posterior_mode"] == 4
    assert summary["stable_probability"] > 0.9


def test_posterior_rejects_unaligned_or_invalid_inputs() -> None:
    matrix = np.full((5, 5), 0.2)
    with pytest.raises(ValueError, match="every rating"):
        anchored_posterior([4], [matrix, matrix])
    with pytest.raises(ValueError, match="positive"):
        anchored_posterior([4], [np.eye(5)])


def test_sustained_posterior_onset_uses_first_low_checkpoint() -> None:
    assert sustained_posterior_drift_onset(
        [0, 5, 10, 15],
        [0.95, 0.42, 0.39, 0.88],
        threshold=0.5,
        sustain_checkpoints=2,
    ) == 5
    assert sustained_posterior_drift_onset(
        [0, 5, 10], [0.95, 0.42, 0.88], threshold=0.5, sustain_checkpoints=2
    ) is None


def test_validation_metrics_and_group_rates() -> None:
    posteriors = np.eye(5)[[0, 1, 3, 4]]
    report = validation_metrics(
        [0, 1, 3, 4],
        posteriors,
        stable_min_score=3,
        stable_probability_threshold=0.5,
    )
    assert report["exact_accuracy"] == 1.0
    assert report["stable_balanced_accuracy"] == 1.0
    assert balanced_accuracy([False, True], [False, True]) == 1.0
    grouped = group_drift_rates(
        [
            {"axis": "a", "condition": "pressure", "drifted": True},
            {"axis": "a", "condition": "control", "drifted": False},
        ],
        axes=["a"],
        pressure_conditions=["pressure"],
        control_conditions=["control"],
    )
    assert grouped["a"]["risk_difference"] == 1.0
