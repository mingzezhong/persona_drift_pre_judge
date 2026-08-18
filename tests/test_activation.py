import pytest
import torch
from torch import nn

from persona_drift.activation import (
    ResidualPoolCapture,
    mean_difference,
    project,
    stack_captures,
    unit_vector,
)


def test_mean_difference_preserves_layer_and_hidden_dimensions() -> None:
    positive = torch.tensor([[[2.0, 0.0]], [[4.0, 2.0]]])
    negative = torch.tensor([[[1.0, 0.0]], [[1.0, 0.0]]])
    result = mean_difference(positive, negative)
    assert result.shape == (1, 2)
    assert torch.allclose(result, torch.tensor([[2.0, 1.0]]))


def test_projection_uses_unit_direction() -> None:
    activations = torch.tensor([[3.0, 4.0], [0.0, 5.0]])
    vector = torch.tensor([0.0, 2.0])
    assert torch.allclose(project(activations, vector), torch.tensor([4.0, 5.0]))


def test_zero_vector_is_rejected() -> None:
    with pytest.raises(ValueError, match="zero persona vector"):
        unit_vector(torch.zeros(3))


def test_response_pooling_and_stack() -> None:
    output = torch.tensor([[[1.0, 2.0], [3.0, 4.0], [5.0, 8.0]]])
    first = ResidualPoolCapture("response_token_mean", response_start=1)
    second = ResidualPoolCapture("response_token_mean", response_start=1)
    first(nn.Identity(), (), output)
    second(nn.Identity(), (), (output + 1.0,))
    stacked = stack_captures([first, second])
    assert stacked.shape == (2, 1, 2)
    assert torch.allclose(stacked[0, 0], torch.tensor([4.0, 6.0]))
    assert torch.allclose(stacked[1, 0], torch.tensor([5.0, 7.0]))

