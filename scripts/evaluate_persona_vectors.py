#!/usr/bin/env python3
"""Run validation-only layer selection and held-out Gate B evaluation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

import torch
import yaml

from persona_drift.extraction import load_activation_payload
from persona_drift.judging import load_jsonl, sha256_file
from persona_drift.representation import (
    bootstrap_paired_metrics,
    cosine_layer_scores,
    select_common_layer,
    summarize_binary_pairs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/gate_b.yaml"))
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def load_vector_payload(path: Path) -> dict[str, Any]:
    try:
        payload = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError as exc:
        if "weights_only" not in str(exc):
            raise
        payload = torch.load(path, map_location="cpu")
    if not isinstance(payload, dict) or not isinstance(payload.get("vectors"), dict):
        raise ValueError("invalid persona-vector payload")
    return payload


def build_projection_rows(
    records: list[dict[str, Any]], vectors: dict[str, torch.Tensor]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        axis = str(record["axis"])
        if axis not in vectors:
            raise ValueError(f"manifest axis has no persona vector: {axis}")
        if record.get("split") not in {"validation", "test"}:
            raise ValueError(f"missing or invalid split for {record['example_id']}")
        activation_path = Path(record["activation_path"])
        payload = load_activation_payload(activation_path)
        activation = payload.get("response_token_mean")
        if not isinstance(activation, torch.Tensor):
            raise ValueError(f"missing response activation: {activation_path}")
        scores = cosine_layer_scores(activation, vectors[axis])
        rows.append(
            {
                "example_id": str(record["example_id"]),
                "prompt_id": str(record["prompt_id"]),
                "topic": str(record.get("topic", "")),
                "split": str(record["split"]),
                "axis": axis,
                "polarity": str(record["polarity"]),
                "seed": int(record["seed"]),
                "accepted": record.get("accepted"),
                "scores": [float(value) for value in scores],
            }
        )
    return rows


def summarize_axis_layer(
    rows: list[dict[str, Any]], *, split: str, axis: str, layer: int
) -> dict[str, Any]:
    selected = [
        row for row in rows if row["split"] == split and row["axis"] == axis
    ]
    if not selected:
        raise ValueError(f"no records for split={split}, axis={axis}")
    return summarize_binary_pairs(
        [row["scores"][layer] for row in selected],
        [row["polarity"] for row in selected],
        [f"{row['prompt_id']}:{row['axis']}:{row['seed']}" for row in selected],
    )


def layer_report(
    rows: list[dict[str, Any]],
    *,
    split: str,
    layer: int,
    axes: list[str],
    bootstrap_samples: int | None = None,
    bootstrap_seed: int = 0,
) -> dict[str, Any]:
    axis_reports: dict[str, Any] = {}
    for axis_index, axis in enumerate(axes):
        metrics = summarize_axis_layer(rows, split=split, axis=axis, layer=layer)
        if bootstrap_samples is not None:
            selected = [
                row
                for row in rows
                if row["split"] == split and row["axis"] == axis
            ]
            metrics["bootstrap"] = bootstrap_paired_metrics(
                [row["scores"][layer] for row in selected],
                [row["polarity"] for row in selected],
                [
                    f"{row['prompt_id']}:{row['axis']}:{row['seed']}"
                    for row in selected
                ],
                samples=bootstrap_samples,
                seed=bootstrap_seed + axis_index,
            )
        axis_reports[axis] = metrics
    return {
        "split": split,
        "layer": layer,
        "axes": axis_reports,
        "mean_auroc": mean(item["auroc"] for item in axis_reports.values()),
        "mean_pair_direction_accuracy": mean(
            item["pair_direction_accuracy"] for item in axis_reports.values()
        ),
    }


def acceptance_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not all(isinstance(row.get("accepted"), bool) for row in rows):
        return {"available": False}
    groups: dict[str, dict[str, int]] = {}
    for axis in sorted({row["axis"] for row in rows}):
        groups[axis] = {}
        for polarity in ("target", "contrast"):
            subset = [
                row
                for row in rows
                if row["axis"] == axis and row["polarity"] == polarity
            ]
            groups[axis][polarity] = sum(row["accepted"] is True for row in subset)
    return {
        "available": True,
        "accepted_examples": sum(row["accepted"] is True for row in rows),
        "total_examples": len(rows),
        "accepted_by_axis_polarity": groups,
        "analysis_filtering": "none_intention_to_treat",
    }


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output_dir = Path(config["outputs"]["projection_dir"])
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"projection output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    vector_path = Path(config["vectors"]["path"])
    actual_vector_hash = sha256_file(vector_path)
    if actual_vector_hash != str(config["vectors"]["sha256"]):
        raise ValueError("persona-vector SHA256 does not match frozen Gate B config")
    vector_payload = load_vector_payload(vector_path)
    vectors = vector_payload["vectors"]
    if not all(isinstance(vector, torch.Tensor) for vector in vectors.values()):
        raise ValueError("all persona vectors must be tensors")

    records = load_jsonl(args.manifest)
    rows = build_projection_rows(records, vectors)
    axes = sorted(vectors)
    layer_counts = {len(row["scores"]) for row in rows}
    if len(layer_counts) != 1:
        raise ValueError(f"inconsistent activation layer counts: {layer_counts}")
    layer_count = layer_counts.pop()
    reference_layer = int(config["vectors"]["reference_layer"])

    validation_layers = [
        layer_report(
            rows,
            split=str(config["data"]["validation_split"]),
            layer=layer,
            axes=axes,
        )
        for layer in range(layer_count)
    ]
    selected_layer = select_common_layer(
        validation_layers, reference_layer=reference_layer
    )
    bootstrap_samples = int(config["bootstrap"]["samples"])
    bootstrap_seed = int(config["bootstrap"]["seed"])
    test_selected = layer_report(
        rows,
        split=str(config["data"]["test_split"]),
        layer=selected_layer,
        axes=axes,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
    )
    test_reference = layer_report(
        rows,
        split=str(config["data"]["test_split"]),
        layer=reference_layer,
        axes=axes,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed + 100,
    )

    gate = config["gate"]
    selected_axes = test_selected["axes"]
    gate_checks = {
        "mean_test_auroc": test_selected["mean_auroc"]
        >= float(gate["min_mean_test_auroc"]),
        "each_axis_test_auroc": all(
            item["auroc"] >= float(gate["min_each_axis_test_auroc"])
            for item in selected_axes.values()
        ),
        "each_axis_test_pair_accuracy": all(
            item["pair_direction_accuracy"]
            >= float(gate["min_each_axis_test_pair_accuracy"])
            for item in selected_axes.values()
        ),
    }
    summary = {
        "protocol": "held_out_gate_b_v1",
        "analysis_policy": "intention_to_treat_no_review_filtering",
        "examples": len(rows),
        "axes": axes,
        "splits": {
            split: sum(row["split"] == split for row in rows)
            for split in sorted({row["split"] for row in rows})
        },
        "layer_selection_rule": config["selection"]["rule"],
        "reference_layer": reference_layer,
        "selected_layer": selected_layer,
        "validation_layer_metrics": validation_layers,
        "test_selected_layer": test_selected,
        "test_reference_layer": test_reference,
        "behavior_review": acceptance_summary(rows),
        "gate_thresholds": gate,
        "gate_checks": gate_checks,
        "gate_pass": all(gate_checks.values()),
        "manifest": str(args.manifest),
        "manifest_sha256": sha256_file(args.manifest),
        "vectors": str(vector_path),
        "vectors_sha256": actual_vector_hash,
        "config": str(args.config),
        "config_sha256": sha256_file(args.config),
    }

    selected_roles = {selected_layer: "selected"}
    if reference_layer == selected_layer:
        selected_roles[selected_layer] = "selected_and_reference"
    else:
        selected_roles[reference_layer] = "reference"
    score_path = output_dir / "projection_scores.csv"
    with score_path.open("x", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "example_id",
            "prompt_id",
            "topic",
            "split",
            "axis",
            "polarity",
            "seed",
            "accepted",
            "layer",
            "layer_role",
            "cosine_projection",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            for layer, role in sorted(selected_roles.items()):
                writer.writerow(
                    {
                        **{name: row[name] for name in fieldnames[:8]},
                        "layer": layer,
                        "layer_role": role,
                        "cosine_projection": row["scores"][layer],
                    }
                )
    summary["projection_scores"] = str(score_path)
    summary["projection_scores_sha256"] = hashlib.sha256(
        score_path.read_bytes()
    ).hexdigest()
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
