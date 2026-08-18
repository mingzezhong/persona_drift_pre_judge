#!/usr/bin/env python3
"""Build causally aligned forecasting examples from immutable Gate A outputs."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from persona_drift.gate_c import (
    build_text_prefix,
    future_drift_label,
    projection_features,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    source = config["source"]
    labels = config["labels"]
    scope = config["scope"]
    output = config["output"]
    trajectories_path = Path(source["trajectories"])
    outcomes_path = Path(source["trajectory_outcomes"])
    gate_a_summary_path = Path(source["gate_a_summary"])
    for path, expected in [
        (trajectories_path, source["trajectories_sha256"]),
        (outcomes_path, source["trajectory_outcomes_sha256"]),
        (gate_a_summary_path, source["gate_a_summary_sha256"]),
    ]:
        observed = sha256(path)
        if observed != str(expected):
            raise ValueError(f"source hash mismatch for {path}: {observed}")
    gate_a_summary = json.loads(gate_a_summary_path.read_text(encoding="utf-8"))
    if gate_a_summary.get("gate_pass") is not True:
        raise ValueError("Gate A source did not pass")
    if float(gate_a_summary["threshold"]["value"]) != float(
        source["gate_a_threshold"]
    ):
        raise ValueError("Gate A threshold differs from the frozen Gate C config")

    outcomes: dict[str, dict[str, str]] = {}
    with outcomes_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            trajectory_id = str(row["trajectory_id"])
            if trajectory_id in outcomes:
                raise ValueError(f"duplicate trajectory outcome: {trajectory_id}")
            outcomes[trajectory_id] = row
    trajectories = read_jsonl(trajectories_path)
    if len(trajectories) != int(source["expected_trajectories"]):
        raise ValueError("trajectory count differs from the frozen source design")
    if {str(row["trajectory_id"]) for row in trajectories} != set(outcomes):
        raise ValueError("trajectory manifest and outcomes have different IDs")

    horizons = sorted(
        {
            int(labels["primary_horizon"]),
            *[int(value) for value in labels["sensitivity_horizons"]],
        }
    )
    total_turns = int(labels["total_turns"])
    union_horizon = min(horizons)
    reference_layer = int(config["features"]["reference_layer"])
    slope_window = int(config["features"]["slope_window"])
    topic_splits = {str(k): str(v) for k, v in scope["topic_splits"].items()}
    dataset_path = Path(output["dataset"])
    summary_path = Path(output["dataset_summary"])
    output_dir = dataset_path.parent
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"dataset output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    partial_path = dataset_path.with_suffix(dataset_path.suffix + ".partial")

    counts: Counter[tuple[str, str, int, str]] = Counter()
    trajectories_by_cell: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    examples = 0
    with partial_path.open("x", encoding="utf-8") as handle:
        for trajectory in trajectories:
            trajectory_id = str(trajectory["trajectory_id"])
            turns = trajectory["turns"]
            if len(turns) != int(source["expected_turns_per_trajectory"]):
                raise ValueError(f"turn count mismatch for {trajectory_id}")
            if [int(item["turn"]) for item in turns] != list(
                range(1, total_turns + 1)
            ):
                raise ValueError(f"turn schedule mismatch for {trajectory_id}")
            outcome = outcomes[trajectory_id]
            onset_raw = str(outcome["drift_onset_turn"]).strip()
            onset = None if not onset_raw else int(onset_raw)
            topic = str(trajectory["topic"])
            if topic not in topic_splits:
                raise ValueError(f"unmapped Gate C topic: {topic}")
            axis = str(trajectory["axis"])
            condition = str(trajectory["condition"])
            trajectories_by_cell[(axis, topic_splits[topic])].add(trajectory_id)
            for index, turn_record in enumerate(turns):
                turn = int(turn_record["turn"])
                union_eligible, _ = future_drift_label(
                    turn,
                    onset,
                    horizon=union_horizon,
                    total_turns=total_turns,
                )
                if not union_eligible:
                    continue
                activation = projection_features(
                    turns,
                    index,
                    reference_layer=reference_layer,
                    slope_window=slope_window,
                )
                example: dict[str, Any] = {
                    "example_id": f"{trajectory_id}::turn-{turn:02d}",
                    "trajectory_id": trajectory_id,
                    "axis": axis,
                    "condition": condition,
                    "topic": topic,
                    "development_split": topic_splits[topic],
                    "seed": int(trajectory["seed"]),
                    "turn": turn,
                    "drift_onset_turn": onset,
                    "activation_features": activation,
                    "text_prefix": build_text_prefix(turns, index),
                }
                for horizon in horizons:
                    eligible, label = future_drift_label(
                        turn,
                        onset,
                        horizon=horizon,
                        total_turns=total_turns,
                    )
                    example[f"eligible_h{horizon}"] = eligible
                    example[f"label_h{horizon}"] = label if eligible else None
                    if eligible:
                        counts[
                            (
                                axis,
                                topic_splits[topic],
                                horizon,
                                "positive" if label else "negative",
                            )
                        ] += 1
                handle.write(json.dumps(example, sort_keys=True) + "\n")
                examples += 1
    partial_path.rename(dataset_path)

    count_tree: dict[str, Any] = {}
    for (axis, split, horizon, label), value in sorted(counts.items()):
        count_tree.setdefault(axis, {}).setdefault(split, {}).setdefault(
            f"h{horizon}", {}
        )[label] = value
    summary = {
        "protocol": "gate_c_causal_examples_v1",
        "mode": config["mode"],
        "confirmatory": False,
        "examples": examples,
        "source_trajectories": len(trajectories),
        "horizons": horizons,
        "primary_horizon": int(labels["primary_horizon"]),
        "counts": count_tree,
        "trajectory_counts": {
            f"{axis}|{split}": len(ids)
            for (axis, split), ids in sorted(trajectories_by_cell.items())
        },
        "config": str(args.config),
        "config_sha256": sha256(args.config),
        "dataset": str(dataset_path),
        "dataset_sha256": sha256(dataset_path),
        "source_hashes": {
            str(trajectories_path): sha256(trajectories_path),
            str(outcomes_path): sha256(outcomes_path),
            str(gate_a_summary_path): sha256(gate_a_summary_path),
        },
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
