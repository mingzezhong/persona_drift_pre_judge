"""Axis-calibrated activation features for Gate C development v2."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


def fit_clean_axis_calibration(
    rows: Sequence[Mapping[str, Any]],
    *,
    axes: Sequence[str],
    split: str,
    clean_conditions: Sequence[str],
    eligibility_key: str,
    minimum_scale: float = 1e-8,
) -> dict[str, dict[str, float]]:
    """Fit label-free projection/norm calibration on clean training rows."""

    if minimum_scale <= 0:
        raise ValueError("minimum_scale must be positive")
    allowed_axes = {str(axis) for axis in axes}
    clean = {str(condition) for condition in clean_conditions}
    values: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"projection": [], "norm": []}
    )
    for row in rows:
        axis = str(row["axis"])
        if (
            axis in allowed_axes
            and str(row["development_split"]) == split
            and str(row["condition"]) in clean
            and bool(row[eligibility_key])
        ):
            features = row["activation_features"]
            values[axis]["projection"].append(
                float(features["projection_layer20"])
            )
            values[axis]["norm"].append(float(features["norm_layer20"]))
    result: dict[str, dict[str, float]] = {}
    for axis in sorted(allowed_axes):
        if axis not in values:
            raise ValueError(f"no clean calibration rows for axis {axis}")
        projection = np.asarray(values[axis]["projection"], dtype=float)
        norm = np.asarray(values[axis]["norm"], dtype=float)
        projection_scale = float(np.std(projection, ddof=0))
        norm_scale = float(np.std(norm, ddof=0))
        if projection_scale < minimum_scale or norm_scale < minimum_scale:
            raise ValueError(f"degenerate clean calibration scale for {axis}")
        result[axis] = {
            "rows": int(len(projection)),
            "projection_mean": float(np.mean(projection)),
            "projection_scale": projection_scale,
            "norm_mean": float(np.mean(norm)),
            "norm_scale": norm_scale,
        }
    return result


def transform_axis_calibrated_rows(
    rows: Sequence[Mapping[str, Any]],
    calibration: Mapping[str, Mapping[str, float]],
) -> list[dict[str, Any]]:
    """Return copied rows with the frozen v2 activation feature mapping."""

    transformed: list[dict[str, Any]] = []
    for row in rows:
        axis = str(row["axis"])
        if axis not in calibration:
            raise ValueError(f"missing calibration for axis {axis}")
        source = row["activation_features"]
        stats = calibration[axis]
        features = {
            "projection_clean_axis_z": (
                float(source["projection_layer20"])
                - float(stats["projection_mean"])
            )
            / float(stats["projection_scale"]),
            "projection_delta_turn1": float(
                source["projection_delta_turn1"]
            ),
            "projection_slope_last3": float(
                source["projection_slope_last3"]
            ),
            "norm_clean_axis_z": (
                float(source["norm_layer20"]) - float(stats["norm_mean"])
            )
            / float(stats["norm_scale"]),
            "turn": float(source["turn"]),
        }
        if not np.isfinite(list(features.values())).all():
            raise ValueError("transformed activation features must be finite")
        copied = dict(row)
        copied["activation_features"] = features
        transformed.append(copied)
    return transformed
