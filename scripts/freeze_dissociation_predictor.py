#!/usr/bin/env python3
"""Freeze and verify the exact Gate C v2 predictors before new data exist."""

from __future__ import annotations

import argparse
import csv
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import sklearn
import yaml

from persona_drift.gate_c_v2 import (
    fit_clean_axis_calibration,
    transform_axis_calibrated_rows,
)
from scripts.analyze_gate_c_development import (
    FeaturePipeline,
    fit_classifier,
    read_jsonl,
    sha256,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"refusing to reuse {args.output_dir}")
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    source = config["source"]
    for key, hash_key in [
        ("dataset", "dataset_sha256"),
        ("embeddings", "embeddings_sha256"),
        ("v1_analysis", "v1_analysis_sha256"),
    ]:
        path = Path(source[key])
        if sha256(path) != str(source[hash_key]):
            raise ValueError(f"source hash mismatch: {path}")
    summary_path = Path(config["output"]["summary"])
    v2_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if v2_summary["new_data_confirmation_authorized"] is not False:
        raise ValueError("expected the frozen positive Gate C v2 failure")

    rows = read_jsonl(Path(source["dataset"]))
    archive = np.load(Path(source["embeddings"]), allow_pickle=False)
    embeddings = archive["embeddings"].astype(np.float64)
    if not np.array_equal(
        archive["example_ids"].astype(str),
        np.asarray([str(row["example_id"]) for row in rows]),
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
    fit_splits = {
        str(config["scope"]["train_split"]),
        str(config["scope"]["validation_split"]),
    }
    fit_mask = np.asarray(
        [
            row["axis"] == positive_axis
            and row["development_split"] in fit_splits
            and bool(row[eligible_key])
            for row in transformed
        ],
        dtype=bool,
    )
    test_mask = np.asarray(
        [
            row["axis"] == positive_axis
            and row["development_split"]
            == str(config["scope"]["development_test_split"])
            and bool(row[eligible_key])
            for row in transformed
        ],
        dtype=bool,
    )
    fit_rows = [row for row, keep in zip(transformed, fit_mask) if keep]
    test_rows = [row for row, keep in zip(transformed, test_mask) if keep]
    fit_embeddings = embeddings[fit_mask]
    test_embeddings = embeddings[test_mask]
    fit_y = np.asarray([int(row[label_key]) for row in fit_rows], dtype=int)
    model_config = deepcopy(config)
    model_config["analysis"]["tfidf"] = config["text_baseline"]["tfidf"]
    selections = {
        "text": ("tfidf", float(config["text_baseline"]["c"])),
        "activation": (
            "activation",
            float(v2_summary["validation"]["activation_selected_c"]),
        ),
        "combined": (
            "combined_tfidf",
            float(v2_summary["validation"]["combined_selected_c"]),
        ),
    }
    predictors = {}
    reproduced = {}
    for label, (representation, c_value) in selections.items():
        pipeline = FeaturePipeline(representation, model_config)
        fit_x = pipeline.fit_transform(fit_rows, fit_embeddings)
        test_x = pipeline.transform(test_rows, test_embeddings)
        model = fit_classifier(fit_x, fit_y, c_value)
        probability = model.predict_proba(test_x)[:, 1]
        predictors[label] = {
            "representation": representation,
            "c": c_value,
            "pipeline": pipeline,
            "model": model,
        }
        reproduced[label] = probability

    predictions_path = Path(config["output"]["primary_predictions"])
    with predictions_path.open(newline="", encoding="utf-8") as handle:
        saved = list(csv.DictReader(handle))
    if [row["example_id"] for row in saved] != [
        row["example_id"] for row in test_rows
    ]:
        raise ValueError("saved v2 prediction IDs are not aligned")
    max_error = {}
    for label, probability in reproduced.items():
        expected = np.asarray(
            [float(row[f"{label}_probability"]) for row in saved], dtype=float
        )
        error = float(np.max(np.abs(expected - probability)))
        if error > 1e-12:
            raise ValueError(f"{label} reproduction error {error} exceeds tolerance")
        max_error[label] = error

    threshold = float(v2_summary["validation"]["combined_threshold"])
    bundle = {
        "protocol": "gate_c_frozen_dissociation_predictor_v1",
        "trusted_local_artifact_only": True,
        "horizon": horizon,
        "positive_axis": positive_axis,
        "negative_control_axis": str(config["scope"]["negative_control_axis"]),
        "calibration": calibration,
        "activation_features": list(config["features"]["activation"]),
        "threshold": threshold,
        "predictors": predictors,
        "development_config": str(args.config),
        "development_config_sha256": sha256(args.config),
        "development_summary": str(summary_path),
        "development_summary_sha256": sha256(summary_path),
        "development_predictions_sha256": sha256(predictions_path),
        "sklearn_version": sklearn.__version__,
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    bundle_path = args.output_dir / "predictor.joblib"
    joblib.dump(bundle, bundle_path, compress=3)
    result = {
        "protocol": bundle["protocol"],
        "frozen_before_confirmation_generation": True,
        "bundle": str(bundle_path),
        "bundle_sha256": sha256(bundle_path),
        "threshold": threshold,
        "horizon": horizon,
        "representations": {
            key: {"name": value[0], "c": value[1]}
            for key, value in selections.items()
        },
        "maximum_reproduction_error": max_error,
        "reproduction_tolerance": 1e-12,
        "development_config_sha256": sha256(args.config),
        "development_summary_sha256": sha256(summary_path),
        "development_predictions_sha256": sha256(predictions_path),
        "sklearn_version": sklearn.__version__,
    }
    result_path = args.output_dir / "summary.json"
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
