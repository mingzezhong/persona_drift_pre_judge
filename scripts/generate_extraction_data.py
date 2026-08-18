#!/usr/bin/env python3
"""Generate BILLY-style contrastive responses and pooled activations."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import torch
import yaml

from persona_drift.hardware import validate_cuda_hardware
from persona_drift.modeling import generate_and_capture_response, load_target
from persona_drift.schema import ExtractionExample


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, default=Path("data/templates/persona_axes.yaml"))
    parser.add_argument("--config", type=Path, default=Path("configs/pilot.yaml"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--axes", nargs="+", default=None)
    parser.add_argument("--prompt-ids", nargs="+", default=None)
    parser.add_argument("--device-map", default="auto")
    parser.add_argument("--skip-hardware-check", action="store_true")
    return parser.parse_args()


def stable_id(prompt_id: str, axis: str, polarity: str, seed: int) -> str:
    raw = f"{prompt_id}:{axis}:{polarity}:{seed}"
    suffix = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"{prompt_id}-{axis}-{polarity}-{seed}-{suffix}"


def generation_settings(config: dict[str, Any]) -> dict[str, Any]:
    settings = dict(config["generation"])
    allowed = {"max_new_tokens", "min_new_tokens", "temperature", "top_p", "do_sample"}
    unexpected = set(settings) - allowed
    if unexpected:
        raise ValueError(f"unsupported generation settings: {sorted(unexpected)}")
    return settings


def compose_system_prompt(axis_system: str, shared_system: str | None) -> str:
    """Apply the same response-format constraint to both persona polarities."""

    shared = (shared_system or "").strip()
    if not shared:
        return axis_system
    return f"{axis_system.rstrip()}\n\n{shared}"


def select_axes(
    axes: dict[str, dict[str, Any]], requested: list[str] | None
) -> list[tuple[str, dict[str, Any]]]:
    """Select axes in requested order and reject misspelled names."""

    if requested is None:
        return list(axes.items())
    missing = sorted(set(requested) - set(axes))
    if missing:
        raise ValueError(f"unknown persona axes: {missing}")
    return [(name, axes[name]) for name in requested]


def select_prompts(
    prompts: list[dict[str, Any]], requested: list[str] | None
) -> list[dict[str, Any]]:
    """Select prompts in requested order and reject misspelled IDs."""

    by_id = {prompt["id"]: prompt for prompt in prompts}
    if len(by_id) != len(prompts):
        raise ValueError("extraction prompt IDs must be unique")
    if requested is None:
        return prompts
    missing = sorted(set(requested) - set(by_id))
    if missing:
        raise ValueError(f"unknown extraction prompt IDs: {missing}")
    return [by_id[prompt_id] for prompt_id in requested]


def prepare_output(output_dir: Path) -> tuple[Path, Path]:
    """Create a fresh immutable output location before loading the model."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    activation_dir = output_dir / "activations"
    activation_dir.mkdir()
    return activation_dir, output_dir / "manifest.jsonl"


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    hardware = config["hardware"]
    template = yaml.safe_load(args.template.read_text(encoding="utf-8"))
    axes = select_axes(template["axes"], args.axes)
    prompts = select_prompts(template["extraction_prompts"], args.prompt_ids)
    shared_system = template.get("shared_extraction_system")
    activation_dir, manifest_path = prepare_output(args.output_dir)
    planned_examples = len(axes) * len(prompts) * 2 * len(args.seeds)
    print(f"planned extraction examples: {planned_examples}")

    if not args.skip_hardware_check:
        validate_cuda_hardware(
            expected_gpu_count=int(hardware["gpu_count"]),
            expected_name_substring=hardware.get("expected_name_substring"),
            require_bf16=bool(hardware.get("allow_bf16", False)),
            min_memory_gib=hardware.get("min_memory_gib"),
        )

    primary_model = config["models"]["primary"]
    model_name = args.model or primary_model["name"]
    revision = args.revision
    if revision is None and args.model is None:
        revision = primary_model.get("revision")
    generation = generation_settings(config)
    target = load_target(
        model_name,
        revision=revision,
        device_map=args.device_map,
        dtype=hardware["dtype"],
        attention_implementation=hardware["attention_implementation"],
        allow_tf32=bool(hardware["allow_tf32"]),
    )

    with manifest_path.open("x", encoding="utf-8") as manifest:
        for axis_name, axis in axes:
            polarities = {
                "target": compose_system_prompt(axis["target_system"], shared_system),
                "contrast": compose_system_prompt(
                    axis["contrast_system"], shared_system
                ),
            }
            for prompt in prompts:
                for polarity, system in polarities.items():
                    for seed in args.seeds:
                        example_id = stable_id(prompt["id"], axis_name, polarity, seed)
                        activation_path = activation_dir / f"{example_id}.pt"
                        if activation_path.exists():
                            raise FileExistsError(f"refusing to overwrite {activation_path}")

                        capture = generate_and_capture_response(
                            target,
                            system=system,
                            user=prompt["user"],
                            seed=seed,
                            generation=generation,
                        )
                        torch.save(
                            {
                                "response_token_mean": capture.response_activations,
                                "last_prompt_token": capture.pre_response,
                                "response_token_ids": capture.response_token_ids,
                                "stop_token_id": capture.stop_token_id,
                            },
                            activation_path,
                        )
                        record = ExtractionExample(
                            example_id=example_id,
                            prompt_id=prompt["id"],
                            axis=axis_name,
                            polarity=polarity,
                            system=system,
                            user=prompt["user"],
                            response=capture.response_text,
                            model=model_name,
                            model_revision=target.resolved_revision,
                            seed=seed,
                            generation=generation,
                        ).to_dict()
                        record["activation_path"] = str(activation_path)
                        for metadata_field in ("topic", "split"):
                            if metadata_field in prompt:
                                record[metadata_field] = prompt[metadata_field]
                        record["response_token_count"] = int(
                            capture.response_token_ids.shape[1]
                        )
                        record["stop_token_id"] = capture.stop_token_id
                        record["forbidden_token_ids"] = list(
                            capture.forbidden_token_ids
                        )
                        manifest.write(json.dumps(record, ensure_ascii=False) + "\n")
                        manifest.flush()


if __name__ == "__main__":
    main()
