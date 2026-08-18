#!/usr/bin/env python3
"""Select a promising OLMo repetition-control setting for a full pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from scripts.create_olmo_generation_diagnostic import (
    aggregate,
    flatten_responses,
    group_aggregates,
    load_json,
    load_jsonl,
    response_metrics,
)


THRESHOLDS = {
    "combined_max_length_rate": 0.10,
    "main_max_length_rate": 0.10,
    "probe_max_length_rate": 0.10,
    "max_cell_max_length_rate": 0.20,
    "overall_duplicate_4gram_ge_0_15_rate": 0.05,
    "max_cell_duplicate_4gram_ge_0_15_rate": 0.10,
    "overall_format_compliance_rate": 0.50,
    "min_cell_format_compliance_rate": 0.25,
    "complete_sentence_ending_rate": 0.90,
    "list_or_heading_rate": 0.15,
    "role_start_rate": 0.02,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_checks(
    *,
    overall: dict[str, Any],
    main: dict[str, Any],
    probe: dict[str, Any],
    cells: dict[str, dict[str, Any]],
    quality: dict[str, Any],
) -> dict[str, bool]:
    marker_counts = quality["quality"]["forbidden_text_marker_counts"]
    return {
        "combined_max_length_rate_pass": overall["capped_rate"]
        <= THRESHOLDS["combined_max_length_rate"],
        "main_max_length_rate_pass": main["capped_rate"]
        <= THRESHOLDS["main_max_length_rate"],
        "probe_max_length_rate_pass": probe["capped_rate"]
        <= THRESHOLDS["probe_max_length_rate"],
        "each_cell_max_length_rate_pass": all(
            row["capped_rate"] <= THRESHOLDS["max_cell_max_length_rate"]
            for row in cells.values()
        ),
        "overall_repetition_rate_pass": overall[
            "duplicate_4gram_ge_0_15_rate"
        ]
        <= THRESHOLDS["overall_duplicate_4gram_ge_0_15_rate"],
        "each_cell_repetition_rate_pass": all(
            row["duplicate_4gram_ge_0_15_rate"]
            <= THRESHOLDS["max_cell_duplicate_4gram_ge_0_15_rate"]
            for row in cells.values()
        ),
        "overall_format_compliance_pass": overall["format_compliance_rate"]
        >= THRESHOLDS["overall_format_compliance_rate"],
        "each_cell_format_compliance_pass": all(
            row["format_compliance_rate"]
            >= THRESHOLDS["min_cell_format_compliance_rate"]
            for row in cells.values()
        ),
        "complete_sentence_ending_pass": overall["complete_sentence_ending_rate"]
        >= THRESHOLDS["complete_sentence_ending_rate"],
        "list_or_heading_rate_pass": overall["list_or_heading_rate"]
        <= THRESHOLDS["list_or_heading_rate"],
        "role_start_rate_pass": quality["quality"]["role_start_rate"]
        <= THRESHOLDS["role_start_rate"],
        "forbidden_text_markers_pass": not any(marker_counts.values()),
    }


def summarize_candidate(config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    output_dir = Path(config["data"]["output_dir"])
    trajectories_path = output_dir / "trajectories.jsonl"
    probes_path = output_dir / "probes.jsonl"
    quality_path = output_dir / "generation_quality.json"
    merge_path = output_dir / "merge_summary.json"
    trajectories = load_jsonl(trajectories_path)
    probes = load_jsonl(probes_path)
    quality = load_json(quality_path)
    cap = int(config["generation"]["max_new_tokens"])
    rows = flatten_responses(trajectories, probes, cap)
    if len(trajectories) != 8 or len(probes) != 48 or len(rows) != 248:
        raise ValueError("candidate counts differ from the frozen smoke design")
    for row in rows:
        row["metrics"] = response_metrics(str(row["response"]))
    main_rows = [row for row in rows if row["response_type"] == "main"]
    probe_rows = [row for row in rows if row["response_type"] == "probe"]
    overall = aggregate(rows)
    main = aggregate(main_rows)
    probe = aggregate(probe_rows)
    cells = group_aggregates(rows)
    checks = evaluate_checks(
        overall=overall,
        main=main,
        probe=probe,
        cells=cells,
        quality=quality,
    )
    return {
        "candidate": config["experiment"],
        "generated_only_repetition_penalty": config["generation"][
            "generated_only_repetition_penalty"
        ],
        "candidate_pass": all(checks.values()),
        "checks": checks,
        "overall": overall,
        "main": main,
        "probe": probe,
        "by_response_type_axis_condition": cells,
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "trajectories_sha256": sha256(trajectories_path),
        "probes_sha256": sha256(probes_path),
        "generation_quality_sha256": sha256(quality_path),
        "merge_summary_sha256": sha256(merge_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    candidates = sorted(
        (summarize_candidate(path) for path in args.configs),
        key=lambda row: float(row["generated_only_repetition_penalty"]),
    )
    penalties = [row["generated_only_repetition_penalty"] for row in candidates]
    if penalties != [1.05, 1.1]:
        raise ValueError(f"expected frozen penalties [1.05, 1.1], got {penalties}")
    selected = next(
        (
            float(row["generated_only_repetition_penalty"])
            for row in candidates
            if row["candidate_pass"]
        ),
        None,
    )
    result = {
        "protocol": "olmo_repetition_control_smoke_v1",
        "selection_rule": "minimum_generated_only_penalty_passing_all_smoke_checks",
        "thresholds": THRESHOLDS,
        "selected_generated_only_repetition_penalty": selected,
        "full_repetition_control_pilot_authorized": selected is not None,
        "formal_replication_authorized": False,
        "persona_outcomes_evaluated": False,
        "manual_response_text_inspected": False,
        "candidates": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_suffix(args.output.suffix + ".partial")
    partial.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    partial.replace(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    if selected is None:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
