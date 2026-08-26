#!/usr/bin/env python3
"""Build the frozen, outcome-blind G1 Persona semantic-review packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from persona_drift.g1_persona_review import (
    PersonaReviewPacketError,
    build_persona_review_assets,
    verify_tracked_persona_review_assets,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sample and anonymize Persona semantic-review items. This command "
            "does not assign raters, produce ratings, select traits, or run a target model."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: inferred from this script)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="optional alternate output root for deterministic verification",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify tracked Persona artifacts without writing files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.verify_only:
            summary = verify_tracked_persona_review_assets(args.project_root)
        else:
            summary = build_persona_review_assets(
                project_root=args.project_root,
                output_root=args.output_root,
            )
    except (PersonaReviewPacketError, OSError, ValueError, KeyError) as exc:
        print(f"G1 Persona review-packet build failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
