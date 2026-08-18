#!/usr/bin/env python3
"""Combine frozen anchors and Qwen probes into blinded measurement review sheets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from scripts.create_measurement_anchors import FIELDNAMES, review_rows


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output = config["output"]
    anchor_path = Path(output["anchor_manifest"])
    qwen_path = Path(config["source"]["qwen_probe_manifest"])
    if sha256(qwen_path) != config["source"]["qwen_probe_manifest_sha256"]:
        raise ValueError("Qwen probe manifest hash mismatch")
    anchors = load_jsonl(anchor_path)
    qwen = load_jsonl(qwen_path)
    if len(anchors) != int(config["design"]["expected_anchors"]):
        raise ValueError("anchor count mismatch")
    if len(qwen) != int(config["design"]["expected_qwen_probes"]):
        raise ValueError("Qwen probe count mismatch")
    combined = anchors + qwen
    if len(combined) != int(config["design"]["expected_combined_examples"]):
        raise ValueError("combined measurement count mismatch")
    ids = [str(row["example_id"]) for row in combined]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate measurement example IDs")
    combined_path = Path(output["combined_manifest"])
    if combined_path.exists():
        raise FileExistsError(f"refusing to overwrite {combined_path}")
    write_jsonl(combined_path, combined)
    for reviewer_id, review_path_raw in output["review_sheets"].items():
        review_path = Path(review_path_raw)
        review_path.parent.mkdir(parents=True, exist_ok=True)
        if review_path.exists():
            raise FileExistsError(f"refusing to overwrite {review_path}")
        with review_path.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(
                review_rows(
                    combined,
                    reviewer_id=reviewer_id,
                    seed=int(config["review_shuffle_seeds"][reviewer_id]),
                )
            )
    summary = {
        "protocol": "persona_measurement_development_dataset_v1",
        "anchors": len(anchors),
        "qwen_probes": len(qwen),
        "combined_examples": len(combined),
        "anchor_manifest": str(anchor_path),
        "anchor_manifest_sha256": sha256(anchor_path),
        "qwen_probe_manifest": str(qwen_path),
        "qwen_probe_manifest_sha256": sha256(qwen_path),
        "combined_manifest": str(combined_path),
        "combined_manifest_sha256": sha256(combined_path),
        "config": str(args.config),
        "config_sha256": sha256(args.config),
    }
    summary_path = Path(output["dataset_summary"])
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
