#!/usr/bin/env python3
"""Post-hoc decomposition of Gate C negative-control alarms by feature family."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from scripts.analyze_gate_c_development import (
    fit_final,
    read_jsonl,
    sha256,
)


def alarm_summary(
    rows: list[dict[str, Any]], probability: np.ndarray, threshold: float
) -> dict[str, Any]:
    alarms = probability >= threshold
    by_condition: dict[str, Any] = {}
    condition_indices: defaultdict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        condition_indices[str(row["condition"])].append(index)
    for condition, raw_indices in sorted(condition_indices.items()):
        indices = np.asarray(raw_indices, dtype=int)
        condition_alarms = alarms[indices]
        condition_trajectories = {
            str(rows[index]["trajectory_id"]) for index in indices
        }
        alarm_trajectories = {
            str(rows[index]["trajectory_id"])
            for index in indices
            if alarms[index]
        }
        by_condition[condition] = {
            "examples": int(len(indices)),
            "alarms": int(np.sum(condition_alarms)),
            "alarms_per_100_eligible_turns": float(
                100.0 * np.mean(condition_alarms)
            ),
            "mean_probability": float(np.mean(probability[indices])),
            "median_probability": float(np.median(probability[indices])),
            "trajectories": len(condition_trajectories),
            "trajectories_with_any_alarm": len(alarm_trajectories),
        }
    trajectory_ids = {str(row["trajectory_id"]) for row in rows}
    alarm_trajectory_ids = {
        str(row["trajectory_id"])
        for row, alarm in zip(rows, alarms)
        if alarm
    }
    return {
        "examples": len(rows),
        "alarms": int(np.sum(alarms)),
        "alarms_per_100_eligible_turns": float(100.0 * np.mean(alarms)),
        "mean_probability": float(np.mean(probability)),
        "median_probability": float(np.median(probability)),
        "trajectories": len(trajectory_ids),
        "trajectories_with_any_alarm": len(alarm_trajectory_ids),
        "by_condition": by_condition,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output = config["output"]
    dataset_path = Path(output["dataset"])
    embeddings_path = Path(output["embeddings"])
    analysis_summary_path = Path(output["analysis_dir"]) / "summary.json"
    analysis_summary = json.loads(
        analysis_summary_path.read_text(encoding="utf-8")
    )
    horizon = int(config["labels"]["primary_horizon"])
    primary = analysis_summary["horizons"][f"h{horizon}"]
    selected_name = str(primary["selected_text_baseline"])
    combined_name = str(primary["combined_representation"])
    threshold = float(primary["threshold_selection"]["selected_threshold"])
    eligible_key = f"eligible_h{horizon}"
    label_key = f"label_h{horizon}"
    positive_axis = str(config["scope"]["positive_axis"])
    negative_axis = str(config["scope"]["negative_control_axis"])

    rows = read_jsonl(dataset_path)
    archive = np.load(embeddings_path, allow_pickle=False)
    embedded_ids = archive["example_ids"].astype(str)
    embeddings = archive["embeddings"].astype(np.float64)
    if not np.array_equal(
        embedded_ids, np.asarray([str(row["example_id"]) for row in rows])
    ):
        raise ValueError("embedding rows are not aligned")

    fit_mask = np.asarray(
        [
            row["axis"] == positive_axis
            and row["development_split"] in {"train", "validation"}
            and bool(row[eligible_key])
            for row in rows
        ],
        dtype=bool,
    )
    negative_mask = np.asarray(
        [
            row["axis"] == negative_axis
            and row["development_split"] == "development_test"
            and bool(row[eligible_key])
            for row in rows
        ],
        dtype=bool,
    )
    fit_rows = [row for row, keep in zip(rows, fit_mask) if keep]
    fit_embeddings = embeddings[fit_mask]
    fit_y = np.asarray([int(row[label_key]) for row in fit_rows], dtype=int)
    negative_rows = [row for row, keep in zip(rows, negative_mask) if keep]
    negative_embeddings = embeddings[negative_mask]
    if any(bool(row[label_key]) for row in negative_rows):
        raise ValueError("development negative control unexpectedly contains drift")

    if selected_name == "prevalence":
        text_probability = np.full(len(negative_rows), float(np.mean(fit_y)))
    else:
        text_probability, _, _ = fit_final(
            selected_name,
            float(primary["validation_baselines"][selected_name]["selected_c"]),
            fit_rows,
            fit_embeddings,
            fit_y,
            negative_rows,
            negative_embeddings,
            config,
        )
    activation_probability, _, _ = fit_final(
        "activation",
        float(primary["activation_selected_c"]),
        fit_rows,
        fit_embeddings,
        fit_y,
        negative_rows,
        negative_embeddings,
        config,
    )
    combined_probability, _, _ = fit_final(
        combined_name,
        float(primary["combined_selected_c"]),
        fit_rows,
        fit_embeddings,
        fit_y,
        negative_rows,
        negative_embeddings,
        config,
    )

    diagnostic_dir = Path(output["root"]) / "diagnostics"
    if diagnostic_dir.exists() and any(diagnostic_dir.iterdir()):
        raise FileExistsError(
            f"diagnostic output directory is not empty: {diagnostic_dir}"
        )
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = diagnostic_dir / "negative_control_decomposition.csv"
    with predictions_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "example_id",
                "trajectory_id",
                "condition",
                "turn",
                "text_probability",
                "activation_probability",
                "combined_probability",
                "threshold",
                "text_alarm",
                "activation_alarm",
                "combined_alarm",
            ],
        )
        writer.writeheader()
        for index, row in enumerate(negative_rows):
            writer.writerow(
                {
                    "example_id": row["example_id"],
                    "trajectory_id": row["trajectory_id"],
                    "condition": row["condition"],
                    "turn": row["turn"],
                    "text_probability": float(text_probability[index]),
                    "activation_probability": float(
                        activation_probability[index]
                    ),
                    "combined_probability": float(combined_probability[index]),
                    "threshold": threshold,
                    "text_alarm": int(text_probability[index] >= threshold),
                    "activation_alarm": int(
                        activation_probability[index] >= threshold
                    ),
                    "combined_alarm": int(
                        combined_probability[index] >= threshold
                    ),
                }
            )
    result = {
        "protocol": "gate_c_negative_control_decomposition_v1",
        "post_hoc_diagnostic": True,
        "confirmatory": False,
        "reason": "localize the prespecified combined-model negative-control alarm rate",
        "primary_horizon": horizon,
        "selected_text_baseline": selected_name,
        "combined_representation": combined_name,
        "primary_threshold_reused_without_retuning": threshold,
        "text": alarm_summary(negative_rows, text_probability, threshold),
        "activation": alarm_summary(
            negative_rows, activation_probability, threshold
        ),
        "combined": alarm_summary(
            negative_rows, combined_probability, threshold
        ),
        "dataset_sha256": sha256(dataset_path),
        "embeddings_sha256": sha256(embeddings_path),
        "primary_analysis_sha256": sha256(analysis_summary_path),
        "predictions": str(predictions_path),
        "predictions_sha256": sha256(predictions_path),
    }
    summary_path = diagnostic_dir / "summary.json"
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
