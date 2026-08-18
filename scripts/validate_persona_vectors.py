#!/usr/bin/env python3
"""Validate persona-vector tensor structure, finiteness, and nonzero norms."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import torch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--expected-layers", type=int, default=28)
    parser.add_argument("--expected-hidden", type=int, default=3584)
    parser.add_argument("--reference-layer", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError as exc:
        if "weights_only" not in str(exc):
            raise
        payload = torch.load(path, map_location="cpu")
    if not isinstance(payload, dict):
        raise ValueError("persona-vector payload must be a dictionary")
    return payload


def validate_vectors(
    payload: dict[str, Any],
    *,
    expected_shape: tuple[int, int],
    reference_layer: int,
) -> dict[str, Any]:
    vectors = payload.get("vectors")
    if not isinstance(vectors, dict) or not vectors:
        raise ValueError("payload must contain a non-empty vectors dictionary")
    if not 0 <= reference_layer < expected_shape[0]:
        raise ValueError("reference layer is outside the expected layer range")

    axes: dict[str, Any] = {}
    for axis, tensor in sorted(vectors.items()):
        if not isinstance(axis, str) or not axis:
            raise ValueError("vector axis names must be non-empty strings")
        if not isinstance(tensor, torch.Tensor):
            raise ValueError(f"vector {axis!r} is not a tensor")
        if tuple(tensor.shape) != expected_shape:
            raise ValueError(
                f"vector {axis!r} has shape {tuple(tensor.shape)}, "
                f"expected {expected_shape}"
            )
        if not bool(torch.isfinite(tensor).all()):
            raise ValueError(f"vector {axis!r} contains non-finite values")
        layer_norms = torch.linalg.vector_norm(tensor.float(), dim=1)
        if not bool((layer_norms > 0).all()):
            raise ValueError(f"vector {axis!r} has a zero-norm layer")
        axes[axis] = {
            "shape": list(tensor.shape),
            "dtype": str(tensor.dtype),
            "layer_norm_min": float(layer_norms.min()),
            "layer_norm_max": float(layer_norms.max()),
            "reference_layer": reference_layer,
            "reference_layer_norm": float(layer_norms[reference_layer]),
        }
    return {"axes": axes, "metadata": payload.get("metadata")}


def main() -> None:
    args = parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    summary = validate_vectors(
        load_payload(args.vectors),
        expected_shape=(args.expected_layers, args.expected_hidden),
        reference_layer=args.reference_layer,
    )
    summary.update(
        {
            "vectors": str(args.vectors),
            "vectors_sha256": hashlib.sha256(args.vectors.read_bytes()).hexdigest(),
            "vectors_bytes": args.vectors.stat().st_size,
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
