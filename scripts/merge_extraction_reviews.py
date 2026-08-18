#!/usr/bin/env python3
"""Merge two frozen AI-judge runs into a strict-consensus manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from persona_drift.judging import (
    load_jsonl,
    merge_independent_reviews,
    sha256_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("configs/ai_judges.yaml")
    )
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def write_jsonl(path: Path, records: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    if temporary.exists():
        raise FileExistsError(f"partial output exists: {temporary}")
    with temporary.open("x", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary.replace(path)


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    judges = list(config["judges"].values())
    if len(judges) != 2:
        raise ValueError("strict consensus currently requires exactly two judges")

    manifest_path = Path(config["input"]["manifest"])
    reviewed_path = Path(config["consensus"]["reviewed_manifest"])
    summary_path = Path(config["consensus"]["summary"])
    if reviewed_path.exists() or summary_path.exists():
        if args.resume and reviewed_path.exists() and summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            print(json.dumps(summary, indent=2))
            return
        raise FileExistsError("refusing to overwrite consensus outputs")

    review_records = [load_jsonl(Path(judge["output"])) for judge in judges]
    reviewed, summary = merge_independent_reviews(
        load_jsonl(manifest_path), review_records[0], review_records[1]
    )
    summary.update(
        {
            "manifest": str(manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
            "judge_outputs": [str(judge["output"]) for judge in judges],
            "judge_output_sha256": [
                sha256_file(Path(judge["output"])) for judge in judges
            ],
            "consensus_rule": config["consensus"]["rule"],
            "disagreement_action": config["consensus"]["disagreement_action"],
        }
    )
    reviewed_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(reviewed_path, reviewed)
    temporary_summary = summary_path.with_suffix(summary_path.suffix + ".partial")
    temporary_summary.write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    temporary_summary.replace(summary_path)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
