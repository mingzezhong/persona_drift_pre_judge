#!/usr/bin/env python3
"""Select a prompt-salience variant using the frozen engineering smoke gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from scripts.analyze_repetition_control_smoke import THRESHOLDS, summarize_candidate


VARIANT_ORDER = ["minimal", "strict3"]


def select_variant(candidates: list[dict[str, Any]]) -> str | None:
    return next(
        (str(row["prompt_salience_variant"]) for row in candidates if row["candidate_pass"]),
        None,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", nargs=2, type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")

    candidates: list[dict[str, Any]] = []
    for config_path in args.configs:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        row = summarize_candidate(config_path)
        row["prompt_salience_variant"] = config["prompt_salience"]["variant"]
        row["prompt_template"] = config["data"]["template"]
        row["prompt_template_sha256"] = config["prompt_salience"]["template_sha256"]
        candidates.append(row)
    variants = [str(row["prompt_salience_variant"]) for row in candidates]
    if variants != VARIANT_ORDER:
        raise ValueError(f"expected frozen variant order {VARIANT_ORDER}, got {variants}")
    selected = select_variant(candidates)
    result = {
        "protocol": "olmo_prompt_salience_smoke_v1",
        "selection_rule": "minimum_prompt_change_passing_all_existing_smoke_checks",
        "thresholds": THRESHOLDS,
        "selected_prompt_salience_variant": selected,
        "full_prompt_salience_pilot_authorized": selected is not None,
        "formal_replication_authorized": False,
        "persona_outcomes_evaluated": False,
        "manual_response_text_inspected": False,
        "candidates": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_suffix(args.output.suffix + ".partial")
    partial.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    partial.replace(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    if selected is None:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
