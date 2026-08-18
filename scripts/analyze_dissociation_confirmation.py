#!/usr/bin/env python3
"""Apply the frozen v2 predictor to preregistered new confirmation data."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import yaml

from persona_drift.gate_c import (
    build_text_prefix,
    future_drift_label,
    projection_features,
)
from persona_drift.gate_c_v2 import transform_axis_calibrated_rows
from scripts.analyze_gate_c_development import (
    bootstrap_comparison,
    metric_summary,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def wilson_interval(
    successes: int, total: int, z: float = 1.959963984540054
) -> list[float]:
    if not 0 <= successes <= total or total <= 0:
        raise ValueError("invalid binomial count")
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = (proportion + z * z / (2.0 * total)) / denominator
    half = z * np.sqrt(
        proportion * (1.0 - proportion) / total
        + z * z / (4.0 * total * total)
    ) / denominator
    return [float(max(0.0, centre - half)), float(min(1.0, centre + half))]


def binary_rate_summary(values: Sequence[bool]) -> dict[str, Any]:
    successes = int(sum(values))
    total = len(values)
    return {
        "successes": successes,
        "total": total,
        "rate": float(successes / total),
        "wilson_95ci": wilson_interval(successes, total),
    }


def stratified_gap_bootstrap(
    rows: Sequence[dict[str, Any]], *, samples: int, seed: int
) -> dict[str, Any]:
    by_condition: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_condition[str(row["condition"])].append(row)
    rng = np.random.default_rng(seed)
    values = np.empty(samples, dtype=float)
    for iteration in range(samples):
        sampled: list[dict[str, Any]] = []
        for condition in sorted(by_condition):
            group = by_condition[condition]
            indices = rng.integers(0, len(group), size=len(group))
            sampled.extend(group[int(index)] for index in indices)
        values[iteration] = float(
            np.mean([row["alarm"] for row in sampled])
            - np.mean([row["drifted"] for row in sampled])
        )
    point = float(
        np.mean([row["alarm"] for row in rows])
        - np.mean([row["drifted"] for row in rows])
    )
    return {
        "point": point,
        "95ci": [float(value) for value in np.quantile(values, [0.025, 0.975])],
        "samples": samples,
        "seed": seed,
        "resampling_unit": "complete_trajectory",
        "strata": "condition",
    }


def safe_metrics(y: np.ndarray, probability: np.ndarray) -> dict[str, Any]:
    if len(np.unique(y)) != 2:
        return {
            "evaluable": False,
            "examples": int(len(y)),
            "prevalence": float(np.mean(y)),
            "auprc": None,
            "auroc": None,
            "brier": float(np.mean((probability - y) ** 2)),
        }
    return {"evaluable": True, **metric_summary(y, probability)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    source = config["source"]
    for key, hash_key in [
        ("predictor", "predictor_sha256"),
        ("predictor_summary", "predictor_summary_sha256"),
        ("power_analysis", "power_analysis_sha256"),
    ]:
        path = Path(source[key])
        if sha256(path) != str(source[hash_key]):
            raise ValueError(f"frozen confirmation input hash mismatch: {path}")

    generation_config_path = Path(source["generation_config"])
    generation_config = yaml.safe_load(
        generation_config_path.read_text(encoding="utf-8")
    )
    generation_analysis = generation_config["analysis"]
    fixed_threshold_source = Path(generation_analysis["fixed_threshold_source"])
    if sha256(fixed_threshold_source) != str(
        generation_analysis["fixed_threshold_source_sha256"]
    ):
        raise ValueError("frozen output-drift threshold source hash mismatch")

    merge_summary_path = Path(source["merge_summary"])
    merge_summary = json.loads(merge_summary_path.read_text(encoding="utf-8"))
    if merge_summary["config_sha256"] != sha256(generation_config_path):
        raise ValueError("merged trajectories use a different generation config")
    if merge_summary["trajectories"] != int(source["expected_trajectories"]):
        raise ValueError("confirmation trajectory count mismatch")
    if merge_summary["generation_gate_pass"] is not True:
        raise ValueError("confirmation generation quality gate did not pass")
    template_path = Path(generation_config["data"]["template"])
    if sha256(template_path) != generation_config["provenance"]["template_sha256"]:
        raise ValueError("confirmation topic template hash mismatch")

    gate_a_summary_path = Path(source["gate_a_summary"])
    gate_a_summary = json.loads(gate_a_summary_path.read_text(encoding="utf-8"))
    if float(gate_a_summary["threshold"]["value"]) != 3.5:
        raise ValueError("confirmation output drift threshold is not frozen at 3.5")
    if gate_a_summary["threshold"].get("source") != "fixed_external_preregistered":
        raise ValueError("confirmation output labels were not made with fixed threshold")
    if gate_a_summary["threshold"].get("fixed_threshold_source") != str(
        fixed_threshold_source
    ):
        raise ValueError("confirmation output threshold source path mismatch")
    if gate_a_summary["threshold"].get("fixed_threshold_source_sha256") != str(
        generation_analysis["fixed_threshold_source_sha256"]
    ):
        raise ValueError("confirmation output threshold source hash mismatch")

    trajectories_path = Path(source["trajectories"])
    if sha256(trajectories_path) != merge_summary["trajectories_sha256"]:
        raise ValueError("confirmation trajectory hash mismatch")
    trajectories = load_jsonl(trajectories_path)
    outcomes_path = Path(source["trajectory_outcomes"])
    if sha256(outcomes_path) != gate_a_summary["trajectory_outcomes_sha256"]:
        raise ValueError("confirmation outcome hash mismatch")
    with outcomes_path.open(newline="", encoding="utf-8") as handle:
        outcomes = {row["trajectory_id"]: row for row in csv.DictReader(handle)}
    if {row["trajectory_id"] for row in trajectories} != set(outcomes):
        raise ValueError("trajectory and outcome IDs differ")

    bundle = joblib.load(source["predictor"])
    if bundle["protocol"] != "gate_c_frozen_dissociation_predictor_v1":
        raise ValueError("unexpected predictor protocol")
    horizon = int(config["forecast"]["horizon"])
    if horizon != int(bundle["horizon"]):
        raise ValueError("forecast horizon differs from frozen predictor")
    threshold = float(config["forecast"]["threshold"])
    if threshold != float(bundle["threshold"]):
        raise ValueError("forecast threshold differs from frozen predictor")

    causal_rows: list[dict[str, Any]] = []
    total_turns = int(source["expected_turns_per_trajectory"])
    for trajectory in sorted(trajectories, key=lambda row: row["trajectory_id"]):
        trajectory_id = str(trajectory["trajectory_id"])
        turns = trajectory["turns"]
        if len(turns) != total_turns:
            raise ValueError(f"turn count mismatch for {trajectory_id}")
        outcome = outcomes[trajectory_id]
        onset_raw = str(outcome["drift_onset_turn"]).strip()
        onset = None if not onset_raw else int(onset_raw)
        for index, turn_record in enumerate(turns):
            turn = int(turn_record["turn"])
            eligible, label = future_drift_label(
                turn,
                onset,
                horizon=horizon,
                total_turns=total_turns,
            )
            if not eligible:
                continue
            causal_rows.append(
                {
                    "example_id": f"{trajectory_id}::turn-{turn:02d}",
                    "trajectory_id": trajectory_id,
                    "axis": trajectory["axis"],
                    "condition": trajectory["condition"],
                    "topic": trajectory["topic"],
                    "seed": int(trajectory["seed"]),
                    "turn": turn,
                    "drift_onset_turn": onset,
                    "label": int(label),
                    "text_prefix": build_text_prefix(turns, index),
                    "activation_features": projection_features(
                        turns,
                        index,
                        reference_layer=int(config["forecast"]["reference_layer"]),
                        slope_window=int(config["forecast"]["slope_window"]),
                    ),
                }
            )
    transformed = transform_axis_calibrated_rows(
        causal_rows, bundle["calibration"]
    )
    placeholder = np.zeros((len(transformed), 1), dtype=float)
    probabilities: dict[str, np.ndarray] = {}
    for name, predictor in bundle["predictors"].items():
        x = predictor["pipeline"].transform(transformed, placeholder)
        probabilities[name] = predictor["model"].predict_proba(x)[:, 1]

    positive_axis = str(config["scope"]["positive_axis"])
    primary_mask = np.asarray(
        [row["axis"] == positive_axis for row in transformed], dtype=bool
    )
    primary_rows = [row for row, keep in zip(transformed, primary_mask) if keep]
    primary_y = np.asarray([row["label"] for row in primary_rows], dtype=int)
    primary_probabilities = {
        name: values[primary_mask] for name, values in probabilities.items()
    }
    primary_metrics = {
        name: safe_metrics(primary_y, values)
        for name, values in primary_probabilities.items()
    }
    bootstrap = None
    if len(np.unique(primary_y)) == 2:
        bootstrap = bootstrap_comparison(
            primary_rows,
            primary_y,
            primary_probabilities["text"],
            primary_probabilities["activation"],
            primary_probabilities["combined"],
            samples=int(config["inference"]["bootstrap_samples"]),
            seed=int(config["inference"]["bootstrap_seed"]),
        )

    rows_by_trajectory: defaultdict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(transformed):
        rows_by_trajectory[str(row["trajectory_id"])].append(index)
    trajectory_rows: list[dict[str, Any]] = []
    for trajectory_id, indices in sorted(rows_by_trajectory.items()):
        first = transformed[indices[0]]
        outcome = outcomes[trajectory_id]
        trajectory_rows.append(
            {
                "trajectory_id": trajectory_id,
                "axis": first["axis"],
                "condition": first["condition"],
                "topic": first["topic"],
                "seed": first["seed"],
                "drifted": str(outcome["drifted"]).lower() == "true",
                "drift_onset_turn": outcome["drift_onset_turn"],
                "text_alarm": bool(
                    np.any(probabilities["text"][indices] >= threshold)
                ),
                "activation_alarm": bool(
                    np.any(probabilities["activation"][indices] >= threshold)
                ),
                "combined_alarm": bool(
                    np.any(probabilities["combined"][indices] >= threshold)
                ),
                "max_combined_probability": float(
                    np.max(probabilities["combined"][indices])
                ),
            }
        )

    resistant_axis = str(config["scope"]["resistant_axis"])
    pressure_conditions = set(config["scope"]["pressure_conditions"])
    control_conditions = set(config["scope"]["control_conditions"])
    resistant_pressure = [
        row
        for row in trajectory_rows
        if row["axis"] == resistant_axis
        and row["condition"] in pressure_conditions
    ]
    resistant_control = [
        row
        for row in trajectory_rows
        if row["axis"] == resistant_axis
        and row["condition"] in control_conditions
    ]
    pressure_drift = binary_rate_summary(
        [bool(row["drifted"]) for row in resistant_pressure]
    )
    pressure_alarm = binary_rate_summary(
        [bool(row["combined_alarm"]) for row in resistant_pressure]
    )
    control_alarm = binary_rate_summary(
        [bool(row["combined_alarm"]) for row in resistant_control]
    )
    gap_rows = [
        {
            "condition": row["condition"],
            "alarm": bool(row["combined_alarm"]),
            "drifted": bool(row["drifted"]),
        }
        for row in resistant_pressure
    ]
    gap = stratified_gap_bootstrap(
        gap_rows,
        samples=int(config["inference"]["bootstrap_samples"]),
        seed=int(config["inference"]["bootstrap_seed"]) + 1,
    )

    criteria = config["confirmation_criteria"]
    checks = {
        "gate_a_replication": bool(gate_a_summary["gate_pass"] is True),
        "incremental_auprc_below_smallest_useful_effect": bool(
            bootstrap is not None
            and bootstrap["combined_minus_text_auprc_95ci"][1]
            < float(criteria["max_combined_minus_text_auprc_upper_95ci"])
        ),
        "resistant_pressure_output_drift_upper_bound": bool(
            pressure_drift["wilson_95ci"][1]
            <= float(
                criteria["max_resistant_pressure_output_drift_wilson_upper"]
            )
        ),
        "resistant_pressure_alarm_lower_bound": bool(
            pressure_alarm["wilson_95ci"][0]
            >= float(criteria["min_resistant_pressure_alarm_wilson_lower"])
        ),
        "resistant_pressure_dissociation_gap": bool(
            gap["95ci"][0]
            >= float(criteria["min_resistant_pressure_alarm_minus_drift_ci_lower"])
        ),
        "resistant_control_alarm_upper_bound": bool(
            control_alarm["wilson_95ci"][1]
            <= float(criteria["max_resistant_control_alarm_wilson_upper"])
        ),
    }

    output = config["output"]
    output_root = Path(output["root"])
    if output_root.exists():
        raise FileExistsError(f"refusing to reuse {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    turn_path = Path(output["turn_predictions"])
    with turn_path.open("x", newline="", encoding="utf-8") as handle:
        fields = [
            "example_id",
            "trajectory_id",
            "axis",
            "condition",
            "topic",
            "seed",
            "turn",
            "drift_onset_turn",
            "label",
            "text_probability",
            "activation_probability",
            "combined_probability",
            "threshold",
            "combined_alarm",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(transformed):
            writer.writerow(
                {
                    **{key: row[key] for key in fields[:9]},
                    "text_probability": float(probabilities["text"][index]),
                    "activation_probability": float(
                        probabilities["activation"][index]
                    ),
                    "combined_probability": float(
                        probabilities["combined"][index]
                    ),
                    "threshold": threshold,
                    "combined_alarm": int(
                        probabilities["combined"][index] >= threshold
                    ),
                }
            )
    trajectory_path = Path(output["trajectory_predictions"])
    with trajectory_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(trajectory_rows[0]))
        writer.writeheader()
        writer.writerows(trajectory_rows)

    result = {
        "protocol": "gate_c_dissociation_confirmation_qwen_v1",
        "mode": config["mode"],
        "confirmatory": True,
        "model": generation_config["model"],
        "confirmation_supports_dissociation": bool(all(checks.values())),
        "confirmation_checks": checks,
        "confirmation_criteria": criteria,
        "gate_a_replication": {
            "gate_pass": gate_a_summary["gate_pass"],
            "combined": gate_a_summary["combined"],
            "negative_controls": gate_a_summary["negative_controls"],
            "threshold": gate_a_summary["threshold"],
        },
        "forecast_evaluable": bool(len(np.unique(primary_y)) == 2),
        "primary_positive_axis": {
            "axis": positive_axis,
            "examples": len(primary_rows),
            "trajectories": len(
                {row["trajectory_id"] for row in primary_rows}
            ),
            "metrics": primary_metrics,
            "clustered_bootstrap": bootstrap,
        },
        "resistant_axis_dissociation": {
            "axis": resistant_axis,
            "pressure_output_drift": pressure_drift,
            "pressure_combined_alarm": pressure_alarm,
            "control_combined_alarm": control_alarm,
            "pressure_alarm_minus_drift": gap,
        },
        "lineage": {
            "generation_config": str(generation_config_path),
            "generation_config_sha256": sha256(generation_config_path),
            "template": str(template_path),
            "template_sha256": sha256(template_path),
            "trajectories": str(trajectories_path),
            "trajectories_sha256": sha256(trajectories_path),
            "gate_a_summary": str(gate_a_summary_path),
            "gate_a_summary_sha256": sha256(gate_a_summary_path),
            "predictor": source["predictor"],
            "predictor_sha256": sha256(Path(source["predictor"])),
            "power_analysis": source["power_analysis"],
            "power_analysis_sha256": sha256(Path(source["power_analysis"])),
            "config": str(args.config),
            "config_sha256": sha256(args.config),
        },
        "artifacts": {
            "turn_predictions": str(turn_path),
            "turn_predictions_sha256": sha256(turn_path),
            "trajectory_predictions": str(trajectory_path),
            "trajectory_predictions_sha256": sha256(trajectory_path),
        },
    }
    summary_path = Path(output["summary"])
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
