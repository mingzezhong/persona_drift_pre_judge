#!/usr/bin/env python3
"""Validate an extraction run and persist a machine-readable summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from persona_drift.extraction import validate_extraction_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-layers", type=int, default=28)
    parser.add_argument("--expected-hidden-size", type=int, default=3584)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output or args.manifest.parent / "validation.json"
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"refusing to overwrite {output}")
    summary = validate_extraction_run(
        args.manifest,
        expected_shape=(args.expected_layers, args.expected_hidden_size),
    ).to_dict()
    rendered = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
