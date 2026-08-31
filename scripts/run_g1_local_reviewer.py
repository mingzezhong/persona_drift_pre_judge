#!/usr/bin/env python3
"""Run one frozen G1 reviewer slot against synthetic or authorized packets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from persona_drift.g1_local_reviewer import (
    ReviewRunnerError,
    prepare_review,
    review_plan,
    run_review,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = (
    PROJECT_ROOT / "configs/g1_reviewer_registry_amendment_3_v2_3.yaml"
)
DEFAULT_PROMPTS = (
    PROJECT_ROOT / "data/rater_specs/g1_local_reviewer_prompts_v2_3.yaml"
)
DEFAULT_SMOKE_PACKET = (
    PROJECT_ROOT / "data/synthetic/g1_reviewer_smoke_v2_3.jsonl"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Offline-only G1 local reviewer. Dry-run validates and plans without "
            "loading torch, transformers, a tokenizer, or a model."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--smoke",
        action="store_true",
        help="use SYN-* inputs under the synthetic-smoke authorization",
    )
    mode.add_argument(
        "--production",
        action="store_true",
        help=(
            "request production review; fails closed until the registry is "
            "frozen_for_production and production_review_authorized=true"
        ),
    )
    parser.add_argument(
        "--slot",
        required=True,
        help="frozen reviewer slot ID, for example primary_01",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="frozen reviewer registry",
    )
    parser.add_argument(
        "--prompts",
        type=Path,
        default=DEFAULT_PROMPTS,
        help="strict prompt and response-schema catalog",
    )
    parser.add_argument(
        "--packet",
        type=Path,
        help="JSONL packet; defaults to the tracked synthetic packet in smoke mode",
    )
    parser.add_argument(
        "--task",
        action="append",
        default=[],
        help=(
            "task ID to retain; repeat to select multiple smoke tasks. "
            "Production packets require exactly one task."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="frozen run metadata; generation is item-at-a-time in this minimal runner",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "append-only JSONL ledger. A per-slot path under outputs/ is used "
            "for smoke; production requires an explicit path."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate hashes/contracts and print assignments without model loading",
    )
    return parser.parse_args(argv)


def _resolve_mode_paths(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> tuple[Path, Path, str | None]:
    if args.smoke:
        packet = args.packet or DEFAULT_SMOKE_PACKET
        output = args.output or (
            PROJECT_ROOT
            / "outputs/g1_local_reviewer"
            / f"synthetic_smoke_{args.slot}.jsonl"
        )
        production_task = None
    else:
        if args.packet is None:
            parser.error("--production requires --packet")
        if args.output is None and not args.dry_run:
            parser.error("--production requires --output")
        if len(args.task) != 1:
            parser.error("--production requires exactly one --task")
        packet = args.packet
        output = args.output or (
            PROJECT_ROOT
            / "outputs/g1_local_reviewer"
            / f"production_dry_run_{args.slot}.jsonl"
        )
        production_task = args.task[0]
    return packet, output, production_task


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    # Parse with the public parser, while retaining a normal parser.error path.
    args = parse_args(argv)
    error_parser = argparse.ArgumentParser(prog=Path(sys.argv[0]).name)
    packet, output, production_task = _resolve_mode_paths(args, error_parser)

    # These locks are harmless during dry-run and make the intended boundary
    # visible to child imports if a real run follows.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    try:
        prepared = prepare_review(
            registry_path=args.registry,
            reviewer_slot_id=args.slot,
            prompts_path=args.prompts,
            packet_path=packet,
            production=bool(args.production),
            production_task=production_task,
            batch_size=args.batch_size,
            selected_tasks=tuple(args.task) if args.smoke else (),
        )
        if args.dry_run:
            result = review_plan(prepared)
            result["output_path_if_executed"] = str(output.resolve())
        else:
            result = run_review(prepared, output_path=output).to_dict()
    except ReviewRunnerError as exc:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result.get("rejected_invalid_output", 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
