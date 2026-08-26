#!/usr/bin/env python3
"""Verify the pinned Anthropic Persona source and build G1-only assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from persona_drift.g1_personas import (
    G1PersonaAssetError,
    build_g1_persona_assets,
    ensure_source_checkout,
    sha256_bytes,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic, outcome-blind G1 Persona source/candidate assets. "
            "This command never loads or runs a target language model."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: inferred from this script)",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        help=(
            "already-extracted anthropics/evals root; when omitted, use/download "
            "the pinned archive under data/raw"
        ),
    )
    parser.add_argument(
        "--archive",
        type=Path,
        help="archive whose SHA256 should be recorded with --source-root",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="fail if the pinned archive is not already present under data/raw",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    try:
        if args.source_root is None:
            if args.archive is not None:
                raise G1PersonaAssetError(
                    "--archive is only valid together with --source-root"
                )
            source_root, archive_sha256 = ensure_source_checkout(
                project_root=project_root,
                allow_download=not args.no_download,
            )
        else:
            if args.archive is None or not args.archive.is_file():
                raise G1PersonaAssetError(
                    "--source-root requires an existing --archive for provenance"
                )
            source_root = args.source_root.resolve()
            archive_sha256 = sha256_bytes(args.archive.read_bytes())
        summary = build_g1_persona_assets(
            project_root=project_root,
            source_root=source_root,
            archive_sha256=archive_sha256,
        )
    except (G1PersonaAssetError, OSError, ValueError) as exc:
        print(f"G1 Persona asset build failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
