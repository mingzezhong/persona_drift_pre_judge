#!/usr/bin/env python3
"""Validate the restart-v2.3 G1 artifact inventory without generating data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from persona_drift.g1_manifest import (  # noqa: E402
    DEFAULT_G1_CONFIG,
    ReadinessStatus,
    evaluate_g1_readiness,
)


EXIT_CODES = {
    ReadinessStatus.READY: 0,
    ReadinessStatus.PREPARATION: 2,
    ReadinessStatus.NOT_READY: 3,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify frozen G1 manifests and report READY only when every "
            "declared artifact passes fail-closed validation."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=REPOSITORY_ROOT / DEFAULT_G1_CONFIG,
        help=(
            "G1 inventory YAML/JSON path (default: configs/g1_v2_3.yaml). "
            "An absent file reports PREPARATION and exits 2."
        ),
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="emit one-line JSON instead of indented JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = evaluate_g1_readiness(args.config)
    payload = report.to_dict()
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=None if args.compact else 2,
        )
    )
    return EXIT_CODES[report.status]


if __name__ == "__main__":
    raise SystemExit(main())
