#!/usr/bin/env python3
"""Run the frozen, non-confirmatory Gate C development analysis."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import yaml
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

from persona_drift.gate_c import stratified_cluster_bootstrap_indices


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def metric_summary(y: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    if len(np.unique(y)) != 2:
        raise ValueError("metrics require both outcome classes")
    return {
        "auprc": float(average_precision_score(y, probability)),
        "auroc": float(roc_auc_score(y, probability)),
        "brier": float(brier_score_loss(y, probability)),
        "prevalence": float(np.mean(y)),
        "examples": int(len(y)),
    }


def threshold_metrics(
    y: np.ndarray, probability: np.ndarray, threshold: float
) -> dict[str, float | int]:
    prediction = probability >= threshold
    positive = y == 1
    negative = ~positive
    true_positive = int(np.sum(prediction & positive))
    false_positive = int(np.sum(prediction & negative))
    return {
        "threshold": float(threshold),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "recall": float(true_positive / max(1, np.sum(positive))),
        "false_positive_rate": float(false_positive / max(1, np.sum(negative))),
        "false_alarms_per_100_eligible_turns": float(
            100.0 * false_positive / len(y)
        ),
    }


def choose_threshold(
    y: np.ndarray, probability: np.ndarray, minimum_recall: float
) -> tuple[float, dict[str, float | int]]:
    candidates = np.unique(np.concatenate(([0.0], probability, [1.0])))
    eligible: list[tuple[float, float, float, dict[str, float | int]]] = []
    for threshold in candidates:
        metrics = threshold_metrics(y, probability, float(threshold))
        if float(metrics["recall"]) >= minimum_recall:
            eligible.append(
                (
                    float(metrics["false_positive_rate"]),
                    -float(threshold),
                    -float(metrics["recall"]),
                    metrics,
                )
            )
    if not eligible:
        raise ValueError("no validation threshold reaches the required recall")
    best = min(eligible, key=lambda item: item[:3])
    return float(best[3]["threshold"]), best[3]


def calibration_bins(
    y: np.ndarray, probability: np.ndarray, bins: int = 10
) -> list[dict[str, float | int]]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    memberships = np.minimum(np.digitize(probability, edges[1:-1]), bins - 1)
    result: list[dict[str, float | int]] = []
    for index in range(bins):
        mask = memberships == index
        if np.any(mask):
            result.append(
                {
                    "bin": index,
                    "n": int(np.sum(mask)),
                    "mean_probability": float(np.mean(probability[mask])),
                    "observed_rate": float(np.mean(y[mask])),
                }
            )
    return result


def activation_matrix(
    rows: Sequence[dict[str, Any]], names: Sequence[str]
) -> np.ndarray:
    matrix = np.asarray(
        [[float(row["activation_features"][name]) for name in names] for row in rows],
        dtype=np.float64,
    )
    if not np.isfinite(matrix).all():
        raise ValueError("non-finite activation feature")
    return matrix


class FeaturePipeline:
    """Fit/transform one baseline or baseline-plus-activation representation."""

    def __init__(self, name: str, config: dict[str, Any]):
        self.name = name
        self.config = config
        self.scaler: StandardScaler | None = None
        self.vectorizer: TfidfVectorizer | None = None

    def _raw_dense(
        self,
        rows: Sequence[dict[str, Any]],
        embeddings: np.ndarray,
    ) -> np.ndarray:
        activation_names = list(self.config["features"]["activation"])
        activation = activation_matrix(rows, activation_names)
        turn = np.asarray([[float(row["turn"])] for row in rows])
        if self.name == "turn":
            return turn
        if self.name == "e5":
            return embeddings
        if self.name == "e5_turn":
            return np.column_stack([embeddings, turn])
        if self.name == "activation" or self.name in {
            "combined_prevalence",
            "combined_turn",
        }:
            return activation
        if self.name in {"combined_e5", "combined_e5_turn"}:
            return np.column_stack([embeddings, activation])
        raise ValueError(f"unsupported dense representation: {self.name}")

    def fit_transform(
        self, rows: Sequence[dict[str, Any]], embeddings: np.ndarray
    ) -> Any:
        if self.name in {"tfidf", "combined_tfidf"}:
            tfidf = self.config["analysis"]["tfidf"]
            self.vectorizer = TfidfVectorizer(
                ngram_range=tuple(int(x) for x in tfidf["ngram_range"]),
                min_df=int(tfidf["min_df"]),
                max_features=int(tfidf["max_features"]),
                sublinear_tf=bool(tfidf["sublinear_tf"]),
                dtype=np.float64,
            )
            text = self.vectorizer.fit_transform([str(row["text_prefix"]) for row in rows])
            if self.name == "tfidf":
                return text
            activation = activation_matrix(rows, self.config["features"]["activation"])
            self.scaler = StandardScaler().fit(activation)
            return sparse.hstack(
                [text, sparse.csr_matrix(self.scaler.transform(activation))],
                format="csr",
            )
        raw = self._raw_dense(rows, embeddings)
        self.scaler = StandardScaler().fit(raw)
        return self.scaler.transform(raw)

    def transform(
        self, rows: Sequence[dict[str, Any]], embeddings: np.ndarray
    ) -> Any:
        if self.name in {"tfidf", "combined_tfidf"}:
            if self.vectorizer is None:
                raise RuntimeError("feature pipeline has not been fitted")
            text = self.vectorizer.transform([str(row["text_prefix"]) for row in rows])
            if self.name == "tfidf":
                return text
            if self.scaler is None:
                raise RuntimeError("activation scaler has not been fitted")
            activation = activation_matrix(rows, self.config["features"]["activation"])
            return sparse.hstack(
                [text, sparse.csr_matrix(self.scaler.transform(activation))],
                format="csr",
            )
        if self.scaler is None:
            raise RuntimeError("feature pipeline has not been fitted")
        return self.scaler.transform(self._raw_dense(rows, embeddings))


def fit_classifier(x: Any, y: np.ndarray, c_value: float) -> LogisticRegression:
    model = LogisticRegression(
        C=float(c_value),
        class_weight="balanced",
        penalty="l2",
        solver="liblinear",
        max_iter=5000,
        random_state=0,
    )
    model.fit(x, y)
    return model


def tune_representation(
    name: str,
    train_rows: Sequence[dict[str, Any]],
    train_embeddings: np.ndarray,
    train_y: np.ndarray,
    validation_rows: Sequence[dict[str, Any]],
    validation_embeddings: np.ndarray,
    validation_y: np.ndarray,
    config: dict[str, Any],
) -> dict[str, Any]:
    pipeline = FeaturePipeline(name, config)
    train_x = pipeline.fit_transform(train_rows, train_embeddings)
    validation_x = pipeline.transform(validation_rows, validation_embeddings)
    candidates: list[dict[str, Any]] = []
    for c_value in config["analysis"]["c_grid"]:
        model = fit_classifier(train_x, train_y, float(c_value))
        probability = model.predict_proba(validation_x)[:, 1]
        metrics = metric_summary(validation_y, probability)
        candidates.append(
            {"c": float(c_value), "metrics": metrics, "probability": probability}
        )
    best = min(
        candidates,
        key=lambda item: (
            -item["metrics"]["auprc"],
            item["metrics"]["brier"],
            item["c"],
        ),
    )
    return {
        "name": name,
        "c": best["c"],
        "validation": best["metrics"],
        "validation_probability": best["probability"],
        "grid": [
            {"c": item["c"], **item["metrics"]} for item in candidates
        ],
    }


def fit_final(
    name: str,
    c_value: float,
    fit_rows: Sequence[dict[str, Any]],
    fit_embeddings: np.ndarray,
    fit_y: np.ndarray,
    test_rows: Sequence[dict[str, Any]],
    test_embeddings: np.ndarray,
    config: dict[str, Any],
) -> tuple[np.ndarray, FeaturePipeline, LogisticRegression]:
    pipeline = FeaturePipeline(name, config)
    fit_x = pipeline.fit_transform(fit_rows, fit_embeddings)
    test_x = pipeline.transform(test_rows, test_embeddings)
    model = fit_classifier(fit_x, fit_y, c_value)
    return model.predict_proba(test_x)[:, 1], pipeline, model


def trajectory_warning_metrics(
    rows: Sequence[dict[str, Any]],
    probability: np.ndarray,
    threshold: float,
    horizon: int,
) -> dict[str, Any]:
    indices: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        if row["drift_onset_turn"] is not None:
            indices.setdefault(str(row["trajectory_id"]), []).append(index)
    lead_times: list[int] = []
    for trajectory_id in sorted(indices):
        alerts = []
        for index in indices[trajectory_id]:
            row = rows[index]
            lead = int(row["drift_onset_turn"]) - int(row["turn"])
            if 1 <= lead <= horizon and probability[index] >= threshold:
                alerts.append(lead)
        if alerts:
            lead_times.append(max(alerts))
    total = len(indices)
    return {
        "drift_trajectories": total,
        "detected_trajectories": len(lead_times),
        "trajectory_detection_rate": float(len(lead_times) / max(1, total)),
        "median_warning_lead_turns": (
            float(np.median(lead_times)) if lead_times else None
        ),
        "recall_at_lead_at_least_1": float(
            sum(lead >= 1 for lead in lead_times) / max(1, total)
        ),
        "recall_at_lead_at_least_3": float(
            sum(lead >= 3 for lead in lead_times) / max(1, total)
        ),
        "recall_at_lead_at_least_5": float(
            sum(lead >= 5 for lead in lead_times) / max(1, total)
        ),
        "detected_lead_times": lead_times,
    }


def bootstrap_comparison(
    rows: Sequence[dict[str, Any]],
    y: np.ndarray,
    text_probability: np.ndarray,
    activation_probability: np.ndarray,
    combined_probability: np.ndarray,
    *,
    samples: int,
    seed: int,
) -> dict[str, Any]:
    groups = [str(row["trajectory_id"]) for row in rows]
    strata = [str(row["condition"]) for row in rows]
    draws = stratified_cluster_bootstrap_indices(
        groups, strata, samples=samples, seed=seed
    )
    activation_delta = np.empty(samples, dtype=float)
    combined_delta = np.empty(samples, dtype=float)
    combined_brier_gain = np.empty(samples, dtype=float)
    for iteration, indices in enumerate(draws):
        sampled_y = y[indices]
        text = text_probability[indices]
        activation = activation_probability[indices]
        combined = combined_probability[indices]
        activation_delta[iteration] = average_precision_score(sampled_y, activation) - average_precision_score(sampled_y, text)
        combined_delta[iteration] = average_precision_score(sampled_y, combined) - average_precision_score(sampled_y, text)
        combined_brier_gain[iteration] = brier_score_loss(sampled_y, text) - brier_score_loss(sampled_y, combined)

    def interval(values: np.ndarray) -> list[float]:
        return [float(x) for x in np.quantile(values, [0.025, 0.975])]

    return {
        "samples": samples,
        "seed": seed,
        "resampling_unit": "complete_trajectory",
        "strata": "condition",
        "activation_minus_text_auprc_95ci": interval(activation_delta),
        "combined_minus_text_auprc_95ci": interval(combined_delta),
        "text_minus_combined_brier_95ci": interval(combined_brier_gain),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output = config["output"]
    dataset_path = Path(output["dataset"])
    dataset_summary_path = Path(output["dataset_summary"])
    embeddings_path = Path(output["embeddings"])
    embeddings_summary_path = Path(output["embeddings_summary"])
    dataset_summary = json.loads(dataset_summary_path.read_text(encoding="utf-8"))
    embeddings_summary = json.loads(embeddings_summary_path.read_text(encoding="utf-8"))
    if sha256(dataset_path) != dataset_summary["dataset_sha256"]:
        raise ValueError("dataset hash mismatch")
    if sha256(embeddings_path) != embeddings_summary["embeddings_sha256"]:
        raise ValueError("embedding hash mismatch")
    if embeddings_summary["dataset_sha256"] != dataset_summary["dataset_sha256"]:
        raise ValueError("embeddings were generated from a different dataset")

    rows = read_jsonl(dataset_path)
    archive = np.load(embeddings_path, allow_pickle=False)
    embedded_ids = archive["example_ids"].astype(str)
    embeddings = archive["embeddings"].astype(np.float64)
    row_ids = np.asarray([str(row["example_id"]) for row in rows])
    if not np.array_equal(embedded_ids, row_ids):
        raise ValueError("embedding rows are not aligned to the dataset")

    analysis_dir = Path(output["analysis_dir"])
    if analysis_dir.exists() and any(analysis_dir.iterdir()):
        raise FileExistsError(f"analysis output directory is not empty: {analysis_dir}")
    analysis_dir.mkdir(parents=True, exist_ok=True)
    positive_axis = str(config["scope"]["positive_axis"])
    negative_axis = str(config["scope"]["negative_control_axis"])
    horizons = sorted(
        {
            int(config["labels"]["primary_horizon"]),
            *[int(x) for x in config["labels"]["sensitivity_horizons"]],
        }
    )
    result: dict[str, Any] = {
        "protocol": "gate_c_development_forecasting_v1",
        "mode": config["mode"],
        "confirmatory": False,
        "selection_policy": "training_and_validation_topics_only",
        "dataset_sha256": sha256(dataset_path),
        "embeddings_sha256": sha256(embeddings_path),
        "config": str(args.config),
        "config_sha256": sha256(args.config),
        "horizons": {},
    }
    primary_payload: dict[str, Any] | None = None

    for horizon in horizons:
        eligible_key = f"eligible_h{horizon}"
        label_key = f"label_h{horizon}"
        masks: dict[str, np.ndarray] = {}
        for split in ["train", "validation", "development_test"]:
            masks[split] = np.asarray(
                [
                    row["axis"] == positive_axis
                    and row["development_split"] == split
                    and bool(row[eligible_key])
                    for row in rows
                ],
                dtype=bool,
            )
        split_rows = {name: [row for row, keep in zip(rows, mask) if keep] for name, mask in masks.items()}
        split_embeddings = {name: embeddings[mask] for name, mask in masks.items()}
        split_y = {
            name: np.asarray([int(row[label_key]) for row in selected], dtype=int)
            for name, selected in split_rows.items()
        }
        for split, y in split_y.items():
            if len(np.unique(y)) != 2:
                raise ValueError(f"{split} h{horizon} lacks both classes")

        prevalence = float(np.mean(split_y["train"]))
        prevalence_probability = np.full(len(split_y["validation"]), prevalence)
        baselines: dict[str, dict[str, Any]] = {
            "prevalence": {
                "name": "prevalence",
                "c": None,
                "validation": metric_summary(split_y["validation"], prevalence_probability),
                "validation_probability": prevalence_probability,
                "grid": [],
            }
        }
        for name in ["turn", "tfidf", "e5", "e5_turn"]:
            baselines[name] = tune_representation(
                name,
                split_rows["train"],
                split_embeddings["train"],
                split_y["train"],
                split_rows["validation"],
                split_embeddings["validation"],
                split_y["validation"],
                config,
            )
        selected_name = min(
            baselines,
            key=lambda name: (
                -baselines[name]["validation"]["auprc"],
                baselines[name]["validation"]["brier"],
                name,
            ),
        )
        activation_tuning = tune_representation(
            "activation",
            split_rows["train"],
            split_embeddings["train"],
            split_y["train"],
            split_rows["validation"],
            split_embeddings["validation"],
            split_y["validation"],
            config,
        )
        combined_name = f"combined_{selected_name}"
        combined_tuning = tune_representation(
            combined_name,
            split_rows["train"],
            split_embeddings["train"],
            split_y["train"],
            split_rows["validation"],
            split_embeddings["validation"],
            split_y["validation"],
            config,
        )
        threshold, validation_threshold_metrics = choose_threshold(
            split_y["validation"],
            combined_tuning["validation_probability"],
            float(config["analysis"]["validation_min_recall"]),
        )

        fit_rows = split_rows["train"] + split_rows["validation"]
        fit_embeddings = np.concatenate(
            [split_embeddings["train"], split_embeddings["validation"]], axis=0
        )
        fit_y = np.concatenate([split_y["train"], split_y["validation"]])
        if selected_name == "prevalence":
            text_probability = np.full(
                len(split_y["development_test"]), float(np.mean(fit_y))
            )
            text_pipeline = None
            text_model = None
        else:
            text_probability, text_pipeline, text_model = fit_final(
                selected_name,
                float(baselines[selected_name]["c"]),
                fit_rows,
                fit_embeddings,
                fit_y,
                split_rows["development_test"],
                split_embeddings["development_test"],
                config,
            )
        activation_probability, _, _ = fit_final(
            "activation",
            float(activation_tuning["c"]),
            fit_rows,
            fit_embeddings,
            fit_y,
            split_rows["development_test"],
            split_embeddings["development_test"],
            config,
        )
        combined_probability, combined_pipeline, combined_model = fit_final(
            combined_name,
            float(combined_tuning["c"]),
            fit_rows,
            fit_embeddings,
            fit_y,
            split_rows["development_test"],
            split_embeddings["development_test"],
            config,
        )
        test_y = split_y["development_test"]
        text_metrics = metric_summary(test_y, text_probability)
        activation_metrics = metric_summary(test_y, activation_probability)
        combined_metrics = metric_summary(test_y, combined_probability)
        horizon_result: dict[str, Any] = {
            "horizon": horizon,
            "split_counts": {
                split: {
                    "examples": int(len(y)),
                    "positive": int(np.sum(y)),
                    "negative": int(len(y) - np.sum(y)),
                    "trajectories": len(
                        {row["trajectory_id"] for row in split_rows[split]}
                    ),
                }
                for split, y in split_y.items()
            },
            "validation_baselines": {
                name: {
                    "selected_c": value["c"],
                    "metrics": value["validation"],
                    "grid": value["grid"],
                }
                for name, value in baselines.items()
            },
            "selected_text_baseline": selected_name,
            "activation_selected_c": activation_tuning["c"],
            "combined_representation": combined_name,
            "combined_selected_c": combined_tuning["c"],
            "threshold_selection": {
                "minimum_validation_recall": float(
                    config["analysis"]["validation_min_recall"]
                ),
                "selected_threshold": threshold,
                "validation_metrics": validation_threshold_metrics,
                "note": "selected on train-fit validation predictions; applied unchanged after train+validation refit",
            },
            "development_test": {
                "text": text_metrics,
                "activation": activation_metrics,
                "combined": combined_metrics,
                "activation_minus_text_auprc": float(
                    activation_metrics["auprc"] - text_metrics["auprc"]
                ),
                "combined_minus_text_auprc": float(
                    combined_metrics["auprc"] - text_metrics["auprc"]
                ),
                "text_minus_combined_brier": float(
                    text_metrics["brier"] - combined_metrics["brier"]
                ),
                "combined_threshold_metrics": threshold_metrics(
                    test_y, combined_probability, threshold
                ),
                "combined_calibration_bins": calibration_bins(
                    test_y, combined_probability
                ),
                "warning": trajectory_warning_metrics(
                    split_rows["development_test"],
                    combined_probability,
                    threshold,
                    horizon,
                ),
            },
        }
        result["horizons"][f"h{horizon}"] = horizon_result

        if horizon == int(config["labels"]["primary_horizon"]):
            bootstrap = bootstrap_comparison(
                split_rows["development_test"],
                test_y,
                text_probability,
                activation_probability,
                combined_probability,
                samples=int(config["analysis"]["bootstrap_samples"]),
                seed=int(config["analysis"]["bootstrap_seed"]),
            )
            horizon_result["development_test"]["clustered_bootstrap"] = bootstrap
            negative_mask = np.asarray(
                [
                    row["axis"] == negative_axis
                    and row["development_split"] == "development_test"
                    and bool(row[eligible_key])
                    for row in rows
                ],
                dtype=bool,
            )
            negative_rows = [row for row, keep in zip(rows, negative_mask) if keep]
            negative_embeddings = embeddings[negative_mask]
            negative_x = combined_pipeline.transform(negative_rows, negative_embeddings)
            negative_probability = combined_model.predict_proba(negative_x)[:, 1]
            false_alarms = int(np.sum(negative_probability >= threshold))
            negative_control = {
                "axis": negative_axis,
                "examples": len(negative_rows),
                "trajectories": len({row["trajectory_id"] for row in negative_rows}),
                "predicted_alarms": false_alarms,
                "false_alarms_per_100_eligible_turns": float(
                    100.0 * false_alarms / max(1, len(negative_rows))
                ),
                "mean_probability": float(np.mean(negative_probability)),
            }
            horizon_result["negative_control"] = negative_control
            primary_payload = {
                "rows": split_rows["development_test"],
                "y": test_y,
                "text": text_probability,
                "activation": activation_probability,
                "combined": combined_probability,
                "negative_rows": negative_rows,
                "negative_probability": negative_probability,
                "threshold": threshold,
            }

    if primary_payload is None:
        raise RuntimeError("primary horizon was not analyzed")
    primary = result["horizons"][f"h{config['labels']['primary_horizon']}"]
    primary_test = primary["development_test"]
    ci = primary_test["clustered_bootstrap"]["combined_minus_text_auprc_95ci"]
    result["development_interpretation"] = {
        "promising": bool(
            primary_test["combined_minus_text_auprc"] > 0.0
            and ci[0] > 0.0
            and primary_test["text_minus_combined_brier"] >= 0.0
        ),
        "criteria": {
            "combined_minus_text_auprc_positive": bool(
                primary_test["combined_minus_text_auprc"] > 0.0
            ),
            "paired_bootstrap_lower_bound_above_zero": bool(ci[0] > 0.0),
            "combined_does_not_worsen_brier": bool(
                primary_test["text_minus_combined_brier"] >= 0.0
            ),
        },
        "confirmatory_claim_allowed": False,
    }

    predictions_path = analysis_dir / "primary_predictions.csv"
    with predictions_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "example_id",
                "trajectory_id",
                "axis",
                "condition",
                "topic",
                "turn",
                "onset",
                "label",
                "text_probability",
                "activation_probability",
                "combined_probability",
                "threshold",
                "combined_alarm",
            ],
        )
        writer.writeheader()
        for index, row in enumerate(primary_payload["rows"]):
            writer.writerow(
                {
                    "example_id": row["example_id"],
                    "trajectory_id": row["trajectory_id"],
                    "axis": row["axis"],
                    "condition": row["condition"],
                    "topic": row["topic"],
                    "turn": row["turn"],
                    "onset": row["drift_onset_turn"],
                    "label": int(primary_payload["y"][index]),
                    "text_probability": float(primary_payload["text"][index]),
                    "activation_probability": float(primary_payload["activation"][index]),
                    "combined_probability": float(primary_payload["combined"][index]),
                    "threshold": float(primary_payload["threshold"]),
                    "combined_alarm": int(
                        primary_payload["combined"][index]
                        >= primary_payload["threshold"]
                    ),
                }
            )
    negative_path = analysis_dir / "negative_control_predictions.csv"
    with negative_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "example_id",
                "trajectory_id",
                "axis",
                "condition",
                "topic",
                "turn",
                "combined_probability",
                "threshold",
                "alarm",
            ],
        )
        writer.writeheader()
        for index, row in enumerate(primary_payload["negative_rows"]):
            probability = float(primary_payload["negative_probability"][index])
            writer.writerow(
                {
                    "example_id": row["example_id"],
                    "trajectory_id": row["trajectory_id"],
                    "axis": row["axis"],
                    "condition": row["condition"],
                    "topic": row["topic"],
                    "turn": row["turn"],
                    "combined_probability": probability,
                    "threshold": float(primary_payload["threshold"]),
                    "alarm": int(probability >= primary_payload["threshold"]),
                }
            )

    result["artifacts"] = {
        "primary_predictions": str(predictions_path),
        "primary_predictions_sha256": sha256(predictions_path),
        "negative_control_predictions": str(negative_path),
        "negative_control_predictions_sha256": sha256(negative_path),
    }
    summary_path = analysis_dir / "summary.json"
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
