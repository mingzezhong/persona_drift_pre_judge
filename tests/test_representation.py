import pytest
import torch

from persona_drift.representation import (
    cosine_layer_scores,
    select_common_layer,
    summarize_binary_pairs,
)


def test_cosine_layer_scores_preserve_direction() -> None:
    vector = torch.tensor([[1.0, 0.0], [0.0, 2.0]])
    aligned = cosine_layer_scores(vector, vector)
    opposed = cosine_layer_scores(-vector, vector)
    assert torch.allclose(aligned, torch.ones(2))
    assert torch.allclose(opposed, -torch.ones(2))


def test_perfect_paired_separation_has_unit_metrics() -> None:
    summary = summarize_binary_pairs(
        [0.8, -0.2, 0.5, -0.5],
        ["target", "contrast", "target", "contrast"],
        ["p1", "p1", "p2", "p2"],
    )
    assert summary["auroc"] == 1.0
    assert summary["pair_direction_accuracy"] == 1.0
    assert summary["pairs"] == 2


def test_layer_selection_uses_reference_tie_break() -> None:
    metrics = [
        {"layer": 19, "mean_auroc": 1.0, "mean_pair_direction_accuracy": 1.0},
        {"layer": 20, "mean_auroc": 1.0, "mean_pair_direction_accuracy": 1.0},
        {"layer": 21, "mean_auroc": 1.0, "mean_pair_direction_accuracy": 1.0},
    ]
    assert select_common_layer(metrics, reference_layer=20) == 20
    with pytest.raises(ValueError, match="reference"):
        select_common_layer(metrics, reference_layer=18)
