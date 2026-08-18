#!/usr/bin/env python3
"""Create a blinded, deterministically shuffled extraction review sheet."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import random
from typing import Any

import yaml

from persona_drift.extraction import load_manifest


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("data/templates/persona_axes.yaml"),
    )
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--shuffle-seed", type=int, default=20260809)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def build_review_rows(
    records: list[dict[str, Any]],
    axes: dict[str, dict[str, Any]],
    *,
    reviewer_id: str,
    shuffle_seed: int,
) -> list[dict[str, Any]]:
    """Remove system instructions and add empty frozen-rubric score columns."""

    if not reviewer_id.strip():
        raise ValueError("reviewer_id must be non-empty")
    rows: list[dict[str, Any]] = []
    for record in records:
        axis_name = str(record["axis"])
        if axis_name not in axes:
            raise ValueError(f"unknown axis in manifest: {axis_name}")
        polarity = str(record["polarity"])
        trait_field = "target_trait" if polarity == "target" else "contrast_trait"
        rows.append(
            {
                "review_order": 0,
                "reviewer_id": reviewer_id,
                "example_id": record["example_id"],
                "prompt_id": record["prompt_id"],
                "axis": axis_name,
                "expected_trait": axes[axis_name][trait_field],
                "seed": record["seed"],
                "user": record["user"],
                "response": record["response"],
                "trait_alignment": "",
                "task_relevance": "",
                "response_integrity": "",
                "prompt_leakage": "",
                "notes": "",
            }
        )
    random.Random(shuffle_seed).shuffle(rows)
    for index, row in enumerate(rows, start=1):
        row["review_order"] = index
    return rows


def main() -> None:
    args = parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    template = yaml.safe_load(args.template.read_text(encoding="utf-8"))
    rows = build_review_rows(
        load_manifest(args.manifest),
        template["axes"],
        reviewer_id=args.reviewer_id,
        shuffle_seed=args.shuffle_seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} blinded review rows to {args.output}")


if __name__ == "__main__":
    main()
