#!/usr/bin/env python3
"""Apply the pilot-frozen generation-quality gate to the formal OLMo run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from scripts.analyze_prompt_salience_pilot import THRESHOLDS, summarize_pilot


def summarize_formal_generation_qc(config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("mode") != "preregistered_qc_remediated_cross_model_replication":
        raise ValueError("configuration is not the frozen formal replication")
    if config.get("formal_generation_quality") != THRESHOLDS:
        raise ValueError("formal thresholds differ from the pilot-frozen thresholds")
    row = summarize_pilot(config_path)
    merge_path = Path(config["data"]["output_dir"]) / "merge_summary.json"
    merge = json.loads(merge_path.read_text(encoding="utf-8"))
    passed = bool(row["pilot_pass"] and merge.get("generation_gate_pass") is True)
    return {
        "protocol": "olmo_qc_v1_formal_generation_gate",
        "formal_generation_qc_pass": passed,
        "persona_outcomes_evaluated": False,
        "manual_response_text_inspected": False,
        "thresholds": THRESHOLDS,
        "checks": row["checks"],
        "overall": row["overall"],
        "main": row["main"],
        "probe": row["probe"],
        "by_response_type_axis_condition_topic": row[
            "by_response_type_axis_condition_topic"
        ],
        "by_topic": row["by_topic"],
        "config": row["config"],
        "config_sha256": row["config_sha256"],
        "trajectories_sha256": row["trajectories_sha256"],
        "probes_sha256": row["probes_sha256"],
        "generation_quality_sha256": row["generation_quality_sha256"],
        "merge_summary_sha256": row["merge_summary_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    result = summarize_formal_generation_qc(args.config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_suffix(args.output.suffix + ".partial")
    partial.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    partial.replace(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["formal_generation_qc_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
