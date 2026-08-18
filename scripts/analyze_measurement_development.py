#!/usr/bin/env python3
"""Calibrate and validate anchored multi-judge persona measurement."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from persona_drift.measurement import (
    anchored_posterior,
    estimate_confusion_matrix,
    group_drift_rates,
    posterior_summary,
    sustained_posterior_drift_onset,
    validation_metrics,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if not rows:
        raise ValueError(f"empty JSONL file: {path}")
    return rows


def index_unique(rows: list[dict[str, Any]], source: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        example_id = str(row.get("example_id", ""))
        if not example_id or example_id in indexed:
            raise ValueError(f"empty or duplicate ID in {source}: {example_id}")
        indexed[example_id] = row
    return indexed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--judges-config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    judges_config = yaml.safe_load(args.judges_config.read_text(encoding="utf-8"))
    output = config["output"]
    root = Path(output["analysis_dir"])
    if root.exists():
        raise FileExistsError(f"refusing to reuse analysis directory: {root}")

    for path_key, hash_key in [
        ("qwen_probe_manifest", "qwen_probe_manifest_sha256"),
        ("persona_template", "persona_template_sha256"),
        ("original_confirmation_summary", "original_confirmation_summary_sha256"),
    ]:
        path = Path(config["source"][path_key])
        if sha256(path) != str(config["source"][hash_key]):
            raise ValueError(f"frozen source hash mismatch: {path}")

    dataset_summary_path = Path(output["dataset_summary"])
    dataset_summary = json.loads(dataset_summary_path.read_text(encoding="utf-8"))
    manifest_path = Path(output["combined_manifest"])
    if sha256(manifest_path) != dataset_summary["combined_manifest_sha256"]:
        raise ValueError("combined measurement manifest hash mismatch")
    manifest_rows = load_jsonl(manifest_path)
    manifest = index_unique(manifest_rows, "measurement manifest")
    expected = int(config["design"]["expected_combined_examples"])
    if len(manifest) != expected:
        raise ValueError("measurement manifest count mismatch")

    judge_ids = list(judges_config["judges"])
    if judge_ids != ["measurement_a", "measurement_b", "measurement_c"]:
        raise ValueError("measurement requires the three frozen judge IDs")
    reviews: dict[str, dict[str, dict[str, Any]]] = {}
    judge_lineage: dict[str, Any] = {}
    for judge_id in judge_ids:
        judge = judges_config["judges"][judge_id]
        path = Path(judge["output"])
        indexed = index_unique(load_jsonl(path), judge_id)
        if set(indexed) != set(manifest):
            raise ValueError(f"judge coverage mismatch: {judge_id}")
        for row in indexed.values():
            if row["judge_model"] != judge["model"]:
                raise ValueError(f"judge model mismatch: {judge_id}")
            if row["judge_revision"] != judge["revision"]:
                raise ValueError(f"judge revision mismatch: {judge_id}")
            score = row["scores"]["trait_alignment"]
            if not isinstance(score, int) or not 0 <= score <= 4:
                raise ValueError(f"invalid trait score: {judge_id}")
        reviews[judge_id] = indexed
        judge_lineage[judge_id] = {
            "model": judge["model"],
            "revision": judge["revision"],
            "output": str(path),
            "output_sha256": sha256(path),
        }

    anchors = [row for row in manifest_rows if "gold_score" in row]
    qwen = [row for row in manifest_rows if "gold_score" not in row]
    if len(anchors) != int(config["design"]["expected_anchors"]):
        raise ValueError("anchor count mismatch")
    if len(qwen) != int(config["design"]["expected_qwen_probes"]):
        raise ValueError("Qwen probe count mismatch")

    alpha = float(config["analysis"]["dirichlet_alpha"])
    axes = list(config["design"]["axes"])
    matrices: dict[str, dict[str, np.ndarray]] = {}
    for axis in axes:
        matrices[axis] = {}
        calibration = [
            row
            for row in anchors
            if row["axis"] == axis and row["anchor_split"] == "calibration"
        ]
        for judge_id in judge_ids:
            matrices[axis][judge_id] = estimate_confusion_matrix(
                [int(row["gold_score"]) for row in calibration],
                [
                    int(reviews[judge_id][row["example_id"]]["scores"]["trait_alignment"])
                    for row in calibration
                ],
                alpha=alpha,
            )

    stable_min_score = int(config["analysis"]["stable_min_score"])
    stable_threshold = float(
        config["analysis"]["stable_probability_threshold"]
    )

    def score_row(row: dict[str, Any]) -> dict[str, Any]:
        axis = str(row["axis"])
        ratings = [
            int(reviews[judge_id][row["example_id"]]["scores"]["trait_alignment"])
            for judge_id in judge_ids
        ]
        posterior = anchored_posterior(
            ratings, [matrices[axis][judge_id] for judge_id in judge_ids]
        )
        return {"ratings": ratings, **posterior_summary(posterior, stable_min_score=stable_min_score)}

    validation = [row for row in anchors if row["anchor_split"] == "validation"]
    validation_scored = [(row, score_row(row)) for row in validation]

    def metrics_for(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
        return validation_metrics(
            [int(row["gold_score"]) for row, _score in rows],
            [score["posterior"] for _row, score in rows],
            stable_min_score=stable_min_score,
            stable_probability_threshold=stable_threshold,
        )

    validation_report = {
        "overall": metrics_for(validation_scored),
        "by_axis": {
            axis: metrics_for(
                [(row, score) for row, score in validation_scored if row["axis"] == axis]
            )
            for axis in axes
        },
    }
    gate = config["analysis"]["validation_gate"]
    checks = {
        "overall_within_one_accuracy": validation_report["overall"]["within_one_accuracy"]
        >= float(gate["min_overall_within_one_accuracy"]),
        "each_axis_within_one_accuracy": all(
            validation_report["by_axis"][axis]["within_one_accuracy"]
            >= float(gate["min_each_axis_within_one_accuracy"])
            for axis in axes
        ),
        "overall_stable_balanced_accuracy": validation_report["overall"]["stable_balanced_accuracy"]
        >= float(gate["min_overall_stable_balanced_accuracy"]),
        "each_axis_stable_balanced_accuracy": all(
            validation_report["by_axis"][axis]["stable_balanced_accuracy"]
            >= float(gate["min_each_axis_stable_balanced_accuracy"])
            for axis in axes
        ),
        "overall_spearman": validation_report["overall"]["spearman_rho"]
        >= float(gate["min_overall_spearman_rho"]),
    }
    measurement_gate_pass = all(checks.values())

    qwen_scored = [(row, score_row(row)) for row in qwen]
    grouped: defaultdict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for row, score in qwen_scored:
        grouped[str(row["trajectory_id"])].append((row, score))
    trajectory_rows: list[dict[str, Any]] = []
    for trajectory_id, values in sorted(grouped.items()):
        ordered = sorted(values, key=lambda value: int(value[0]["checkpoint_turn"]))
        turns = [int(row["checkpoint_turn"]) for row, _score in ordered]
        if turns != [0, 5, 10, 15, 20, 25]:
            raise ValueError(f"checkpoint schedule mismatch: {trajectory_id}")
        probabilities = [float(score["stable_probability"]) for _row, score in ordered]
        onset = sustained_posterior_drift_onset(
            turns,
            probabilities,
            threshold=stable_threshold,
            sustain_checkpoints=int(config["analysis"]["sustain_checkpoints"]),
        )
        first = ordered[0][0]
        trajectory_rows.append(
            {
                "trajectory_id": trajectory_id,
                "axis": first["axis"],
                "condition": first["condition"],
                "topic": first["topic"],
                "seed": first["seed"],
                "drifted": onset is not None,
                "drift_onset_turn": "" if onset is None else onset,
                "baseline_stable_probability": probabilities[0],
                "final_stable_probability": probabilities[-1],
            }
        )
    scientific = group_drift_rates(
        trajectory_rows,
        axes=axes,
        pressure_conditions=["gradual_pressure", "abrupt_pressure"],
        control_conditions=["neutral", "topic_shift"],
    )

    root.mkdir(parents=True, exist_ok=False)
    checkpoint_path = Path(output["checkpoint_scores"])
    checkpoint_fields = [
        "example_id", "trajectory_id", "axis", "condition", "topic", "seed",
        "checkpoint_turn", "measurement_a", "measurement_b", "measurement_c",
        "posterior_mean", "posterior_mode", "stable_probability",
    ]
    with checkpoint_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=checkpoint_fields)
        writer.writeheader()
        for row, score in qwen_scored:
            writer.writerow(
                {
                    **{key: row[key] for key in checkpoint_fields[:7]},
                    "measurement_a": score["ratings"][0],
                    "measurement_b": score["ratings"][1],
                    "measurement_c": score["ratings"][2],
                    "posterior_mean": score["posterior_mean"],
                    "posterior_mode": score["posterior_mode"],
                    "stable_probability": score["stable_probability"],
                }
            )
    trajectory_path = Path(output["trajectory_outcomes"])
    with trajectory_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(trajectory_rows[0]))
        writer.writeheader()
        writer.writerows(trajectory_rows)

    scoring_model = {
        "protocol": "anchored_three_judge_measurement_v1",
        "alpha": alpha,
        "stable_min_score": stable_min_score,
        "stable_probability_threshold": stable_threshold,
        "sustain_checkpoints": int(config["analysis"]["sustain_checkpoints"]),
        "axes": {
            axis: {
                judge_id: matrices[axis][judge_id].tolist() for judge_id in judge_ids
            }
            for axis in axes
        },
        "judges": judge_lineage,
        "anchor_manifest": output["anchor_manifest"],
        "anchor_manifest_sha256": sha256(Path(output["anchor_manifest"])),
    }
    scoring_path = Path(output["scoring_model"])
    scoring_path.write_text(
        json.dumps(scoring_model, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = {
        "protocol": "persona_drift_measurement_development_v1",
        "confirmatory": False,
        "measurement_gate_pass": measurement_gate_pass,
        "measurement_gate_checks": checks,
        "validation": validation_report,
        "qwen_development_outcomes": scientific,
        "qwen_outcomes_used_for_measurement_selection": False,
        "known_previous_judge_prompt_id_leakage_removed": True,
        "future_llama_replication_authorized": measurement_gate_pass,
        "lineage": {
            "config": str(args.config),
            "config_sha256": sha256(args.config),
            "judges_config": str(args.judges_config),
            "judges_config_sha256": sha256(args.judges_config),
            "combined_manifest_sha256": sha256(manifest_path),
            "judges": judge_lineage,
        },
        "artifacts": {
            "scoring_model": str(scoring_path),
            "scoring_model_sha256": sha256(scoring_path),
            "checkpoint_scores": str(checkpoint_path),
            "checkpoint_scores_sha256": sha256(checkpoint_path),
            "trajectory_outcomes": str(trajectory_path),
            "trajectory_outcomes_sha256": sha256(trajectory_path),
        },
    }
    summary_path = Path(output["summary"])
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not measurement_gate_pass:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
