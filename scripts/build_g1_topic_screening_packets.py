#!/usr/bin/env python3
"""Build complete PREPARATION-stage G1 Topic screening packets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from persona_drift.g1_topic_screening import (  # noqa: E402
    build_topic_screening_packets,
    verify_tracked_topic_screening_packets,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize all 12,032 MMLU-Pro triage inputs and all 158 "
            "Anthropic logical-anchor full-screen inputs without running raters."
        )
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="project root (default: inferred from this script)",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="build and validate in memory without replacing tracked packets",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify tracked packet byte hashes and counts without rebuilding",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.no_write and args.verify_only:
        raise SystemExit("--no-write and --verify-only are mutually exclusive")
    if args.verify_only:
        manifest = verify_tracked_topic_screening_packets(args.repository_root)
    else:
        manifest = build_topic_screening_packets(
            args.repository_root,
            write_outputs=not args.no_write,
        )
    artifacts = {Path(item["path"]).name: item for item in manifest["artifacts"]}
    summary = {
        "implementation_status": manifest["implementation_status"],
        "g1_ready": manifest["g1_ready"],
        "ratings_collected": manifest["ratings_collected"],
        "mmlu_rater_rows": artifacts[
            "topic_mmlu_triage_input_v2_3.jsonl"
        ]["row_count"],
        "anthropic_rater_rows": artifacts[
            "topic_anthropic_full_screen_input_v2_3.jsonl"
        ]["row_count"],
        "final_36_selected": manifest["final_36_topic_selection_performed"],
        "outputs_written": not args.no_write and not args.verify_only,
        "verified_only": args.verify_only,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
