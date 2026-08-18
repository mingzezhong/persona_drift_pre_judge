#!/usr/bin/env python3
"""Create a frozen, blinded anchor manifest and three shuffled review sheets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
from typing import Any

import yaml


FIELDNAMES = [
    "review_order",
    "reviewer_id",
    "example_id",
    "prompt_id",
    "axis",
    "expected_trait",
    "seed",
    "user",
    "response",
    "trait_alignment",
    "task_relevance",
    "response_integrity",
    "prompt_leakage",
    "notes",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_anchor(template: str, scenario: dict[str, Any], axis: dict[str, Any]) -> str:
    return template.format(**scenario, **axis)


def build_records(config: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for axis_name, axis in config["axes"].items():
        for scenario in config["scenarios"]:
            split = str(scenario["split"])
            for score in range(5):
                example_id = f"anchor-{axis_name}-{scenario['id']}-score-{score}"
                records.append(
                    {
                        "example_id": example_id,
                        "prompt_id": f"anchor-{scenario['id']}",
                        "axis": axis_name,
                        "polarity": "target",
                        "expected_trait": axis["expected_trait"],
                        "seed": 0,
                        "user": render_anchor(
                            str(scenario["user"]), scenario, axis
                        ),
                        "response": render_anchor(
                            str(axis["responses"][score]), scenario, axis
                        ),
                        "gold_score": score,
                        "anchor_split": split,
                        "anchor_scenario": str(scenario["id"]),
                        "provenance": "hand_authored_behavioral_anchor_v1",
                    }
                )
    return records


def review_rows(
    records: list[dict[str, Any]], *, reviewer_id: str, seed: int
) -> list[dict[str, Any]]:
    rows = [
        {
            "review_order": 0,
            "reviewer_id": reviewer_id,
            "example_id": row["example_id"],
            "prompt_id": row["prompt_id"],
            "axis": row["axis"],
            "expected_trait": row["expected_trait"],
            "seed": row["seed"],
            "user": row["user"],
            "response": row["response"],
            "trait_alignment": "",
            "task_relevance": "",
            "response_integrity": "",
            "prompt_leakage": "",
            "notes": "",
        }
        for row in records
    ]
    random.Random(seed).shuffle(rows)
    for order, row in enumerate(rows, start=1):
        row["review_order"] = order
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output = config["output"]
    manifest_path = Path(output["anchor_manifest"])
    if manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite {manifest_path}")
    records = build_records(config)
    expected = int(config["design"]["expected_anchors"])
    if len(records) != expected:
        raise ValueError(f"created {len(records)} anchors, expected {expected}")
    counts: dict[tuple[str, str, int], int] = {}
    for row in records:
        key = (row["axis"], row["anchor_split"], row["gold_score"])
        counts[key] = counts.get(key, 0) + 1
    required = {
        (axis, split, score): int(count)
        for axis in config["axes"]
        for split, count in config["design"]["scenarios_per_split"].items()
        for score in range(5)
    }
    if counts != required:
        raise ValueError("anchor cells are not exactly balanced")
    manifest_path.parent.mkdir(parents=True, exist_ok=False)
    with manifest_path.open("x", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "protocol": "anchored_persona_measurement_v1",
        "anchors": len(records),
        "anchor_manifest": str(manifest_path),
        "anchor_manifest_sha256": sha256(manifest_path),
        "config": str(args.config),
        "config_sha256": sha256(args.config),
        "counts": {"|".join(map(str, key)): value for key, value in sorted(counts.items())},
    }
    summary_path = Path(output["anchor_summary"])
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
