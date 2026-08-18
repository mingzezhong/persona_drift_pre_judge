#!/usr/bin/env python3
"""Validate the frozen token-only OLMo length-pilot design."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


BASE_CONFIG_SHA256 = (
    "cfe1ff38c7f2e4eeeb66de01848279d91b2e4d033707c4539946ada75271c4d6"
)
CAPS = (256, 384)
PILOT_SEEDS = [601, 602]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_config(base: dict[str, Any], cap: int) -> dict[str, Any]:
    expected = copy.deepcopy(base)
    root = f"outputs/cross_model_replication/olmo_length_pilot_v1/cap{cap}"
    expected["experiment"] = f"cross_model_length_pilot_olmo_v1_cap{cap}"
    expected["mode"] = "engineering_generation_length_pilot"
    expected["data"]["output_dir"] = root
    expected["data"]["seeds"] = PILOT_SEEDS
    expected["data"]["expected_trajectories"] = 48
    expected["data"]["expected_main_turns"] = 1200
    expected["data"]["expected_probes"] = 288
    expected["generation"]["max_new_tokens"] = cap
    expected["analysis"]["confirmatory"] = False
    expected["analysis"]["outcomes_must_not_be_evaluated"] = True
    forbidden_root = f"{root}/analysis_forbidden"
    expected["output"] = {
        "analysis_dir": forbidden_root,
        "summary": f"{forbidden_root}/summary.json",
        "checkpoint_scores": f"{forbidden_root}/checkpoint_scores.csv",
        "trajectory_outcomes": f"{forbidden_root}/trajectory_outcomes.csv",
        "per_judge_trajectory_outcomes": (
            f"{forbidden_root}/per_judge_trajectory_outcomes.csv"
        ),
    }
    return expected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--configs", type=Path, nargs="+", required=True)
    parser.add_argument(
        "--failed-run-root",
        type=Path,
        default=Path("outputs/cross_model_replication/olmo_v1"),
    )
    args = parser.parse_args()
    if sha256(args.base_config) != BASE_CONFIG_SHA256:
        raise ValueError("base replication config hash changed")
    base = yaml.safe_load(args.base_config.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    caps: list[int] = []
    for config_path in args.configs:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        cap = int(config["generation"]["max_new_tokens"])
        caps.append(cap)
        if config != expected_config(base, cap):
            raise ValueError(f"pilot config has unauthorized differences: {cap}")
        output_root = Path(config["data"]["output_dir"])
        if output_root.exists():
            raise FileExistsError(f"pilot output already exists: {output_root}")
        rows.append(
            {
                "cap": cap,
                "config": str(config_path),
                "config_sha256": sha256(config_path),
                "output_root": str(output_root),
            }
        )
    if sorted(caps) != list(CAPS) or len(caps) != len(set(caps)):
        raise ValueError(f"candidate caps must be exactly {list(CAPS)}")
    if set(PILOT_SEEDS) & {int(value) for value in base["data"]["seeds"]}:
        raise ValueError("length-pilot seeds overlap failed formal run")
    quality_path = args.failed_run_root / "generation_quality.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    if quality.get("gate_pass") is not False:
        raise ValueError("source run did not fail its frozen generation gate")
    if (args.failed_run_root / "judges").exists() or (
        args.failed_run_root / "analysis"
    ).exists():
        raise FileExistsError("source run unexpectedly has judge or analysis output")
    result = {
        "protocol": "olmo_generation_length_pilot_v1_preflight",
        "base_config_sha256": sha256(args.base_config),
        "source_generation_quality_sha256": sha256(quality_path),
        "candidate_configs": sorted(rows, key=lambda row: int(row["cap"])),
        "pilot_seeds": PILOT_SEEDS,
        "source_outcomes_not_evaluated": True,
        "pilot_outcomes_forbidden": True,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
