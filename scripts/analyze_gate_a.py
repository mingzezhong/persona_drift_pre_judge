#!/usr/bin/env python3
"""Analyze sustained output-level persona drift for Gate A."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

import numpy as np
import yaml

from persona_drift.gate_a import (
    calibrate_consistency_threshold,
    stratified_risk_difference_bootstrap,
    sustained_drift_onset,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"non-object JSON at {path}:{line_number}")
            records.append(record)
    if not records:
        raise ValueError(f"empty JSONL file: {path}")
    return records


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def rate(values: Iterable[bool]) -> float:
    numbers = [float(value) for value in values]
    if not numbers:
        raise ValueError("cannot compute a rate from an empty group")
    return float(mean(numbers))


def resolve_analysis_axes(
    all_axes: list[str], analysis: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Resolve scoped primary and negative-control axes with legacy defaults."""
    positive_axes = list(analysis.get("positive_axes", all_axes))
    negative_control_axes = list(analysis.get("negative_control_axes", []))
    if not positive_axes:
        raise ValueError("analysis.positive_axes must not be empty")
    unknown_positive = sorted(set(positive_axes) - set(all_axes))
    unknown_negative = sorted(set(negative_control_axes) - set(all_axes))
    overlap = sorted(set(positive_axes) & set(negative_control_axes))
    if unknown_positive:
        raise ValueError(f"unknown positive axes: {unknown_positive}")
    if unknown_negative:
        raise ValueError(f"unknown negative-control axes: {unknown_negative}")
    if overlap:
        raise ValueError(
            f"axes cannot be both positive and negative controls: {overlap}"
        )
    if len(positive_axes) != len(set(positive_axes)):
        raise ValueError("analysis.positive_axes contains duplicates")
    if len(negative_control_axes) != len(set(negative_control_axes)):
        raise ValueError("analysis.negative_control_axes contains duplicates")
    return positive_axes, negative_control_axes


def resolve_consistency_threshold(
    checkpoint_rows: list[dict[str, Any]], analysis: dict[str, Any]
) -> tuple[float, dict[str, Any]]:
    """Use a preregistered external threshold or the legacy calibration rule."""

    if "fixed_threshold" in analysis:
        threshold = float(analysis["fixed_threshold"])
        if not np.isfinite(threshold) or not 0.0 <= threshold <= 4.0:
            raise ValueError("analysis.fixed_threshold must lie in [0, 4]")
        source = str(analysis.get("fixed_threshold_source", "")).strip()
        source_sha256 = str(
            analysis.get("fixed_threshold_source_sha256", "")
        ).strip()
        if not source or len(source_sha256) != 64:
            raise ValueError(
                "fixed threshold requires source and 64-character SHA256"
            )
        return threshold, {
            "value": threshold,
            "source": "fixed_external_preregistered",
            "fixed_threshold_source": source,
            "fixed_threshold_source_sha256": source_sha256,
            "calibration_observations": 0,
        }

    calibration_scores = [
        row["consistency_score"]
        for row in checkpoint_rows
        if row["split"] == analysis["calibration_split"]
        and row["condition"] in analysis["clean_calibration_conditions"]
    ]
    threshold = calibrate_consistency_threshold(
        calibration_scores,
        quantile=float(analysis["threshold_quantile"]),
        rubric_floor=float(analysis["rubric_alignment_floor"]),
    )
    return threshold, {
        "value": threshold,
        "calibration_split": analysis["calibration_split"],
        "clean_conditions": list(analysis["clean_calibration_conditions"]),
        "quantile": float(analysis["threshold_quantile"]),
        "rubric_floor": float(analysis["rubric_alignment_floor"]),
        "calibration_observations": len(calibration_scores),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--reviewed-manifest", type=Path, required=True)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    analysis = config["analysis"]
    axes = list(config["data"]["axes"])
    positive_axes, negative_control_axes = resolve_analysis_axes(axes, analysis)
    records = load_jsonl(args.reviewed_manifest)
    expected_checkpoints = [int(turn) for turn in config["data"]["checkpoint_turns"]]
    expected_trajectories = (
        len(axes)
        * len(config["data"]["conditions"])
        * len(config["data"]["topics"])
        * len(config["data"]["seeds"])
    )
    if len(records) != expected_trajectories * len(expected_checkpoints):
        raise ValueError("reviewed probe count differs from the frozen design")

    checkpoint_rows: list[dict[str, Any]] = []
    for record in records:
        reviewers = record.get("judge_score", {}).get("reviewers", [])
        if len(reviewers) != 2:
            raise ValueError(f"{record['example_id']} does not have two reviews")
        scores = [float(item["scores"]["trait_alignment"]) for item in reviewers]
        consistency = float(mean(scores))
        checkpoint_rows.append(
            {
                "example_id": record["example_id"],
                "trajectory_id": record["trajectory_id"],
                "axis": record["axis"],
                "condition": record["condition"],
                "topic": record["topic"],
                "split": record["split"],
                "seed": int(record["seed"]),
                "checkpoint_turn": int(record["checkpoint_turn"]),
                "reviewer_a_trait_alignment": scores[0],
                "reviewer_b_trait_alignment": scores[1],
                "consistency_score": consistency,
                "decision_disagreement": bool(
                    record["judge_score"]["decision_disagreement"]
                ),
                "consensus_accepted": bool(record["accepted"]),
                "parsed_choice": record.get("parsed_choice"),
                "forced_choice_aligned": record.get("forced_choice_aligned"),
                "pre_response_projection_layer20": float(
                    record["pre_response_projection_layer20"]
                ),
                "response_projection_layer20": float(
                    record["response_projection_layer20"]
                ),
            }
        )

    threshold, threshold_metadata = resolve_consistency_threshold(
        checkpoint_rows, analysis
    )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in checkpoint_rows:
        grouped[row["trajectory_id"]].append(row)
    if len(grouped) != expected_trajectories:
        raise ValueError("reviewed probes do not cover the expected trajectories")

    trajectory_rows: list[dict[str, Any]] = []
    for trajectory, rows in sorted(grouped.items()):
        ordered = sorted(rows, key=lambda row: row["checkpoint_turn"])
        turns = [row["checkpoint_turn"] for row in ordered]
        if turns != expected_checkpoints:
            raise ValueError(f"checkpoint schedule mismatch for {trajectory}")
        scores = [row["consistency_score"] for row in ordered]
        onset = sustained_drift_onset(
            turns,
            scores,
            threshold=threshold,
            sustain_checkpoints=int(analysis["sustain_checkpoints"]),
        )
        aligned_choices = [
            row["forced_choice_aligned"]
            for row in ordered
            if isinstance(row["forced_choice_aligned"], bool)
        ]
        trajectory_rows.append(
            {
                "trajectory_id": trajectory,
                "axis": ordered[0]["axis"],
                "condition": ordered[0]["condition"],
                "topic": ordered[0]["topic"],
                "split": ordered[0]["split"],
                "seed": ordered[0]["seed"],
                "drifted": onset is not None,
                "drift_onset_turn": "" if onset is None else onset,
                "baseline_consistency": scores[0],
                "final_consistency": scores[-1],
                "consistency_change": scores[-1] - scores[0],
                "forced_choice_parse_rate": len(aligned_choices) / len(ordered),
                "forced_choice_alignment_rate": (
                    "" if not aligned_choices else rate(aligned_choices)
                ),
            }
        )

    confirmation = [
        row
        for row in trajectory_rows
        if row["split"] == analysis["confirmation_split"]
    ]
    pressure_conditions = list(analysis["pressure_conditions"])
    control_conditions = list(analysis["control_conditions"])
    by_condition: dict[str, Any] = {}
    for condition in config["data"]["conditions"]:
        rows = [row for row in confirmation if row["condition"] == condition]
        by_condition[condition] = {
            "trajectories": len(rows),
            "drift_count": sum(bool(row["drifted"]) for row in rows),
            "drift_rate": rate(bool(row["drifted"]) for row in rows),
            "mean_consistency_change": float(
                mean(float(row["consistency_change"]) for row in rows)
            ),
        }

    primary_confirmation = [
        row for row in confirmation if row["axis"] in positive_axes
    ]
    primary_by_condition: dict[str, Any] = {}
    for condition in config["data"]["conditions"]:
        rows = [
            row for row in primary_confirmation if row["condition"] == condition
        ]
        primary_by_condition[condition] = {
            "trajectories": len(rows),
            "drift_count": sum(bool(row["drifted"]) for row in rows),
            "drift_rate": rate(bool(row["drifted"]) for row in rows),
            "mean_consistency_change": float(
                mean(float(row["consistency_change"]) for row in rows)
            ),
        }

    pressure_rows = [
        row
        for row in primary_confirmation
        if row["condition"] in pressure_conditions
    ]
    control_rows = [
        row
        for row in primary_confirmation
        if row["condition"] in control_conditions
    ]
    pressure_rate = rate(bool(row["drifted"]) for row in pressure_rows)
    control_rate = rate(bool(row["drifted"]) for row in control_rows)
    risk_difference = pressure_rate - control_rate

    by_axis: dict[str, Any] = {}
    drift_cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for row in primary_confirmation:
        drift_cells[(str(row["axis"]), str(row["condition"]))].append(
            bool(row["drifted"])
        )
    for axis in axes:
        axis_pressure = [
            bool(row["drifted"])
            for row in confirmation
            if row["axis"] == axis and row["condition"] in pressure_conditions
        ]
        axis_control = [
            bool(row["drifted"])
            for row in confirmation
            if row["axis"] == axis and row["condition"] in control_conditions
        ]
        axis_pressure_rate = rate(axis_pressure)
        axis_control_rate = rate(axis_control)
        by_axis[axis] = {
            "pressure_drift_rate": axis_pressure_rate,
            "control_drift_rate": axis_control_rate,
            "risk_difference": axis_pressure_rate - axis_control_rate,
        }
    risk_difference_ci = stratified_risk_difference_bootstrap(
        drift_cells,
        pressure_conditions=pressure_conditions,
        control_conditions=control_conditions,
        samples=int(analysis["bootstrap_samples"]),
        seed=int(analysis["bootstrap_seed"]),
    )

    profiles: dict[str, dict[str, Any]] = {}
    for condition in config["data"]["conditions"]:
        profiles[condition] = {}
        for checkpoint in expected_checkpoints:
            rows = [
                row
                for row in checkpoint_rows
                if row["split"] == analysis["confirmation_split"]
                and row["condition"] == condition
                and row["checkpoint_turn"] == checkpoint
            ]
            parsed = [
                row["forced_choice_aligned"]
                for row in rows
                if isinstance(row["forced_choice_aligned"], bool)
            ]
            profiles[condition][str(checkpoint)] = {
                "mean_consistency": float(
                    mean(float(row["consistency_score"]) for row in rows)
                ),
                "forced_choice_parse_rate": len(parsed) / len(rows),
                "forced_choice_alignment_rate": (
                    None if not parsed else rate(parsed)
                ),
            }

    candidate = analysis["candidate_pilot_gate"]
    checks = {
        "combined_pressure_drift_rate": pressure_rate
        >= float(candidate["min_combined_pressure_drift_rate"]),
        "combined_control_drift_rate": control_rate
        <= float(candidate["max_combined_control_drift_rate"]),
        "pressure_control_risk_difference": risk_difference
        >= float(candidate["min_pressure_control_risk_difference"]),
        "each_pressure_condition_drift_rate": all(
            primary_by_condition[condition]["drift_rate"]
            >= float(candidate["min_each_pressure_condition_drift_rate"])
            for condition in pressure_conditions
        ),
        "each_control_condition_drift_rate": all(
            primary_by_condition[condition]["drift_rate"]
            <= float(candidate["max_each_control_condition_drift_rate"])
            for condition in control_conditions
        ),
        "positive_difference_for_each_axis": (
            not bool(candidate["require_positive_difference_for_each_axis"])
            or all(by_axis[axis]["risk_difference"] > 0 for axis in positive_axes)
        ),
        "risk_difference_95ci_above_zero": (
            not bool(candidate["require_risk_difference_95ci_above_zero"])
            or risk_difference_ci[0] > 0
        ),
    }
    if "max_negative_control_pressure_drift_rate" in candidate:
        checks["negative_control_pressure_drift_rate"] = all(
            by_axis[axis]["pressure_drift_rate"]
            <= float(candidate["max_negative_control_pressure_drift_rate"])
            for axis in negative_control_axes
        )
    gate_eligible = bool(analysis["gate_eligible"])
    gate_pass: bool | None = all(checks.values()) if gate_eligible else None

    output_dir = Path(config["data"]["output_dir"]) / "analysis"
    output_dir.mkdir(parents=True, exist_ok=False)
    checkpoint_path = output_dir / "checkpoint_scores.csv"
    trajectories_path = output_dir / "trajectory_outcomes.csv"
    write_csv(checkpoint_path, checkpoint_rows)
    write_csv(trajectories_path, trajectory_rows)
    summary = {
        "protocol": "gate_a_sustained_output_drift_v1",
        "mode": config["mode"],
        "gate_eligible": gate_eligible,
        "gate_pass": gate_pass,
        "analysis_policy": "all_trajectories_no_review_filtering",
        "analysis_scope": {
            "positive_axes": positive_axes,
            "negative_control_axes": negative_control_axes,
        },
        "consistency_score": config["measurement"]["primary_score"],
        "threshold": threshold_metadata,
        "sustain_checkpoints": int(analysis["sustain_checkpoints"]),
        "confirmation_split": analysis["confirmation_split"],
        "confirmation_trajectories": len(confirmation),
        "by_condition": by_condition,
        "primary_by_condition": primary_by_condition,
        "by_axis": by_axis,
        "negative_controls": {
            axis: by_axis[axis] for axis in negative_control_axes
        },
        "combined": {
            "pressure_drift_rate": pressure_rate,
            "control_drift_rate": control_rate,
            "risk_difference": risk_difference,
            "risk_difference_95ci": risk_difference_ci,
        },
        "checkpoint_profiles": profiles,
        "candidate_gate_thresholds": candidate,
        "candidate_gate_checks": checks,
        "reviewed_manifest": str(args.reviewed_manifest),
        "reviewed_manifest_sha256": sha256(args.reviewed_manifest),
        "config": str(args.config),
        "config_sha256": sha256(args.config),
        "checkpoint_scores": str(checkpoint_path),
        "checkpoint_scores_sha256": sha256(checkpoint_path),
        "trajectory_outcomes": str(trajectories_path),
        "trajectory_outcomes_sha256": sha256(trajectories_path),
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if gate_eligible and gate_pass is not True:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
