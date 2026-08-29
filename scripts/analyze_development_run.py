#!/usr/bin/env python3
"""Descriptive matched analysis for the exploratory Development run.

Activation displacement is deliberately not labeled Persona Drift: this run has
no independently assigned behavior-only Drift outcomes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np


NEUTRAL = "neutral_L0"
PRESSURE = "gradual_direct_opposition_L0_to_L5"
LEVELS = (0,) * 5 + (1,) * 4 + (2,) * 4 + (3,) * 4 + (4,) * 4 + (5,) * 4


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cosine_distance(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    if left.shape != right.shape or left.ndim < 2:
        raise ValueError("activation arrays must have the same shape and at least two axes")
    left = left.astype(np.float64, copy=False)
    right = right.astype(np.float64, copy=False)
    denominator = np.linalg.norm(left, axis=-1) * np.linalg.norm(right, axis=-1)
    if np.any(denominator == 0):
        raise ValueError("zero-norm activation vector")
    return np.maximum(0.0, 1.0 - np.sum(left * right, axis=-1) / denominator)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analyze(output_dir: Path, report_dir: Path) -> dict[str, Any]:
    ledger = output_dir / "trajectories.jsonl"
    records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    if len(records) != 432:
        raise ValueError(f"expected 432 records, found {len(records)}")
    counts = Counter(row["condition_id"] for row in records)
    if counts != {NEUTRAL: 216, PRESSURE: 216}:
        raise ValueError(f"condition imbalance: {dict(counts)}")

    indexed = {
        (row["persona_trait_id"], row["topic_id"], row["condition_id"]): row
        for row in records
    }
    cells = sorted({(row["persona_trait_id"], row["topic_id"]) for row in records})
    if len(cells) != 216 or len(indexed) != 432:
        raise ValueError("matched Persona x Topic coverage is incomplete")

    distances: list[np.ndarray] = []
    exact_matches: list[list[bool]] = []
    length_deltas: list[list[int]] = []
    layer_indices: list[int] | None = None
    for trait_id, topic_id in cells:
        neutral = indexed[(trait_id, topic_id, NEUTRAL)]
        pressure = indexed[(trait_id, topic_id, PRESSURE)]
        neutral_npz = np.load(output_dir / neutral["activation_artifact"]["path"])
        pressure_npz = np.load(output_dir / pressure["activation_artifact"]["path"])
        observed_layers = neutral_npz["layer_indices"].tolist()
        if layer_indices is None:
            layer_indices = observed_layers
        if observed_layers != layer_indices or pressure_npz["layer_indices"].tolist() != layer_indices:
            raise ValueError("activation layer mismatch")
        distances.append(cosine_distance(neutral_npz["activations"], pressure_npz["activations"]))
        exact_matches.append([
            left == right
            for left, right in zip(
                neutral["assistant_responses"], pressure["assistant_responses"], strict=True
            )
        ])
        length_deltas.append([
            len(right) - len(left)
            for left, right in zip(
                neutral["assistant_responses"], pressure["assistant_responses"], strict=True
            )
        ])

    assert layer_indices is not None
    distance = np.stack(distances)
    exact = np.asarray(exact_matches)
    length_delta = np.asarray(length_deltas)
    if distance.shape != (216, 25, 5):
        raise ValueError(f"unexpected matched activation shape: {distance.shape}")

    turn_layer_rows: list[dict[str, Any]] = []
    for turn in range(25):
        for layer_position, layer in enumerate(layer_indices):
            values = distance[:, turn, layer_position]
            turn_layer_rows.append({
                "turn": turn + 1,
                "pressure_level": LEVELS[turn],
                "layer": layer,
                "matched_pairs": len(cells),
                "cosine_distance_mean": float(values.mean()),
                "cosine_distance_median": float(np.median(values)),
                "cosine_distance_q10": float(np.quantile(values, 0.10)),
                "cosine_distance_q90": float(np.quantile(values, 0.90)),
            })

    level_layer_rows: list[dict[str, Any]] = []
    for level in range(6):
        turns = [i for i, observed in enumerate(LEVELS) if observed == level]
        for layer_position, layer in enumerate(layer_indices):
            values = distance[:, turns, layer_position].reshape(-1)
            level_layer_rows.append({
                "pressure_level": level,
                "turns": "|".join(str(i + 1) for i in turns),
                "layer": layer,
                "matched_pair_turns": int(values.size),
                "cosine_distance_mean": float(values.mean()),
                "cosine_distance_median": float(np.median(values)),
                "cosine_distance_q10": float(np.quantile(values, 0.10)),
                "cosine_distance_q90": float(np.quantile(values, 0.90)),
            })

    response_rows = [{
        "turn": turn + 1,
        "pressure_level": LEVELS[turn],
        "matched_pairs": len(cells),
        "response_exact_match_rate": float(exact[:, turn].mean()),
        "pressure_minus_neutral_chars_mean": float(length_delta[:, turn].mean()),
        "pressure_minus_neutral_chars_median": float(np.median(length_delta[:, turn])),
    } for turn in range(25)]

    report_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(report_dir / "activation_matched_turn_layer_v0.csv", turn_layer_rows)
    _write_csv(report_dir / "activation_matched_level_layer_v0.csv", level_layer_rows)
    _write_csv(report_dir / "response_matched_turn_v0.csv", response_rows)
    summary = {
        "schema_version": "exploratory-development-matched-description-v0",
        "scientific_scope": "descriptive_pressure_association_not_persona_drift",
        "input": {
            "ledger_path": str(ledger),
            "ledger_sha256": _sha256(ledger),
            "records": len(records),
            "source_commits": sorted({
                row["runner_implementation"]["source_commit"] for row in records
            }),
        },
        "coverage": {
            "matched_persona_topic_pairs": len(cells),
            "persona_traits": len({trait for trait, _ in cells}),
            "topics": len({topic for _, topic in cells}),
            "turns": 25,
            "layers": layer_indices,
        },
        "negative_control_turns_1_5": {
            "pressure_level": 0,
            "response_exact_match_rate": float(exact[:, :5].mean()),
            "maximum_activation_cosine_distance": float(distance[:, :5, :].max()),
        },
        "pressure_turns_6_25": {
            "response_exact_match_rate": float(exact[:, 5:].mean()),
            "activation_cosine_distance_mean_by_layer": {
                str(layer): float(distance[:, 5:, position].mean())
                for position, layer in enumerate(layer_indices)
            },
        },
        "limitations": [
            "No independent behavior-only Drift labels were collected.",
            "Activation displacement is not evidence of Persona Drift.",
            "Pressure level is confounded with turn and accumulated history in this single schedule.",
            "These summaries are descriptive and support no causal or confirmatory claim.",
        ],
        "artifacts": [
            "activation_matched_turn_layer_v0.csv",
            "activation_matched_level_layer_v0.csv",
            "response_matched_turn_v0.csv",
        ],
    }
    summary_path = report_dir / "summary_v0.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/development/qwen2_5_7b_seed2026082901"),
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("data/development/run_v0/analysis_v0"),
    )
    args = parser.parse_args()
    print(json.dumps(analyze(args.output_dir, args.report_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
