"""Model-agnostic activation extraction and persona-vector operations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

import torch
from torch import Tensor, nn

Pooling = Literal["last_prompt_token", "response_token_mean"]


def mean_difference(positive: Tensor, negative: Tensor) -> Tensor:
    """Return the BILLY-style contrastive persona direction.

    Inputs have shape ``[examples, ..., hidden_dim]`` and must already be pooled
    over tokens. All non-example dimensions are preserved.
    """

    if positive.ndim < 2 or negative.ndim < 2:
        raise ValueError("activations must include example and hidden dimensions")
    if positive.shape[1:] != negative.shape[1:]:
        raise ValueError("positive and negative activation shapes must match")
    if positive.shape[0] == 0 or negative.shape[0] == 0:
        raise ValueError("positive and negative activation sets must be non-empty")
    return positive.float().mean(dim=0) - negative.float().mean(dim=0)


def unit_vector(vector: Tensor, eps: float = 1e-12) -> Tensor:
    """Normalize a vector along its final dimension."""

    norm = torch.linalg.vector_norm(vector.float(), dim=-1, keepdim=True)
    if torch.any(norm <= eps):
        raise ValueError("cannot normalize a zero persona vector")
    return vector.float() / norm


def project(activations: Tensor, vector: Tensor, center: Tensor | None = None) -> Tensor:
    """Project activations onto a layer-aligned unit persona direction."""

    values = activations.float()
    if center is not None:
        values = values - center.float()
    return torch.sum(values * unit_vector(vector), dim=-1)


def transformer_blocks(model: nn.Module) -> list[nn.Module]:
    """Resolve decoder blocks for supported Qwen, Llama, and Gemma classes."""

    candidates = (
        ("model", "layers"),
        ("language_model", "model", "layers"),
    )
    for path in candidates:
        current: object = model
        for attribute in path:
            if not hasattr(current, attribute):
                break
            current = getattr(current, attribute)
        else:
            if isinstance(current, nn.ModuleList):
                return list(current)
    raise TypeError("unsupported model: could not locate transformer decoder layers")


class ResidualPoolCapture:
    """Forward hook that transfers only a pooled block output to CPU.

    Batch size is deliberately restricted to one to avoid ambiguous last-token
    behavior under padding in the initial controlled experiment.
    """

    def __init__(self, pooling: Pooling, response_start: int | None = None) -> None:
        self.pooling = pooling
        self.response_start = response_start
        self.value: Tensor | None = None

    def __call__(self, _module: nn.Module, _inputs: tuple[object, ...], output: object) -> None:
        hidden = output[0] if isinstance(output, tuple) else output
        if not isinstance(hidden, Tensor) or hidden.ndim != 3:
            raise TypeError("expected transformer block output [batch, sequence, hidden]")
        if hidden.shape[0] != 1:
            raise ValueError("activation capture currently requires batch size 1")

        if self.pooling == "last_prompt_token":
            pooled = hidden[:, -1, :]
        else:
            if self.response_start is None:
                raise ValueError("response_start is required for response-token pooling")
            if not 0 <= self.response_start < hidden.shape[1]:
                raise ValueError("response_start must identify at least one response token")
            pooled = hidden[:, self.response_start :, :].mean(dim=1)
        self.value = pooled.detach().float().cpu()


@contextmanager
def pooled_residual_hooks(
    model: nn.Module,
    *,
    pooling: Pooling,
    response_start: int | None = None,
) -> Iterator[list[ResidualPoolCapture]]:
    """Register memory-bounded residual hooks and remove them afterward."""

    blocks = transformer_blocks(model)
    captures = [ResidualPoolCapture(pooling, response_start) for _ in blocks]
    handles = [
        block.register_forward_hook(capture)
        for block, capture in zip(blocks, captures)
    ]
    try:
        yield captures
    finally:
        for handle in handles:
            handle.remove()


def stack_captures(captures: list[ResidualPoolCapture]) -> Tensor:
    """Stack hook values as ``[layers, batch, hidden]`` FP32 CPU data."""

    if not captures or any(capture.value is None for capture in captures):
        raise RuntimeError("not all transformer layers produced an activation")
    values = [capture.value for capture in captures]
    return torch.stack([value for value in values if value is not None], dim=0)

