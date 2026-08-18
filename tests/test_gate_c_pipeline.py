import numpy as np
import pytest
import torch

from scripts.analyze_gate_c_development import (
    choose_threshold,
    metric_summary,
    threshold_metrics,
)
from scripts.embed_gate_c_prefixes import average_pool


def test_average_pool_ignores_padding_and_normalizes_denominator() -> None:
    hidden = torch.tensor(
        [[[1.0, 3.0], [3.0, 5.0], [99.0, 99.0]], [[2.0, 4.0], [8.0, 8.0], [9.0, 9.0]]]
    )
    mask = torch.tensor([[1, 1, 0], [1, 0, 0]])
    pooled = average_pool(hidden, mask)
    assert torch.allclose(pooled, torch.tensor([[2.0, 4.0], [2.0, 4.0]]))


def test_threshold_selection_minimizes_false_positive_rate() -> None:
    y = np.asarray([1, 1, 0, 0])
    probability = np.asarray([0.9, 0.4, 0.8, 0.1])
    threshold, metrics = choose_threshold(y, probability, 1.0)
    assert threshold == pytest.approx(0.4)
    assert metrics["recall"] == 1.0
    assert metrics["false_positive_rate"] == pytest.approx(0.5)


def test_metric_and_false_alarm_denominators() -> None:
    y = np.asarray([1, 0, 0, 0])
    probability = np.asarray([0.8, 0.9, 0.2, 0.1])
    summary = metric_summary(y, probability)
    assert summary["examples"] == 4
    thresholded = threshold_metrics(y, probability, 0.5)
    assert thresholded["false_positive"] == 1
    assert thresholded["false_alarms_per_100_eligible_turns"] == 25.0
