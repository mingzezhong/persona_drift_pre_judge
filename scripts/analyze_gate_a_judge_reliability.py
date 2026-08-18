#!/usr/bin/env python3
"""Report per-judge Gate A sensitivity instead of relying only on score means."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.stats import spearmanr
import yaml

from persona_drift.gate_a import sustained_drift_onset
from scripts.analyze_gate_a import resolve_consistency_threshold


REVIEWER_COLUMNS = (
    "reviewer_a_trait_alignment",
    "reviewer_b_trait_alignment",
)


def rate(values: Iterable[bool]) -> float:
    numbers = [float(value) for value in values]
    if not numbers:
        raise ValueError("cannot compute a rate from an empty group")
    return float(mean(numbers))


def score_agreement(
    score_pairs: Sequence[Sequence[float]],
) -> dict[str, Any]:
    values = np.asarray(score_pairs, dtype=float)
    if values.ndim != 2 or values.shape[1] != 2 or len(values) == 0:
        raise ValueError("score pairs must be a non-empty [n, 2] matrix")
    if not np.isfinite(values).all():
        raise ValueError("score pairs must be finite")
    rho, p_value = spearmanr(values[:, 0], values[:, 1])
    pair_counts = Counter((float(a), float(b)) for a, b in values)
    return {
        "examples": int(len(values)),
        "exact_agreement": float(np.mean(values[:, 0] == values[:, 1])),
        "mean_absolute_difference": float(
            np.mean(np.abs(values[:, 0] - values[:, 1]))
        ),
        "mean_reviewer_a": float(np.mean(values[:, 0])),
        "mean_reviewer_b": float(np.mean(values[:, 1])),
        "mean_a_minus_b": float(np.mean(values[:, 0] - values[:, 1])),
        "spearman_rho": None if math.isnan(float(rho)) else float(rho),
        "spearman_p_value": (
            None if math.isnan(float(p_value)) else float(p_value)
        ),
        "score_pair_counts": {
            f"{a:g}|{b:g}": count for (a, b), count in sorted(pair_counts.items())
        },
    }


def reviewer_analysis(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    reviewer_column: str,
) -> dict[str, Any]:
    analysis = config["analysis"]
    reviewer_checkpoint_rows = [
        {
            "split": row["split"],
            "condition": row["condition"],
            "consistency_score": float(row[reviewer_column]),
        }
        for row in rows
    ]
    threshold, threshold_metadata = resolve_consistency_threshold(
        reviewer_checkpoint_rows, analysis
    )
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["trajectory_id"])].append(row)

    outcomes: list[dict[str, Any]] = []
    for trajectory_id, trajectory_rows in sorted(grouped.items()):
        ordered = sorted(trajectory_rows, key=lambda row: int(row["checkpoint_turn"]))
        turns = [int(row["checkpoint_turn"]) for row in ordered]
        scores = [float(row[reviewer_column]) for row in ordered]
        onset = sustained_drift_onset(
            turns,
            scores,
            threshold=threshold,
            sustain_checkpoints=int(analysis["sustain_checkpoints"]),
        )
        outcomes.append(
            {
                "trajectory_id": trajectory_id,
                "axis": ordered[0]["axis"],
                "condition": ordered[0]["condition"],
                "split": ordered[0]["split"],
                "drifted": onset is not None,
                "onset": onset,
                "baseline": scores[0],
                "final": scores[-1],
                "change": scores[-1] - scores[0],
            }
        )

    confirmation = [
        outcome
        for outcome in outcomes
        if outcome["split"] == analysis["confirmation_split"]
    ]
    pressure_conditions = list(analysis["pressure_conditions"])
    control_conditions = list(analysis["control_conditions"])
    by_axis: dict[str, Any] = {}
    for axis in config["data"]["axes"]:
        pressure = [
            outcome
            for outcome in confirmation
            if outcome["axis"] == axis
            and outcome["condition"] in pressure_conditions
        ]
        control = [
            outcome
            for outcome in confirmation
            if outcome["axis"] == axis
            and outcome["condition"] in control_conditions
        ]
        pressure_rate = rate(outcome["drifted"] for outcome in pressure)
        control_rate = rate(outcome["drifted"] for outcome in control)
        by_axis[str(axis)] = {
            "pressure_drift_rate": pressure_rate,
            "control_drift_rate": control_rate,
            "risk_difference": pressure_rate - control_rate,
            "mean_pressure_final_change": float(
                mean(float(outcome["change"]) for outcome in pressure)
            ),
            "mean_control_final_change": float(
                mean(float(outcome["change"]) for outcome in control)
            ),
        }
    by_condition: dict[str, Any] = {}
    for condition in config["data"]["conditions"]:
        condition_rows = [
            outcome for outcome in confirmation if outcome["condition"] == condition
        ]
        by_condition[str(condition)] = {
            "drift_rate": rate(outcome["drifted"] for outcome in condition_rows),
            "mean_final_change": float(
                mean(float(outcome["change"]) for outcome in condition_rows)
            ),
        }
    return {
        "threshold": threshold,
        "threshold_metadata": threshold_metadata,
        "by_axis": by_axis,
        "by_condition": by_condition,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--checkpoint-scores", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    with args.checkpoint_scores.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    expected = (
        len(config["data"]["axes"])
        * len(config["data"]["conditions"])
        * len(config["data"]["topics"])
        * len(config["data"]["seeds"])
        * len(config["data"]["checkpoint_turns"])
    )
    if len(rows) != expected:
        raise ValueError("checkpoint-score count differs from the frozen design")
    pairs = [
        [float(row[REVIEWER_COLUMNS[0]]), float(row[REVIEWER_COLUMNS[1]])]
        for row in rows
    ]
    per_reviewer = {
        column: reviewer_analysis(rows, config, column)
        for column in REVIEWER_COLUMNS
    }
    directional = {
        axis: all(
            per_reviewer[column]["by_axis"][axis]["risk_difference"] > 0
            for column in REVIEWER_COLUMNS
        )
        for axis in config["data"]["axes"]
    }
    report = {
        "protocol": "gate_a_two_judge_sensitivity_v1",
        "agreement": score_agreement(pairs),
        "per_reviewer": per_reviewer,
        "both_reviewers_positive_pressure_control_difference_by_axis": directional,
        "all_axes_directionally_confirmed": all(directional.values()),
        "config": str(args.config),
        "checkpoint_scores": str(args.checkpoint_scores),
    }
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

