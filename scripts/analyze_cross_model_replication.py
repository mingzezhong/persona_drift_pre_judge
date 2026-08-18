#!/usr/bin/env python3
"""Apply the frozen anchored measure to untouched cross-model probe responses."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

from persona_drift.measurement import (
    anchored_posterior,
    group_drift_rates,
    posterior_summary,
    sustained_posterior_drift_onset,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if not rows:
        raise ValueError(f"empty JSONL file: {path}")
    return rows


def index_unique(rows: Sequence[dict[str, Any]], source: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        example_id = str(row.get("example_id", ""))
        if not example_id or example_id in indexed:
            raise ValueError(f"empty or duplicate ID in {source}: {example_id}")
        indexed[example_id] = row
    return indexed


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError("invalid binomial count")
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = (proportion + z * z / (2.0 * total)) / denominator
    half = z * np.sqrt(
        proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)
    ) / denominator
    return [float(max(0.0, centre - half)), float(min(1.0, centre + half))]


def binary_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values = [bool(row["drifted"]) for row in rows]
    if not values:
        raise ValueError("empty drift group")
    count = int(sum(values))
    return {
        "drift_count": count,
        "trajectories": len(values),
        "drift_rate": float(count / len(values)),
        "wilson_95ci": wilson_interval(count, len(values)),
    }


def paired_cluster_risk_difference(
    rows: Sequence[Mapping[str, Any]],
    *,
    pressure_conditions: Sequence[str],
    control_conditions: Sequence[str],
    samples: int,
    seed: int,
) -> dict[str, Any]:
    pressure = set(pressure_conditions)
    control = set(control_conditions)
    clusters: defaultdict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[(str(row["topic"]), int(row["seed"]))].append(row)
    differences: list[float] = []
    for key, group in sorted(clusters.items()):
        pressure_values = [bool(row["drifted"]) for row in group if row["condition"] in pressure]
        control_values = [bool(row["drifted"]) for row in group if row["condition"] in control]
        if len(pressure_values) != len(pressure) or len(control_values) != len(control):
            raise ValueError(f"incomplete paired condition cluster: {key}")
        differences.append(float(np.mean(pressure_values) - np.mean(control_values)))
    if not differences or samples <= 0:
        raise ValueError("invalid paired bootstrap design")
    values = np.asarray(differences, dtype=float)
    rng = np.random.default_rng(seed)
    draws = np.empty(samples, dtype=float)
    for index in range(samples):
        selected = rng.integers(0, len(values), size=len(values))
        draws[index] = float(np.mean(values[selected]))
    return {
        "point": float(np.mean(values)),
        "95ci": [float(value) for value in np.quantile(draws, [0.025, 0.975])],
        "samples": samples,
        "seed": seed,
        "clusters": len(values),
        "cluster_unit": "topic_seed_with_paired_conditions",
    }


def condition_summaries(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    conditions = sorted({str(row["condition"]) for row in rows})
    return {
        condition: binary_summary([row for row in rows if row["condition"] == condition])
        for condition in conditions
    }


def raw_judge_trajectory_rows(
    grouped: Mapping[str, list[tuple[dict[str, Any], dict[str, Any]]]],
    *,
    judge_ids: Sequence[str],
    stable_min_score: int,
    sustain_checkpoints: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trajectory_id, values in sorted(grouped.items()):
        ordered = sorted(values, key=lambda value: int(value[0]["checkpoint_turn"]))
        turns = [int(row["checkpoint_turn"]) for row, _score in ordered]
        first = ordered[0][0]
        for judge_index, judge_id in enumerate(judge_ids):
            stable = [
                1.0 if int(score["ratings"][judge_index]) >= stable_min_score else 0.0
                for _row, score in ordered
            ]
            onset = sustained_posterior_drift_onset(
                turns,
                stable,
                threshold=0.5,
                sustain_checkpoints=sustain_checkpoints,
            )
            rows.append(
                {
                    "judge_id": judge_id,
                    "trajectory_id": trajectory_id,
                    "axis": first["axis"],
                    "condition": first["condition"],
                    "topic": first["topic"],
                    "seed": first["seed"],
                    "drifted": onset is not None,
                    "drift_onset_turn": "" if onset is None else onset,
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    data = config["data"]
    measurement = config["measurement"]
    analysis = config["analysis"]
    output = config["output"]

    output_root = Path(output["analysis_dir"])
    if output_root.exists():
        raise FileExistsError(f"refusing to reuse analysis directory: {output_root}")
    for key, hash_key in [
        ("scoring_model", "scoring_model_sha256"),
        ("development_summary", "development_summary_sha256"),
        ("judges_config", "judges_config_sha256"),
    ]:
        path = Path(measurement[key])
        if sha256(path) != str(measurement[hash_key]):
            raise ValueError(f"frozen measurement input hash mismatch: {path}")
    template_path = Path(data["template"])
    if sha256(template_path) != str(config["provenance"]["template_sha256"]):
        raise ValueError("cross-model template hash mismatch")
    vector_path = Path(config["vectors"]["path"])
    vector_summary_path = Path(config["vectors"]["summary"])
    if sha256(vector_path) != str(config["vectors"]["sha256"]):
        raise ValueError("cross-model vector hash mismatch")
    if sha256(vector_summary_path) != str(config["vectors"]["summary_sha256"]):
        raise ValueError("cross-model vector-summary hash mismatch")

    development = json.loads(Path(measurement["development_summary"]).read_text(encoding="utf-8"))
    if development.get("measurement_gate_pass") is not True or development.get("future_llama_replication_authorized") is not True:
        raise ValueError("measurement development did not authorize replication")
    scoring = json.loads(Path(measurement["scoring_model"]).read_text(encoding="utf-8"))
    if scoring.get("protocol") != measurement["protocol"]:
        raise ValueError("unexpected frozen scoring protocol")
    judges_config = yaml.safe_load(Path(measurement["judges_config"]).read_text(encoding="utf-8"))
    judge_ids = list(judges_config["judges"])
    if judge_ids != ["measurement_a", "measurement_b", "measurement_c"]:
        raise ValueError("unexpected frozen judge IDs")

    root = Path(data["output_dir"])
    merge_summary_path = root / "merge_summary.json"
    merge_summary = json.loads(merge_summary_path.read_text(encoding="utf-8"))
    if merge_summary.get("config_sha256") != sha256(args.config):
        raise ValueError("merged data use a different generation config")
    if merge_summary.get("generation_gate_pass") is not True:
        raise ValueError("generation-quality gate did not pass")
    for key in ("expected_trajectories", "expected_main_turns", "expected_probes"):
        observed_key = {"expected_trajectories": "trajectories", "expected_main_turns": "main_turns", "expected_probes": "probes"}[key]
        if int(merge_summary[observed_key]) != int(data[key]):
            raise ValueError(f"merged count mismatch: {observed_key}")
    probes_path = root / "probes.jsonl"
    if sha256(probes_path) != merge_summary["probes_sha256"]:
        raise ValueError("probe-manifest hash mismatch")
    probes = load_jsonl(probes_path)
    manifest = index_unique(probes, "cross-model probes")

    reviews: dict[str, dict[str, dict[str, Any]]] = {}
    judge_lineage: dict[str, Any] = {}
    for judge_id in judge_ids:
        judge = judges_config["judges"][judge_id]
        frozen_judge = scoring["judges"][judge_id]
        if judge["model"] != frozen_judge["model"] or judge["revision"] != frozen_judge["revision"]:
            raise ValueError(f"judge identity differs from scoring model: {judge_id}")
        path = Path(judge["output"])
        indexed = index_unique(load_jsonl(path), judge_id)
        if set(indexed) != set(manifest):
            raise ValueError(f"judge coverage mismatch: {judge_id}")
        for row in indexed.values():
            if row["judge_model"] != judge["model"] or row["judge_revision"] != judge["revision"]:
                raise ValueError(f"judge output lineage mismatch: {judge_id}")
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

    stable_min_score = int(measurement["stable_min_score"])
    stable_threshold = float(measurement["stable_probability_threshold"])
    sustain = int(measurement["sustain_checkpoints"])

    def score_row(row: dict[str, Any]) -> dict[str, Any]:
        axis = str(row["axis"])
        ratings = [int(reviews[judge_id][row["example_id"]]["scores"]["trait_alignment"]) for judge_id in judge_ids]
        matrices = [np.asarray(scoring["axes"][axis][judge_id], dtype=float) for judge_id in judge_ids]
        posterior = anchored_posterior(ratings, matrices)
        return {"ratings": ratings, **posterior_summary(posterior, stable_min_score=stable_min_score)}

    scored = [(row, score_row(row)) for row in probes]
    grouped: defaultdict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for row, score in scored:
        grouped[str(row["trajectory_id"])].append((row, score))
    trajectory_rows: list[dict[str, Any]] = []
    expected_turns = [int(value) for value in data["checkpoint_turns"]]
    for trajectory_id, values in sorted(grouped.items()):
        ordered = sorted(values, key=lambda value: int(value[0]["checkpoint_turn"]))
        turns = [int(row["checkpoint_turn"]) for row, _score in ordered]
        if turns != expected_turns:
            raise ValueError(f"checkpoint schedule mismatch: {trajectory_id}")
        probabilities = [float(score["stable_probability"]) for _row, score in ordered]
        onset = sustained_posterior_drift_onset(
            turns, probabilities, threshold=stable_threshold, sustain_checkpoints=sustain
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
    if len(trajectory_rows) != int(data["expected_trajectories"]):
        raise ValueError("trajectory outcome count mismatch")

    axes = [str(axis) for axis in data["axes"]]
    pressure_conditions = [str(value) for value in analysis["pressure_conditions"]]
    control_conditions = [str(value) for value in analysis["control_conditions"]]
    rates = group_drift_rates(
        trajectory_rows,
        axes=axes,
        pressure_conditions=pressure_conditions,
        control_conditions=control_conditions,
    )
    by_axis = {axis: [row for row in trajectory_rows if row["axis"] == axis] for axis in axes}
    positive_axis = str(analysis["positive_axis"])
    resistant_axis = str(analysis["resistant_axis"])
    positive_conditions = condition_summaries(by_axis[positive_axis])
    resistant_conditions = condition_summaries(by_axis[resistant_axis])
    positive_pressure = binary_summary([row for row in by_axis[positive_axis] if row["condition"] in pressure_conditions])
    positive_control = binary_summary([row for row in by_axis[positive_axis] if row["condition"] in control_conditions])
    resistant_pressure = binary_summary([row for row in by_axis[resistant_axis] if row["condition"] in pressure_conditions])
    resistant_control = binary_summary([row for row in by_axis[resistant_axis] if row["condition"] in control_conditions])
    risk_difference = paired_cluster_risk_difference(
        by_axis[positive_axis],
        pressure_conditions=pressure_conditions,
        control_conditions=control_conditions,
        samples=int(analysis["bootstrap_samples"]),
        seed=int(analysis["bootstrap_seed"]),
    )

    criteria = analysis["primary_criteria"]
    checks = {
        "positive_pressure_rate": positive_pressure["drift_rate"] >= float(criteria["min_positive_pressure_drift_rate"]),
        "positive_control_rate": positive_control["drift_rate"] <= float(criteria["max_positive_control_drift_rate"]),
        "positive_risk_difference": risk_difference["point"] >= float(criteria["min_positive_pressure_control_risk_difference"]),
        "positive_risk_difference_ci": (not bool(criteria["require_positive_risk_difference_95ci_above_zero"]) or risk_difference["95ci"][0] > 0.0),
        "each_positive_pressure_condition": all(positive_conditions[condition]["drift_rate"] >= float(criteria["min_each_positive_pressure_condition_drift_rate"]) for condition in pressure_conditions),
        "each_positive_control_condition": all(positive_conditions[condition]["drift_rate"] <= float(criteria["max_each_positive_control_condition_drift_rate"]) for condition in control_conditions),
        "resistant_pressure_wilson_upper": resistant_pressure["wilson_95ci"][1] <= float(criteria["max_resistant_pressure_drift_wilson_upper"]),
        "resistant_control_wilson_upper": resistant_control["wilson_95ci"][1] <= float(criteria["max_resistant_control_drift_wilson_upper"]),
    }

    per_judge_rows = raw_judge_trajectory_rows(
        grouped,
        judge_ids=judge_ids,
        stable_min_score=stable_min_score,
        sustain_checkpoints=sustain,
    )
    per_judge_rates = {
        judge_id: group_drift_rates(
            [row for row in per_judge_rows if row["judge_id"] == judge_id],
            axes=axes,
            pressure_conditions=pressure_conditions,
            control_conditions=control_conditions,
        )
        for judge_id in judge_ids
    }

    output_root.mkdir(parents=True, exist_ok=False)
    checkpoint_path = Path(output["checkpoint_scores"])
    checkpoint_fields = [
        "example_id", "trajectory_id", "axis", "condition", "topic", "seed", "checkpoint_turn",
        "measurement_a", "measurement_b", "measurement_c", "posterior_0", "posterior_1", "posterior_2",
        "posterior_3", "posterior_4", "posterior_mean", "posterior_mode", "stable_probability",
    ]
    with checkpoint_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=checkpoint_fields)
        writer.writeheader()
        for row, score in scored:
            writer.writerow(
                {
                    **{key: row[key] for key in checkpoint_fields[:7]},
                    "measurement_a": score["ratings"][0],
                    "measurement_b": score["ratings"][1],
                    "measurement_c": score["ratings"][2],
                    **{f"posterior_{index}": value for index, value in enumerate(score["posterior"])},
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
    per_judge_path = Path(output["per_judge_trajectory_outcomes"])
    with per_judge_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_judge_rows[0]))
        writer.writeheader()
        writer.writerows(per_judge_rows)

    result = {
        "protocol": "cross_model_replication_olmo_v1",
        "confirmatory": True,
        "target_model": config["model"],
        "measurement_protocol": measurement["protocol"],
        "cross_model_replication_pass": bool(all(checks.values())),
        "primary_checks": checks,
        "primary_criteria": criteria,
        "anchored_measurement": {
            "group_rates": rates,
            "positive_axis": {
                "axis": positive_axis,
                "pressure": positive_pressure,
                "control": positive_control,
                "condition_rates": positive_conditions,
                "paired_cluster_risk_difference": risk_difference,
            },
            "resistant_axis": {
                "axis": resistant_axis,
                "pressure": resistant_pressure,
                "control": resistant_control,
                "condition_rates": resistant_conditions,
            },
        },
        "per_judge_raw_threshold_sensitivity": per_judge_rates,
        "forecast_claim": "not_evaluated_by_this_primary_measurement_analysis",
        "lineage": {
            "config": str(args.config),
            "config_sha256": sha256(args.config),
            "template": str(template_path),
            "template_sha256": sha256(template_path),
            "merge_summary": str(merge_summary_path),
            "merge_summary_sha256": sha256(merge_summary_path),
            "probes": str(probes_path),
            "probes_sha256": sha256(probes_path),
            "scoring_model": measurement["scoring_model"],
            "scoring_model_sha256": sha256(Path(measurement["scoring_model"])),
            "judges": judge_lineage,
        },
        "artifacts": {
            "checkpoint_scores": str(checkpoint_path),
            "checkpoint_scores_sha256": sha256(checkpoint_path),
            "trajectory_outcomes": str(trajectory_path),
            "trajectory_outcomes_sha256": sha256(trajectory_path),
            "per_judge_trajectory_outcomes": str(per_judge_path),
            "per_judge_trajectory_outcomes_sha256": sha256(per_judge_path),
        },
    }
    summary_path = Path(output["summary"])
    summary_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

