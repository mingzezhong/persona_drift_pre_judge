#!/usr/bin/env python3
"""Evaluate axis-calibrated Gate C development v2 without confirmatory claims."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import yaml

from persona_drift.gate_c_v2 import (
    fit_clean_axis_calibration,
    transform_axis_calibrated_rows,
)
from scripts.analyze_gate_c_development import (
    FeaturePipeline,
    bootstrap_comparison,
    choose_threshold,
    fit_classifier,
    fit_final,
    metric_summary,
    read_jsonl,
    sha256,
    threshold_metrics,
    trajectory_warning_metrics,
    tune_representation,
)


def feature_distribution(
    rows: Sequence[dict[str, Any]], names: Sequence[str]
) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for name in names:
        values = np.asarray(
            [float(row["activation_features"][name]) for row in rows],
            dtype=float,
        )
        result[name] = {
            "mean": float(np.mean(values)),
            "standard_deviation": float(np.std(values, ddof=0)),
            "minimum": float(np.min(values)),
            "maximum": float(np.max(values)),
        }
    return result


def negative_alarm_summary(
    rows: Sequence[dict[str, Any]], probability: np.ndarray, threshold: float
) -> dict[str, Any]:
    alarms = probability >= threshold
    condition_indices: defaultdict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        condition_indices[str(row["condition"])].append(index)
    by_condition: dict[str, Any] = {}
    for condition, raw_indices in sorted(condition_indices.items()):
        indices = np.asarray(raw_indices, dtype=int)
        alarm_trajectories = {
            str(rows[index]["trajectory_id"])
            for index in indices
            if alarms[index]
        }
        by_condition[condition] = {
            "examples": int(len(indices)),
            "alarms": int(np.sum(alarms[indices])),
            "alarms_per_100_eligible_turns": float(
                100.0 * np.mean(alarms[indices])
            ),
            "trajectories_with_any_alarm": len(alarm_trajectories),
            "mean_probability": float(np.mean(probability[indices])),
        }
    trajectory_ids = {str(row["trajectory_id"]) for row in rows}
    alarm_trajectories = {
        str(row["trajectory_id"])
        for row, alarm in zip(rows, alarms)
        if alarm
    }
    return {
        "examples": len(rows),
        "alarms": int(np.sum(alarms)),
        "alarms_per_100_eligible_turns": float(100.0 * np.mean(alarms)),
        "trajectories": len(trajectory_ids),
        "trajectories_with_any_alarm": len(alarm_trajectories),
        "mean_probability": float(np.mean(probability)),
        "by_condition": by_condition,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    source = config["source"]
    for key, hash_key in [
        ("dataset", "dataset_sha256"),
        ("embeddings", "embeddings_sha256"),
        ("v1_analysis", "v1_analysis_sha256"),
    ]:
        path = Path(source[key])
        if sha256(path) != str(source[hash_key]):
            raise ValueError(f"frozen v2 source hash mismatch: {path}")
    v1 = json.loads(Path(source["v1_analysis"]).read_text(encoding="utf-8"))
    if v1["development_interpretation"]["promising"] is not False:
        raise ValueError("v2 rationale requires the frozen v1 failure")

    rows = read_jsonl(Path(source["dataset"]))
    archive = np.load(Path(source["embeddings"]), allow_pickle=False)
    embedded_ids = archive["example_ids"].astype(str)
    embeddings = archive["embeddings"].astype(np.float64)
    if not np.array_equal(
        embedded_ids, np.asarray([str(row["example_id"]) for row in rows])
    ):
        raise ValueError("embedding rows are not aligned")
    horizon = int(config["scope"]["primary_horizon"])
    eligible_key = f"eligible_h{horizon}"
    label_key = f"label_h{horizon}"
    calibration_config = config["calibration"]
    calibration = fit_clean_axis_calibration(
        rows,
        axes=calibration_config["axes"],
        split=str(calibration_config["split"]),
        clean_conditions=calibration_config["clean_conditions"],
        eligibility_key=eligible_key,
        minimum_scale=float(calibration_config["minimum_scale"]),
    )
    transformed = transform_axis_calibrated_rows(rows, calibration)

    positive_axis = str(config["scope"]["positive_axis"])
    negative_axis = str(config["scope"]["negative_control_axis"])
    split_names = {
        "train": str(config["scope"]["train_split"]),
        "validation": str(config["scope"]["validation_split"]),
        "development_test": str(
            config["scope"]["development_test_split"]
        ),
    }
    masks: dict[str, np.ndarray] = {
        role: np.asarray(
            [
                row["axis"] == positive_axis
                and row["development_split"] == split
                and bool(row[eligible_key])
                for row in transformed
            ],
            dtype=bool,
        )
        for role, split in split_names.items()
    }
    split_rows = {
        name: [row for row, keep in zip(transformed, mask) if keep]
        for name, mask in masks.items()
    }
    split_embeddings = {
        name: embeddings[mask] for name, mask in masks.items()
    }
    split_y = {
        name: np.asarray([int(row[label_key]) for row in selected], dtype=int)
        for name, selected in split_rows.items()
    }
    if any(len(np.unique(y)) != 2 for y in split_y.values()):
        raise ValueError("every positive-axis split must contain both classes")

    model_config = deepcopy(config)
    model_config["analysis"]["tfidf"] = config["text_baseline"]["tfidf"]
    text_name = str(config["text_baseline"]["representation"])
    text_c = float(config["text_baseline"]["c"])
    text_pipeline_validation = FeaturePipeline(text_name, model_config)
    text_train_x = text_pipeline_validation.fit_transform(
        split_rows["train"], split_embeddings["train"]
    )
    text_validation_x = text_pipeline_validation.transform(
        split_rows["validation"], split_embeddings["validation"]
    )
    text_validation_model = fit_classifier(
        text_train_x, split_y["train"], text_c
    )
    text_validation_probability = text_validation_model.predict_proba(
        text_validation_x
    )[:, 1]
    activation_tuning = tune_representation(
        "activation",
        split_rows["train"],
        split_embeddings["train"],
        split_y["train"],
        split_rows["validation"],
        split_embeddings["validation"],
        split_y["validation"],
        model_config,
    )
    combined_name = f"combined_{text_name}"
    combined_tuning = tune_representation(
        combined_name,
        split_rows["train"],
        split_embeddings["train"],
        split_y["train"],
        split_rows["validation"],
        split_embeddings["validation"],
        split_y["validation"],
        model_config,
    )
    threshold, validation_threshold = choose_threshold(
        split_y["validation"],
        combined_tuning["validation_probability"],
        float(config["analysis"]["validation_min_recall"]),
    )

    fit_rows = split_rows["train"] + split_rows["validation"]
    fit_embeddings = np.concatenate(
        [split_embeddings["train"], split_embeddings["validation"]], axis=0
    )
    fit_y = np.concatenate([split_y["train"], split_y["validation"]])
    text_probability, _, _ = fit_final(
        text_name,
        text_c,
        fit_rows,
        fit_embeddings,
        fit_y,
        split_rows["development_test"],
        split_embeddings["development_test"],
        model_config,
    )
    activation_probability, activation_pipeline, activation_model = fit_final(
        "activation",
        float(activation_tuning["c"]),
        fit_rows,
        fit_embeddings,
        fit_y,
        split_rows["development_test"],
        split_embeddings["development_test"],
        model_config,
    )
    combined_probability, combined_pipeline, combined_model = fit_final(
        combined_name,
        float(combined_tuning["c"]),
        fit_rows,
        fit_embeddings,
        fit_y,
        split_rows["development_test"],
        split_embeddings["development_test"],
        model_config,
    )
    test_y = split_y["development_test"]
    text_metrics = metric_summary(test_y, text_probability)
    activation_metrics = metric_summary(test_y, activation_probability)
    combined_metrics = metric_summary(test_y, combined_probability)
    bootstrap = bootstrap_comparison(
        split_rows["development_test"],
        test_y,
        text_probability,
        activation_probability,
        combined_probability,
        samples=int(config["analysis"]["bootstrap_samples"]),
        seed=int(config["analysis"]["bootstrap_seed"]),
    )

    negative_mask = np.asarray(
        [
            row["axis"] == negative_axis
            and row["development_split"] == split_names["development_test"]
            and bool(row[eligible_key])
            for row in transformed
        ],
        dtype=bool,
    )
    negative_rows = [
        row for row, keep in zip(transformed, negative_mask) if keep
    ]
    negative_embeddings = embeddings[negative_mask]
    if any(bool(row[label_key]) for row in negative_rows):
        raise ValueError("v2 negative-control development test contains drift")
    text_negative_pipeline = FeaturePipeline(text_name, model_config)
    text_fit_x = text_negative_pipeline.fit_transform(fit_rows, fit_embeddings)
    text_negative_x = text_negative_pipeline.transform(
        negative_rows, negative_embeddings
    )
    text_negative_model = fit_classifier(text_fit_x, fit_y, text_c)
    text_negative_probability = text_negative_model.predict_proba(
        text_negative_x
    )[:, 1]
    activation_negative_probability = activation_model.predict_proba(
        activation_pipeline.transform(negative_rows, negative_embeddings)
    )[:, 1]
    combined_negative_probability = combined_model.predict_proba(
        combined_pipeline.transform(negative_rows, negative_embeddings)
    )[:, 1]

    delta = float(combined_metrics["auprc"] - text_metrics["auprc"])
    brier_gain = float(text_metrics["brier"] - combined_metrics["brier"])
    warning = trajectory_warning_metrics(
        split_rows["development_test"],
        combined_probability,
        threshold,
        horizon,
    )
    negative_combined = negative_alarm_summary(
        negative_rows, combined_negative_probability, threshold
    )
    decision_config = config["development_decision"]
    checks = {
        "minimum_auprc_increment": bool(
            delta >= float(decision_config["min_combined_minus_text_auprc"])
        ),
        "bootstrap_lower_bound_above_zero": bool(
            bootstrap["combined_minus_text_auprc_95ci"][0] > 0.0
        ),
        "combined_brier_not_worse": bool(brier_gain >= 0.0),
        "negative_control_alarm_cap": bool(
            negative_combined["alarms_per_100_eligible_turns"]
            <= float(
                decision_config[
                    "max_negative_control_alarms_per_100_turns"
                ]
            )
        ),
        "trajectory_detection_rate": bool(
            warning["trajectory_detection_rate"]
            >= float(
                decision_config["min_drift_trajectory_detection_rate"]
            )
        ),
        "median_warning_lead": bool(
            warning["median_warning_lead_turns"] is not None
            and warning["median_warning_lead_turns"]
            >= float(decision_config["min_median_warning_lead_turns"])
        ),
    }
    result: dict[str, Any] = {
        "protocol": "gate_c_axis_calibrated_development_v2",
        "mode": config["mode"],
        "post_hoc_development": True,
        "confirmatory": False,
        "new_data_confirmation_authorized": bool(all(checks.values())),
        "decision_checks": checks,
        "decision_thresholds": decision_config,
        "source_hashes": {
            str(source[key]): sha256(Path(source[key]))
            for key in ["dataset", "embeddings", "v1_analysis"]
        },
        "config": str(args.config),
        "config_sha256": sha256(args.config),
        "calibration": calibration,
        "features": config["features"]["activation"],
        "split_counts": {
            name: {
                "examples": int(len(y)),
                "positive": int(np.sum(y)),
                "negative": int(len(y) - np.sum(y)),
                "trajectories": len(
                    {row["trajectory_id"] for row in split_rows[name]}
                ),
            }
            for name, y in split_y.items()
        },
        "validation": {
            "text": metric_summary(
                split_y["validation"], text_validation_probability
            ),
            "text_c_frozen_from_v1": text_c,
            "activation_selected_c": activation_tuning["c"],
            "combined_selected_c": combined_tuning["c"],
            "combined_threshold": threshold,
            "combined_threshold_metrics": validation_threshold,
        },
        "development_test": {
            "text": text_metrics,
            "activation": activation_metrics,
            "combined": combined_metrics,
            "activation_minus_text_auprc": float(
                activation_metrics["auprc"] - text_metrics["auprc"]
            ),
            "combined_minus_text_auprc": delta,
            "text_minus_combined_brier": brier_gain,
            "combined_threshold_metrics": threshold_metrics(
                test_y, combined_probability, threshold
            ),
            "warning": warning,
            "clustered_bootstrap": bootstrap,
        },
        "negative_control": {
            "text": negative_alarm_summary(
                negative_rows, text_negative_probability, threshold
            ),
            "activation": negative_alarm_summary(
                negative_rows, activation_negative_probability, threshold
            ),
            "combined": negative_combined,
        },
        "transformed_feature_distributions": {
            "positive_train": feature_distribution(
                split_rows["train"], config["features"]["activation"]
            ),
            "positive_development_test": feature_distribution(
                split_rows["development_test"],
                config["features"]["activation"],
            ),
            "negative_development_test": feature_distribution(
                negative_rows, config["features"]["activation"]
            ),
        },
    }

    output = config["output"]
    output_root = Path(output["root"])
    if output_root.exists():
        raise FileExistsError(f"v2 output root already exists: {output_root}")
    analysis_dir = Path(output["summary"]).parent
    analysis_dir.mkdir(parents=True, exist_ok=False)
    primary_path = Path(output["primary_predictions"])
    with primary_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "example_id",
                "trajectory_id",
                "condition",
                "turn",
                "onset",
                "label",
                "text_probability",
                "activation_probability",
                "combined_probability",
                "threshold",
                "combined_alarm",
            ]
        )
        for index, row in enumerate(split_rows["development_test"]):
            writer.writerow(
                [
                    row["example_id"],
                    row["trajectory_id"],
                    row["condition"],
                    row["turn"],
                    row["drift_onset_turn"],
                    int(test_y[index]),
                    float(text_probability[index]),
                    float(activation_probability[index]),
                    float(combined_probability[index]),
                    threshold,
                    int(combined_probability[index] >= threshold),
                ]
            )
    negative_path = Path(output["negative_control_predictions"])
    with negative_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "example_id",
                "trajectory_id",
                "condition",
                "turn",
                "text_probability",
                "activation_probability",
                "combined_probability",
                "threshold",
                "combined_alarm",
            ]
        )
        for index, row in enumerate(negative_rows):
            writer.writerow(
                [
                    row["example_id"],
                    row["trajectory_id"],
                    row["condition"],
                    row["turn"],
                    float(text_negative_probability[index]),
                    float(activation_negative_probability[index]),
                    float(combined_negative_probability[index]),
                    threshold,
                    int(combined_negative_probability[index] >= threshold),
                ]
            )
    result["artifacts"] = {
        "primary_predictions": str(primary_path),
        "primary_predictions_sha256": sha256(primary_path),
        "negative_control_predictions": str(negative_path),
        "negative_control_predictions_sha256": sha256(negative_path),
    }
    summary_path = Path(output["summary"])
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
