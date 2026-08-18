"""Pure helpers for prospective Gate C persona-drift forecasting."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import numpy as np


def future_drift_label(
    turn: int,
    onset: int | None,
    *,
    horizon: int,
    total_turns: int,
) -> tuple[bool, bool]:
    """Return eligibility and future-onset label for one pre-response turn."""

    if not 1 <= turn <= total_turns:
        raise ValueError("turn must lie within the trajectory")
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    if onset is not None:
        if not 1 <= onset <= total_turns:
            raise ValueError("onset must lie within the trajectory")
        eligible = turn < onset
        return eligible, bool(eligible and onset - turn <= horizon)
    eligible = turn + horizon <= total_turns
    return eligible, False


def projection_features(
    turns: Sequence[Mapping[str, Any]],
    index: int,
    *,
    reference_layer: int,
    slope_window: int = 3,
) -> dict[str, float]:
    """Build causal activation features through ``turns[index]`` only."""

    if not 0 <= index < len(turns):
        raise IndexError("turn index is out of range")
    if slope_window <= 0:
        raise ValueError("slope_window must be positive")
    current = turns[index]
    first = turns[0]
    projection = float(current["pre_response_projection_layer20"])
    array_projection = float(current["pre_response_projection"][reference_layer])
    if not np.isclose(projection, array_projection, rtol=0.0, atol=1e-6):
        raise ValueError("stored reference-layer projection is inconsistent")
    norm = float(current["pre_response_norm_layer20"])
    array_norm = float(current["pre_response_norm"][reference_layer])
    if not np.isclose(norm, array_norm, rtol=0.0, atol=1e-5):
        raise ValueError("stored reference-layer norm is inconsistent")

    start = max(0, index - slope_window + 1)
    recent = np.asarray(
        [
            float(item["pre_response_projection_layer20"])
            for item in turns[start : index + 1]
        ],
        dtype=float,
    )
    if len(recent) == 1:
        slope = 0.0
    else:
        x = np.arange(len(recent), dtype=float)
        slope = float(np.sum((x - x.mean()) * (recent - recent.mean())))
        slope /= float(np.sum((x - x.mean()) ** 2))
    values = {
        "projection_layer20": projection,
        "projection_delta_turn1": projection
        - float(first["pre_response_projection_layer20"]),
        "projection_slope_last3": slope,
        "norm_layer20": norm,
        "turn": float(current["turn"]),
    }
    if not np.isfinite(list(values.values())).all():
        raise ValueError("activation features must be finite")
    return values


def build_text_prefix(
    turns: Sequence[Mapping[str, Any]], index: int
) -> str:
    """Render the persona-free observable prefix before the current response."""

    if not 0 <= index < len(turns):
        raise IndexError("turn index is out of range")
    parts: list[str] = []
    for prior in turns[:index]:
        parts.append(f"User: {str(prior['user']).strip()}")
        parts.append(f"Assistant: {str(prior['response']).strip()}")
    parts.append(f"User: {str(turns[index]['user']).strip()}")
    prefix = "\n".join(parts)
    if not prefix.strip():
        raise ValueError("text prefix must not be empty")
    return prefix


def stratified_cluster_bootstrap_indices(
    groups: Sequence[str],
    strata: Sequence[str],
    *,
    samples: int,
    seed: int,
) -> Iterator[np.ndarray]:
    """Yield row indices after resampling whole groups within each stratum."""

    if len(groups) != len(strata) or not groups:
        raise ValueError("groups and strata must be non-empty and aligned")
    if samples <= 0:
        raise ValueError("samples must be positive")
    rows_by_group: dict[str, list[int]] = {}
    stratum_by_group: dict[str, str] = {}
    for index, (group, stratum) in enumerate(zip(groups, strata)):
        rows_by_group.setdefault(str(group), []).append(index)
        previous = stratum_by_group.setdefault(str(group), str(stratum))
        if previous != str(stratum):
            raise ValueError("one group cannot belong to multiple strata")
    groups_by_stratum: dict[str, list[str]] = {}
    for group, stratum in stratum_by_group.items():
        groups_by_stratum.setdefault(stratum, []).append(group)
    rng = np.random.default_rng(seed)
    for _ in range(samples):
        sampled_rows: list[int] = []
        for stratum in sorted(groups_by_stratum):
            candidates = sorted(groups_by_stratum[stratum])
            selected = rng.choice(candidates, size=len(candidates), replace=True)
            for group in selected:
                sampled_rows.extend(rows_by_group[str(group)])
        yield np.asarray(sampled_rows, dtype=int)
