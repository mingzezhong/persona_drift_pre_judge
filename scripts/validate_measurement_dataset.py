#!/usr/bin/env python3
"""Validate frozen measurement anchors, combined manifest, and review sheets."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output = config["output"]
    summary_path = Path(output["dataset_summary"])
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest_path = Path(output["combined_manifest"])
    anchor_path = Path(output["anchor_manifest"])
    qwen_path = Path(config["source"]["qwen_probe_manifest"])
    expected = int(config["design"]["expected_combined_examples"])

    checks = {
        "config_hash": summary["config_sha256"] == sha256(args.config),
        "anchor_hash": summary["anchor_manifest_sha256"] == sha256(anchor_path),
        "qwen_hash": summary["qwen_probe_manifest_sha256"] == sha256(qwen_path),
        "combined_hash": summary["combined_manifest_sha256"] == sha256(manifest_path),
    }
    rows = load_jsonl(manifest_path)
    ids = [str(row["example_id"]) for row in rows]
    checks["combined_count"] = len(rows) == expected
    checks["unique_ids"] = len(ids) == len(set(ids))
    anchors = [row for row in rows if "gold_score" in row]
    checks["anchor_count"] = len(anchors) == int(config["design"]["expected_anchors"])
    cells = Counter(
        (row["axis"], row["anchor_split"], int(row["gold_score"]))
        for row in anchors
    )
    checks["balanced_anchor_cells"] = all(
        cells[(axis, split, score)] == int(count)
        for axis in config["design"]["axes"]
        for split, count in config["design"]["scenarios_per_split"].items()
        for score in range(5)
    )

    review_orders: list[list[str]] = []
    review_details: dict[str, Any] = {}
    for reviewer_id, path_raw in output["review_sheets"].items():
        path = Path(path_raw)
        with path.open(encoding="utf-8", newline="") as handle:
            review = list(csv.DictReader(handle))
        review_ids = [row["example_id"] for row in review]
        valid = (
            len(review) == expected
            and len(review_ids) == len(set(review_ids))
            and set(review_ids) == set(ids)
            and all(row["reviewer_id"] == reviewer_id for row in review)
        )
        checks[f"review_{reviewer_id}"] = valid
        review_orders.append(review_ids)
        review_details[reviewer_id] = {
            "rows": len(review),
            "sha256": sha256(path),
        }
    checks["independent_review_orders"] = len(
        {tuple(order) for order in review_orders}
    ) == len(review_orders)
    report = {
        "protocol": "measurement_dataset_validation_v1",
        "checks": checks,
        "validation_pass": all(checks.values()),
        "combined_examples": len(rows),
        "anchors": len(anchors),
        "review_sheets": review_details,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["validation_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
