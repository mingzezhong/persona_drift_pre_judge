"""Layerwise persona projection metrics for held-out representation tests."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score
import torch
from torch import Tensor
from torch.nn import functional as F


def cosine_layer_scores(activation: Tensor, vector: Tensor) -> Tensor:
    """Return one cosine persona projection per layer."""

    if activation.ndim != 2 or vector.ndim != 2:
        raise ValueError("activation and vector must both have shape [layers, hidden]")
    if activation.shape != vector.shape:
        raise ValueError(
            f"activation shape {tuple(activation.shape)} differs from vector "
            f"shape {tuple(vector.shape)}"
        )
    if not bool(torch.isfinite(activation).all()) or not bool(
        torch.isfinite(vector).all()
    ):
        raise ValueError("projection inputs must be finite")
    if bool((torch.linalg.vector_norm(vector.float(), dim=1) == 0).any()):
        raise ValueError("persona vector contains a zero-norm layer")
    return F.cosine_similarity(activation.float(), vector.float(), dim=1)


def paired_score_arrays(
    scores: Sequence[float],
    polarities: Sequence[str],
    pair_ids: Sequence[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Return aligned target and contrast arrays for complete unique pairs."""

    if not (len(scores) == len(polarities) == len(pair_ids)) or not scores:
        raise ValueError("paired inputs must be non-empty and have equal length")
    grouped: dict[str, dict[str, float]] = defaultdict(dict)
    for score, polarity, pair_id in zip(scores, polarities, pair_ids):
        if polarity not in {"target", "contrast"}:
            raise ValueError(f"invalid polarity: {polarity}")
        if polarity in grouped[pair_id]:
            raise ValueError(f"duplicate {polarity} for pair {pair_id}")
        grouped[pair_id][polarity] = float(score)
    for pair_id, pair in grouped.items():
        if set(pair) != {"target", "contrast"}:
            raise ValueError(f"incomplete score pair: {pair_id}")
    ordered = sorted(grouped)
    target = np.asarray([grouped[key]["target"] for key in ordered], dtype=float)
    contrast = np.asarray(
        [grouped[key]["contrast"] for key in ordered], dtype=float
    )
    return target, contrast


def summarize_binary_pairs(
    scores: Sequence[float],
    polarities: Sequence[str],
    pair_ids: Sequence[str],
) -> dict[str, Any]:
    """Summarize example classification and matched-pair separation."""

    target, contrast = paired_score_arrays(scores, polarities, pair_ids)
    labels = np.concatenate((np.ones(len(target)), np.zeros(len(contrast))))
    combined_scores = np.concatenate((target, contrast))
    deltas = target - contrast
    standard_deviation = float(deltas.std(ddof=1)) if len(deltas) > 1 else 0.0
    effect = (
        float(deltas.mean() / standard_deviation)
        if standard_deviation > 0
        else None
    )
    return {
        "examples": int(len(combined_scores)),
        "pairs": int(len(target)),
        "auroc": float(roc_auc_score(labels, combined_scores)),
        "average_precision": float(
            average_precision_score(labels, combined_scores)
        ),
        "pair_direction_accuracy": float((deltas > 0).mean()),
        "paired_delta_mean": float(deltas.mean()),
        "paired_delta_std": standard_deviation,
        "paired_effect_dz": effect,
    }


def bootstrap_paired_metrics(
    scores: Sequence[float],
    polarities: Sequence[str],
    pair_ids: Sequence[str],
    *,
    samples: int,
    seed: int,
) -> dict[str, list[float]]:
    """Pair-cluster bootstrap CIs for the primary held-out metrics."""

    if samples <= 0:
        raise ValueError("bootstrap samples must be positive")
    target, contrast = paired_score_arrays(scores, polarities, pair_ids)
    rng = np.random.default_rng(seed)
    aurocs: list[float] = []
    accuracies: list[float] = []
    deltas: list[float] = []
    pair_count = len(target)
    for _ in range(samples):
        indices = rng.integers(0, pair_count, size=pair_count)
        sampled_target = target[indices]
        sampled_contrast = contrast[indices]
        labels = np.concatenate(
            (np.ones(pair_count), np.zeros(pair_count))
        )
        combined = np.concatenate((sampled_target, sampled_contrast))
        difference = sampled_target - sampled_contrast
        aurocs.append(float(roc_auc_score(labels, combined)))
        accuracies.append(float((difference > 0).mean()))
        deltas.append(float(difference.mean()))

    def interval(values: Sequence[float]) -> list[float]:
        return [
            float(np.percentile(values, 2.5)),
            float(np.percentile(values, 97.5)),
        ]

    return {
        "auroc_95ci": interval(aurocs),
        "pair_direction_accuracy_95ci": interval(accuracies),
        "paired_delta_mean_95ci": interval(deltas),
    }


def select_common_layer(
    metrics_by_layer: Sequence[dict[str, Any]], *, reference_layer: int
) -> int:
    """Apply the frozen validation-only common-layer selection rule."""

    if not metrics_by_layer:
        raise ValueError("no validation layer metrics")
    layers = {int(item["layer"]) for item in metrics_by_layer}
    if reference_layer not in layers:
        raise ValueError("reference layer is absent from validation metrics")
    selected = max(
        metrics_by_layer,
        key=lambda item: (
            float(item["mean_auroc"]),
            float(item["mean_pair_direction_accuracy"]),
            -abs(int(item["layer"]) - reference_layer),
            -int(item["layer"]),
        ),
    )
    return int(selected["layer"])
