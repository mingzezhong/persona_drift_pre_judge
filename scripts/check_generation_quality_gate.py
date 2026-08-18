#!/usr/bin/env python3
"""Evaluate frozen generation-integrity thresholds for an extraction run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from persona_drift.extraction import load_manifest, summarize_generation_qc
from persona_drift.judging import sha256_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fail-on-gate", action="store_true")
    return parser.parse_args()


def evaluate_generation_gate(
    quality: dict[str, Any], thresholds: dict[str, Any]
) -> dict[str, Any]:
    if quality.get("available") is not True:
        raise ValueError("generation QC fields are unavailable")
    max_role = float(thresholds["max_role_start_rate"])
    max_length = float(thresholds["max_length_rate"])
    role_pass = float(quality["role_start_rate"]) <= max_role
    length_pass = float(quality["max_length_rate"]) <= max_length
    return {
        "generation_qc": quality,
        "thresholds": {
            "max_role_start_rate": max_role,
            "max_length_rate": max_length,
        },
        "checks": {
            "role_start_rate_pass": role_pass,
            "max_length_rate_pass": length_pass,
        },
        "gate_pass": role_pass and length_pass,
    }


def main() -> None:
    args = parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    rubric = yaml.safe_load(args.rubric.read_text(encoding="utf-8"))
    summary = evaluate_generation_gate(
        summarize_generation_qc(load_manifest(args.manifest)),
        rubric["generation_quality_gate"],
    )
    summary.update(
        {
            "manifest": str(args.manifest),
            "manifest_sha256": sha256_file(args.manifest),
            "rubric": str(args.rubric),
            "rubric_sha256": sha256_file(args.rubric),
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if args.fail_on_gate and not summary["gate_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
