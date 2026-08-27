#!/usr/bin/env python3
"""Promote the G1 reviewer registry only after five complete smoke ledgers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from persona_drift.g1_reviewer_promotion import (  # noqa: E402
    PRODUCTION_REGISTRY_PATH,
    PROMPT_CATALOG_PATH,
    SLOT_IDS,
    SMOKE_LEDGER_DIRECTORY,
    SMOKE_REGISTRY_PATH,
    SMOKE_REPORT_PATH,
    SYNTHETIC_PACKET_PATH,
    ReviewerPromotionError,
    promote_g1_reviewer_registry,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate five append-only synthetic-smoke ledgers and write a new "
            "production-frozen reviewer registry. Missing evidence fails closed."
        )
    )
    parser.add_argument("--project-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--registry", type=Path, default=SMOKE_REGISTRY_PATH)
    parser.add_argument(
        "--synthetic-packet", type=Path, default=SYNTHETIC_PACKET_PATH
    )
    parser.add_argument("--prompts", type=Path, default=PROMPT_CATALOG_PATH)
    parser.add_argument(
        "--ledger-directory", type=Path, default=SMOKE_LEDGER_DIRECTORY
    )
    for slot in SLOT_IDS:
        parser.add_argument(
            f"--{slot.replace('_', '-')}-ledger",
            dest=f"{slot}_ledger",
            type=Path,
            help=(
                f"{slot} smoke ledger; defaults to "
                f"--ledger-directory/{slot}.jsonl"
            ),
        )
    parser.add_argument("--report-output", type=Path, default=SMOKE_REPORT_PATH)
    parser.add_argument(
        "--production-registry-output",
        type=Path,
        default=PRODUCTION_REGISTRY_PATH,
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="validate and serialize in memory without writing either artifact",
    )
    return parser


def _rooted(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.project_root.resolve()
    ledger_directory = _rooted(root, args.ledger_directory)
    ledger_paths = {
        slot: _rooted(root, getattr(args, f"{slot}_ledger"))
        if getattr(args, f"{slot}_ledger") is not None
        else ledger_directory / f"{slot}.jsonl"
        for slot in SLOT_IDS
    }
    report_output = _rooted(root, args.report_output)
    production_output = _rooted(root, args.production_registry_output)
    try:
        artifacts = promote_g1_reviewer_registry(
            registry_path=_rooted(root, args.registry),
            ledger_paths_by_slot=ledger_paths,
            synthetic_packet_path=_rooted(root, args.synthetic_packet),
            prompt_catalog_path=_rooted(root, args.prompts),
            report_output_path=report_output,
            production_registry_output_path=production_output,
            write_outputs=not args.no_write,
        )
    except (OSError, ReviewerPromotionError, ValueError) as exc:
        print(f"G1 reviewer promotion failed closed: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "status": artifacts.report["status"],
                "validated_slot_count": artifacts.report["validation"][
                    "validated_slot_count"
                ],
                "production_review_authorized": artifacts.production_registry[
                    "production_review_authorized"
                ],
                "report_output": str(report_output),
                "production_registry_output": str(production_output),
                "outputs_written": not args.no_write,
                "models_run": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
