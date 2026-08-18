#!/usr/bin/env python3
"""Evaluate the frozen full OLMo prompt-salience quality pilot."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from scripts.create_olmo_generation_diagnostic import (
    aggregate,
    flatten_responses,
    load_json,
    load_jsonl,
    response_metrics,
)


THRESHOLDS = {
    "combined_max_length_rate": 0.10,
    "main_max_length_rate": 0.10,
    "probe_max_length_rate": 0.10,
    "max_topic_cell_max_length_rate": 0.20,
    "overall_duplicate_4gram_ge_0_15_rate": 0.05,
    "max_topic_cell_duplicate_4gram_ge_0_15_rate": 0.10,
    "overall_format_compliance_rate": 0.85,
    "min_topic_cell_format_compliance_rate": 0.75,
    "complete_sentence_ending_rate": 0.95,
    "list_or_heading_rate": 0.05,
    "role_start_rate": 0.02,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def grouped_aggregates(
    rows: list[dict[str, Any]], fields: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups["/".join(str(row[field]) for field in fields)].append(row)
    return {name: aggregate(group) for name, group in sorted(groups.items())}


def evaluate_checks(
    *,
    overall: dict[str, Any],
    main: dict[str, Any],
    probe: dict[str, Any],
    topic_cells: dict[str, dict[str, Any]],
    topics: dict[str, dict[str, Any]],
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
        "each_topic_cell_max_length_rate_pass": all(
            row["capped_rate"] <= THRESHOLDS["max_topic_cell_max_length_rate"]
            for row in topic_cells.values()
        ),
        "each_topic_max_length_rate_pass": all(
            row["capped_rate"] <= THRESHOLDS["combined_max_length_rate"]
            for row in topics.values()
        ),
        "overall_repetition_rate_pass": overall[
            "duplicate_4gram_ge_0_15_rate"
        ]
        <= THRESHOLDS["overall_duplicate_4gram_ge_0_15_rate"],
        "each_topic_cell_repetition_rate_pass": all(
            row["duplicate_4gram_ge_0_15_rate"]
            <= THRESHOLDS["max_topic_cell_duplicate_4gram_ge_0_15_rate"]
            for row in topic_cells.values()
        ),
        "overall_format_compliance_pass": overall["format_compliance_rate"]
        >= THRESHOLDS["overall_format_compliance_rate"],
        "each_topic_cell_format_compliance_pass": all(
            row["format_compliance_rate"]
            >= THRESHOLDS["min_topic_cell_format_compliance_rate"]
            for row in topic_cells.values()
        ),
        "complete_sentence_ending_pass": overall["complete_sentence_ending_rate"]
        >= THRESHOLDS["complete_sentence_ending_rate"],
        "list_or_heading_rate_pass": overall["list_or_heading_rate"]
        <= THRESHOLDS["list_or_heading_rate"],
        "role_start_rate_pass": quality["quality"]["role_start_rate"]
        <= THRESHOLDS["role_start_rate"],
        "forbidden_text_markers_pass": not any(marker_counts.values()),
    }


def summarize_pilot(config_path: Path) -> dict[str, Any]:
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
    expected = config["data"]
    counts = (
        len(trajectories),
        sum(len(row["turns"]) for row in trajectories),
        len(probes),
        len(rows),
    )
    expected_counts = (
        int(expected["expected_trajectories"]),
        int(expected["expected_main_turns"]),
        int(expected["expected_probes"]),
        int(expected["expected_main_turns"]) + int(expected["expected_probes"]),
    )
    if counts != expected_counts:
        raise ValueError(f"pilot counts {counts} differ from frozen {expected_counts}")
    design = Counter(
        (row["axis"], row["condition"], row["topic"], int(row["seed"]))
        for row in trajectories
    )
    expected_design = {
        (axis, condition, topic, int(seed))
        for axis in expected["axes"]
        for condition in expected["conditions"]
        for topic in expected["topics"]
        for seed in expected["seeds"]
    }
    if set(design) != expected_design or any(count != 1 for count in design.values()):
        raise ValueError("trajectory coverage differs from the frozen pilot design")
    for row in rows:
        row["metrics"] = response_metrics(str(row["response"]))
    main_rows = [row for row in rows if row["response_type"] == "main"]
    probe_rows = [row for row in rows if row["response_type"] == "probe"]
    overall = aggregate(rows)
    main = aggregate(main_rows)
    probe = aggregate(probe_rows)
    topic_cells = grouped_aggregates(
        rows, ("response_type", "axis", "condition", "topic")
    )
    topics = grouped_aggregates(rows, ("topic",))
    checks = evaluate_checks(
        overall=overall,
        main=main,
        probe=probe,
        topic_cells=topic_cells,
        topics=topics,
        quality=quality,
    )
    return {
        "pilot_pass": all(checks.values()),
        "checks": checks,
        "overall": overall,
        "main": main,
        "probe": probe,
        "by_response_type_axis_condition_topic": topic_cells,
        "by_topic": topics,
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "trajectories_sha256": sha256(trajectories_path),
        "probes_sha256": sha256(probes_path),
        "generation_quality_sha256": sha256(quality_path),
        "merge_summary_sha256": sha256(merge_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    row = summarize_pilot(args.config)
    passed = bool(row["pilot_pass"])
    result = {
        "protocol": "olmo_prompt_salience_pilot_v1",
        "thresholds": THRESHOLDS,
        "prompt_salience_variant": config["prompt_salience"]["variant"],
        "pilot_pass": passed,
        "qc_remediated_formal_replication_authorized": passed,
        "formal_reserved_seeds": config["provenance"]["formal_reserved_seeds"],
        "persona_outcomes_evaluated": False,
        "manual_response_text_inspected": False,
        "pilot": row,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_suffix(args.output.suffix + ".partial")
    partial.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    partial.replace(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
