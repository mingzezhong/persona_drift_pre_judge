#!/usr/bin/env python3
"""Select an OLMo generation cap using token-only engineering QC."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml


THRESHOLDS = {
    "combined_max_length_rate": 0.10,
    "main_max_length_rate": 0.10,
    "probe_max_length_rate": 0.10,
    "max_axis_condition_main_rate": 0.15,
    "max_axis_condition_probe_rate": 0.20,
    "role_start_rate": 0.02,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"non-object JSON at {path}:{line_number}")
            records.append(record)
    return records


def length_summary(counts: Iterable[int], cap: int) -> dict[str, Any]:
    values = [int(value) for value in counts]
    if not values:
        raise ValueError("cannot summarize an empty token-count group")
    maximum = sum(value >= cap for value in values)
    return {
        "responses": len(values),
        "max_length_examples": maximum,
        "max_length_rate": maximum / len(values),
        "token_count_min": min(values),
        "token_count_max": max(values),
    }


def evaluate_checks(
    *,
    combined: dict[str, Any],
    main: dict[str, Any],
    probe: dict[str, Any],
    main_groups: dict[str, dict[str, Any]],
    probe_groups: dict[str, dict[str, Any]],
    quality: dict[str, Any],
) -> dict[str, bool]:
    quality_metrics = quality["quality"]
    forbidden_counts = quality_metrics["forbidden_text_marker_counts"]
    checks = {
        "combined_max_length_rate_pass": (
            float(combined["max_length_rate"])
            <= THRESHOLDS["combined_max_length_rate"]
        ),
        "main_max_length_rate_pass": (
            float(main["max_length_rate"]) <= THRESHOLDS["main_max_length_rate"]
        ),
        "probe_max_length_rate_pass": (
            float(probe["max_length_rate"])
            <= THRESHOLDS["probe_max_length_rate"]
        ),
        "each_axis_condition_main_rate_pass": (
            max(float(row["max_length_rate"]) for row in main_groups.values())
            <= THRESHOLDS["max_axis_condition_main_rate"]
        ),
        "each_axis_condition_probe_rate_pass": (
            max(float(row["max_length_rate"]) for row in probe_groups.values())
            <= THRESHOLDS["max_axis_condition_probe_rate"]
        ),
        "role_start_rate_pass": (
            float(quality_metrics["role_start_rate"])
            <= THRESHOLDS["role_start_rate"]
        ),
        "forbidden_text_markers_pass": not any(
            int(value) for value in forbidden_counts.values()
        ),
    }
    return checks


def summarize_candidate(config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    cap = int(config["generation"]["max_new_tokens"])
    root = Path(config["data"]["output_dir"])
    trajectories_path = root / "trajectories.jsonl"
    probes_path = root / "probes.jsonl"
    quality_path = root / "generation_quality.json"
    merge_summary_path = root / "merge_summary.json"
    trajectories = load_jsonl(trajectories_path)
    probes = load_jsonl(probes_path)
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    merge_summary = json.loads(merge_summary_path.read_text(encoding="utf-8"))
    expected_trajectories = int(config["data"]["expected_trajectories"])
    expected_main_turns = int(config["data"]["expected_main_turns"])
    expected_probes = int(config["data"]["expected_probes"])
    if len(trajectories) != expected_trajectories:
        raise ValueError(f"trajectory count mismatch for cap {cap}")
    if len(probes) != expected_probes:
        raise ValueError(f"probe count mismatch for cap {cap}")
    if merge_summary["main_turns"] != expected_main_turns:
        raise ValueError(f"main-turn count mismatch for cap {cap}")
    if merge_summary["config_sha256"] != sha256(config_path):
        raise ValueError(f"merge config hash mismatch for cap {cap}")

    main_counts: list[int] = []
    probe_counts: list[int] = []
    main_group_counts: dict[str, list[int]] = defaultdict(list)
    probe_group_counts: dict[str, list[int]] = defaultdict(list)
    for trajectory in trajectories:
        group = f"{trajectory['axis']}/{trajectory['condition']}"
        for turn in trajectory["turns"]:
            count = int(turn["response_token_count"])
            main_counts.append(count)
            main_group_counts[group].append(count)
    for probe_row in probes:
        group = f"{probe_row['axis']}/{probe_row['condition']}"
        count = int(probe_row["response_token_count"])
        probe_counts.append(count)
        probe_group_counts[group].append(count)
    if len(main_counts) != expected_main_turns:
        raise ValueError(f"rendered main-turn count mismatch for cap {cap}")

    combined = length_summary(main_counts + probe_counts, cap)
    main = length_summary(main_counts, cap)
    probe = length_summary(probe_counts, cap)
    main_groups = {
        group: length_summary(values, cap)
        for group, values in sorted(main_group_counts.items())
    }
    probe_groups = {
        group: length_summary(values, cap)
        for group, values in sorted(probe_group_counts.items())
    }
    checks = evaluate_checks(
        combined=combined,
        main=main,
        probe=probe,
        main_groups=main_groups,
        probe_groups=probe_groups,
        quality=quality,
    )
    if int(quality["quality"]["responses"]) != combined["responses"]:
        raise ValueError(f"quality response count mismatch for cap {cap}")
    if int(quality["quality"]["max_length_examples"]) != combined[
        "max_length_examples"
    ]:
        raise ValueError(f"quality max-length count mismatch for cap {cap}")
    return {
        "cap": cap,
        "candidate_pass": all(checks.values()),
        "checks": checks,
        "combined": combined,
        "main": main,
        "probe": probe,
        "main_by_axis_condition": main_groups,
        "probe_by_axis_condition": probe_groups,
        "role_start_rate": quality["quality"]["role_start_rate"],
        "forbidden_text_marker_counts": quality["quality"][
            "forbidden_text_marker_counts"
        ],
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "trajectories_sha256": sha256(trajectories_path),
        "probes_sha256": sha256(probes_path),
        "generation_quality_sha256": sha256(quality_path),
        "merge_summary_sha256": sha256(merge_summary_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    candidates = sorted(
        (summarize_candidate(path) for path in args.configs),
        key=lambda row: int(row["cap"]),
    )
    caps = [int(row["cap"]) for row in candidates]
    if caps != [256, 384]:
        raise ValueError(f"expected frozen candidates [256, 384], got {caps}")
    selected = next(
        (int(row["cap"]) for row in candidates if row["candidate_pass"]), None
    )
    result = {
        "protocol": "olmo_generation_length_pilot_v1",
        "selection_rule": "minimum_cap_passing_all_token_only_qc_checks",
        "thresholds": THRESHOLDS,
        "selected_max_new_tokens": selected,
        "formal_replication_authorized": selected is not None,
        "response_text_inspected": False,
        "persona_outcomes_evaluated": False,
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
