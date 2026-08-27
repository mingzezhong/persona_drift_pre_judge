#!/usr/bin/env python3
"""Build deterministic G1 Persona scalar queues or the later pair packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from persona_drift.g1_persona_stages import (  # noqa: E402
    PAIR_PACKET_PATH,
    PRIMARY_PACKET_PATHS,
    PRIMARY_SLOTS,
    SOURCE_PACKET_PATH,
    STAGE_MANIFEST_PATH,
    PersonaStagePacketError,
    build_pair_stage_packet_from_ledgers,
    build_scalar_stage_packets,
    write_bytes_exact,
)


def _rooted(root: Path, value: Path) -> Path:
    return value if value.is_absolute() else root / value


def _add_common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="repository root; relative artifact paths are resolved below it",
    )
    parser.add_argument(
        "--source-packet", type=Path, default=SOURCE_PACKET_PATH
    )
    for slot in PRIMARY_SLOTS:
        parser.add_argument(
            f"--{slot.replace('_', '-')}-packet",
            dest=f"{slot}_packet",
            type=Path,
            default=PRIMARY_PACKET_PATHS[slot],
        )
    parser.add_argument(
        "--manifest-output", type=Path, default=STAGE_MANIFEST_PATH
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Transform the frozen 2,304-row Persona packet without running models."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    scalar = commands.add_parser(
        "scalar",
        help="write three 27-row primary queues with three blind repeats each",
    )
    _add_common_paths(scalar)

    pair = commands.add_parser(
        "pair",
        help="consume three complete accepted scalar ledgers and write all 276 pairs",
    )
    _add_common_paths(pair)
    for slot in PRIMARY_SLOTS:
        pair.add_argument(
            f"--{slot.replace('_', '-')}-ledger",
            dest=f"{slot}_ledger",
            type=Path,
            required=True,
        )
    pair.add_argument("--pair-output", type=Path, default=PAIR_PACKET_PATH)
    return parser


def _scalar_paths(args: argparse.Namespace) -> dict[str, Path]:
    root = args.project_root.resolve()
    return {
        slot: _rooted(root, getattr(args, f"{slot}_packet"))
        for slot in PRIMARY_SLOTS
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.project_root.resolve()
    source_path = _rooted(root, args.source_packet)
    packet_paths = _scalar_paths(args)
    manifest_path = _rooted(root, args.manifest_output)
    try:
        source_bytes = source_path.read_bytes()
        path_labels = {
            slot: getattr(args, f"{slot}_packet") for slot in PRIMARY_SLOTS
        }
        if args.command == "scalar":
            stage = build_scalar_stage_packets(
                source_bytes,
                source_path=args.source_packet,
                packet_paths=path_labels,
            )
            for slot in PRIMARY_SLOTS:
                write_bytes_exact(packet_paths[slot], stage.packet_bytes[slot])
            write_bytes_exact(manifest_path, stage.manifest_bytes)
            summary = {
                "blind_repeats_per_primary": 3,
                "command": "scalar",
                "models_run": False,
                "packet_sha256s": {
                    slot: stage.manifest["scalar_inputs"]["primary_packets"][slot][
                        "byte_sha256"
                    ]
                    for slot in PRIMARY_SLOTS
                },
                "rows_per_primary": 27,
                "source_packet_sha256": stage.source_sha256,
            }
        else:
            pair_output = _rooted(root, args.pair_output)
            ledger_paths = {
                slot: _rooted(root, getattr(args, f"{slot}_ledger"))
                for slot in PRIMARY_SLOTS
            }
            pair_stage = build_pair_stage_packet_from_ledgers(
                source_bytes,
                source_path=args.source_packet,
                scalar_packet_bytes_by_slot={
                    slot: packet_paths[slot].read_bytes() for slot in PRIMARY_SLOTS
                },
                scalar_packet_paths=path_labels,
                scalar_ledger_bytes_by_slot={
                    slot: ledger_paths[slot].read_bytes() for slot in PRIMARY_SLOTS
                },
                scalar_ledger_paths={
                    slot: getattr(args, f"{slot}_ledger") for slot in PRIMARY_SLOTS
                },
                pair_packet_path=args.pair_output,
            )
            write_bytes_exact(pair_output, pair_stage.packet_bytes)
            write_bytes_exact(manifest_path, pair_stage.manifest_bytes)
            summary = {
                "command": "pair",
                "definition_evidence_per_candidate": 3,
                "models_run": False,
                "pair_packet_sha256": pair_stage.manifest["pair_packet"][
                    "byte_sha256"
                ],
                "pair_rows": len(pair_stage.rows),
            }
    except (OSError, KeyError, PersonaStagePacketError, ValueError) as exc:
        print(f"G1 Persona stage build failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
