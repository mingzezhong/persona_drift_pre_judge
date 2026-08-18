"""Validated records for contrastive extraction and trajectory checkpoints."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Polarity = Literal["target", "contrast"]


@dataclass(frozen=True)
class ExtractionExample:
    example_id: str
    prompt_id: str
    axis: str
    polarity: Polarity
    system: str
    user: str
    response: str
    model: str
    model_revision: str
    seed: int
    generation: dict[str, Any] = field(default_factory=dict)
    judge_score: float | None = None
    accepted: bool | None = None

    def __post_init__(self) -> None:
        required_text = {
            "example_id": self.example_id,
            "prompt_id": self.prompt_id,
            "axis": self.axis,
            "system": self.system,
            "user": self.user,
            "model": self.model,
            "model_revision": self.model_revision,
        }
        empty = [name for name, value in required_text.items() if not value.strip()]
        if empty:
            raise ValueError(f"required text fields are empty: {empty}")
        if self.polarity not in ("target", "contrast"):
            raise ValueError(f"invalid polarity: {self.polarity}")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
        if self.judge_score is not None and not 0.0 <= self.judge_score <= 1.0:
            raise ValueError("judge_score must lie in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CheckpointRecord:
    trajectory_id: str
    axis: str
    condition: str
    topic: str
    seed: int
    turn: int
    prefix_hash: str
    model: str
    model_revision: str
    generation: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.seed < 0 or self.turn < 0:
            raise ValueError("seed and turn must be non-negative")
        if not self.prefix_hash.strip():
            raise ValueError("prefix_hash is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

