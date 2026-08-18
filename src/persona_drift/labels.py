"""Operational labels for sustained and future persona drift."""

from __future__ import annotations

from collections.abc import Sequence


def sustained_drift_onset(
    turns: Sequence[int],
    scores: Sequence[float],
    *,
    threshold: float,
    sustain_checkpoints: int = 2,
    lower_is_drift: bool = True,
) -> int | None:
    """Return the first turn of the first sustained threshold crossing."""

    if len(turns) != len(scores):
        raise ValueError("turns and scores must have equal length")
    if sustain_checkpoints < 1:
        raise ValueError("sustain_checkpoints must be positive")
    if any(current >= following for current, following in zip(turns, turns[1:])):
        raise ValueError("turns must be strictly increasing")

    def is_drift(score: float) -> bool:
        return score < threshold if lower_is_drift else score > threshold

    for start in range(0, len(scores) - sustain_checkpoints + 1):
        window = scores[start : start + sustain_checkpoints]
        if all(is_drift(score) for score in window):
            return turns[start]
    return None


def future_drift_labels(
    turns: Sequence[int],
    onset_turn: int | None,
    *,
    horizon_turns: int,
) -> list[int | None]:
    """Label onset in ``(turn, turn + horizon]`` and mask post-onset samples."""

    if horizon_turns < 1:
        raise ValueError("horizon_turns must be positive")

    labels: list[int | None] = []
    for turn in turns:
        if onset_turn is not None and turn >= onset_turn:
            labels.append(None)
        elif onset_turn is not None and onset_turn <= turn + horizon_turns:
            labels.append(1)
        else:
            labels.append(0)
    return labels

