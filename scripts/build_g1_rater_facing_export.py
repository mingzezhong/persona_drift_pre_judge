#!/usr/bin/env python3
"""Build the frozen data-only G1 reviewer export without running a model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from persona_drift.g1_rater_export import (  # noqa: E402
    RaterExportError,
    build_rater_facing_export,
    canonical_sha256,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest, attestation = build_rater_facing_export(
            args.project_root, args.output_directory
        )
    except RaterExportError as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "all_required_reviews_complete": False,
                "attestation_sha256": canonical_sha256(attestation),
                "file_count": len(manifest["files"]),
                "g1_pass": False,
                "manifest_sha256": canonical_sha256(manifest),
                "models_run": False,
                "ratings_generated": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
