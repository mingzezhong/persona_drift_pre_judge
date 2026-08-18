#!/usr/bin/env python3
"""Summarize complete accepted pairs and evaluate the frozen quality gate."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any

import yaml

from persona_drift.judging import load_jsonl, sha256_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def summarize_pair_quality(
    records: list[dict[str, Any]],
    *,
    min_pair_rate: float,
    max_disagreement_rate: float,
) -> dict[str, Any]:
    pairs: dict[tuple[str, str, int], dict[str, dict[str, Any]]] = {}
    disagreements = 0
    for record in records:
        key = (
            str(record["prompt_id"]),
            str(record["axis"]),
            int(record["seed"]),
        )
        polarity = str(record["polarity"])
        if polarity not in {"target", "contrast"}:
            raise ValueError(f"invalid polarity for pair {key}: {polarity}")
        pair = pairs.setdefault(key, {})
        if polarity in pair:
            raise ValueError(f"duplicate polarity {polarity!r} for pair {key}")
        pair[polarity] = record
        disagreements += int(
            bool(record.get("judge_score", {}).get("decision_disagreement", False))
        )

    totals: dict[str, int] = defaultdict(int)
    complete: dict[str, int] = defaultdict(int)
    for key, pair in pairs.items():
        if set(pair) != {"target", "contrast"}:
            raise ValueError(f"incomplete raw pair {key}: {sorted(pair)}")
        axis = key[1]
        totals[axis] += 1
        complete[axis] += int(
            pair["target"].get("accepted") is True
            and pair["contrast"].get("accepted") is True
        )

    axes = {
        axis: {
            "raw_pairs": totals[axis],
            "complete_accepted_pairs": complete[axis],
            "complete_pair_rate": complete[axis] / totals[axis],
            "passes": complete[axis] / totals[axis] >= min_pair_rate,
        }
        for axis in sorted(totals)
    }
    disagreement_rate = disagreements / len(records)
    return {
        "examples": len(records),
        "raw_pairs": len(pairs),
        "axes": axes,
        "judge_decision_disagreements": disagreements,
        "judge_decision_disagreement_rate": disagreement_rate,
        "thresholds": {
            "min_complete_pair_rate_per_axis": min_pair_rate,
            "max_judge_decision_disagreement_rate": max_disagreement_rate,
        },
        "gate_pass": all(item["passes"] for item in axes.values())
        and disagreement_rate <= max_disagreement_rate,
    }


def main() -> None:
    args = parse_args()
    if args.output.exists():
        if args.resume:
            print(args.output.read_text(encoding="utf-8"), end="")
            return
        raise FileExistsError(f"refusing to overwrite {args.output}")
    rubric = yaml.safe_load(args.rubric.read_text(encoding="utf-8"))
    gate = rubric["paired_quality_gate"]
    summary = summarize_pair_quality(
        load_jsonl(args.manifest),
        min_pair_rate=float(gate["min_complete_pair_rate_per_axis"]),
        max_disagreement_rate=float(
            gate["max_judge_decision_disagreement_rate"]
        ),
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
    temporary = args.output.with_suffix(args.output.suffix + ".partial")
    temporary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
