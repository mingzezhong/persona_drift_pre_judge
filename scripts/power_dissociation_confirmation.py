#!/usr/bin/env python3
"""Trajectory-resampling precision analysis for dissociation confirmation."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if not 0 <= successes <= total or total <= 0:
        raise ValueError("invalid binomial count")
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = (proportion + z * z / (2.0 * total)) / denominator
    half = z * np.sqrt(
        proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)
    ) / denominator
    return [float(max(0.0, centre - half)), float(min(1.0, centre + half))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--v2-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260920)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    with args.predictions.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("empty development prediction table")
    by_condition: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        by_condition[row["condition"]][row["trajectory_id"]].append(row)
    if set(len(groups) for groups in by_condition.values()) != {10}:
        raise ValueError("expected 10 development trajectories per condition")

    rng = np.random.default_rng(args.seed)
    target_totals = [40, 80, 120, 160]
    precision: dict[str, dict[str, float | int | list[float]]] = {}
    for target_total in target_totals:
        per_condition = target_total // len(by_condition)
        if per_condition * len(by_condition) != target_total:
            raise ValueError("target trajectory total must balance conditions")
        deltas = np.empty(args.samples, dtype=float)
        for iteration in range(args.samples):
            sampled: list[dict[str, str]] = []
            for condition in sorted(by_condition):
                groups = by_condition[condition]
                ids = sorted(groups)
                selected = rng.choice(ids, size=per_condition, replace=True)
                for trajectory_id in selected:
                    sampled.extend(groups[str(trajectory_id)])
            y = np.asarray([int(row["label"]) for row in sampled], dtype=int)
            text = np.asarray(
                [float(row["text_probability"]) for row in sampled]
            )
            combined = np.asarray(
                [float(row["combined_probability"]) for row in sampled]
            )
            deltas[iteration] = average_precision_score(y, combined) - average_precision_score(y, text)
        precision[str(target_total)] = {
            "trajectories": target_total,
            "per_condition": per_condition,
            "median_delta_auprc": float(np.median(deltas)),
            "empirical_95_interval": [
                float(value) for value in np.quantile(deltas, [0.025, 0.975])
            ],
            "probability_estimate_below_0_05": float(np.mean(deltas < 0.05)),
        }

    v2 = json.loads(args.v2_summary.read_text(encoding="utf-8"))
    negative = v2["negative_control"]
    if negative["combined"]["trajectories_with_any_alarm"] != 20:
        raise ValueError("unexpected development negative-control alarm count")
    recommended_per_axis = 120
    pressure_trajectories_per_axis = 60
    result = {
        "protocol": "gate_c_dissociation_confirmation_power_v1",
        "development_only": True,
        "method": "complete-trajectory resampling within condition",
        "bootstrap_samples_per_target": args.samples,
        "seed": args.seed,
        "smallest_useful_incremental_auprc": 0.05,
        "precision_by_positive_axis_trajectory_total": precision,
        "recommended_design": {
            "topics": 3,
            "conditions": 4,
            "seeds_per_topic": 10,
            "trajectories_per_axis": recommended_per_axis,
            "axes": 2,
            "total_trajectories": 240,
            "pressure_trajectories_per_axis": pressure_trajectories_per_axis,
            "rationale": "N=120 has empirical 97.5th-percentile delta AUPRC below 0.05 and provides 60 resistant pressure trajectories",
        },
        "binomial_precision_at_recommended_design": {
            "zero_of_60_drift_wilson_95ci": wilson(0, 60),
            "sixty_of_60_alarm_wilson_95ci": wilson(60, 60),
            "zero_of_60_control_alarm_wilson_95ci": wilson(0, 60),
        },
        "inputs": {
            "development_predictions": str(args.predictions),
            "development_predictions_sha256": sha256(args.predictions),
            "v2_summary": str(args.v2_summary),
            "v2_summary_sha256": sha256(args.v2_summary),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
