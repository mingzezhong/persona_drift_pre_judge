#!/usr/bin/env python3
"""Run the partitioned Gate A generator with isolated repetition controls."""

from __future__ import annotations

from typing import Any

from scripts import generate_partitioned_gate_a_trajectories as base
from persona_drift.repetition_control import (
    generate_and_capture_repetition_controlled_conversation,
)


def repetition_generation_settings(config: dict[str, Any]) -> dict[str, Any]:
    settings = dict(config["generation"])
    allowed = {
        "max_new_tokens",
        "min_new_tokens",
        "temperature",
        "top_p",
        "do_sample",
        "generated_only_repetition_penalty",
        "generated_only_no_repeat_ngram_size",
    }
    unexpected = set(settings) - allowed
    if unexpected:
        raise ValueError(f"unsupported generation settings: {sorted(unexpected)}")
    return settings


def main() -> None:
    base.generation_settings = repetition_generation_settings
    base.generate_and_capture_conversation = (
        generate_and_capture_repetition_controlled_conversation
    )
    base.main()


if __name__ == "__main__":
    main()
