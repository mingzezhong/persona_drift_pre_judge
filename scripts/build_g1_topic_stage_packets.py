#!/usr/bin/env python3
"""Join completed primary Topic triage ledgers into anonymous next-stage inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from persona_drift.g1_topic_stages import (  # noqa: E402
    ANTHROPIC_PACKET,
    EXPECTED_ANTHROPIC_COUNT,
    EXPECTED_MMLU_COUNT,
    INITIAL_WRITER_PACKET,
    MMLU_PACKET,
    PRIMARY_01_RESULTS,
    PRIMARY_02_RESULTS,
    REMAINING_DOUBLE_REJECT_PACKET,
    SCREENING_MANIFEST,
    TRIAGE_JOIN_MANIFEST,
    build_topic_stage_packets,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Strictly join two complete primary Topic-triage ledgers, freeze the "
            "10% double-reject audit, and write anonymous stage packets."
        )
    )
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--primary-01-results", type=Path, default=PRIMARY_01_RESULTS)
    parser.add_argument("--primary-02-results", type=Path, default=PRIMARY_02_RESULTS)
    parser.add_argument("--mmlu-packet", type=Path, default=MMLU_PACKET)
    parser.add_argument("--anthropic-packet", type=Path, default=ANTHROPIC_PACKET)
    parser.add_argument("--screening-manifest", type=Path, default=SCREENING_MANIFEST)
    parser.add_argument("--initial-writer-output", type=Path, default=INITIAL_WRITER_PACKET)
    parser.add_argument(
        "--remaining-double-reject-output",
        type=Path,
        default=REMAINING_DOUBLE_REJECT_PACKET,
    )
    parser.add_argument("--join-manifest-output", type=Path, default=TRIAGE_JOIN_MANIFEST)
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="validate and build in memory without replacing outputs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = build_topic_stage_packets(
        args.repository_root,
        primary_01_results_path=args.primary_01_results,
        primary_02_results_path=args.primary_02_results,
        mmlu_packet_path=args.mmlu_packet,
        anthropic_packet_path=args.anthropic_packet,
        screening_manifest_path=args.screening_manifest,
        initial_writer_output_path=args.initial_writer_output,
        remaining_double_reject_output_path=args.remaining_double_reject_output,
        join_manifest_output_path=args.join_manifest_output,
        expected_mmlu_count=EXPECTED_MMLU_COUNT,
        expected_anthropic_count=EXPECTED_ANTHROPIC_COUNT,
        write_outputs=not args.no_write,
    )
    sets = manifest["triage_sets"]
    artifacts = {item["role"]: item for item in manifest["output_artifacts"]}
    print(
        json.dumps(
            {
                "status": manifest["implementation_status"],
                "U_nonreject_count": sets["U"]["count"],
                "D_double_reject_count": sets["D"]["count"],
                "audited_double_reject_count": sets["A"]["count"],
                "initial_writer_rows": artifacts[
                    "INITIAL_SCENARIO_WRITER_INPUT"
                ]["row_count"],
                "remaining_double_reject_rows": artifacts[
                    "CONTINGENT_PRIMARY_03_TRIAGE_INPUT"
                ]["row_count"],
                "outputs_written": not args.no_write,
                "model_executed": False,
                "scenario_cards_generated": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
