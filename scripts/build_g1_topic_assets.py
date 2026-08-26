#!/usr/bin/env python3
"""Download, audit, and materialize PREPARATION-stage G1 Topic assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from persona_drift.g1_topics import build_g1_topic_assets  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Lock official MMLU-Pro and Anthropic source bytes, audit their "
            "native schemas, and generate outcome-blind PREPARATION manifests."
        )
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="project root (default: inferred from this script)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="fail if any locked raw file is absent instead of downloading it",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="audit sources without replacing tracked manifests/reports",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_g1_topic_assets(
        args.repository_root,
        download_missing=not args.offline,
        write_outputs=not args.no_write,
    )
    pools = {
        item["source"]: item
        for item in result["candidate_pool_manifest"]["candidate_pools"]
    }
    report = result["audit_report"]
    summary = {
        "implementation_status": report["implementation_status"],
        "g1_ready": report["g1_ready"],
        "mmlu_test_candidates": pools["mmlu_pro"]["structurally_eligible_count"],
        "anthropic_raw_rows": pools["anthropic_sycophancy"]["raw_row_count"],
        "anthropic_logical_candidates_draft": pools["anthropic_sycophancy"][
            "logical_candidate_count"
        ],
        "anthropic_parse_failures": pools["anthropic_sycophancy"][
            "parse_failure_count"
        ],
        "final_topics_selected": False,
        "scenario_content_generated": False,
        "outputs_written": not args.no_write,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
