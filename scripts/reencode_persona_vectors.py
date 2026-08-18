#!/usr/bin/env python3
"""Construct target-model persona vectors from a frozen reviewed text corpus."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

import torch
import yaml

from persona_drift.activation import mean_difference, pooled_residual_hooks, stack_captures
from persona_drift.hardware import validate_cuda_hardware
from persona_drift.modeling import (
    generation_stop_token_ids,
    input_device,
    load_target,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if not rows:
        raise ValueError(f"empty JSONL file: {path}")
    return rows


def validate_source_rows(
    rows: list[dict[str, Any]],
    *,
    axes: list[str],
    expected_rows: int,
    expected_pairs_per_axis: int,
    source_model: str,
    require_all_accepted: bool,
) -> dict[str, Any]:
    if len(rows) != expected_rows:
        raise ValueError(f"expected {expected_rows} source rows, found {len(rows)}")
    expected_axes = set(axes)
    if {str(row.get("axis")) for row in rows} != expected_axes:
        raise ValueError("source axes differ from the frozen configuration")
    seen_ids: set[str] = set()
    pairs: dict[tuple[str, str, int], set[str]] = defaultdict(set)
    for row in rows:
        example_id = str(row.get("example_id", ""))
        if not example_id or example_id in seen_ids:
            raise ValueError(f"empty or duplicate example ID: {example_id}")
        seen_ids.add(example_id)
        if require_all_accepted and row.get("accepted") is not True:
            raise ValueError(f"source example is not accepted: {example_id}")
        if str(row.get("model")) != source_model:
            raise ValueError(f"source-model mismatch: {example_id}")
        polarity = str(row.get("polarity"))
        if polarity not in {"target", "contrast"}:
            raise ValueError(f"invalid polarity: {example_id}")
        for field in ("system", "user", "response", "prompt_id"):
            if not str(row.get(field, "")).strip():
                raise ValueError(f"empty {field}: {example_id}")
        key = (str(row["prompt_id"]), str(row["axis"]), int(row["seed"]))
        if polarity in pairs[key]:
            raise ValueError(f"duplicate pair polarity: {key} {polarity}")
        pairs[key].add(polarity)
    if any(polarities != {"target", "contrast"} for polarities in pairs.values()):
        raise ValueError("source contains an incomplete contrastive pair")
    pair_counts = {
        axis: sum(key[1] == axis for key in pairs)
        for axis in axes
    }
    if any(count != expected_pairs_per_axis for count in pair_counts.values()):
        raise ValueError(f"unexpected pair counts by axis: {pair_counts}")
    return {
        "rows": len(rows),
        "pairs": len(pairs),
        "pairs_by_axis": pair_counts,
        "all_accepted": all(row.get("accepted") is True for row in rows),
    }


def _chat_ids(tokenizer: Any, messages: list[dict[str, str]], *, generation: bool) -> torch.Tensor:
    encoded = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=generation,
        return_tensors="pt",
    )
    if isinstance(encoded, dict):
        encoded = encoded.get("input_ids")
    if not isinstance(encoded, torch.Tensor) or encoded.ndim != 2 or encoded.shape[0] != 1:
        raise TypeError("chat template must return one [batch, sequence] tensor")
    return encoded


def teacher_forced_ids(
    tokenizer: Any, *, system: str, user: str, response: str
) -> tuple[torch.Tensor, int]:
    prefix = _chat_ids(
        tokenizer,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        generation=True,
    )
    full = _chat_ids(
        tokenizer,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": response},
        ],
        generation=False,
    )
    response_start = int(prefix.shape[1])
    if full.shape[1] <= response_start or not torch.equal(
        prefix, full[:, :response_start]
    ):
        raise ValueError("assistant-generation prefix is not a prefix of the full chat")
    terminal_ids = set(generation_stop_token_ids(tokenizer))
    while full.shape[1] > response_start and int(full[0, -1]) in terminal_ids:
        full = full[:, :-1]
    if full.shape[1] <= response_start:
        raise ValueError("teacher-forced response contains no content token")
    return full, response_start


@torch.inference_mode()
def capture_response(target: Any, row: dict[str, Any]) -> torch.Tensor:
    input_ids, response_start = teacher_forced_ids(
        target.tokenizer,
        system=str(row["system"]),
        user=str(row["user"]),
        response=str(row["response"]),
    )
    input_ids = input_ids.to(input_device(target.model))
    with pooled_residual_hooks(
        target.model,
        pooling="response_token_mean",
        response_start=response_start,
    ) as captures:
        target.model(
            input_ids=input_ids,
            attention_mask=torch.ones_like(input_ids),
            use_cache=False,
        )
    return stack_captures(captures)[:, 0, :]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    source = config["source"]
    model_config = config["model"]
    vector_config = config["vectors"]
    hardware = config["hardware"]

    source_path = Path(source["reviewed_manifest"])
    if sha256(source_path) != str(source["reviewed_manifest_sha256"]):
        raise ValueError("reviewed source-manifest hash mismatch")
    access_path = Path(model_config["access_check_config"])
    if sha256(access_path) != str(model_config["access_check_config_sha256"]):
        raise ValueError("target model access-check config hash mismatch")
    output_path = Path(vector_config["output"])
    summary_path = Path(vector_config["summary"])
    if output_path.exists() or summary_path.exists():
        raise FileExistsError("refusing to overwrite cross-model vector artifacts")

    axes = [str(axis) for axis in vector_config["axes"]]
    rows = load_jsonl(source_path)
    source_stats = validate_source_rows(
        rows,
        axes=axes,
        expected_rows=int(source["expected_rows"]),
        expected_pairs_per_axis=int(source["expected_pairs_per_axis"]),
        source_model=str(source["source_model"]),
        require_all_accepted=bool(source["require_all_accepted"]),
    )
    validate_cuda_hardware(
        expected_gpu_count=int(hardware["gpu_count"]),
        expected_name_substring=hardware.get("expected_name_substring"),
        require_bf16=bool(hardware.get("allow_bf16", False)),
        min_memory_gib=hardware.get("min_memory_gib"),
    )
    target = load_target(
        str(model_config["name"]),
        revision=str(model_config["revision"]),
        dtype=str(hardware["dtype"]),
        attention_implementation=str(hardware["attention_implementation"]),
        allow_tf32=bool(hardware["allow_tf32"]),
    )
    if target.resolved_revision != str(model_config["revision"]):
        raise ValueError("resolved target-model revision differs from config")

    grouped: dict[tuple[str, str], list[torch.Tensor]] = defaultdict(list)
    for index, row in enumerate(sorted(rows, key=lambda item: str(item["example_id"])), start=1):
        activation = capture_response(target, row)
        if not bool(torch.isfinite(activation).all()):
            raise ValueError(f"non-finite activation: {row['example_id']}")
        grouped[(str(row["axis"]), str(row["polarity"]))].append(activation)
        print(f"[{index}/{len(rows)}] {row['example_id']}", flush=True)

    vectors: dict[str, torch.Tensor] = {}
    axis_metadata: dict[str, Any] = {}
    reference_layer = int(vector_config["reference_layer"])
    for axis in axes:
        target_rows = torch.stack(grouped[(axis, "target")])
        contrast_rows = torch.stack(grouped[(axis, "contrast")])
        vector = mean_difference(target_rows, contrast_rows)
        if not 0 <= reference_layer < vector.shape[0]:
            raise ValueError("reference layer is outside the target model")
        if not bool(torch.isfinite(vector).all()):
            raise ValueError(f"non-finite persona vector: {axis}")
        if float(torch.linalg.vector_norm(vector[reference_layer])) <= 1e-12:
            raise ValueError(f"zero reference-layer persona vector: {axis}")
        vectors[axis] = vector
        axis_metadata[axis] = {
            "pairs": int(target_rows.shape[0]),
            "shape": list(vector.shape),
            "reference_layer_norm": float(torch.linalg.vector_norm(vector[reference_layer])),
        }

    metadata = {
        "protocol": "cross_model_vector_olmo_v1",
        "method": str(vector_config["method"]),
        "pooling": str(vector_config["pooling"]),
        "contrast": str(vector_config["contrast"]),
        "reference_layer": reference_layer,
        "source_manifest": str(source_path),
        "source_manifest_sha256": sha256(source_path),
        "source_stats": source_stats,
        "target_model": str(model_config["name"]),
        "target_model_revision": target.resolved_revision,
        "config": str(args.config),
        "config_sha256": sha256(args.config),
        "axes": axis_metadata,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"vectors": vectors, "metadata": metadata}, output_path)
    result = {
        **metadata,
        "vector_file": str(output_path),
        "vector_file_sha256": sha256(output_path),
    }
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

