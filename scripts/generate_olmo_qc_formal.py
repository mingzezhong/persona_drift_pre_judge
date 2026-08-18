#!/usr/bin/env python3
"""Generate formal OLMo shards with the pilot-approved isolated controls."""

from __future__ import annotations

from scripts import generate_partitioned_gate_a_trajectories as base
from scripts.generate_repetition_control_smoke import repetition_generation_settings
from persona_drift.repetition_control import (
    generate_and_capture_repetition_controlled_conversation,
)


def main() -> None:
    base.generation_settings = repetition_generation_settings
    base.generate_and_capture_conversation = (
        generate_and_capture_repetition_controlled_conversation
    )
    base.main()


if __name__ == "__main__":
    main()
