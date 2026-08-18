#!/usr/bin/env python3
"""Build layerwise persona vectors from complete reviewed contrastive pairs."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

import torch

from persona_drift.activation import mean_difference


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-unjudged",
        action="store_true",
        help="Include complete raw pairs without requiring accepted=true.",
    )
    return parser.parse_args()


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"expected JSON object at {path}:{line_number}")
            records.append(record)
    if not records:
        raise ValueError(f"manifest is empty: {path}")
    return records


def select_complete_pairs(
    records: list[dict[str, Any]], *, allow_unjudged: bool = False
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep both polarities only when the complete pair is eligible."""

    pairs: dict[tuple[str, str, int], dict[str, dict[str, Any]]] = {}
    for record in records:
        try:
            key = (
                str(record["prompt_id"]),
                str(record["axis"]),
                int(record["seed"]),
            )
            polarity = str(record["polarity"])
        except KeyError as exc:
            raise ValueError(f"record is missing pair field: {exc.args[0]}") from exc
        if polarity not in {"target", "contrast"}:
            raise ValueError(f"invalid polarity for pair {key}: {polarity}")
        pair = pairs.setdefault(key, {})
        if polarity in pair:
            raise ValueError(f"duplicate polarity {polarity!r} for pair {key}")
        pair[polarity] = record

    selected: list[dict[str, Any]] = []
    included_by_axis: dict[str, int] = defaultdict(int)
    excluded_by_axis: dict[str, int] = defaultdict(int)
    for key, pair in pairs.items():
        if set(pair) != {"target", "contrast"}:
            raise ValueError(f"incomplete raw contrastive pair {key}: {sorted(pair)}")
        eligible = allow_unjudged or all(
            pair[polarity].get("accepted") is True
            for polarity in ("target", "contrast")
        )
        axis = key[1]
        if eligible:
            selected.extend((pair["target"], pair["contrast"]))
            included_by_axis[axis] += 1
        else:
            excluded_by_axis[axis] += 1

    stats = {
        "raw_examples": len(records),
        "raw_pairs": len(pairs),
        "included_examples": len(selected),
        "included_pairs": len(selected) // 2,
        "excluded_pairs": len(pairs) - len(selected) // 2,
        "included_pairs_by_axis": dict(sorted(included_by_axis.items())),
        "excluded_pairs_by_axis": dict(sorted(excluded_by_axis.items())),
        "eligibility": (
            "complete_raw_pairs" if allow_unjudged else "complete_accepted_pairs"
        ),
    }
    return selected, stats


def load_activation(path: Path) -> torch.Tensor:
    try:
        payload = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError as exc:
        if "weights_only" not in str(exc):
            raise
        payload = torch.load(path, map_location="cpu")
    tensor = payload["response_token_mean"]
    if not isinstance(tensor, torch.Tensor) or tensor.ndim != 2:
        raise ValueError(f"expected [layers, hidden] response activation in {path}")
    return tensor.float()


def main() -> None:
    args = parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    records = load_records(args.manifest)
    selected, pair_stats = select_complete_pairs(
        records, allow_unjudged=args.allow_unjudged
    )
    grouped: dict[tuple[str, str], list[torch.Tensor]] = defaultdict(list)
    metadata: dict[str, Any] = {
        "source_manifest": str(args.manifest),
        "source_manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "pair_selection": pair_stats,
        "axes": {},
    }

    for record in selected:
        activation_path = Path(record["activation_path"])
        grouped[(record["axis"], record["polarity"])].append(
            load_activation(activation_path)
        )

    vectors: dict[str, torch.Tensor] = {}
    axes = sorted({str(record["axis"]) for record in records})
    for axis in axes:
        target = grouped.get((axis, "target"), [])
        contrast = grouped.get((axis, "contrast"), [])
        if not target or not contrast:
            raise ValueError(f"axis {axis!r} lacks a complete eligible pair")
        if len(target) != len(contrast):
            raise RuntimeError(f"internal pairing error for axis {axis!r}")
        target_tensor = torch.stack(target)
        contrast_tensor = torch.stack(contrast)
        vectors[axis] = mean_difference(target_tensor, contrast_tensor)
        metadata["axes"][axis] = {
            "complete_pairs": len(target),
            "target_examples": len(target),
            "contrast_examples": len(contrast),
            "shape": list(vectors[axis].shape),
        }

    if not vectors:
        raise ValueError("no eligible complete extraction pairs found")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"vectors": vectors, "metadata": metadata}, args.output)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
