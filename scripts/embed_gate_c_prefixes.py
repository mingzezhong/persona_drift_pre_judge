#!/usr/bin/env python3
"""Encode frozen Gate C text prefixes with a pinned E5 checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from transformers import AutoModel, AutoTokenizer


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def average_pool(
    last_hidden_state: torch.Tensor, attention_mask: torch.Tensor
) -> torch.Tensor:
    """E5 model-card attention-mask average pooling in float32."""

    mask = attention_mask.unsqueeze(-1).to(dtype=torch.float32)
    hidden = last_hidden_state.to(dtype=torch.float32)
    return (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    encoder = config["text_encoder"]
    output = config["output"]
    dataset_path = Path(output["dataset"])
    dataset_summary_path = Path(output["dataset_summary"])
    summary = json.loads(dataset_summary_path.read_text(encoding="utf-8"))
    if sha256(dataset_path) != summary["dataset_sha256"]:
        raise ValueError("dataset hash does not match its frozen summary")

    records = read_jsonl(dataset_path)
    if len(records) != int(summary["examples"]):
        raise ValueError("dataset row count does not match its summary")
    example_ids = np.asarray([row["example_id"] for row in records])
    if len(set(example_ids.tolist())) != len(example_ids):
        raise ValueError("example IDs must be unique")
    prefix = str(encoder["input_prefix"])
    texts = [prefix + str(row["text_prefix"]) for row in records]

    output_path = Path(output["embeddings"])
    summary_path = Path(output["embeddings_summary"])
    output_dir = output_path.parent
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"embedding output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    if not torch.cuda.is_available():
        raise RuntimeError("the pinned E5 embedding job requires a CUDA GPU")
    if str(encoder["pooling"]) != "attention_mask_average":
        raise ValueError("unsupported pooling rule")
    if not bool(encoder["normalize"]):
        raise ValueError("E5 embeddings must remain L2-normalized")

    model_name = str(encoder["name"])
    revision = str(encoder["revision"])
    tokenizer = AutoTokenizer.from_pretrained(model_name, revision=revision)
    tokenizer.truncation_side = str(encoder["truncation_side"])
    if tokenizer.truncation_side not in {"left", "right"}:
        raise ValueError("truncation_side must be left or right")
    model = AutoModel.from_pretrained(
        model_name,
        revision=revision,
        torch_dtype=torch.bfloat16,
    ).eval().cuda()
    resolved_revision = getattr(model.config, "_commit_hash", None)
    if resolved_revision and str(resolved_revision) != revision:
        raise ValueError(
            f"resolved model revision {resolved_revision} differs from {revision}"
        )

    batches: list[np.ndarray] = []
    batch_size = int(encoder["batch_size"])
    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            tokens = tokenizer(
                texts[start : start + batch_size],
                max_length=int(encoder["max_length"]),
                padding=True,
                truncation=True,
                return_tensors="pt",
            )
            tokens = {
                key: value.cuda(non_blocking=True) for key, value in tokens.items()
            }
            outputs = model(**tokens)
            pooled = average_pool(
                outputs.last_hidden_state, tokens["attention_mask"]
            )
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            batches.append(
                pooled.cpu().numpy().astype(np.float32, copy=False)
            )
    embeddings = np.concatenate(batches, axis=0)
    if embeddings.shape[0] != len(example_ids) or not np.isfinite(embeddings).all():
        raise ValueError("invalid embedding matrix")
    norms = np.linalg.norm(embeddings, axis=1)
    if not np.allclose(norms, 1.0, rtol=2e-3, atol=2e-3):
        raise ValueError("E5 embeddings are not unit normalized")

    partial_path = output_path.with_suffix(output_path.suffix + ".partial")
    with partial_path.open("xb") as handle:
        np.savez_compressed(
            handle, example_ids=example_ids, embeddings=embeddings
        )
    partial_path.rename(output_path)
    result = {
        "protocol": "gate_c_e5_prefix_embeddings_v1",
        "mode": config["mode"],
        "confirmatory": False,
        "model": model_name,
        "requested_revision": revision,
        "resolved_revision": resolved_revision,
        "pooling": encoder["pooling"],
        "input_prefix": prefix,
        "max_length": int(encoder["max_length"]),
        "truncation_side": tokenizer.truncation_side,
        "dtype": str(encoder["dtype"]),
        "examples": len(example_ids),
        "shape": list(embeddings.shape),
        "dataset": str(dataset_path),
        "dataset_sha256": sha256(dataset_path),
        "embeddings": str(output_path),
        "embeddings_sha256": sha256(output_path),
        "config": str(args.config),
        "config_sha256": sha256(args.config),
        "gpu": torch.cuda.get_device_name(0),
    }
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
