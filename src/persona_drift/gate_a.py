"""Pure helpers for controlled Gate A persona-drift trajectories."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import re
from typing import Any, Mapping, Sequence

import numpy as np


CONDITIONS = (
    "neutral",
    "gradual_pressure",
    "abrupt_pressure",
    "topic_shift",
)


def stable_seed(*parts: object) -> int:
    """Return a stable nonnegative 31-bit seed from experiment identity fields."""

    raw = ":".join(str(part) for part in parts)
    return int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16) % (2**31)


def trajectory_id(axis: str, condition: str, topic: str, seed: int) -> str:
    raw = f"{axis}:{condition}:{topic}:{seed}"
    suffix = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"gate-a-{axis}-{condition}-{topic}-{seed}-{suffix}"


def _render(sequence: Sequence[str], fields: Mapping[str, Any]) -> list[str]:
    try:
        return [template.format(**fields) for template in sequence]
    except KeyError as exc:
        raise ValueError(f"topic is missing template field: {exc.args[0]}") from exc


def build_turn_messages(
    template: Mapping[str, Any],
    *,
    axis: str,
    condition: str,
    topic: Mapping[str, Any],
    total_turns: int,
    abrupt_onset_turn: int,
) -> list[str]:
    """Render the frozen controlled user sequence for one trajectory."""

    if condition not in CONDITIONS:
        raise ValueError(f"unknown Gate A condition: {condition}")
    common = template["turn_sequences"]["common"]
    axis_sequences = template["turn_sequences"]["axes"][axis]
    if condition == "neutral":
        messages = _render(common["neutral"], topic)
    elif condition == "topic_shift":
        messages = _render(common["topic_shift"], topic)
    elif condition == "gradual_pressure":
        messages = _render(axis_sequences["gradual_pressure"], topic)
    else:
        neutral_prefix = common["neutral"][: abrupt_onset_turn - 1]
        pressure_suffix = axis_sequences["abrupt_pressure"]
        messages = _render(neutral_prefix, topic) + _render(pressure_suffix, topic)
    if len(messages) != total_turns:
        raise ValueError(
            f"{axis}/{condition} rendered {len(messages)} turns, expected {total_turns}"
        )
    if any(not message.strip() for message in messages):
        raise ValueError(f"{axis}/{condition} contains an empty user turn")
    return messages


CHOICE_PATTERN = re.compile(
    r"^\s*(?:choice\s*[:\-]?\s*)?([ab])(?:\b|[.):\-])", re.IGNORECASE
)


def parse_forced_choice(text: str) -> str | None:
    """Parse a leading A/B decision without searching explanatory prose."""

    match = CHOICE_PATTERN.search(text)
    return match.group(1).upper() if match else None


def calibrate_consistency_threshold(
    scores: Sequence[float], *, quantile: float, rubric_floor: float
) -> float:
    """Calibrate a lower-tail threshold from clean trajectories only."""

    values = np.asarray(scores, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("clean calibration scores must be a non-empty finite vector")
    if not 0 <= quantile <= 1:
        raise ValueError("calibration quantile must be in [0, 1]")
    try:
        empirical = float(np.quantile(values, quantile, method="lower"))
    except TypeError:  # NumPy < 1.22 compatibility.
        empirical = float(np.quantile(values, quantile, interpolation="lower"))
    return max(float(rubric_floor), empirical)


def sustained_drift_onset(
    checkpoint_turns: Sequence[int],
    consistency_scores: Sequence[float],
    *,
    threshold: float,
    sustain_checkpoints: int,
) -> int | None:
    """Return the first checkpoint in the first sustained below-threshold run."""

    if len(checkpoint_turns) != len(consistency_scores) or not checkpoint_turns:
        raise ValueError("checkpoint turns and scores must be non-empty and aligned")
    if sustain_checkpoints <= 0:
        raise ValueError("sustain_checkpoints must be positive")
    if list(checkpoint_turns) != sorted(set(checkpoint_turns)):
        raise ValueError("checkpoint turns must be strictly increasing")
    run_start: int | None = None
    run_length = 0
    for turn, score in zip(checkpoint_turns, consistency_scores):
        if float(score) < threshold:
            if run_start is None:
                run_start = int(turn)
            run_length += 1
            if run_length >= sustain_checkpoints:
                return run_start
        else:
            run_start = None
            run_length = 0
    return None


def stratified_risk_difference_bootstrap(
    drift_by_cell: Mapping[tuple[str, str], Sequence[bool]],
    *,
    pressure_conditions: Sequence[str],
    control_conditions: Sequence[str],
    samples: int,
    seed: int,
) -> list[float]:
    """Bootstrap pressure-minus-control drift rate within axis/condition cells."""

    if samples <= 0:
        raise ValueError("bootstrap samples must be positive")
    if not drift_by_cell:
        raise ValueError("drift cells are empty")
    arrays: dict[tuple[str, str], np.ndarray] = {}
    for cell, values in drift_by_cell.items():
        array = np.asarray(values, dtype=float)
        if len(array) == 0:
            raise ValueError(f"empty drift cell: {cell}")
        arrays[cell] = array
    axes = sorted({axis for axis, _condition in arrays})
    required = {
        (axis, condition)
        for axis in axes
        for condition in tuple(pressure_conditions) + tuple(control_conditions)
    }
    if set(arrays) != required:
        raise ValueError("bootstrap cells do not exactly cover axes and conditions")

    rng = np.random.default_rng(seed)
    differences: list[float] = []
    for _ in range(samples):
        sampled: dict[tuple[str, str], np.ndarray] = {}
        for cell, array in arrays.items():
            sampled[cell] = array[rng.integers(0, len(array), size=len(array))]
        pressure = np.concatenate(
            [
                sampled[(axis, condition)]
                for axis in axes
                for condition in pressure_conditions
            ]
        )
        control = np.concatenate(
            [
                sampled[(axis, condition)]
                for axis in axes
                for condition in control_conditions
            ]
        )
        differences.append(float(pressure.mean() - control.mean()))
    return [
        float(np.percentile(differences, 2.5)),
        float(np.percentile(differences, 97.5)),
    ]


def group_records(
    records: Sequence[Mapping[str, Any]], key: str
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record[key])].append(record)
    return dict(grouped)
