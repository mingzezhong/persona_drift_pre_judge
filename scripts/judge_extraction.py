#!/usr/bin/env python3
"""Score one blinded extraction review sheet with one frozen open model."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

import torch
from torch import Tensor
from transformers import AutoModelForCausalLM, AutoTokenizer
import yaml

from persona_drift.judging import (
    accepted_by_rubric,
    build_judge_messages,
    load_jsonl,
    parse_judge_output,
    sha256_file,
)
from persona_drift.modeling import input_device, resolve_dtype


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("configs/ai_judges.yaml")
    )
    parser.add_argument("--judge-id", required=True)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def load_review_sheet(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"review sheet is empty: {path}")
    ids = [row.get("example_id", "") for row in rows]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError(f"review sheet has empty or duplicate example IDs: {path}")
    return rows


def validate_existing(
    records: list[dict[str, Any]],
    rows: list[dict[str, str]],
    *,
    reviewer_id: str,
    model_name: str,
    revision: str,
    complete: bool,
) -> set[str]:
    expected_ids = {row["example_id"] for row in rows}
    completed: set[str] = set()
    for record in records:
        example_id = str(record.get("example_id", ""))
        if example_id not in expected_ids or example_id in completed:
            raise ValueError(f"invalid or duplicate completed example: {example_id}")
        if record.get("reviewer_id") != reviewer_id:
            raise ValueError("existing output reviewer ID does not match config")
        if record.get("judge_model") != model_name:
            raise ValueError("existing output model does not match config")
        if record.get("judge_revision") != revision:
            raise ValueError("existing output revision does not match config")
        parse_judge_output(json.dumps(record.get("scores", {})))
        if not isinstance(record.get("accepted"), bool):
            raise ValueError(f"invalid decision for completed example: {example_id}")
        completed.add(example_id)
    if complete and completed != expected_ids:
        raise ValueError("final judge output is incomplete")
    return completed


def generate_completion(
    model: torch.nn.Module,
    tokenizer: Any,
    messages: list[dict[str, str]],
    *,
    max_new_tokens: int,
) -> str:
    encoded = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_tensors="pt",
        return_dict=True,
    )
    if isinstance(encoded, Tensor):
        encoded = {
            "input_ids": encoded,
            "attention_mask": torch.ones_like(encoded),
        }
    device = input_device(model)
    inputs = {name: value.to(device) for name, value in encoded.items()}
    prompt_length = inputs["input_ids"].shape[1]
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            do_sample=False,
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    completion_ids = output[0, prompt_length:]
    return tokenizer.decode(completion_ids, skip_special_tokens=True).strip()


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    try:
        judge = config["judges"][args.judge_id]
    except KeyError as exc:
        raise ValueError(f"unknown judge ID: {args.judge_id}") from exc
    inference = config["inference"]
    manifest_path = Path(config["input"]["manifest"])
    rubric_path = Path(config["input"]["rubric"])
    review_path = Path(judge["review_sheet"])
    output_path = Path(judge["output"])
    partial_path = output_path.with_suffix(output_path.suffix + ".partial")
    rows = load_review_sheet(review_path)

    manifest_ids = {record["example_id"] for record in load_jsonl(manifest_path)}
    review_ids = {row["example_id"] for row in rows}
    if manifest_ids != review_ids:
        raise ValueError("review sheet does not exactly cover the input manifest")
    if any(row.get("reviewer_id") != judge["reviewer_id"] for row in rows):
        raise ValueError("review sheet reviewer ID does not match judge config")

    reviewer_id = str(judge["reviewer_id"])
    model_name = str(judge["model"])
    revision = str(judge["revision"])
    if output_path.exists():
        if not args.resume:
            raise FileExistsError(f"refusing to overwrite {output_path}")
        records = load_jsonl(output_path)
        validate_existing(
            records,
            rows,
            reviewer_id=reviewer_id,
            model_name=model_name,
            revision=revision,
            complete=True,
        )
        print(f"validated complete existing output: {output_path}")
        return

    completed: set[str] = set()
    if partial_path.exists():
        if not args.resume:
            raise FileExistsError(f"partial output exists: {partial_path}")
        completed = validate_existing(
            load_jsonl(partial_path),
            rows,
            reviewer_id=reviewer_id,
            model_name=model_name,
            revision=revision,
            complete=False,
        )
        print(f"resuming after {len(completed)} completed examples")

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for AI judging")
    if torch.cuda.device_count() != 1:
        raise RuntimeError(
            "each judge process must see exactly one GPU; set CUDA_VISIBLE_DEVICES"
        )
    dtype = resolve_dtype(str(inference["dtype"]))
    tokenizer_kwargs = dict(judge.get("tokenizer_kwargs", {}))
    tokenizer = AutoTokenizer.from_pretrained(
        model_name, revision=revision, **tokenizer_kwargs
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        revision=revision,
        dtype=dtype,
        device_map=str(inference["device_map"]),
        low_cpu_mem_usage=True,
        attn_implementation=str(inference["attention_implementation"]),
    )
    model.eval()
    resolved_revision = str(
        getattr(model.config, "_commit_hash", None) or revision
    )
    if resolved_revision != revision:
        raise RuntimeError(
            f"resolved model revision {resolved_revision} differs from {revision}"
        )

    rubric = yaml.safe_load(rubric_path.read_text(encoding="utf-8"))
    config_hash = sha256_file(args.config)
    rubric_hash = sha256_file(rubric_path)
    manifest_hash = sha256_file(manifest_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    max_retries = int(inference["max_retries"])

    with partial_path.open("a", encoding="utf-8") as handle:
        for position, row in enumerate(rows, start=1):
            if row["example_id"] in completed:
                continue
            messages = build_judge_messages(row, rubric)
            raw_outputs: list[str] = []
            scores = None
            last_error: Exception | None = None
            for _attempt in range(max_retries + 1):
                raw = generate_completion(
                    model,
                    tokenizer,
                    messages,
                    max_new_tokens=int(inference["max_new_tokens"]),
                )
                raw_outputs.append(raw)
                try:
                    scores = parse_judge_output(raw)
                    break
                except ValueError as exc:
                    last_error = exc
                    messages = messages + [
                        {"role": "assistant", "content": raw},
                        {
                            "role": "user",
                            "content": (
                                "The previous answer was not valid. Return only one "
                                "JSON object with the five required fields and valid "
                                "types; do not add markdown or explanation."
                            ),
                        },
                    ]
            if scores is None:
                raise RuntimeError(
                    f"could not parse judge output for {row['example_id']}: {last_error}"
                )
            record = {
                "review_order": int(row.get("review_order", position)),
                "reviewer_id": reviewer_id,
                "example_id": row["example_id"],
                "judge_model": model_name,
                "judge_revision": resolved_revision,
                "scores": scores.to_dict(),
                "accepted": accepted_by_rubric(scores, rubric),
                "attempts": len(raw_outputs),
                "raw_model_outputs": raw_outputs,
                "config_sha256": config_hash,
                "rubric_sha256": rubric_hash,
                "manifest_sha256": manifest_hash,
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            print(
                f"[{position}/{len(rows)}] {row['example_id']} "
                f"accepted={record['accepted']}"
            )

    final_records = load_jsonl(partial_path)
    validate_existing(
        final_records,
        rows,
        reviewer_id=reviewer_id,
        model_name=model_name,
        revision=revision,
        complete=True,
    )
    partial_path.replace(output_path)
    print(f"wrote {len(final_records)} judgments to {output_path}")


if __name__ == "__main__":
    main()
