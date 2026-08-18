"""Correlation metrics for output-based persona behavior scores."""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

import numpy as np


def _validated_pair(
    left: Sequence[float], right: Sequence[float]
) -> tuple[np.ndarray, np.ndarray]:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("correlation inputs must have equal length of at least two")
    x = np.asarray(left, dtype=float)
    y = np.asarray(right, dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("correlation inputs must be finite")
    if float(x.std()) == 0 or float(y.std()) == 0:
        raise ValueError("correlation inputs must have nonzero variance")
    return x, y


def pearson_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    """Return Pearson's correlation after strict input validation."""

    x, y = _validated_pair(left, right)
    return float(np.corrcoef(x, y)[0, 1])


def average_ranks(values: Sequence[float]) -> np.ndarray:
    """Return one-based average ranks, including deterministic tie handling."""

    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) == 0 or not np.isfinite(array).all():
        raise ValueError("rank input must be a non-empty finite vector")
    order = np.argsort(array, kind="mergesort")
    ranks = np.empty(len(array), dtype=float)
    start = 0
    while start < len(array):
        end = start + 1
        while end < len(array) and array[order[end]] == array[order[start]]:
            end += 1
        average = (start + 1 + end) / 2.0
        ranks[order[start:end]] = average
        start = end
    return ranks


def spearman_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    """Return Spearman's rank correlation with average ranks for ties."""

    x, y = _validated_pair(left, right)
    return pearson_correlation(average_ranks(x), average_ranks(y))


def bootstrap_clustered_correlations(
    projections: Sequence[float],
    behavior_scores: Sequence[float],
    cluster_ids: Sequence[str],
    *,
    samples: int,
    seed: int,
) -> dict[str, list[float]]:
    """Bootstrap Pearson and Spearman correlations by complete pair cluster."""

    if not (
        len(projections) == len(behavior_scores) == len(cluster_ids)
        and len(projections) >= 2
    ):
        raise ValueError("bootstrap inputs must be non-empty and have equal length")
    if samples <= 0:
        raise ValueError("bootstrap samples must be positive")

    grouped: dict[str, list[int]] = defaultdict(list)
    for index, cluster_id in enumerate(cluster_ids):
        grouped[str(cluster_id)].append(index)
    ordered_clusters = sorted(grouped)
    if len(ordered_clusters) < 2:
        raise ValueError("at least two clusters are required")

    x = np.asarray(projections, dtype=float)
    y = np.asarray(behavior_scores, dtype=float)
    _validated_pair(x, y)
    rng = np.random.default_rng(seed)
    pearson_values: list[float] = []
    spearman_values: list[float] = []
    for _ in range(samples):
        sampled_clusters = rng.integers(
            0, len(ordered_clusters), size=len(ordered_clusters)
        )
        indices = np.concatenate(
            [
                np.asarray(grouped[ordered_clusters[index]], dtype=int)
                for index in sampled_clusters
            ]
        )
        pearson_values.append(pearson_correlation(x[indices], y[indices]))
        spearman_values.append(spearman_correlation(x[indices], y[indices]))

    def interval(values: Sequence[float]) -> list[float]:
        return [
            float(np.percentile(values, 2.5)),
            float(np.percentile(values, 97.5)),
        ]

    return {
        "pearson_r_95ci": interval(pearson_values),
        "spearman_rho_95ci": interval(spearman_values),
    }
