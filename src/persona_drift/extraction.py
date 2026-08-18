"""Integrity checks for immutable persona-vector extraction runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

import torch


REQUIRED_FIELDS = {
    "example_id",
    "prompt_id",
    "axis",
    "polarity",
    "system",
    "user",
    "response",
    "model",
    "model_revision",
    "seed",
    "generation",
    "activation_path",
}


@dataclass(frozen=True)
class ExtractionValidationSummary:
    manifest: str
    manifest_sha256: str
    examples: int
    pairs: int
    axes: list[str]
    prompt_ids: list[str]
    seeds: list[int]
    models: list[str]
    model_revisions: list[str]
    activation_shape: list[int]
    activation_bytes: int
    generation_qc: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_manifest(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL manifest with useful line-specific parse errors."""

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


def validate_extraction_run(
    manifest_path: Path,
    *,
    expected_shape: tuple[int, int] | None = None,
) -> ExtractionValidationSummary:
    """Validate records, contrastive pairing, and pooled activation payloads."""

    records = load_manifest(manifest_path)
    seen_ids: set[str] = set()
    pairs: dict[tuple[str, str, int], dict[str, dict[str, Any]]] = {}
    common_shape: tuple[int, int] | None = None
    activation_bytes = 0

    for record in records:
        missing = sorted(REQUIRED_FIELDS - set(record))
        if missing:
            raise ValueError(f"record is missing required fields: {missing}")
        example_id = str(record["example_id"])
        if example_id in seen_ids:
            raise ValueError(f"duplicate example_id: {example_id}")
        seen_ids.add(example_id)
        if not str(record["response"]).strip():
            raise ValueError(f"empty response: {example_id}")
        polarity = str(record["polarity"])
        if polarity not in {"target", "contrast"}:
            raise ValueError(f"invalid polarity for {example_id}: {polarity}")

        pair_key = (str(record["prompt_id"]), str(record["axis"]), int(record["seed"]))
        pair = pairs.setdefault(pair_key, {})
        if polarity in pair:
            raise ValueError(f"duplicate polarity {polarity!r} for pair {pair_key}")
        pair[polarity] = record

        activation_path = Path(record["activation_path"])
        if not activation_path.is_absolute():
            activation_path = Path.cwd() / activation_path
        if not activation_path.is_file():
            raise FileNotFoundError(f"missing activation file: {activation_path}")
        activation_bytes += activation_path.stat().st_size
        payload = load_activation_payload(activation_path)
        for key in ("response_token_mean", "last_prompt_token"):
            tensor = payload.get(key)
            if not isinstance(tensor, torch.Tensor) or tensor.ndim != 2:
                raise ValueError(f"{activation_path}:{key} must be [layers, hidden]")
            shape = tuple(tensor.shape)
            if expected_shape is not None and shape != expected_shape:
                raise ValueError(
                    f"{activation_path}:{key} has shape {shape}, expected {expected_shape}"
                )
            if common_shape is None:
                common_shape = shape
            elif shape != common_shape:
                raise ValueError(
                    f"inconsistent activation shape {shape}; expected {common_shape}"
                )
            if not bool(torch.isfinite(tensor).all()):
                raise ValueError(f"non-finite values in {activation_path}:{key}")

    for pair_key, polarities in pairs.items():
        if set(polarities) != {"target", "contrast"}:
            raise ValueError(f"incomplete contrastive pair {pair_key}: {sorted(polarities)}")
        target = polarities["target"]
        contrast = polarities["contrast"]
        for field in ("user", "model", "model_revision", "generation"):
            if target[field] != contrast[field]:
                raise ValueError(f"paired records disagree on {field}: {pair_key}")

    models = sorted({str(record["model"]) for record in records})
    revisions = sorted({str(record["model_revision"]) for record in records})
    if len(models) != 1 or len(revisions) != 1:
        raise ValueError(
            f"one extraction run must use one model and revision: {models}, {revisions}"
        )
    if common_shape is None:
        raise RuntimeError("no activation tensors were validated")

    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    generation_qc = summarize_generation_qc(records)
    return ExtractionValidationSummary(
        manifest=str(manifest_path),
        manifest_sha256=digest,
        examples=len(records),
        pairs=len(pairs),
        axes=sorted({str(record["axis"]) for record in records}),
        prompt_ids=sorted({str(record["prompt_id"]) for record in records}),
        seeds=sorted({int(record["seed"]) for record in records}),
        models=models,
        model_revisions=revisions,
        activation_shape=list(common_shape),
        activation_bytes=activation_bytes,
        generation_qc=generation_qc,
    )


def summarize_generation_qc(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize truncation and terminal chat-control tokens when recorded."""

    if any("response_token_count" not in record for record in records):
        return {"available": False}
    token_counts = [int(record["response_token_count"]) for record in records]
    stop_counts = Counter(
        "none" if record.get("stop_token_id") is None else str(record["stop_token_id"])
        for record in records
    )
    max_length_examples = sum(
        count >= int(record["generation"]["max_new_tokens"])
        for count, record in zip(token_counts, records)
    )
    ordered = sorted(token_counts)
    role_start_examples = stop_counts.get("151644", 0)
    return {
        "available": True,
        "token_count_min": ordered[0],
        "token_count_median": ordered[len(ordered) // 2],
        "token_count_max": ordered[-1],
        "stop_token_counts": dict(sorted(stop_counts.items())),
        "max_length_examples": max_length_examples,
        "max_length_rate": max_length_examples / len(records),
        "role_start_examples": role_start_examples,
        "role_start_rate": role_start_examples / len(records),
    }


def load_activation_payload(path: Path) -> dict[str, Any]:
    """Load a tensor-only payload, with compatibility for older test PyTorch."""

    try:
        payload = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError as exc:
        if "weights_only" not in str(exc):
            raise
        payload = torch.load(path, map_location="cpu")
    if not isinstance(payload, dict):
        raise ValueError(f"activation payload must be a dictionary: {path}")
    return payload
