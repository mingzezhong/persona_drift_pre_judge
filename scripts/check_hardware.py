#!/usr/bin/env python3
"""Print and validate compute-node GPUs using the restart-v2 config."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import yaml

from persona_drift.hardware import validate_cuda_hardware


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("configs/restart_v2.yaml")
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    hardware = config["hardware"]
    devices = validate_cuda_hardware(
        expected_gpu_count=int(hardware["gpu_count"]),
        expected_name_substring=hardware.get("expected_name_substring"),
        require_bf16=bool(hardware.get("allow_bf16", False)),
        min_memory_gib=hardware.get("min_memory_gib"),
    )
    print(json.dumps([asdict(device) for device in devices], indent=2))


if __name__ == "__main__":
    main()
