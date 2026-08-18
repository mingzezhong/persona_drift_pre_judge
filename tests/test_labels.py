import pytest

from persona_drift.labels import future_drift_labels, sustained_drift_onset


def test_sustained_onset_ignores_one_checkpoint_excursion() -> None:
    turns = [0, 5, 10, 15, 20]
    scores = [0.9, 0.4, 0.8, 0.3, 0.2]
    assert sustained_drift_onset(turns, scores, threshold=0.5) == 15


def test_future_labels_exclude_current_and_post_drift_checkpoints() -> None:
    turns = [0, 5, 10, 15, 20]
    assert future_drift_labels(turns, 15, horizon_turns=5) == [0, 0, 1, None, None]


def test_no_onset_produces_only_negative_labels() -> None:
    assert future_drift_labels([0, 5, 10], None, horizon_turns=5) == [0, 0, 0]


def test_turns_must_be_strictly_increasing() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        sustained_drift_onset([0, 5, 5], [1.0, 0.5, 0.2], threshold=0.6)

