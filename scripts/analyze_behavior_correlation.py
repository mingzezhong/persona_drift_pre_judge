#!/usr/bin/env python3
"""Complete Gate B with an output-based behavioral correlation analysis."""

from __future__ import annotations

from collections import defaultdict
import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from persona_drift.behavior import (
    bootstrap_clustered_correlations,
    pearson_correlation,
    spearman_correlation,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    inputs = config["inputs"]
    reviewed_path = Path(inputs["reviewed_manifest"])
    projection_path = Path(inputs["projection_scores"])
    expected_hashes = {
        reviewed_path: inputs["reviewed_manifest_sha256"],
        projection_path: inputs["projection_scores_sha256"],
    }
    for path, expected in expected_hashes.items():
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"SHA256 mismatch for {path}: {actual} != {expected}")

    reviewed = {row["example_id"]: row for row in load_jsonl(reviewed_path)}
    with projection_path.open(newline="", encoding="utf-8") as handle:
        projection_rows = list(csv.DictReader(handle))

    split = config["analysis"]["split"]
    layer = int(config["analysis"]["layer"])
    selected = [
        row
        for row in projection_rows
        if row["split"] == split and int(row["layer"]) == layer
    ]
    if not selected:
        raise RuntimeError("no projection rows match the configured split and layer")
    if len({row["example_id"] for row in selected}) != len(selected):
        raise RuntimeError("projection rows contain duplicate example IDs")

    per_example: list[dict[str, Any]] = []
    for row in selected:
        source = reviewed[row["example_id"]]
        reviewers = source["judge_score"]["reviewers"]
        trait_scores = [
            float(reviewer["scores"]["trait_alignment"])
            for reviewer in reviewers
        ]
        expected_reviewers = int(config["behavior_score"]["reviewers"])
        if len(trait_scores) != expected_reviewers:
            raise RuntimeError(
                f"{row['example_id']} has {len(trait_scores)} reviewers, "
                f"expected {expected_reviewers}"
            )
        alignment_mean = sum(trait_scores) / len(trait_scores)
        polarity_sign = 1.0 if row["polarity"] == "target" else -1.0
        signed_score = polarity_sign * alignment_mean / 4.0
        per_example.append(
            {
                "example_id": row["example_id"],
                "prompt_id": row["prompt_id"],
                "topic": row["topic"],
                "split": row["split"],
                "axis": row["axis"],
                "polarity": row["polarity"],
                "seed": int(row["seed"]),
                "pair_id": f"{row['prompt_id']}|{row['axis']}|{row['seed']}",
                "cosine_projection": float(row["cosine_projection"]),
                "trait_alignment_mean": alignment_mean,
                "signed_behavior_score": signed_score,
                "accepted": bool(source["accepted"]),
            }
        )

    axes = sorted({row["axis"] for row in per_example})
    expected_axes = sorted(config["analysis"]["expected_axes"])
    if axes != expected_axes:
        raise RuntimeError(f"observed axes {axes} differ from expected {expected_axes}")
    grouped_polarities: dict[str, set[str]] = defaultdict(set)
    for row in per_example:
        grouped_polarities[row["pair_id"]].add(row["polarity"])
    incomplete = [
        pair_id
        for pair_id, polarities in grouped_polarities.items()
        if polarities != {"target", "contrast"}
    ]
    if incomplete:
        raise RuntimeError(f"incomplete behavior-score pairs: {incomplete}")

    metrics: dict[str, Any] = {}
    bootstrap = config["bootstrap"]
    for offset, axis in enumerate(axes):
        rows = [row for row in per_example if row["axis"] == axis]
        projections = [row["cosine_projection"] for row in rows]
        behavior_scores = [row["signed_behavior_score"] for row in rows]
        pair_ids = [row["pair_id"] for row in rows]
        expected_examples = int(config["analysis"]["expected_examples_per_axis"])
        expected_pairs = int(config["analysis"]["expected_pairs_per_axis"])
        if len(rows) != expected_examples or len(set(pair_ids)) != expected_pairs:
            raise RuntimeError(
                f"{axis} has {len(rows)} examples and {len(set(pair_ids))} pairs; "
                f"expected {expected_examples} and {expected_pairs}"
            )
        metrics[axis] = {
            "examples": len(rows),
            "pairs": len(set(pair_ids)),
            "pearson_r": pearson_correlation(projections, behavior_scores),
            "spearman_rho": spearman_correlation(projections, behavior_scores),
            "bootstrap": bootstrap_clustered_correlations(
                projections,
                behavior_scores,
                pair_ids,
                samples=int(bootstrap["samples"]),
                seed=int(bootstrap["seed"]) + offset,
            ),
        }

    gate = config["gate"]
    threshold_check = all(
        item["spearman_rho"] >= float(gate["min_each_axis_spearman_rho"])
        for item in metrics.values()
    )
    ci_check = (
        not bool(gate["require_each_axis_spearman_95ci_above_zero"])
        or all(
            item["bootstrap"]["spearman_rho_95ci"][0] > 0
            for item in metrics.values()
        )
    )
    output_dir = Path(config["outputs"]["directory"])
    output_dir.mkdir(parents=True, exist_ok=False)
    per_example_path = output_dir / "behavior_scores.csv"
    with per_example_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_example[0]))
        writer.writeheader()
        writer.writerows(per_example)

    summary = {
        "protocol": "gate_b_output_behavior_correlation_v1",
        "design_status": config["design_status"],
        "analysis_policy": "intention_to_treat_no_review_filtering",
        "behavior_surface": config["behavior_score"],
        "split": split,
        "layer": layer,
        "examples": len(per_example),
        "axes": metrics,
        "gate_thresholds": gate,
        "gate_checks": {
            "each_axis_spearman_threshold": threshold_check,
            "each_axis_spearman_ci_above_zero": ci_check,
        },
        "gate_pass": threshold_check and ci_check,
        "reviewed_manifest": str(reviewed_path),
        "reviewed_manifest_sha256": sha256(reviewed_path),
        "projection_scores": str(projection_path),
        "projection_scores_sha256": sha256(projection_path),
        "config": str(args.config),
        "config_sha256": sha256(args.config),
        "behavior_scores": str(per_example_path),
        "behavior_scores_sha256": sha256(per_example_path),
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["gate_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
